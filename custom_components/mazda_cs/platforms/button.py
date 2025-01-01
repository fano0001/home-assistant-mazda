"""Platform for Mazda button integration."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
import logging

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from ..entity import MazdaEntity
from ..const import DATA_ENTITY_MANAGER, DATA_INTEGRATION_HELPER, DATA_VEHICLES, DOMAIN

_LOGGER = logging.getLogger(__name__)

@dataclass
class MazdaButtonRequiredKeysMixin:
    """Mixin for required keys."""
    press_action: Callable[[Any], None]

@dataclass
class MazdaButtonEntityDescription(
    ButtonEntityDescription, MazdaButtonRequiredKeysMixin
):
    """Describes a Mazda button entity."""
    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True

BUTTON_ENTITIES = [
    MazdaButtonEntityDescription(
        key="refresh",
        translation_key="refresh",
        icon="mdi:refresh",
        press_action=lambda helper, vehicle_id: helper.async_refresh_vehicle(vehicle_id),
    ),
]

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    entity_manager = hass.data[DOMAIN][config_entry.entry_id][DATA_ENTITY_MANAGER]
    helper = hass.data[DOMAIN][config_entry.entry_id][DATA_INTEGRATION_HELPER]
    vehicles = hass.data[DOMAIN][config_entry.entry_id][DATA_VEHICLES]

    entities: list[ButtonEntity] = []

    for vehicle in vehicles:
        for description in BUTTON_ENTITIES:
            if description.is_supported(vehicle):
                entities.append(
                    MazdaButtonEntity(
                        helper,
                        entity_manager,
                        vehicle["id"],
                        vehicle["vin"],
                        description
                    )
                )

    async_add_entities(entities)

class MazdaButtonEntity(MazdaEntity, ButtonEntity):
    """Representation of a Mazda vehicle button."""

    entity_description: MazdaButtonEntityDescription

    def __init__(
        self, 
        helper, 
        entity_manager, 
        vehicle_id: str,
        vin: str,
        description: MazdaButtonEntityDescription
    ):
        """Initialize Mazda button."""
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

    async def async_press(self) -> None:
        """Handle the button press."""
        try:
            await self.entity_description.press_action(self._helper, self.vehicle_id)
            await self._entity_manager.async_request_update(self.vehicle_id)
        except Exception as ex:
            _LOGGER.error("Error pressing button: %s", ex)
