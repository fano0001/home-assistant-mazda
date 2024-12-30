"""Platform for Mazda button integration."""
from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.helpers import logging

_LOGGER = logging.getLogger(__name__)

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import (
    MazdaAccountLockedException,
    MazdaAPI as MazdaAPIClient,
    MazdaAPIEncryptionException,
    MazdaAuthenticationException,
    MazdaException,
    MazdaTokenExpiredException,
)
from .entity import MazdaEntity
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN, BUTTON_TYPE_REFRESH
from .pymazda.exceptions import MazdaLoginFailedException


async def handle_button_press(
    client: MazdaAPIClient,
    key: str,
    vehicle_id: int,
    coordinator: DataUpdateCoordinator,
) -> None:
    """Handle a press for a Mazda button entity."""
    api_method = getattr(client, key)

    try:
        await api_method(vehicle_id)
    except (
        MazdaException,
        MazdaAuthenticationException,
        MazdaAccountLockedException,
        MazdaTokenExpiredException,
        MazdaAPIEncryptionException,
        MazdaLoginFailedException,
    ) as ex:
        raise HomeAssistantError(ex) from ex


async def handle_refresh_vehicle_status(
    client: MazdaAPIClient,
    key: str,
    vehicle_id: int,
    coordinator: DataUpdateCoordinator,
) -> None:
    """Handle a request to refresh the vehicle status."""
    try:
        # Force a fresh data update from the API
        await client.get_vehicle_status(vehicle_id)
        await coordinator.async_request_refresh()
    except (
        MazdaException,
        MazdaAuthenticationException,
        MazdaAccountLockedException,
        MazdaTokenExpiredException,
        MazdaAPIEncryptionException,
        MazdaLoginFailedException,
    ) as ex:
        raise HomeAssistantError(f"Failed to refresh vehicle status: {str(ex)}") from ex


@dataclass
class MazdaButtonEntityDescription(ButtonEntityDescription):
    """Describes a Mazda button entity."""

    # Function to determine whether the vehicle supports this button,
    # given the coordinator data
    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True

    async_press: Callable[
        [MazdaAPIClient, str, int, DataUpdateCoordinator], Awaitable
    ] = handle_button_press


BUTTON_ENTITIES = [
    MazdaButtonEntityDescription(
        key="start_engine",
        translation_key="start_engine",
        icon="mdi:engine",
        is_supported=lambda data: not data["isElectric"],
    ),
    MazdaButtonEntityDescription(
        key="stop_engine",
        translation_key="stop_engine",
        icon="mdi:engine-off",
        is_supported=lambda data: not data["isElectric"],
    ),
    MazdaButtonEntityDescription(
        key="turn_on_hazard_lights",
        translation_key="turn_on_hazard_lights",
        icon="mdi:hazard-lights",
        is_supported=lambda data: not data["isElectric"],
    ),
    MazdaButtonEntityDescription(
        key="turn_off_hazard_lights",
        translation_key="turn_off_hazard_lights",
        icon="mdi:hazard-lights",
        is_supported=lambda data: not data["isElectric"],
    ),
    MazdaButtonEntityDescription(
        key="lock_doors",
        translation_key="lock_doors",
        icon="mdi:lock",
        is_supported=lambda data: True,
    ),
    MazdaButtonEntityDescription(
        key="unlock_doors",
        translation_key="unlock_doors",
        icon="mdi:lock-open",
        is_supported=lambda data: True,
    ),
    MazdaButtonEntityDescription(
        key="refresh_vehicle_status",
        translation_key="refresh_vehicle_status",
        icon="mdi:refresh",
        async_press=handle_refresh_vehicle_status,
        is_supported=lambda data: True,
    ),
]


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the button platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    _LOGGER.debug("Starting Mazda button setup")
    _LOGGER.debug("Coordinator data structure: %s", type(coordinator.data))
    _LOGGER.debug("Coordinator data content: %s", coordinator.data)
    _LOGGER.debug("Number of vehicles: %d", len(coordinator.data))
    
    # Verify coordinator data structure
    if not isinstance(coordinator.data, list):
        _LOGGER.error("Coordinator data is not a list: %s", type(coordinator.data))
        return
    if len(coordinator.data) == 0:
        _LOGGER.error("No vehicle data found in coordinator")
        return
    if not isinstance(coordinator.data[0], dict):
        _LOGGER.error("Vehicle data is not a dictionary: %s", type(coordinator.data[0]))
        return

    entities = []
    for index, data in enumerate(coordinator.data):
        _LOGGER.debug("Processing vehicle index %d", index)
        _LOGGER.debug("Vehicle data: %s", data)
        for description in BUTTON_ENTITIES:
            _LOGGER.debug("Processing button: %s", description.key)
            is_supported = description.is_supported(data)
            _LOGGER.debug("Button %s supported: %s", description.key, is_supported)
            if is_supported:
                entities.append(MazdaButtonEntity(client, coordinator, index, description))
    
    _LOGGER.debug("Total button entities to add: %d", len(entities))
    async_add_entities(entities)


class MazdaButtonEntity(MazdaEntity, ButtonEntity):
    """Representation of a Mazda button."""

    entity_description: MazdaButtonEntityDescription

    def __init__(
        self,
        client: MazdaAPIClient,
        coordinator: DataUpdateCoordinator,
        index: int,
        description: MazdaButtonEntityDescription,
    ) -> None:
        """Initialize Mazda button."""
        super().__init__(client, coordinator, index)
        self.entity_description = description

        self._attr_unique_id = f"{self.vin}_{description.key}"
        
        if description.key == "door_lock_control":
            self._attr_extra_state_attributes = {
                "lock_status": self.data["status"]["lockStatus"]["doors"].lower()
            }

    async def async_press(self) -> None:
        """Press the button."""
        if self.entity_description.key == "door_lock_control":
            current_status = self.data["status"]["lockStatus"]["doors"].lower()
            if current_status in ["locked", "locking"]:
                await self.client.unlock_doors(self.vehicle_id)
            else:
                await self.client.lock_doors(self.vehicle_id)
            await self.coordinator.async_request_refresh()
        else:
            await self.entity_description.async_press(
                self.client, self.entity_description.key, self.vehicle_id, self.coordinator
            )
