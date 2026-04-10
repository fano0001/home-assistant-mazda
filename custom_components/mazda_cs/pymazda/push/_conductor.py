"""Minimal StationDM Conductor request builder (updateuser) for diagnostics."""

from __future__ import annotations

import hashlib
import json
import time
from datetime import datetime
from typing import Any

from aiohttp import ClientSession, ClientTimeout

from ..crypto_utils import encrypt_aes128cbc_buffer_to_base64_str

CONDUCTOR_IV = "0102030405060708"
CONDUCTOR_VERSION = "v1"
CONDUCTOR_DEVICE_OS = "ANDROID"

# Per-region StationDM Conductor configuration.
# Source: assets/config/*_core_config.json in com.interrait.mymazda 9.0.8 APK.
# Used by service.setting.updateuser to register the FCM push token so that
# Mazda's Conductor backend delivers push notifications to this client.
CONDUCTOR_CONFIG: dict[str, dict[str, str]] = {
    "MNAO": {
        "server_url": "https://cdt.stationdm.com/api/service/api/index",
        "app_key": "iYSHWb3BfZAohz70tW9ymktooMQxg28UO2E581-NoDB4X:SfOdaNsYUo3;6pte6YHunpCIHtzTlfdw-N#IVrQFKn#OurYCYI0p69uvIhb2tRhrAC:G9:8$Lh48*mgYtQ",
    },
    "MCI": {
        "server_url": "https://cdt-mci.stationdm.com/api/service/api/index",
        "app_key": "tCrTSRN0RSErBho01ZNq2L#fqM$7PPvO;:XwTVqoMAT9Td;adadJ0CS:WX3*wex9Vhqg9U-#DaGme#1kFtGr3gZFTjGZpTblVp4t$nQ2X;dxx3b3UAJP:gIVWkiAUAlN",
    },
    "MME": {
        "server_url": "https://cdt-mme.stationdm.com/api/service/api/index",
        "app_key": "LVIbbGZsjroUyLfc95AtgI:aXUQA62pDO0LwIg$lXaqY5H-SdsQ7SjCFm$02Fa;DIsPPmCrnNRpzJj#MD-4By*2YJIhXRQuEq2;lwHqrzBT1-:tKG4*9w5r1-v1qK4:U",
    },
    "MJO": {
        "server_url": "https://cdt-jp.stationdm.com/api/service/api/index",
        "app_key": "w0bniKBEiMylQr9aPeg9##MiAYgAlJ58zUm0bpq2ELzytrqid1*pR$iKclOOmXPp6U#Y4RtxxY7gcO5E5IK1STSHpx8g1Mk8NOLt;L41o1xh42QzH6ZDI7t1RLWg27W3",
    },
    "MA": {
        "server_url": "https://cdt-ma.stationdm.com/api/service/api/index",
        "app_key": "a0KA1YNNOda6oN6GxtgbO9JtlyN4Er1JuCqzcI1:kpl335DRsRLduJ*SV8DPJ2*pXWutneiRqJCaHhO2uHVrjVyMs;*RzOseoTQSib#XbVh0C2DyazBHidWUr543hiAi",
    },
}

_TIMEOUT = ClientTimeout(total=15)


def _sha256_hex(data: str) -> str:
    return hashlib.sha256(data.encode("utf-8")).hexdigest().lower()


def derive_conductor_keys(app_key: str) -> tuple[str, str]:
    """Derive Conductor enc/sign keys from app key (matches SDK q.s())."""
    if len(app_key) < 99:
        raise ValueError("Conductor app key is too short to derive keys")
    val1 = _sha256_hex(app_key + app_key[33:66]).upper()
    val2 = _sha256_hex(val1 + app_key[66:99])
    enc_key = val2[4:20]
    sign_key = (
        val2[20:32]
        + val2[0:10]
        + val2[4:6]
        + val2[10:20]
        + val2[6:12]
    )
    return enc_key, sign_key

