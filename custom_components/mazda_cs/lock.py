"""Platform for Mazda lock integration."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import (
    EVENT_REMOTE_SERVICE_RESULT,
    MazdaEntity,
)
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lock platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

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
        command_utc = datetime.now(timezone.utc)
        await self.client.lock_doors(self.vehicle_id)
        self._command_in_progress = True
        self.async_write_ha_state()
        self.hass.async_create_task(self._poll_and_unlock("doorLock", command_utc))

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle doors."""
        if self._command_in_progress:
            return
        command_utc = datetime.now(timezone.utc)
        await self.client.unlock_doors(self.vehicle_id)
        self._command_in_progress = True
        self.async_write_ha_state()
        self.hass.async_create_task(self._poll_and_unlock("doorUnlock", command_utc))

