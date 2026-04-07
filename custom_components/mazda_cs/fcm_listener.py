"""Firebase Cloud Messaging push listener for Mazda Connected Services."""

from __future__ import annotations

import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import CONF_FCM_CREDENTIALS, DATA_HEALTH_COORDINATOR, DOMAIN

try:
    from .pymazda.push import MazdaPushClient

    _PUSH_AVAILABLE = True
except ImportError:
    MazdaPushClient = None  # type: ignore[assignment,misc]
    _PUSH_AVAILABLE = False

_LOGGER = logging.getLogger(__name__)

# HA event fired on every incoming push — subscribe in Developer Tools → Events
# to observe raw payloads, or use in automations with trigger platform: event.
EVENT_MAZDA_PUSH = "mazda_cs_push"

# Action codes that warrant an immediate coordinator refresh so HA state
# reflects the vehicle change without waiting for the 3-minute poll interval.
_REFRESH_CODES = frozenset(
    [
        "001",   # INBOX_REMOTE — remote command result (lock/unlock/engine/A/C/lights)
        "003",   # INBOX_VEHICLE_STATUS
        "004",   # INBOX_SECURITY — Security alerts
        "019",   # INBOX_REMOTE_AC_EXTENSION
        "021",   # INBOX_EV_REMOTE
        "022",   # INBOX_REAL_TIME_VEHICLE_STATUS
        "023",   # INBOX_EV_VEHICLE_STATUS
        "026",   # INBOX_LOW_BATTERY - Low 12V battery
        "027",   # INBOX_EV_LOW_BATTERY
        "032",   # INBOX_GEOFENCE_ALERT
        "034",   # INBOX_SVT_ALERT
        "D002",  # CDT_INBOX_CP_CHARGE_COMPLETED
    ]
)

# Action codes documented but not requiring a refresh:
        # "009",   # INBOX_BCALL_HIGH - B-Call high priority
        # "014",   # INBOX_BCALL_LOW - B-Call low priority
        # "017",   # INBOX_TAKEOVER_FAILED - Takeover failed
        # "024",   # INBOX_ECONNECT_EVENT - eConnect event
        # "029",   # INBOX_EV_BATTERY_ADVICE - EV battery advice
        # "030",   # INBOX_EV_BATTERY_PRAISE - EV battery praise
        # "031",   # INBOX_GEOFENCE_SETTING - Geofence settings
        # "033",   # INBOX_SVT_SETTING - SVT (Stolen Vehicle Tracking) settings
        # "035",   # *(undocumented)* - Seen in push notification handler only — absent from `InboxCodeEnum`; likely a newer type