def conductor_device_id_from_user_sub(user_sub: str) -> str:
    """Derive Conductor deviceId from JWT sub claim.

    Identical derivation to the Mazda API ``device-id`` header: SHA1(sub) as
    lowercase hex, so both systems see the same device identity string.
    """
    return hashlib.sha1(user_sub.encode("utf-8")).hexdigest()

def build_update_user_payload(
    *,
    push_token: str,
    device_id: str,
    language: str | None = None,
    locale: str | None = None,
    timezone: str | None = None,
    app_version: str | None = None,
    device_type: str | None = None,
    device_os: str | None = None,
    device_os_version: str | None = None,
    device_model: str | None = None,
    user_id: str | None = None,
    primary_id: str | None = None,
    partner1_id: str | None = None,
) -> str:
    """Return the JSON string used as 'payload' in service.setting.updateuser.

    APK (`q.java`): updateuser sends userId (q.p()) = last non-empty of
    primaryId → partner2Id → partner1Id, cached from a prior q.q() call.

    ``primary_id``  → Conductor ``primaryId``  — Mazda ``custId`` (getUserInfo/v4), MNAO only.
    ``partner1_id`` → Conductor ``partner1Id`` — Mazda ``usherId`` (getUserInfo/v4), userId fallback.
    partner2Id (internalUserId from getCvUserIds/v4) is omitted to avoid that extra API call.
    email and partner2Id belong to q.i().q() (service.configuration) only — not sent here.
    """
    payload: dict[str, Any] = {"deviceId": device_id, "pushToken": push_token}
    if timezone:
        payload["timezone"] = timezone
    if language:
        payload["language"] = language
    if locale:
        payload["locale"] = locale
    if app_version:
        payload["appVersion"] = app_version
    if device_type:
        payload["deviceType"] = device_type
    if device_os:
        payload["deviceOs"] = device_os
    if device_os_version:
        payload["deviceOsVersion"] = device_os_version
    if device_model:
        payload["deviceModel"] = device_model
    if user_id:
        payload["userId"] = user_id
    if primary_id:
        payload["primaryId"] = primary_id
    if partner1_id:
        payload["partner1Id"] = partner1_id
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False)


def build_update_user_envelope(payload_json: str) -> str:
    """Wrap payload into the Conductor service envelope (plaintext)."""
    envelope = {
        "service": "service.setting.updateuser",
        "payload": payload_json,
    }
    return json.dumps(envelope, separators=(",", ":"), ensure_ascii=False)


def conductor_sign(encrypted_payload: str, timestamp: str, sign_key: str) -> str:
    """Generate c_sign header (matches SDK d.f())."""
    base = encrypted_payload or ""
    if timestamp:
        base += timestamp
        if len(timestamp) > 6:
            base += timestamp[6:]
        if len(timestamp) > 3:
            base += timestamp[3:]
    return _sha256_hex(base + sign_key).upper()


def default_timezone() -> str:
    return datetime.now().astimezone().strftime("%z")


async def _post_conductor(
    session: ClientSession,
    url: str,
    plaintext: str,
    enc_key: str,
    sign_key: str,
    app_key: str,
    device_id: str,
) -> tuple[int, str]:
    """Encrypt, sign, and POST a single Conductor request."""
    encrypted = encrypt_aes128cbc_buffer_to_base64_str(
        plaintext.encode("utf-8"),
        enc_key,
        CONDUCTOR_IV,
    )
    timestamp = str(int(time.time() * 1000))
    signature = conductor_sign(encrypted, timestamp, sign_key)
    headers = {
        "Content-Type": "application/json",
        "c_version": CONDUCTOR_VERSION,
        "c_device_id": device_id,
        "c_app_key": app_key,
        "c_timestamp": timestamp,
        "c_sign": signature,
    }
    async with session.post(url, headers=headers, data=encrypted, timeout=_TIMEOUT) as resp:
        text = await resp.text()
        return resp.status, text


