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

from ..entity import MazdaEntity
from ..const import DATA_ENTITY_MANAGER, DATA_INTEGRATION_HELPER, DATA_VEHICLES, DOMAIN

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

def _vehicle_health_value(data) -> dict:
    """Get vehicle health status with safe access."""
    try:
        status = data.get("status", {})
        tire_pressure = status.get("tirePressure", {})
        
        return {
            "engine_oil_status": status.get("engineOilStatus", "unknown"),
            "engine_oil_life": status.get("engineOilLifePercent", 100),
            "brake_pad_status": status.get("brakePadStatus", "unknown"),
            "battery_voltage": status.get("batteryVoltage", 0),
            "tire_pressure": {
                "front_left": tire_pressure.get("frontLeftTirePressurePsi", 0),
                "front_right": tire_pressure.get("frontRightTirePressurePsi", 0),
                "rear_left": tire_pressure.get("rearLeftTirePressurePsi", 0),
                "rear_right": tire_pressure.get("rearRightTirePressurePsi", 0)
            }
        }
    except Exception as ex:
        _LOGGER.error("Error extracting vehicle health data: %s", ex)
        return {}

SENSOR_ENTITIES = [
    MazdaSensorEntityDescription(
        key="vehicle_health",
        translation_key="vehicle_health",
        icon="mdi:car-wrench",
        state_class=SensorStateClass.MEASUREMENT,
        is_supported=_vehicle_health_supported,
        value=_vehicle_health_value,
    ),
    MazdaSensorEntityDescription(
        key="fuel_remaining",
        translation_key="fuel_remaining",
        icon="mdi:gas-station",
        state_class=SensorStateClass.MEASUREMENT,
        native_unit_of_measurement=PERCENTAGE,
        device_class=SensorDeviceClass.BATTERY,
        value=lambda data: data.get("status", {}).get("fuelRemainingPercent", 0),
    ),
    MazdaSensorEntityDescription(
        key="odometer",
        translation_key="odometer",
        icon="mdi:counter",
        state_class=SensorStateClass.TOTAL_INCREASING,
        native_unit_of_measurement=UnitOfLength.MILES,
        device_class=SensorDeviceClass.DISTANCE,
        value=lambda data: data.get("status", {}).get("odometerMiles", 0),
    ),
]

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the sensor platform."""
    entity_manager = hass.data[DOMAIN][config_entry.entry_id][DATA_ENTITY_MANAGER]
    helper = hass.data[DOMAIN][config_entry.entry_id][DATA_INTEGRATION_HELPER]
    vehicles = hass.data[DOMAIN][config_entry.entry_id][DATA_VEHICLES]

    entities: list[SensorEntity] = []

    for vehicle in vehicles:
        for description in SENSOR_ENTITIES:
            if description.is_supported(vehicle):
                entities.append(
                    MazdaSensorEntity(
                        helper,
                        entity_manager,
                        vehicle["id"],
                        vehicle["vin"],
                        description
                    )
                )

    async_add_entities(entities)

class MazdaSensorEntity(MazdaEntity, SensorEntity):
    """Representation of a Mazda vehicle sensor."""

    entity_description: MazdaSensorEntityDescription

    def __init__(
        self, 
        helper, 
        entity_manager, 
        vehicle_id: str,
        vin: str,
        description: MazdaSensorEntityDescription
    ):
        """Initialize Mazda sensor."""
        super().__init__(helper, entity_manager, vehicle_id, vin)
        self.entity_description = description
        self._attr_unique_id = f"{self.vin}_{description.key}"
        self._attr_name = description.translation_key
        
        # Register with entity manager for updates
        self._entity_manager.register_entity(
            self._attr_unique_id,
            self,
            description.key
        )

    @property
    def native_value(self) -> StateType:
        """Return the state of the sensor."""
        try:
            return self.entity_description.value(self._helper.get_vehicle_data(self.vehicle_id))
        except Exception as ex:
            _LOGGER.error("Error getting sensor value: %s", ex)
            return None

    async def async_update(self) -> None:
        """Update the sensor."""
        try:
            await self._helper.async_update_vehicle(self.vehicle_id)
        except Exception as ex:
            _LOGGER.error("Error updating sensor: %s", ex)
