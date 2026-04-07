"""Android GCM check-in and registration for Mazda push notifications.

Registers as an Android device (not Chrome/web) so that Mazda's backend sends
plain FCM data messages.  Plain data messages arrive on the MCS connection as
DataMessageStanza.app_data key-value pairs — no web-push ECDH encryption layer.
"""

from __future__ import annotations

import base64
import hashlib
import logging
import struct
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ._proto.android_checkin_pb2 import (
    DEVICE_ANDROID_OS,
    AndroidCheckinProto,
)
from ._proto.checkin_pb2 import (
    AndroidCheckinRequest,
    AndroidCheckinResponse,
)

_LOGGER = logging.getLogger(__name__)

GCM_CHECKIN_URL = "https://android.clients.google.com/checkin"
GCM_REGISTER_URL = "https://android.clients.google.com/c2dm/register3"

# Firebase Installations + FCM (modern FirebaseMessaging.getToken) endpoints
FIS_INSTALLATIONS_URL = (
    "https://firebaseinstallations.googleapis.com/v1/projects/"
    "my-mazda-app/installations"
)
FIS_AUTH_TOKEN_URL = (
    "https://firebaseinstallations.googleapis.com/v1/projects/"
    "my-mazda-app/installations/{fid}/authTokens:generate"
)
FIS_DELETE_URL = (
    "https://firebaseinstallations.googleapis.com/v1/projects/"
    "my-mazda-app/installations/{fid}"
)

# MyMazda Android app identity — must match what the app sends so Mazda's
# Firebase project recognises the sender and routes messages correctly.
MAZDA_APP_PACKAGE = "com.interrait.mymazda"
MAZDA_SENDER_ID = "583786267773"  # messaging_sender_id from google-services.json

# Firebase credentials extracted from com.interrait.mymazda 9.0.8 APK
FCM_PROJECT_ID = "my-mazda-app"
FCM_APP_ID = "1:583786267773:android:e1aaf592642d239e"
FCM_API_KEY = "AIzaSyAnYvHIERUEsluFJdJC9GO17h4eY8d-g9g"
FCM_SENDER_ID = "583786267773"

# Firebase SDK version string format used by Android clients (a:<major>.<minor>.<patch>)
FIS_SDK_VERSION = "a:17.1.0"
FCM_CLIENT_LIBRARY = "fcm-23.3.0"
FCM_APP_VERSION_CODE = "604"
FCM_APP_VERSION_NAME = "9.0.8"
FCM_GMSV = "201817023"
FCM_OSV = "30"
FCM_TARGET_VER = "29"
FCM_PLATFORM = "0"
FIREBASE_APP_NAME = "[DEFAULT]"
FCM_ANDROID_PACKAGE = "com.interrait.mymazda"
FCM_ANDROID_CERT_SHA1 = "FE728CBB5FA50A3CB9F9EECE17DBDFA78785064B"

_TIMEOUT = ClientTimeout(total=10)