def _decrypt_conductor_response(encrypted_b64: str, enc_key: str) -> dict[str, Any] | None:
    """Decrypt and JSON-parse a Conductor response payload field."""
    from ..crypto_utils import decrypt_aes128cbc_buffer_to_str  # noqa: PLC0415
    try:
        import base64  # noqa: PLC0415
        data = base64.b64decode(encrypted_b64)
        decrypted = decrypt_aes128cbc_buffer_to_str(data, enc_key, CONDUCTOR_IV)
        return json.loads(decrypted)
    except Exception:  # noqa: BLE001
        return None


async def send_app_init(
    session: ClientSession,
    *,
    server_url: str,
    app_key: str,
    device_id: str,
) -> tuple[int, str, str, str]:
    """Send service.app.init and return session enc/sign keys from the response.

    Must be called before service.setting.updateuser.  The plaintext body is
    ``{"deviceId": "<device_id>", "timestamp": "<ms>"}`` encrypted directly
    (no service/payload envelope), posted to ``server_url + "/initRequest"``.

    Returns ``(http_status, raw_text, session_enc_key, session_sign_key)``.
    On success the server returns new enc/sign keys in the encrypted payload
    that must be used for all subsequent requests in this session.
    Falls back to the derived keys if decryption or key extraction fails.
    """
    enc_key, sign_key = derive_conductor_keys(app_key)
    timestamp_ms = str(int(time.time() * 1000))
    plaintext = json.dumps(
        {"deviceId": device_id, "timestamp": timestamp_ms},
        separators=(",", ":"),
        ensure_ascii=False,
    )
    status, text = await _post_conductor(
        session,
        server_url + "/initRequest",
        plaintext,
        enc_key,
        sign_key,
        app_key,
        device_id,
    )

    # Extract server-issued session keys from the encrypted response payload.
    # The server response JSON: {"state":"S","payload":"<b64>","sign":"..."}
    # The decrypted payload contains {"encKey":"...", "signKey":"...", ...}
    session_enc_key = enc_key
    session_sign_key = sign_key
    try:
        resp_json = json.loads(text)
        if resp_json.get("state") == "S" and resp_json.get("payload"):
            inner = _decrypt_conductor_response(resp_json["payload"], enc_key)
            if inner:
                session_enc_key = inner.get("encKey", enc_key)
                session_sign_key = inner.get("signKey", sign_key)
    except Exception:  # noqa: BLE001
        pass

    return status, text, session_enc_key, session_sign_key


async def send_update_user(
    session: ClientSession,
    *,
    server_url: str,
    app_key: str,
    device_id: str,
    push_token: str,
    session_enc_key: str | None = None,
    session_sign_key: str | None = None,
    language: str | None = None,
    locale: str | None = None,
    timezone: str | None = None,
    app_version: str | None = None,
    device_type: str | None = None,
    device_os: str | None = None,
    device_os_version: str | None = None,
    device_model: str | None = None,
    user_id: str | None = None,
    primary_id: str | None = None,
    partner1_id: str | None = None,
) -> tuple[int, str]:
    """Send service.setting.updateuser to register the FCM push token.

    ``session_enc_key`` / ``session_sign_key``: server-issued keys from
    ``send_app_init``; fall back to keys derived from ``app_key`` if omitted.
    """
    derived_enc, derived_sign = derive_conductor_keys(app_key)
    enc_key = session_enc_key or derived_enc
    sign_key = session_sign_key or derived_sign
    payload_json = build_update_user_payload(
        push_token=push_token,
        device_id=device_id,
        language=language,
        locale=locale,
        timezone=timezone,
        app_version=app_version,
        device_type=device_type,
        device_os=device_os,
        device_os_version=device_os_version,
        device_model=device_model,
        user_id=user_id,
        primary_id=primary_id,
        partner1_id=partner1_id,
    )
    plaintext = build_update_user_envelope(payload_json)
    return await _post_conductor(
        session,
        server_url,
        plaintext,
        enc_key,
        sign_key,
        app_key,
        device_id,
    )
