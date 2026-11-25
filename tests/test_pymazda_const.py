"""The exact app and device values sent to Mazda, Azure B2C and Google.

Literals on purpose: an app update should show up here in every place it reaches.
"""

from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest
from homeassistant.core import HomeAssistant

from custom_components.mazda_cs.oauth import MazdaOAuth2Implementation
from custom_components.mazda_cs.pymazda import const
from custom_components.mazda_cs.pymazda.connection import SIGN_PACKAGE_ID, Connection
from custom_components.mazda_cs.pymazda.exceptions import MazdaConnectionException
from custom_components.mazda_cs.pymazda.push import _register

MSAL_PARAMS = {
    "x-app-name": "com.interrait.mymazda",
    "x-app-ver": "10.0.1",
    "x-client-SKU": "MSAL.Android",
    "x-client-Ver": "5.4.0",
    "x-client-OS": "36",
    "x-client-DM": "Pixel 9",
    "x-client-CPU": "arm64-v8a",
}


def test_user_agents() -> None:
    """Both User-Agents name the same Android version."""
    assert const.USER_AGENT_BASE_API == "MyMazda/10.0.1 (Linux; Android 16)"
    assert const.USER_AGENT_DALVIK == (
        "Dalvik/2.1.0 (Linux; U; Android 16; Pixel 9 Build/BP2A.250605.031.A2)"
    )


def test_sign_package_id() -> None:
    """Key derivation keeps its own constant; see connection.py."""
    assert SIGN_PACKAGE_ID == "com.interrait.mymazda"


@pytest.mark.parametrize("region", ["MNAO", "MCI", "MME", "MJO", "MA"])
async def test_authorize_parameters(hass: HomeAssistant, region: str) -> None:
    """The sign-in URL carries the MSAL values."""
    data = MazdaOAuth2Implementation(hass, region).extra_authorize_data
    assert {key: data[key] for key in MSAL_PARAMS} == MSAL_PARAMS


def test_gcm_registration_fields() -> None:
    """Push registration reports the app version and Android SDK."""
    fields = _register._gcm_fis_fields("fid", "auth")  # noqa: SLF001
    for prefix in ("", "X-"):
        assert fields[f"{prefix}app_ver"] == "653"
        assert fields[f"{prefix}app_ver_name"] == "10.0.1"
        assert fields[f"{prefix}osv"] == "36"
    assert fields["cliv"] == fields["X-cliv"] == "fcm-25.0.1"
    assert const.FIS_SDK_VERSION == "a:19.0.1"
    assert const.APP_TARGET_SDK == "36"


async def test_api_headers() -> None:
    """Requests to Mazda's API carry the app version, package and User-Agent."""
    session = MagicMock()
    session.request = AsyncMock(side_effect=aiohttp.ClientError)
    conn = Connection("test-sub", "MNAO", AsyncMock(), websession=session)
    with pytest.raises(MazdaConnectionException):
        await conn.api_request("POST", "test", needs_keys=True, needs_auth=False)

    headers = session.request.call_args_list[0].kwargs["headers"]
    assert headers["user-agent"] == "MyMazda/10.0.1 (Linux; Android 16)"
    assert headers["app-version"] == "10.0.1"
    assert headers["app-unique-id"] == "com.interrait.mymazda"
    assert headers["app-os"] == "ANDROID"