class MazdaFcmListener:
    """Manages an Android FCM push subscription for one config entry.

    Lifecycle:
        1. ``async_start()`` — registers with GCM/FCM (lightweight re-check-in
           if stored credentials exist, otherwise full registration).  Returns
           the FCM token, or ``None`` if unavailable.
        2. Pass the token to ``mazda_client.attach(fcm_token=token)`` so
           Mazda's backend knows where to push notifications.
        3. ``async_stop()`` on integration unload.

    Credential persistence:
        GCM credentials (android_id, security_token, token) are stored in
        ``entry.data[CONF_FCM_CREDENTIALS]``, the same mechanism used for
        OAuth tokens.  On explicit removal the FCM token is invalidated at
        Firebase (GCM unregister) and a fresh registration will occur on
        the next setup.
    """

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        region: str = "MNAO",
        conductor_device_id: str = "",
    ) -> None:
        self._hass = hass
        self._entry = entry
        self._coordinator = coordinator
        self._region = region
        self._conductor_device_id = conductor_device_id
        self._client: MazdaPushClient | None = None
        self._fcm_token: str | None = None

    @property
    def fcm_token(self) -> str | None:
        """FCM token available after a successful async_start()."""
        return self._fcm_token

    async def async_start(self) -> str | None:
        """Register with FCM and start the MCS listener.  Returns token or None."""
        if not _PUSH_AVAILABLE:
            _LOGGER.warning(
                "pymazda.push is unavailable (missing protobuf?); "
                "FCM push notifications disabled, falling back to polling."
            )
            return None

        stored = self._entry.data.get(CONF_FCM_CREDENTIALS)
        if stored:
            _LOGGER.debug("FCM: loaded credentials from entry.data (android_id=%s)", stored.get("android_id"))

        self._client = MazdaPushClient(
            credentials=stored,
            credentials_updated_callback=self._on_credentials_updated,
        )

        try:
            self._fcm_token = await self._client.checkin_or_register()
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("FCM check-in / registration failed: %s", ex)
            self._client = None
            return None

        if not self._fcm_token:
            _LOGGER.warning("FCM registration returned no token")
            self._client = None
            return None

        _LOGGER.debug("FCM registered, token prefix: %s...", self._fcm_token[:20])

        try:
            await self._client.start(self._on_notification)
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("FCM MCS listener failed to start: %s", ex)
            self._client = None
            return None

        # Register the FCM token with StationDM Conductor so Mazda's push
        # backend delivers notifications to this client.
        # APK-confirmed: updateuser only needs deviceId + pushToken + device metadata.
        _LOGGER.debug(
            "Conductor registration: region=%s deviceId=%s",
            self._region,
            self._conductor_device_id if self._conductor_device_id else "(MISSING)",
        )
        result = await self._client.register_with_conductor(
            self._region,
            conductor_device_id=self._conductor_device_id or None,
        )
        if result:
            status, text = result
            if status == 200:
                _LOGGER.debug("Conductor updateuser succeeded")
            else:
                _LOGGER.warning("Conductor updateuser returned HTTP %d: %s", status, text)

        return self._fcm_token

    async def async_stop(self, unregister: bool = False) -> None:
        """Stop the FCM listener connection.

        ``unregister=True``: invalidate the FCM token at Firebase so that Mazda's
        backend receives INVALID_REGISTRATION on the next push delivery attempt.
        Pass this when the integration is being fully removed, not just restarted.
        """
        if self._client:
            try:
                await self._client.stop(unregister=unregister)
            except Exception as ex:  # noqa: BLE001
                _LOGGER.debug("FCM stop error (ignored): %s", ex)
            self._client = None

    # ------------------------------------------------------------------
    # Internal callbacks (called from within the asyncio event loop)
    # ------------------------------------------------------------------

    def _on_credentials_updated(self, credentials: dict[str, Any]) -> None:
        """Persist updated GCM credentials to entry.data."""
        new_data = {**self._entry.data, CONF_FCM_CREDENTIALS: credentials}
        self._hass.config_entries.async_update_entry(self._entry, data=new_data)
        _LOGGER.debug(
            "FCM credentials updated (android_id=%s), persisted to entry.data",
            credentials.get("android_id"),
        )

    def _on_notification(self, payload: dict[str, Any]) -> None:
        """Handle an incoming FCM push notification.

        Payload keys (confirmed from live traffic, com.interrait.mymazda):
          a             — action code, matches InboxCodeEnum (e.g. "001")
          r             — result ID (e.g. "00120250101000000_01")
          t             — timestamp ms
          v             — VIN
          title / body  — notification text
          cdtMessageId  — Conductor delivery tracking ID
        """
        action_code = payload.get("a", "") or payload.get("actionCode", "")
        _LOGGER.debug("FCM push received — actionCode=%s payload=%s", action_code, payload)

        self._hass.bus.async_fire(
            EVENT_MAZDA_PUSH,
            {
                "action_code": action_code,
                "vin": payload.get("v", ""),
                "result_id": payload.get("r", ""),
                "title": payload.get("title", ""),
                "body": payload.get("body", ""),
                "data": payload,
            },
        )

        if action_code in _REFRESH_CODES:
            _LOGGER.debug("FCM push triggers coordinator refresh (actionCode=%s)", action_code)
            self._hass.async_create_task(self._coordinator.async_request_refresh())

        if action_code == "010":
            _LOGGER.debug("FCM push triggers health coordinator refresh")
            entry_data = self._hass.data.get(DOMAIN, {}).get(self._entry.entry_id, {})
            health_coordinator = entry_data.get(DATA_HEALTH_COORDINATOR)
            if health_coordinator:
                self._hass.async_create_task(health_coordinator.async_request_refresh())
