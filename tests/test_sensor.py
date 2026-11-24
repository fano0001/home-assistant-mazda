"""Tests for ``MazdaSensorEntity`` availability after a field disappears."""

import datetime
import logging
from unittest.mock import AsyncMock

import pytest

from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mazda_cs.const import DOMAIN
from custom_components.mazda_cs.sensor import SENSOR_ENTITIES, MazdaSensorEntity


def _sensor(hass: HomeAssistant, key: str, status: dict) -> MazdaSensorEntity:
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
            "modelYear": "2021",
            "carlineName": "CX-5",
            "status": status,
        }
    ]
    description = next(d for d in SENSOR_ENTITIES if d.key == key)
    return MazdaSensorEntity(None, coordinator, 0, description)


async def test_sensor_unavailable_when_field_disappears(hass: HomeAssistant) -> None:
    """A null frame after setup marks the sensor unavailable instead of raising."""
    sensor = _sensor(hass, "odometer", {"odometerKm": 1234.5})
    assert sensor.available is True
    assert sensor.native_value == 1234

    sensor.coordinator.data[0]["status"]["odometerKm"] = None

    assert sensor.available is False


async def test_string_sensor_unavailable_instead_of_none_string(
    hass: HomeAssistant,
) -> None:
    """A null light switch mode must not show up as the string "None"."""
    sensor = _sensor(hass, "light_combi_sw_mode", {"tnsLight": {"lightCombiSWMode": 2}})
    assert sensor.available is True
    assert sensor.native_value == "2"

    sensor.coordinator.data[0]["status"]["tnsLight"]["lightCombiSWMode"] = None

    assert sensor.available is False


async def test_battery_sensor_unavailable_above_127(hass: HomeAssistant) -> None:
    """socEcmAEst above 127 (invalid frame) would show more than 100 %."""
    sensor = _sensor(hass, "soc_ecm_a_est", {"batteryStatus": {"socEcmAEst": 127}})
    assert sensor.available is True

    sensor.coordinator.data[0]["status"]["batteryStatus"]["socEcmAEst"] = 200

    assert sensor.available is False


async def test_location_timestamp_sensor(hass: HomeAssistant) -> None:
    """The location timestamp is a timestamp sensor, unavailable without a fix time."""
    acquired = datetime.datetime(2026, 11, 22, 19, 38, 11, tzinfo=datetime.UTC)
    sensor = _sensor(hass, "location_timestamp", {"positionTimestamp": acquired})
    assert sensor.available is True
    assert sensor.native_value == acquired

    sensor.coordinator.data[0]["status"]["positionTimestamp"] = None

    assert sensor.available is False


@pytest.mark.parametrize(
    ("key", "group", "field"),
    [
        (
            "next_maintenance_distance",
            "maintenanceInfo",
            "nextMaintenanceDistanceKm",
        ),
        (
            "next_oil_change_distance",
            "oilMaintenanceInfo",
            "nextOilChangeDistanceKm",
        ),
    ],
)
@pytest.mark.parametrize(
    ("value", "available"),
    [
        (5011, True),
        (0, True),
        (65534, True),
        (65535, False),
        (65536, False),
        (None, False),
    ],
)
async def test_remaining_distance_limits(
    hass: HomeAssistant, key, group, field, value, available
) -> None:
    """65535 or out of range means the distance is not supported or not enabled."""
    sensor = _sensor(hass, key, {group: {field: value}})
    sensor.coordinator.data[0]["hasFuel"] = True

    assert sensor.available is available


@pytest.mark.parametrize(
    ("key", "group", "field", "available"),
    [
        (
            "next_maintenance_distance",
            "maintenanceInfo",
            "nextMaintenanceDistanceKm",
            True,
        ),
        (
            "next_oil_change_distance",
            "oilMaintenanceInfo",
            "nextOilChangeDistanceKm",
            False,
        ),
    ],
)
async def test_negative_distance(
    hass: HomeAssistant, key: str, group: str, field: str, available: bool
) -> None:
    """The app shows a negative service distance but hides a negative oil distance."""
    sensor = _sensor(hass, key, {group: {field: -500}})
    sensor.coordinator.data[0]["hasFuel"] = True

    assert sensor.available is available
    if available:
        assert sensor.native_value == -500
