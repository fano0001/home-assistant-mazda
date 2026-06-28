"""Platform for Mazda lock integration."""

from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MazdaConfigEntry, MazdaEntity
from .pymazda.exceptions import MazdaException


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MazdaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lock platform."""
    client = config_entry.runtime_data.client
    coordinator = config_entry.runtime_data.coordinator

    entities = []

    for index, _ in enumerate(coordinator.data):
        entities.append(MazdaLock(client, coordinator, index))

    async_add_entities(entities)


class MazdaLock(MazdaEntity, LockEntity):
    """Class for the lock."""

    _attr_translation_key = "lock"

    def __init__(self, client, coordinator, index) -> None:
        """Initialize Mazda lock."""
        super().__init__(client, coordinator, index)

        self._attr_unique_id = self.vin
        self._command_in_progress = False

    @property
    def is_locked(self) -> bool | None:
        """Return true if lock is locked."""
        return self.client.get_assumed_lock_state(self.vehicle_id)

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the vehicle doors."""
        if self._command_in_progress:
            return
        try:
            await self.client.lock_doors(self.vehicle_id)
        except MazdaException as ex:
            raise HomeAssistantError(ex) from ex
        self._command_in_progress = True
        self.async_write_ha_state()
        self.hass.async_create_task(self._push_and_unlock("doorLock"))

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle doors."""
        if self._command_in_progress:
            return
        try:
            await self.client.unlock_doors(self.vehicle_id)
        except MazdaException as ex:
            raise HomeAssistantError(ex) from ex
        self._command_in_progress = True
        self.async_write_ha_state()
        self.hass.async_create_task(self._push_and_unlock("doorUnlock"))
