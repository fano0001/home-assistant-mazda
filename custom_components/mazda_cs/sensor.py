"""Platform for Mazda sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import PERCENTAGE, UnitOfLength, UnitOfPressure, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.typing import StateType

from .entity import MazdaEntity
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN

_LOGGER = logging.getLogger(__name__)

@dataclass
class MazdaSensorRequiredKeysMixin:
    """Mixin for required keys."""

    value: Callable[[dict[str, Any]], StateType]

@dataclass
class MazdaSensorEntityDescription(
    SensorEntityDescription, MazdaSensorRequiredKeysMixin
):
    """Describes a Mazda sensor entity."""

    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True

def _vehicle_health_supported(data):
    """Determine if vehicle health data is supported."""
    return True

def _vehicle_health_value(data):
    """Get vehicle health status."""
    return {
        "engine_oil_status": data["status"].get("engineOilStatus", "unknown"),
        "engine_oil_life": data["status"].get("engineOilLifePercent", 100),
        "brake_pad_status": data["status"].get("brakePadStatus", "unknown"),
        "battery_voltage": data["status"].get("batteryVoltage", 0),
        "tire_pressure": {
            "front_left": data["status"]["tirePressure"].get("frontLeftTirePressurePsi", 0),
            "front_right": data["status"]["tirePressure"].get("frontRightTirePressurePsi", 0),
            "rear_left": data["status"]["tirePressure"].get("rearLeftTirePressurePsi", 0),
            "rear_right": data["status"]["tirePressure"].get("rearRightTirePressurePsi", 0)
        }
    }

SENSOR_ENTITIES = [
    MazdaSensorEntityDescription(
        key="vehicle_health",
        translation_key="vehicle_health",
        icon="mdi:car-wrench",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_vehicle_health_supported,
        value=_vehicle_health_value,
    ),
]

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    if coordinator.data is None:
        _LOGGER.error("Coordinator data is not available")
        return

    entities: list[SensorEntity] = []

    for index, data in enumerate(coordinator.data):
        for description in SENSOR_ENTITIES:
            if description.is_supported(data):
                entities.append(
                    MazdaSensorEntity(client, coordinator, index, description)
                )

    async_add_entities(entities)

class MazdaSensorEntity(MazdaEntity, SensorEntity):
    """Representation of a Mazda vehicle sensor."""

    entity_description: MazdaSensorEntityDescription

    def __init__(self, client, coordinator, index, description):
        """Initialize Mazda sensor."""
        super().__init__(client, coordinator, index)
        self.entity_description = description
        self._attr_unique_id = f"{self.vin}_{description.key}"

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        return self.entity_description.value(self.data)
