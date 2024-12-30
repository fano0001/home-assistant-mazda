"""Platform for Mazda lock integration."""
from __future__ import annotations

from typing import Any

from homeassistant.components.lock import LockEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from . import MazdaEntity
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

    _attr_has_entity_name = True
    _attr_translation_key = "lock"

    def __init__(self, client, coordinator, index) -> None:
        """Initialize Mazda lock."""
        super().__init__(client, coordinator, index)
        self._attr_unique_id = self.vin
        self._attr_is_locking = False
        self._attr_is_unlocking = False

    @property
    def is_locked(self) -> bool | None:
        """Return true if lock is locked."""
        try:
            state = self.client.get_assumed_lock_state(self.vehicle_id)
            # Keep track of state but return None for separate buttons
            return None
        except:
            return None

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the vehicle doors."""
        self._attr_is_locking = True
        self.async_write_ha_state()
        try:
            await self.client.lock_doors(self.vehicle_id)
        finally:
            self._attr_is_locking = False
            self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle doors."""
        self._attr_is_unlocking = True
        self.async_write_ha_state()
        try:
            await self.client.unlock_doors(self.vehicle_id)
        finally:
            self._attr_is_unlocking = False
            self.async_write_ha_state()
