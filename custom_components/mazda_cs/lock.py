"""Platform for Mazda lock integration."""
from __future__ import annotations

import logging
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
        
        # Verify required attributes from MazdaEntity
        if not hasattr(self, 'vin'):
            raise AttributeError("MazdaEntity must provide 'vin' attribute")
        if not hasattr(self, 'vehicle_id'):
            raise AttributeError("MazdaEntity must provide 'vehicle_id' attribute")
            
        self._attr_unique_id = f"mazda_lock_{self.vin}"
        self._attr_is_locking = False
        self._attr_is_unlocking = False
        self._attr_assumed_state = True
        self._logger = logging.getLogger(__name__)

    @property
    def is_locked(self) -> bool | None:
        """Return true if lock is locked."""
        try:
            return self.coordinator.data[self.index]["is_locked"]
        except KeyError:
            self._logger.debug("Lock state not available in coordinator data")
            return None
        except Exception as ex:
            self._logger.error("Error getting lock state: %s", ex)
            return None

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the vehicle doors."""
        self._attr_is_locking = True
        self.async_write_ha_state()
        try:
            await self.client.lock_doors(self.vehicle_id)
            # Request immediate refresh to update state
            await self.coordinator.async_request_refresh()
        except Exception as ex:
            self._logger.error("Failed to lock Mazda: %s", ex)
            raise
        finally:
            self._attr_is_locking = False
            self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle doors."""
        self._attr_is_unlocking = True
        self.async_write_ha_state()
        try:
            await self.client.unlock_doors(self.vehicle_id)
            # Request immediate refresh to update state
            await self.coordinator.async_request_refresh()
        except Exception as ex:
            self._logger.error("Failed to unlock Mazda: %s", ex)
            raise
        finally:
            self._attr_is_unlocking = False
            self.async_write_ha_state()
