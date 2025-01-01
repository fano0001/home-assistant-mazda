"""Platform for Mazda lock integration."""
from __future__ import annotations

import logging
from typing import Any

from homeassistant.components.lock import LockEntity, LockEntityFeature
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .. import MazdaEntity
from ..const import DATA_ENTITY_MANAGER, DATA_INTEGRATION_HELPER, DATA_VEHICLES, DOMAIN

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the lock platform."""
    entity_manager = hass.data[DOMAIN][config_entry.entry_id][DATA_ENTITY_MANAGER]
    helper = hass.data[DOMAIN][config_entry.entry_id][DATA_INTEGRATION_HELPER]
    vehicles = hass.data[DOMAIN][config_entry.entry_id][DATA_VEHICLES]

    entities = []
    for vehicle in vehicles:
        entities.append(
            MazdaLock(
                helper,
                entity_manager,
                vehicle["id"],
                vehicle["vin"]
            )
        )

    async_add_entities(entities)

class MazdaLock(MazdaEntity, LockEntity):
    """Class for the lock."""

    _attr_has_entity_name = True
    _attr_translation_key = "lock"
    _attr_supported_features = LockEntityFeature.OPEN | LockEntityFeature.UNLOCK

    def __init__(self, helper, entity_manager, vehicle_id, vin) -> None:
        """Initialize Mazda lock."""
        super().__init__(helper, entity_manager, vehicle_id, vin)
        self._attr_unique_id = f"mazda_lock_{self.vin}"
        self._attr_is_locking = False
        self._attr_is_unlocking = False
        self._attr_assumed_state = True

    @property
    def is_locked(self) -> bool | None:
        """Return true if lock is locked."""
        try:
            return self._helper.get_vehicle_status(self.vehicle_id).get("is_locked")
        except Exception as ex:
            _LOGGER.error("Error getting lock state: %s", ex)
            return None

    async def async_lock(self, **kwargs: Any) -> None:
        """Lock the vehicle doors."""
        self._attr_is_locking = True
        self.async_write_ha_state()
        try:
            await self._helper.async_lock_vehicle(self.vehicle_id)
            await self._entity_manager.async_request_update(self.vehicle_id)
        except Exception as ex:
            _LOGGER.error("Failed to lock Mazda: %s", ex)
            raise
        finally:
            self._attr_is_locking = False
            self.async_write_ha_state()

    async def async_unlock(self, **kwargs: Any) -> None:
        """Unlock the vehicle doors."""
        self._attr_is_unlocking = True
        self.async_write_ha_state()
        try:
            await self._helper.async_unlock_vehicle(self.vehicle_id)
            await self._entity_manager.async_request_update(self.vehicle_id)
        except Exception as ex:
            _LOGGER.error("Failed to unlock Mazda: %s", ex)
            raise
        finally:
            self._attr_is_unlocking = False
            self.async_write_ha_state()
