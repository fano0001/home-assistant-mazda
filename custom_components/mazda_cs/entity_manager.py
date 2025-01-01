"""Optimized entity update management for Mazda integration."""
import asyncio
import logging
from datetime import datetime
from typing import Dict, Set, Any, Optional
from collections import defaultdict

from homeassistant.core import HomeAssistant, State, CALLBACK_TYPE
from homeassistant.helpers.entity_registry import EntityRegistry
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util

_LOGGER = logging.getLogger(__name__)

class EntityUpdateManager:
    """Manages entity updates with batching and rate limiting."""
    
    def __init__(self, hass: HomeAssistant):
        """Initialize the update manager."""
        self.hass = hass
        self._entity_registry: Optional[EntityRegistry] = None
        self._pending_updates: Dict[str, Any] = {}
        self._update_lock = asyncio.Lock()
        self._batch_size = 10
        self._batch_delay = 0.1  # 100ms between batches
        self._entity_cooldowns: Dict[str, datetime] = {}
        self._min_update_interval = 5  # Minimum seconds between updates
        self._entity_groups: Dict[str, Set[str]] = defaultdict(set)
        self._scheduled_update = None
        
    async def async_setup(self):
        """Set up the update manager."""
        self._entity_registry = self.hass.helpers.entity_registry.async_get(self.hass)
        
        # Schedule periodic cleanup
        async_track_time_interval(
            self.hass,
            self._async_cleanup_cooldowns,
            interval=dt_util.timedelta(minutes=5)
        )
        
    def group_entities(self, vehicle_id: str, entity_ids: Set[str]):
        """Group entities by vehicle for coordinated updates."""
        self._entity_groups[vehicle_id] = entity_ids
        
    async def async_schedule_update(self, entity_id: str, new_state: Any):
        """Schedule an entity update with rate limiting."""
        now = dt_util.utcnow()
        
        # Check cooldown
        if entity_id in self._entity_cooldowns:
            last_update = self._entity_cooldowns[entity_id]
            if (now - last_update).total_seconds() < self._min_update_interval:
                _LOGGER.debug(f"Skipping update for {entity_id} - within cooldown period")
                return
        
        async with self._update_lock:
            self._pending_updates[entity_id] = new_state
            
            # Schedule batch update if not already scheduled
            if not self._scheduled_update:
                self._scheduled_update = asyncio.create_task(
                    self._process_pending_updates()
                )
                
    async def _process_pending_updates(self):
        """Process pending updates in batches."""
        try:
            while self._pending_updates:
                batch = {}
                
                # Group updates by vehicle where possible
                vehicle_batches = defaultdict(dict)
                ungrouped_updates = {}
                
                # Sort updates into vehicle groups
                for entity_id, new_state in self._pending_updates.items():
                    vehicle_id = self._find_vehicle_group(entity_id)
                    if vehicle_id:
                        vehicle_batches[vehicle_id][entity_id] = new_state
                    else:
                        ungrouped_updates[entity_id] = new_state
                
                # Process vehicle groups first
                for vehicle_id, updates in vehicle_batches.items():
                    await self._process_vehicle_batch(vehicle_id, updates)
                    await asyncio.sleep(self._batch_delay)
                
                # Process remaining updates in batches
                items = list(ungrouped_updates.items())
                for i in range(0, len(items), self._batch_size):
                    batch = dict(items[i:i + self._batch_size])
                    await self._update_batch(batch)
                    await asyncio.sleep(self._batch_delay)
                
                self._pending_updates.clear()
                
        except Exception as ex:
            _LOGGER.error(f"Error processing entity updates: {str(ex)}")
        finally:
            self._scheduled_update = None
            
    async def _process_vehicle_batch(self, vehicle_id: str, updates: Dict[str, Any]):
        """Process updates for a single vehicle's entities."""
        try:
            # Update all entities for this vehicle at once
            for entity_id, new_state in updates.items():
                self._entity_cooldowns[entity_id] = dt_util.utcnow()
                await self.hass.states.async_set(entity_id, new_state)
                
            _LOGGER.debug(f"Updated {len(updates)} entities for vehicle {vehicle_id}")
            
        except Exception as ex:
            _LOGGER.error(f"Error updating vehicle {vehicle_id} entities: {str(ex)}")
            
    def _find_vehicle_group(self, entity_id: str) -> Optional[str]:
        """Find which vehicle group an entity belongs to."""
        for vehicle_id, entities in self._entity_groups.items():
            if entity_id in entities:
                return vehicle_id
        return None
            
    async def _update_batch(self, batch: Dict[str, Any]):
        """Update a batch of entities."""
        try:
            update_time = dt_util.utcnow()
            for entity_id, new_state in batch.items():
                self._entity_cooldowns[entity_id] = update_time
                await self.hass.states.async_set(entity_id, new_state)
                
            _LOGGER.debug(f"Updated batch of {len(batch)} entities")
            
        except Exception as ex:
            _LOGGER.error(f"Error updating entity batch: {str(ex)}")
            
    async def _async_cleanup_cooldowns(self, _now: datetime):
        """Clean up expired cooldown entries."""
        now = dt_util.utcnow()
        expired = [
            entity_id for entity_id, last_update in self._entity_cooldowns.items()
            if (now - last_update).total_seconds() > self._min_update_interval
        ]
        for entity_id in expired:
            del self._entity_cooldowns[entity_id]
