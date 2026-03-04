"""Platform for Mazda button integration."""
from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import (
    EVENT_REMOTE_SERVICE_RESULT,
    MazdaAPI as MazdaAPIClient,
    MazdaAPIEncryptionException,
    MazdaEntity,
    MazdaException,
    MazdaTokenExpiredException,
)
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN


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
        MazdaTokenExpiredException,
        MazdaAPIEncryptionException,
    ) as ex:
        raise HomeAssistantError(ex) from ex


async def handle_refresh_vehicle_status(
    client: MazdaAPIClient,
    key: str,
    vehicle_id: int,
    coordinator: DataUpdateCoordinator,
) -> None:
    """Handle a request to refresh the vehicle status."""
    await handle_button_press(client, key, vehicle_id, coordinator)

    await coordinator.async_request_refresh()


@dataclass
class MazdaButtonEntityDescription(ButtonEntityDescription):
    """Describes a Mazda button entity."""

    # Function to determine whether the vehicle supports this button,
    # given the coordinator data
    is_supported: Callable[[dict[str, Any]], bool] = lambda data: True

    async_press: Callable[
        [MazdaAPIClient, str, int, DataUpdateCoordinator], Awaitable
    ] = handle_button_press

    # Set to False for buttons that don't send a remote command to the vehicle
    track_result: bool = field(default=True)


BUTTON_ENTITIES = [
    MazdaButtonEntityDescription(
        key="start_engine",
        translation_key="start_engine",
        icon="mdi:engine",
        is_supported=lambda data: not data["isElectric"] and data["hasRemoteStart"],
    ),
    MazdaButtonEntityDescription(
        key="stop_engine",
        translation_key="stop_engine",
        icon="mdi:engine-off",
        is_supported=lambda data: not data["isElectric"] and data["hasRemoteStart"],
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
        key="flash_lights",
        translation_key="flash_lights",
        icon="mdi:car-light-high",
        is_supported=lambda data: data["hasFlashLight"],
    ),
    MazdaButtonEntityDescription(
        key="refresh_vehicle_status",
        translation_key="refresh_vehicle_status",
        icon="mdi:refresh",
        async_press=handle_refresh_vehicle_status,
        is_supported=lambda data: data["isElectric"],
        track_result=False,
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

    async_add_entities(
        MazdaButtonEntity(client, coordinator, index, description)
        for index, data in enumerate(coordinator.data)
        for description in BUTTON_ENTITIES
        if description.is_supported(data)
    )


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
        self._command_in_progress = False

    async def async_press(self) -> None:
        """Press the button."""
        if self.entity_description.track_result and self._command_in_progress:
            return
        command_utc = datetime.now(timezone.utc)
        await self.entity_description.async_press(
            self.client, self.entity_description.key, self.vehicle_id, self.coordinator
        )
        if self.entity_description.track_result:
            self._command_in_progress = True
            self.hass.async_create_task(self._poll_and_unlock(command_utc))

    async def _poll_and_unlock(self, command_utc: datetime) -> None:
        """Poll for remote command result then re-allow button presses."""
        try:
            if self.data.get("enableButtonResultPolling", False):
                result = await self.client.poll_remote_service_result(self.vehicle_id, command_utc)
                if result:
                    self.hass.bus.async_fire(
                        EVENT_REMOTE_SERVICE_RESULT,
                        {
                            "vehicle_id": self.vehicle_id,
                            "vin": self.vin,
                            "action": self.entity_description.key,
                            **result,
                        },
                    )
            else:
                await asyncio.sleep(20)
        finally:
            self._command_in_progress = False
