"""pymazda push notification client.

Subscribes to Firebase Cloud Messaging as an Android device and delivers
incoming push payloads via a callback.  Designed as a standalone component —
no Home Assistant dependencies.

Usage::

    from pymazda.push import MazdaPushClient

    def on_push(data: dict) -> None:
        print(data.get("actionCode"))

    client = MazdaPushClient(
        credentials=stored_dict,                    # None on first run
        credentials_updated_callback=save_to_disk,
    )
    token = await client.checkin_or_register()   # pass to mazda_client.attach()
    await client.start(on_push)
    # ...later...
    await client.stop()
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import Any

from aiohttp import ClientSession

from ._conductor import (
    CONDUCTOR_CONFIG,
    CONDUCTOR_DEVICE_OS,
    default_timezone,
    send_app_init,
    send_update_user,
)
from ._mcs import McsClient, MessageCallback
from ._register import FCM_APP_VERSION_NAME, checkin_and_register, fis_delete_installation, gcm_unregister

_LOGGER = logging.getLogger(__name__)

CredentialsUpdatedCallback = Callable[[dict[str, Any]], None]


class MazdaPushClient:
    """Firebase Cloud Messaging client for the MyMazda app.

    Credentials dict schema (persisted in ``entry.data[CONF_FCM_CREDENTIALS]``)::

        {
            "android_id":      str,   # GCM device ID
            "security_token":  str,   # GCM security token
            "token":           str,   # FCM registration token → Mazda deviceToken
            "fid":             str,   # Firebase Installation ID (FIS path only)
            "refresh_token":   str,   # FIS long-lived refresh token (FIS path only)
        }
    """

    def __init__(
        self,
        credentials: dict[str, Any] | None = None,
        credentials_updated_callback: CredentialsUpdatedCallback | None = None,
        websession: ClientSession | None = None,
    ) -> None:
        self._credentials = credentials
        self._credentials_updated_cb = credentials_updated_callback
        self._websession = websession
        self._mcs: McsClient | None = None
        self._local_session: ClientSession | None = None

    @property
    def credentials(self) -> dict[str, Any] | None:
        """Current credentials dict — persist this across restarts."""
        return self._credentials

    def is_started(self) -> bool:
        return self._mcs is not None and self._mcs.is_started()

    async def checkin_or_register(self) -> str | None:
        """Check in (or register fresh) with GCM.

        On first call: performs full GCM check-in + Android app registration
        and fires ``credentials_updated_callback`` with the new credentials.
        On subsequent calls with existing credentials: performs a lightweight
        re-check-in that reuses the existing registration token.

        Returns the FCM token to pass to ``mazda_client.attach(fcm_token=...)``,
        or None if registration failed.
        """
        session = self._get_session()
        creds = await checkin_and_register(session, existing=self._credentials)
        if creds is None:
            return None

        if creds != self._credentials:
            self._credentials = creds
            if self._credentials_updated_cb:
                self._credentials_updated_cb(creds)

        return creds["token"]

    async def start(self, on_message: MessageCallback) -> None:
        """Open the MCS connection and start receiving push notifications.

        ``on_message`` is called from within the event loop whenever a data
        message arrives.  Its argument is a ``dict[str, str]`` matching the
        FCM data payload (e.g. ``{"a": "001", "v": "<vin>", "title": "..."}``).

        Must call ``checkin_or_register()`` first.
        """
        if self._credentials is None:
            raise RuntimeError("Call checkin_or_register() before start()")

        self._mcs = McsClient(
            android_id=self._credentials["android_id"],
            security_token=self._credentials["security_token"],
            on_message=on_message,
        )
        await self._mcs.start()

    async def register_with_conductor(
        self,
        region: str,
        *,
        push_token: str | None = None,
        conductor_device_id: str | None = None,
    ) -> tuple[int, str] | None:
        """Register the FCM push token with the StationDM Conductor backend.

        Must be called after ``checkin_or_register()`` so that a token is available.
        ``push_token`` defaults to the token returned by ``checkin_or_register()``.
        ``region`` selects the per-region Conductor server URL and app key.

        Returns ``(http_status, response_text)`` on completion, or ``None`` if
        the region is unknown or no push token is available.
        """
        cfg = CONDUCTOR_CONFIG.get(region)
        if cfg is None:
            _LOGGER.warning("Conductor: unknown region %r — skipping updateuser", region)
            return None

        token = push_token or (self._credentials or {}).get("token")
        if not token:
            _LOGGER.warning("Conductor: no push token available — skipping updateuser")
            return None

        if not conductor_device_id:
            _LOGGER.warning("Conductor: no device_id provided — skipping updateuser")
            return None
        device_id = conductor_device_id

        session = self._get_session()
        server_url = cfg["server_url"]
        app_key = cfg["app_key"]
        try:
            init_status, init_text, sess_enc, sess_sign = await send_app_init(
                session,
                server_url=server_url,
                app_key=app_key,
                device_id=device_id,
            )
            _LOGGER.debug(
                "Conductor init: region=%s status=%d response=%s",
                region, init_status, init_text,
            )
            if init_status != 200:
                _LOGGER.warning(
                    "Conductor init failed (HTTP %d) — skipping updateuser", init_status
                )
                return init_status, init_text

            status, text = await send_update_user(
                session,
                server_url=server_url,
                app_key=app_key,
                device_id=device_id,
                push_token=token,
                session_enc_key=sess_enc,
                session_sign_key=sess_sign,
                timezone=default_timezone(),
                app_version=FCM_APP_VERSION_NAME,
                device_type=CONDUCTOR_DEVICE_OS,
                device_os=CONDUCTOR_DEVICE_OS,
            )
            _LOGGER.debug("Conductor deviceId used: %s", device_id)
            _LOGGER.debug(
                "Conductor updateuser: region=%s status=%d response=%s",
                region, status, text,
            )
            return status, text
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("Conductor register failed: %s", ex)
            return None

    async def stop(self, unregister: bool = False) -> None:
        """Stop the MCS listener and release resources.

        ``unregister=True``: invalidate the FCM token at Firebase before stopping.
        FIS-path credentials use ``fis_delete_installation``; legacy credentials
        fall back to GCM ``register3`` unregister.  Equivalent to
        ``FirebaseMessaging.deleteToken()`` — use on integration removal so
        Mazda's push backend receives INVALID_REGISTRATION on its next delivery
        attempt and cleans up the stale Conductor entry.
        """
        if unregister and self._credentials:
            session = self._get_session()
            fid = self._credentials.get("fid")
            refresh_token = self._credentials.get("refresh_token")
            if fid and refresh_token:
                # FIS-path token: delete the installation directly — more reliable
                # than c2dm/register3 delete which requires FIS auth fields to
                # locate the token and returns token=<sender_id> without them.
                await fis_delete_installation(session, fid=fid, refresh_token=refresh_token)
            else:
                # Legacy GCM token (no FID): fall back to register3 unregister.
                await gcm_unregister(
                    session,
                    android_id=self._credentials.get("android_id", ""),
                    security_token=self._credentials.get("security_token", ""),
                    fcm_token=self._credentials.get("token"),
                )

        if self._mcs:
            await self._mcs.stop()
            self._mcs = None
        if self._local_session and not self._local_session.closed:
            await self._local_session.close()
            self._local_session = None

    def _get_session(self) -> ClientSession:
        if self._websession and not self._websession.closed:
            return self._websession
        if self._local_session is None or self._local_session.closed:
            self._local_session = ClientSession()
        return self._local_session
