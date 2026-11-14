"""Tests for the Mazda config flow: reauth region handling and manual sign-in."""

import time
from unittest.mock import AsyncMock, patch

import jwt
import pytest
from homeassistant.config_entries import SOURCE_REAUTH, SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry
from yarl import URL

from custom_components.mazda_cs import async_setup_entry
from custom_components.mazda_cs.const import (
    DOMAIN,
    MOBILE_REDIRECT_URI,
    OAUTH2_AUTH,
    OAUTH2_HOSTS,
)
from custom_components.mazda_cs.oauth import MazdaOAuth2Implementation

TOKEN = {
    "access_token": "access",
    "refresh_token": "refresh",
    "expires_at": 9999999999,
    "expires_in": 3600,
}


def _entry(region: str) -> MockConfigEntry:
    data = {"auth_implementation": DOMAIN, "region": region, "token": dict(TOKEN)}
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=f"sub-{region}",
        data=data,
        version=2,
        minor_version=4,
    )


async def _start_reauth(hass: HomeAssistant, entry: MockConfigEntry) -> dict:
    return await hass.config_entries.flow.async_init(
        DOMAIN,
        context={"source": SOURCE_REAUTH, "entry_id": entry.entry_id},
        data=entry.data,
    )


@pytest.mark.parametrize("region", ["MNAO", "MCI", "MME", "MJO", "MA"])
async def test_reauth_authorizes_against_entry_region(
    hass: HomeAssistant, region: str
) -> None:
    """Reauth must use the entry's own region, never a hardcoded MNAO default."""
    entry = _entry(region)
    entry.add_to_hass(hass)

    result = await _start_reauth(hass, entry)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reauth_confirm"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "auth"}
    )
    assert result["type"] is FlowResultType.EXTERNAL_STEP
    url = result["url"]
    assert OAUTH2_HOSTS[region] in url
    assert OAUTH2_AUTH[region]["tenant_id"] in url
    assert OAUTH2_AUTH[region]["client_id"] in url


async def test_setup_ignores_other_entry_implementation(hass: HomeAssistant) -> None:
    """An entry authenticates against its own region's B2C tenant.

    Implementations all register under the same key, so the registry only holds
    the last entry set up. Two entries in different regions is an unlikely setup,
    but the implementation should still follow the entry rather than the registry.
    """
    entry = _entry("MME")
    entry.add_to_hass(hass)

    # An MNAO entry loaded afterwards leaves its implementation in the registry.
    config_entry_oauth2_flow.async_register_implementation(
        hass, DOMAIN, MazdaOAuth2Implementation(hass, "MNAO")
    )

    session = AsyncMock()
    session.async_ensure_token_valid.side_effect = TimeoutError
    with patch(
        "homeassistant.helpers.config_entry_oauth2_flow.OAuth2Session",
        return_value=session,
    ) as mock_session:
        with pytest.raises(Exception):  # noqa: B017 - ConfigEntryNotReady
            await async_setup_entry(hass, entry)

    implementation = mock_session.call_args[0][2]
    assert OAUTH2_HOSTS["MME"] in implementation.token_url


# ---------------------------------------------------------------------------
# Manual sign-in — the user pastes the msauth:// redirect from the console.
# ---------------------------------------------------------------------------

_RESOLVE_EXTERNAL_DATA = (
    "custom_components.mazda_cs.oauth.MazdaOAuth2Implementation"
    ".async_resolve_external_data"
)
_SUB = "sub-mnao"


def _token() -> dict:
    """Return a token as the B2C exchange would, with a JWT carrying ``sub``."""
    return {
        "access_token": jwt.encode(
            {"sub": _SUB}, "test-signing-key-" * 2, algorithm="HS256"
        ),
        "refresh_token": "refresh",
        "expires_in": 3600,
        "expires_at": time.time() + 3600,
    }


def _callback_url(authorize_url: str, **params: str) -> str:
    """Build the msauth:// redirect B2C sends after sign-in."""
    state = URL(authorize_url).query["state"]
    return str(URL(MOBILE_REDIRECT_URI).with_query({"state": state, **params}))


