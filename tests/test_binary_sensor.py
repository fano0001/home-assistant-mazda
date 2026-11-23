"""Tests for health binary sensor creation and the power-save sensor's values."""

from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from homeassistant.core import HomeAssistant

from custom_components.mazda_cs import binary_sensor
from custom_components.mazda_cs.binary_sensor import (
    MazdaBinarySensorEntityDescription,
    MazdaHealthBinarySensorEntity,
)

_VEHICLE = {
    "id": 1,
    "vin": "JM1TESTVIN",
    "modelYear": "2021",
    "carlineName": "CX-5",
    "hasFuel": True,
}

_ALWAYS = MazdaBinarySensorEntityDescription(
    key="health_always", value_fn=lambda h: None
)
_NEVER = MazdaBinarySensorEntityDescription(
    key="health_never", value_fn=lambda h: None, is_supported=lambda data: False
)


async def _health_entities(
    hass: HomeAssistant, *, health_report_available: bool
) -> list[MazdaHealthBinarySensorEntity]:
    coordinator = MagicMock(data=[dict(_VEHICLE)])
    entry = SimpleNamespace(
        runtime_data=SimpleNamespace(
            client=None,
            coordinator=coordinator,
            health_coordinator=MagicMock(),
            health_report_available=health_report_available,
        )
    )
    added = []
    with (
        patch.object(binary_sensor, "BINARY_SENSOR_ENTITIES", []),
        patch.object(binary_sensor, "HEALTH_BINARY_SENSOR_ENTITIES", [_ALWAYS, _NEVER]),
    ):
        await binary_sensor.async_setup_entry(hass, entry, added.extend)
    return added


async def test_health_entities_respect_is_supported(hass: HomeAssistant) -> None:
    """A health description whose is_supported is False creates no entity."""
    entities = await _health_entities(hass, health_report_available=True)

    assert [e.entity_description.key for e in entities] == ["health_always"]


async def test_no_health_entities_without_permission(hass: HomeAssistant) -> None:
    """Without the healthReports service no health entity is created."""
    entities = await _health_entities(hass, health_report_available=False)

    assert entities == []


@pytest.mark.parametrize(
    ("raw", "supported", "is_on"),
    [
        (0, True, False),
        (1, True, True),
        # Not supported; also never "on" if it turns up after setup.
        (2, False, False),
        (None, False, False),
    ],
)
def test_power_save_mode(raw, supported, is_on) -> None:
    """Only 1 is power save; 2 means the vehicle does not support it."""
    description = next(
        d for d in binary_sensor.BINARY_SENSOR_ENTITIES if d.key == "pw_sav_mode"
    )
    data = {"status": {"vehicleCondition": {"pwSavMode": raw}}}

    assert description.is_supported(data) is supported
    assert description.value_fn(data) is is_on
