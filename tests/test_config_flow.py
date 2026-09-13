"""Tests for the Mazda config flow's reauth region handling."""

from unittest.mock import AsyncMock, patch

import pytest
from homeassistant.config_entries import SOURCE_REAUTH
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.helpers import config_entry_oauth2_flow
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mazda_cs import async_setup_entry
from custom_components.mazda_cs.const import DOMAIN, OAUTH2_AUTH, OAUTH2_HOSTS
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
        minor_version=3,
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
