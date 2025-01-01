"""Platform for Mazda binary sensor integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
import logging

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..entity import MazdaEntity
from ..const import DATA_ENTITY_MANAGER, DATA_INTEGRATION_HELPER, DATA_VEHICLES, DOMAIN

_LOGGER = logging.getLogger(__name__)

@dataclass
class MazdaBinarySensorRequiredKeysMixin:
    """Mixin for required keys."""
    is_on: Callable[[dict[str, Any]], bool]

@dataclass
class MazdaBinarySensorEntityDescription(
    BinarySensorEntityDescription, MazdaBinarySensorRequiredKeysMixin
):
    """Describes a Mazda binary sensor entity."""
    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True

BINARY_SENSOR_ENTITIES = [
    MazdaBinarySensorEntityDescription(
        key="door",
        translation_key="door",
        device_class=BinarySensorDeviceClass.DOOR,
        is_on=lambda data: any(
            door["status"] == "OPEN"
            for door in data.get("status", {}).get("doors", [])
        ),
    ),
    MazdaBinarySensorEntityDescription(
        key="engine",
        translation_key="engine",
        device_class=BinarySensorDeviceClass.RUNNING,
        is_on=lambda data: data.get("status", {}).get("engineRunning", False),
    ),
]

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the binary sensor platform."""
    entity_manager = hass.data[DOMAIN][config_entry.entry_id][DATA_ENTITY_MANAGER]
    helper = hass.data[DOMAIN][config_entry.entry_id][DATA_INTEGRATION_HELPER]
    vehicles = hass.data[DOMAIN][config_entry.entry_id][DATA_VEHICLES]

    entities: list[BinarySensorEntity] = []

    for vehicle in vehicles:
        for description in BINARY_SENSOR_ENTITIES:
            if description.is_supported(vehicle):
                entities.append(
                    MazdaBinarySensorEntity(
                        helper,
                        entity_manager,
                        vehicle["id"],
                        vehicle["vin"],
                        description
                    )
                )

    async_add_entities(entities)

class MazdaBinarySensorEntity(MazdaEntity, BinarySensorEntity):
    """Representation of a Mazda vehicle binary sensor."""

    entity_description: MazdaBinarySensorEntityDescription

    def __init__(
        self, 
        helper, 
        entity_manager, 
        vehicle_id: str,
        vin: str,
        description: MazdaBinarySensorEntityDescription
    ):
        """Initialize Mazda binary sensor."""
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
    def is_on(self) -> bool:
        """Return true if the binary sensor is on."""
        try:
            return self.entity_description.is_on(self._helper.get_vehicle_data(self.vehicle_id))
        except Exception as ex:
            _LOGGER.error("Error getting binary sensor state: %s", ex)
            return False

    async def async_update(self) -> None:
        """Update the binary sensor."""
        try:
            await self._helper.async_update_vehicle(self.vehicle_id)
        except Exception as ex:
            _LOGGER.error("Error updating binary sensor: %s", ex)
