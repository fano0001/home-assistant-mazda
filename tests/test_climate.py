"""Tests for the climate entity's cabin temperature."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mazda_cs.climate import MazdaClimateEntity
from custom_components.mazda_cs.const import DOMAIN


def _climate(hass: HomeAssistant, unit: str, cabin: float | None) -> MazdaClimateEntity:
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
            "hvacSetting": {"temperatureUnit": unit},
            "evStatus": {"hvacInfo": {"interiorTemperatureCelsius": cabin}},
        }
    ]
    client = MagicMock()
    client.get_assumed_hvac_setting.return_value = {"temperature": 70}
    return MazdaClimateEntity(client, coordinator, 0, "MNAO")


@pytest.mark.parametrize(
    ("unit", "cabin", "expected"),
    [("F", 20.0, 68.0), ("C", 20.0, 20.0), ("F", None, None), ("C", None, None)],
)
async def test_current_temperature(hass: HomeAssistant, unit, cabin, expected) -> None:
    """A missing cabin temperature is unknown and does not stop the entity."""
    assert _climate(hass, unit, cabin).current_temperature == expected