@pytest.fixture
def mock_client():
    """Stub the account lookups made while creating the entry."""
    with patch("custom_components.mazda_cs.config_flow.MazdaAPI") as client_cls:
        client = client_cls.return_value
        client.get_user_info = AsyncMock(
            return_value={"userInfo": {"contactMailAddress": "driver@example.com"}}
        )
        client.close = AsyncMock()
        yield client


@pytest.fixture
def mock_setup_entry():
    """Keep the created entry from setting up against Mazda."""
    with patch(
        "custom_components.mazda_cs.async_setup_entry", return_value=True
    ) as setup:
        yield setup


async def _start_manual(hass: HomeAssistant) -> dict:
    """Start a user flow and pick the manual sign-in from the menu."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"region": "MNAO"}
    )
    assert result["type"] is FlowResultType.MENU
    assert result["menu_options"] == ["auth", "auth_manual"]
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "auth_manual"}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "auth_manual"
    return result


async def test_manual_paste_creates_entry(
    hass: HomeAssistant, mock_client, mock_setup_entry
) -> None:
    """Pasting the msauth:// redirect completes a fresh setup."""
    result = await _start_manual(hass)
    authorize_url = result["description_placeholders"]["authorize_url"]
    assert OAUTH2_HOSTS["MNAO"] in authorize_url

    with patch(_RESOLVE_EXTERNAL_DATA, return_value=_token()) as mock_resolve:
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"callback_url": _callback_url(authorize_url, code="auth-code")},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "Mazda (driver@example.com)"
    assert result["result"].unique_id == _SUB
    assert result["data"]["region"] == "MNAO"
    # Same shape the OAuth callback view would have handed the flow
    external_data = mock_resolve.call_args.args[0]
    assert external_data["code"] == "auth-code"
    assert external_data["state"]["redirect_uri"] == MOBILE_REDIRECT_URI


async def test_manual_reuses_authorize_url_after_error(hass: HomeAssistant) -> None:
    """A rejected paste re-shows the same authorize URL (same PKCE challenge)."""
    result = await _start_manual(hass)
    authorize_url = result["description_placeholders"]["authorize_url"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"callback_url": "not a url"}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_callback_url"}
    assert result["description_placeholders"]["authorize_url"] == authorize_url


async def test_manual_paste_rejects_authorization_error(hass: HomeAssistant) -> None:
    """B2C returning an error (e.g. cancelled sign-in) is reported on the form."""
    result = await _start_manual(hass)
    authorize_url = result["description_placeholders"]["authorize_url"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"callback_url": _callback_url(authorize_url, error="access_denied")},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "authorize_rejected"}


async def test_manual_paste_rejects_wrong_state(hass: HomeAssistant) -> None:
    """A URL from another sign-in attempt is rejected instead of exchanged."""
    result = await _start_manual(hass)

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "callback_url": str(
                URL(MOBILE_REDIRECT_URI).with_query(
                    {"state": "stale", "code": "auth-code"}
                )
            )
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "state_mismatch"}


async def test_manual_paste_rejects_missing_code(hass: HomeAssistant) -> None:
    """A URL without a code is rejected with a copy-the-address message."""
    result = await _start_manual(hass)
    authorize_url = result["description_placeholders"]["authorize_url"]

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"callback_url": _callback_url(authorize_url)}
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "invalid_callback_url"}


async def test_reauth_manual_paste(hass: HomeAssistant, mock_setup_entry) -> None:
    """Reauth offers the same menu and completes through the manual path."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=_SUB,
        data={"auth_implementation": DOMAIN, "region": "MME", "token": dict(TOKEN)},
        version=2,
        minor_version=4,
    )
    entry.add_to_hass(hass)

    result = await _start_reauth(hass, entry)
    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {"next_step_id": "auth_manual"}
    )
    authorize_url = result["description_placeholders"]["authorize_url"]
    assert OAUTH2_HOSTS["MME"] in authorize_url

    token = _token()
    with patch(_RESOLVE_EXTERNAL_DATA, return_value=token):
        result = await hass.config_entries.flow.async_configure(
            result["flow_id"],
            {"callback_url": _callback_url(authorize_url, code="auth-code")},
        )

    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reauth_successful"
    assert entry.data["token"]["access_token"] == token["access_token"]
