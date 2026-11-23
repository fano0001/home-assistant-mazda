"""Tests for the charging switch's follow-up status request."""

import logging
from unittest.mock import AsyncMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mazda_cs.const import DOMAIN
from custom_components.mazda_cs.pymazda.exceptions import MazdaException
from custom_components.mazda_cs.switch import MazdaChargingSwitch

_COMMANDS = [("async_turn_on", "start_charging"), ("async_turn_off", "stop_charging")]


def _switch(hass: HomeAssistant) -> MazdaChargingSwitch:
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = DataUpdateCoordinator(
        hass,
        logging.getLogger(__name__),
        name=DOMAIN,
        update_method=AsyncMock(),
        update_interval=None,
        config_entry=entry,
    )
    coordinator.data = [
        {
            "id": 1,
            "vin": "JM1TESTVIN",
            "modelYear": "2024",
            "carlineName": "CX-90",
            "evStatus": {"chargeInfo": {"charging": False}},
        }
    ]
    coordinator.async_request_refresh = AsyncMock()
    switch = MazdaChargingSwitch(AsyncMock(), coordinator, 0)
    switch.hass = hass
    switch.entity_id = "switch.charging"
    return switch


@pytest.mark.parametrize(("action", "command"), _COMMANDS)
async def test_command_requests_a_report_without_reading(
    hass: HomeAssistant, action, command
) -> None:
    """The vehicle is asked for a report, which the next push or poll reads."""
    switch = _switch(hass)

    await getattr(switch, action)()

    getattr(switch.client, command).assert_awaited_once_with(1)
    switch.client.refresh_vehicle_status.assert_awaited_once_with(1)
    switch.coordinator.async_request_refresh.assert_not_awaited()


@pytest.mark.parametrize(("action", "command"), _COMMANDS)
async def test_failed_report_request_does_not_fail_the_command(
    hass: HomeAssistant, caplog: pytest.LogCaptureFixture, action, command
) -> None:
    """An accepted command succeeds; the failed follow-up is logged."""
    switch = _switch(hass)
    switch.client.refresh_vehicle_status.side_effect = MazdaException("timed out")

    await getattr(switch, action)()

    getattr(switch.client, command).assert_awaited_once_with(1)
    assert (
        "Charge command accepted, but requesting a new status report failed: timed out"
        in caplog.text
    )


@pytest.mark.parametrize(("action", "command"), _COMMANDS)
async def test_rejected_command_fails_without_a_report_request(
    hass: HomeAssistant, action, command
) -> None:
    """A rejected command is still an error, and nothing more is sent."""
    switch = _switch(hass)
    getattr(switch.client, command).side_effect = MazdaException("rejected")

    with pytest.raises(HomeAssistantError, match="rejected"):
        await getattr(switch, action)()

    switch.client.refresh_vehicle_status.assert_not_awaited()