def _firebase_app_name_hash() -> str:
    digest = hashlib.sha1(FIREBASE_APP_NAME.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode("utf-8").rstrip("=")


async def _fis_create_installation(session: ClientSession) -> dict[str, Any] | None:
    """Create a Firebase Installation and return fid + refresh token + auth token."""
    headers = {
        "x-goog-api-key": FCM_API_KEY,
        "Content-Type": "application/json",
        "X-Android-Package": FCM_ANDROID_PACKAGE,
        "X-Android-Cert": FCM_ANDROID_CERT_SHA1,
    }
    body = {
        "appId": FCM_APP_ID,
        "authVersion": "FIS_v2",
        "sdkVersion": FIS_SDK_VERSION,
    }

    try:
        async with session.post(
            FIS_INSTALLATIONS_URL,
            headers=headers,
            json=body,
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.warning(
                    "FIS create installation failed: HTTP %d — %s", resp.status, text
                )
                return None
            data = await resp.json()
            if "fid" not in data or "refreshToken" not in data:
                _LOGGER.warning("FIS create installation returned unexpected payload")
                return None
            return data
    except Exception as ex:  # noqa: BLE001
        _LOGGER.warning("FIS create installation error: %s", ex)
        return None


async def _fis_generate_auth_token(
    session: ClientSession, fid: str, refresh_token: str
) -> dict[str, Any] | None:
    """Generate a Firebase Installations auth token using refresh token."""
    headers = {
        "x-goog-api-key": FCM_API_KEY,
        "Content-Type": "application/json",
        "Authorization": f"FIS_v2 {refresh_token}",
        "X-Android-Package": FCM_ANDROID_PACKAGE,
        "X-Android-Cert": FCM_ANDROID_CERT_SHA1,
    }
    body = {"installation": {"sdkVersion": FIS_SDK_VERSION}}

    try:
        async with session.post(
            FIS_AUTH_TOKEN_URL.format(fid=fid),
            headers=headers,
            json=body,
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status != 200:
                text = await resp.text()
                _LOGGER.warning(
                    "FIS auth token generate failed: HTTP %d — %s", resp.status, text
                )
                return None
            data = await resp.json()
            if "token" not in data:
                _LOGGER.warning("FIS auth token response missing token")
                return None
            return data
    except Exception as ex:  # noqa: BLE001
        _LOGGER.warning("FIS auth token generate error: %s", ex)
        return None


async def fcm_get_token_via_fis(
    session: ClientSession, existing: dict | None = None
) -> dict[str, str] | None:
    """Get an FCM token using Firebase Installations (modern getToken flow).

    Returns dict: {"android_id": str, "security_token": str, "fid": str, "refresh_token": str, "token": str}
    """
    android_id = None
    security_token = None

    if existing:
        android_id = existing.get("android_id")
        security_token = existing.get("security_token")

    if android_id and security_token:
        checkin_resp = await gcm_check_in(
            session, int(android_id), int(security_token)
        )
    else:
        checkin_resp = await gcm_check_in(session)

    if not checkin_resp:
        _LOGGER.warning("FIS flow: GCM check-in failed; cannot obtain device creds")
        return None

    android_id = str(checkin_resp["androidId"])
    security_token = str(checkin_resp["securityToken"])

    if existing:
        fid = existing.get("fid")
        refresh_token = existing.get("refresh_token")
        existing_token = existing.get("token")
        if fid and refresh_token:
            auth_data = await _fis_generate_auth_token(session, fid, refresh_token)
            if auth_data and auth_data.get("token"):
                token = await gcm_register(
                    session,
                    android_id=android_id,
                    security_token=security_token,
                    extra_fields=_gcm_fis_fields(fid, auth_data["token"]),
                )
                if token:
                    return {
                        "android_id": android_id,
                        "security_token": security_token,
                        "fid": fid,
                        "refresh_token": refresh_token,
                        "token": token,
                    }
            if existing_token:
                _LOGGER.debug(
                    "FIS token refresh failed, reusing existing token prefix: %s...",
                    existing_token[:20],
                )
                return {
                    "android_id": android_id,
                    "security_token": security_token,
                    "fid": fid,
                    "refresh_token": refresh_token,
                    "token": existing_token,
                }

    installation = await _fis_create_installation(session)
    if not installation:
        return None

    fid = installation.get("fid")
    refresh_token = installation.get("refreshToken")
    auth_token = installation.get("authToken", {}).get("token")
    if not fid or not refresh_token or not auth_token:
        _LOGGER.warning("FIS create installation missing required fields")
        return None

    token = await gcm_register(
        session,
        android_id=android_id,
        security_token=security_token,
        extra_fields=_gcm_fis_fields(fid, auth_token),
    )
    if not token:
        return None

    return {
        "android_id": android_id,
        "security_token": security_token,
        "fid": fid,
        "refresh_token": refresh_token,
        "token": token,
    }


def _gcm_fis_fields(fid: str, auth_token: str) -> dict[str, str]:
    return {
        "X-appid": fid,
        "X-gmp_app_id": FCM_APP_ID,
        "X-Goog-Firebase-Installations-Auth": auth_token,
        "X-cliv": FCM_CLIENT_LIBRARY,
        "X-firebase-app-name-hash": _firebase_app_name_hash(),
        "X-app_ver": FCM_APP_VERSION_CODE,
        "X-app_ver_name": FCM_APP_VERSION_NAME,
        "X-osv": FCM_OSV,
        "X-gmsv": FCM_GMSV,
        "X-scope": "*",
        "X-subtype": FCM_SENDER_ID,
        "appid": fid,
        "gmp_app_id": FCM_APP_ID,
        "Goog-Firebase-Installations-Auth": auth_token,
        "cliv": FCM_CLIENT_LIBRARY,
        "firebase-app-name-hash": _firebase_app_name_hash(),
        "app_ver": FCM_APP_VERSION_CODE,
        "app_ver_name": FCM_APP_VERSION_NAME,
        "osv": FCM_OSV,
        "gmsv": FCM_GMSV,
        "scope": "*",
        "subtype": FCM_SENDER_ID,
        "cert": FCM_ANDROID_CERT_SHA1,
    }


def _checkin_payload(
    android_id: int | None = None,
    security_token: int | None = None,
) -> AndroidCheckinRequest:
    """Build a minimal Android check-in request payload."""
    checkin = AndroidCheckinProto()
    checkin.type = DEVICE_ANDROID_OS  # 1 — Android, NOT Chrome (3)

    req = AndroidCheckinRequest()
    req.user_serial_number = 0
    req.checkin.CopyFrom(checkin)
    req.version = 3
    if android_id and security_token:
        req.id = int(android_id)
        req.security_token = int(security_token)
    return req


async def gcm_check_in(
    session: ClientSession,
    android_id: int | None = None,
    security_token: int | None = None,
    retries: int = 3,
) -> dict[str, Any] | None:
    """Check in with Google Cloud Messaging.

    Returns a dict with at minimum ``androidId`` and ``securityToken`` keys
    (camelCase, from protobuf MessageToDict), or None on failure.
    """
    from google.protobuf.json_format import MessageToDict  # noqa: PLC0415

    payload = _checkin_payload(android_id, security_token)

    for attempt in range(retries):
        try:
            async with session.post(
                GCM_CHECKIN_URL,
                headers={"Content-Type": "application/x-protobuf"},
                data=payload.SerializeToString(),
                timeout=_TIMEOUT,
            ) as resp:
                if resp.status == 200:
                    raw = await resp.read()
                    acir = AndroidCheckinResponse()
                    acir.ParseFromString(raw)
                    result = MessageToDict(acir)
                    _LOGGER.debug("GCM check-in succeeded: androidId=%s", result.get("androidId"))
                    return result
                text = await resp.text()
                _LOGGER.warning(
                    "GCM check-in attempt %d/%d failed: HTTP %d — %s",
                    attempt + 1, retries, resp.status, text,
                )
        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("GCM check-in attempt %d/%d error: %s", attempt + 1, retries, ex)

        # Retry without existing credentials on second attempt
        if attempt == 0 and android_id:
            payload = _checkin_payload()

    return None


async def gcm_register(
    session: ClientSession,
    android_id: str,
    security_token: str,
    retries: int = 3,
    extra_fields: dict[str, str] | None = None,
) -> str | None:
    """Register the Android app identity with GCM.

    Returns the GCM registration token (passed to Mazda's attach endpoint as
    ``deviceToken``), or None on failure.

    Key differences from Chrome/web registration:
    - ``sender`` = Mazda's sender ID, NOT the Chrome server key
    - ``app`` = Mazda's package name
    - ``X-subtype`` = sender ID (matches how Firebase SDK 23.x registers)
    - ``X-Android-Package`` / ``X-Android-Cert`` headers always included
    """
    headers = {
        "Authorization": f"AidLogin {android_id}:{security_token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Android-Package": FCM_ANDROID_PACKAGE,
        "X-Android-Cert": FCM_ANDROID_CERT_SHA1,
    }
    # X-subtype = sender_id is the correct value used by Firebase SDK 23.x
    # (package name was the old GCM style that produces differently-routed tokens)
    x_subtype = MAZDA_SENDER_ID
    if extra_fields and "subtype" in extra_fields:
        x_subtype = extra_fields["subtype"]
    body = {
        "app": MAZDA_APP_PACKAGE,
        "X-subtype": x_subtype,
        "device": android_id,
        "sender": MAZDA_SENDER_ID,
        "cert": FCM_ANDROID_CERT_SHA1,
    }
    if extra_fields:
        body.setdefault("gcm_ver", FCM_GMSV)
        body.setdefault("plat", FCM_PLATFORM)
        body.setdefault("app_ver", FCM_APP_VERSION_CODE)
        body.setdefault("app_ver_name", FCM_APP_VERSION_NAME)
        body.setdefault("osv", FCM_OSV)
        body.setdefault("target_ver", FCM_TARGET_VER)
        body.update(extra_fields)

    for attempt in range(retries):
        try:
            async with session.post(
                GCM_REGISTER_URL,
                headers=headers,
                data=body,
                timeout=_TIMEOUT,
            ) as resp:
                text = await resp.text()

            if "Error" in text or resp.status != 200:
                _LOGGER.warning(
                    "GCM register attempt %d/%d failed: %s",
                    attempt + 1, retries, text,
                )
                continue

            token = text.split("=", 1)[1] if "=" in text else text.strip()
            _LOGGER.debug("GCM registration succeeded, token prefix: %s...", token[:20])
            return token

        except Exception as ex:  # noqa: BLE001
            _LOGGER.warning("GCM register attempt %d/%d error: %s", attempt + 1, retries, ex)

    return None


async def fis_delete_installation(
    session: ClientSession,
    fid: str,
    refresh_token: str,
) -> bool:
    """Delete a Firebase Installation, invalidating all tokens tied to it.

    Equivalent to ``FirebaseInstallations.getInstance().delete()`` on Android.
    More reliable than ``c2dm/register3`` delete for FIS-path tokens because it
    doesn't require a fresh FIS auth token — the long-lived refresh token is used
    directly as the ``FIS_v2`` bearer credential.

    Returns True on success (HTTP 200), False otherwise (best-effort).
    """
    headers = {
        "Authorization": f"FIS_v2 {refresh_token}",
        "x-goog-api-key": FCM_API_KEY,
        "X-Android-Package": FCM_ANDROID_PACKAGE,
        "X-Android-Cert": FCM_ANDROID_CERT_SHA1,
    }
    try:
        async with session.delete(
            FIS_DELETE_URL.format(fid=fid),
            headers=headers,
            timeout=_TIMEOUT,
        ) as resp:
            if resp.status == 200:
                _LOGGER.debug("FIS installation deleted (fid=%s)", fid)
                return True
            text = await resp.text()
            _LOGGER.debug(
                "FIS installation delete failed (non-fatal): HTTP %d — %s", resp.status, text
            )
            return False
    except Exception as ex:  # noqa: BLE001
        _LOGGER.debug("FIS installation delete error (non-fatal): %s", ex)
        return False


async def gcm_unregister(
    session: ClientSession,
    android_id: str,
    security_token: str,
    fcm_token: str | None = None,
) -> bool:
    """Unregister the FCM token so Firebase stops routing to this device.

    Equivalent to ``FirebaseMessaging.getInstance().deleteToken()`` on Android.
    Called on integration unload so the old token becomes invalid — subsequent
    Mazda push attempts to the old token will receive INVALID_REGISTRATION from
    Firebase, causing Mazda's backend to remove the stale Conductor entry.

    ``fcm_token`` must be the registration token returned by ``gcm_register()``
    (stored in credentials["token"]).  Without it, Firebase has no specific
    registration to delete and echoes back the sender ID as ``token=<sender_id>``
    instead of ``deleted=<token>``.

    Returns True if unregistration was confirmed, False otherwise (best-effort).
    """
    headers = {
        "Authorization": f"AidLogin {android_id}:{security_token}",
        "Content-Type": "application/x-www-form-urlencoded",
        "X-Android-Package": FCM_ANDROID_PACKAGE,
        "X-Android-Cert": FCM_ANDROID_CERT_SHA1,
    }
    body = {
        "app": MAZDA_APP_PACKAGE,
        "X-subtype": MAZDA_SENDER_ID,
        "device": android_id,
        "sender": MAZDA_SENDER_ID,
        "cert": FCM_ANDROID_CERT_SHA1,
        "delete": "true",
    }
    if fcm_token:
        body["token"] = fcm_token
    try:
        async with session.post(
            GCM_REGISTER_URL,
            headers=headers,
            data=body,
            timeout=_TIMEOUT,
        ) as resp:
            text = await resp.text()
        if resp.status == 200 and "deleted" in text.lower():
            _LOGGER.debug("GCM unregistration succeeded")
            return True
        _LOGGER.debug("GCM unregistration response (non-fatal): HTTP %d — %s", resp.status, text)
        return False
    except Exception as ex:  # noqa: BLE001
        _LOGGER.debug("GCM unregistration error (non-fatal): %s", ex)
        return False


async def checkin_and_register(
    session: ClientSession,
    existing: dict | None = None,
) -> dict[str, str] | None:
    """GCM check-in + register — Android push-receiver flow.

    Uses Firebase Installations (FIS) as the primary path because FIS tokens
    include X-gmp_app_id (the Firebase App ID), which ties the registration to
    the specific app instance.  Mazda's Conductor backend uses Firebase's HTTP
    v1 send API, which requires app-instance tokens produced via the FIS path.
    Plain GCM register3 tokens (no gmp_app_id) are legacy sender-scoped tokens
    that may not be routable via FCM v1 — kept as fallback only.

    Returns ``{"android_id": str, "security_token": str, "token": str}`` on
    success, or None on failure.
    """
    # Primary: FIS path — token carries X-gmp_app_id so Firebase routes it as
    # an app-instance token (required for FCM HTTP v1 delivery from Conductor).
    fis_creds = await fcm_get_token_via_fis(session, existing=existing)
    if fis_creds:
        _LOGGER.info(
            "FCM token source: FIS path (android_id=%s token_prefix=%s...)",
            fis_creds["android_id"],
            fis_creds["token"][:30],
        )
        return fis_creds

    _LOGGER.warning("FCM FIS path failed — falling back to plain GCM register3")

    # Fallback: plain GCM register3 (legacy sender-scoped token, no gmp_app_id)
    android_id_int = None
    security_token_int = None
    if existing:
        android_id_int = int(existing.get("android_id", 0)) or None
        security_token_int = int(existing.get("security_token", 0)) or None

    checkin_resp = await gcm_check_in(session, android_id_int, security_token_int)
    if not checkin_resp:
        _LOGGER.warning("GCM check-in also failed — no FCM token available")
        return None

    android_id = str(checkin_resp["androidId"])
    security_token = str(checkin_resp["securityToken"])
    token = await gcm_register(session, android_id, security_token)
    if not token:
        _LOGGER.warning("GCM register3 fallback also failed")
        return None

    _LOGGER.info(
        "FCM token source: plain GCM register3 fallback (android_id=%s token_prefix=%s...)",
        android_id,
        token[:30],
    )
    return {
        "android_id": android_id,
        "security_token": security_token,
        "token": token,
    }
