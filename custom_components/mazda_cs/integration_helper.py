"""Helper to tie together all optimized components."""
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional, List, Any

from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.util import dt as dt_util
from homeassistant.const import STATE_UNAVAILABLE

from .connection import EnhancedConnection
from .entity_manager import EntityUpdateManager
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

class MazdaIntegrationHelper:
    """Helper class to manage Mazda integration components."""
    
    def __init__(self, hass: HomeAssistant, entry_id: str):
        """Initialize the helper."""
        self.hass = hass
        self.entry_id = entry_id
        self._connection: Optional[EnhancedConnection] = None
        self._entity_manager: Optional[EntityUpdateManager] = None
        self._vehicle_status_cache: Dict[str, Dict] = {}
        self._last_full_update: Optional[datetime] = None
        self._update_lock = asyncio.Lock()
        self._vehicle_update_tasks: Dict[str, asyncio.Task] = {}
        self._error_count = 0
        self._recovery_mode = False
        self._vehicle_list_cache: Optional[List[Dict]] = None
        self._last_vehicle_list_update = 0
        
    async def async_setup(self, connection: EnhancedConnection):
        """Set up the helper with all components."""
        self._connection = connection
        self._entity_manager = EntityUpdateManager(self.hass)
        await self._entity_manager.async_setup()
        
        # Set up periodic status check
        async_track_time_interval(
            self.hass,
            self._async_check_system_status,
            timedelta(minutes=15)
        )
        
        # Set up error recovery monitor
        async_track_time_interval(
            self.hass,
            self._async_monitor_errors,
            timedelta(minutes=5)
        )
        
    async def async_update_vehicle(self, vehicle_id: str) -> Optional[Dict]:
        """Update a single vehicle with error handling and caching."""
        try:
            if vehicle_id in self._vehicle_update_tasks and not self._vehicle_update_tasks[vehicle_id].done():
                _LOGGER.debug(f"Update already in progress for vehicle {vehicle_id}")
                return self._vehicle_status_cache.get(vehicle_id)
                
            async with self._update_lock:
                # Check cache first
                cache_age = 0
                if vehicle_id in self._vehicle_status_cache:
                    cache_age = (dt_util.utcnow() - self._vehicle_status_cache[vehicle_id].get('last_update', dt_util.utcnow())).total_seconds()
                    
                # Use cache if it's less than 2 minutes old and we're in recovery mode
                if self._recovery_mode and cache_age < 120:
                    _LOGGER.debug(f"Using cached data for vehicle {vehicle_id} (age: {cache_age}s)")
                    return self._vehicle_status_cache.get(vehicle_id)
                
                # Create update task
                self._vehicle_update_tasks[vehicle_id] = asyncio.create_task(
                    self._async_fetch_vehicle_status(vehicle_id)
                )
                
                try:
                    status = await self._vehicle_update_tasks[vehicle_id]
                    if status:
                        self._error_count = 0
                        self._recovery_mode = False
                        return status
                except Exception as ex:
                    self._error_count += 1
                    _LOGGER.error(f"Failed to update vehicle {vehicle_id}: {str(ex)}")
                    return self._vehicle_status_cache.get(vehicle_id)
                finally:
                    del self._vehicle_update_tasks[vehicle_id]
                    
        except Exception as ex:
            _LOGGER.error(f"Error in vehicle update handler: {str(ex)}")
            return None
            
    async def _async_fetch_vehicle_status(self, vehicle_id: str) -> Optional[Dict]:
        """Fetch vehicle status with retry logic."""
        try:
            status = await self._connection.send_request(
                "GET",
                f"vehicles/{vehicle_id}/status"
            )
            
            if status:
                status['last_update'] = dt_util.utcnow()
                self._vehicle_status_cache[vehicle_id] = status
                await self._process_vehicle_status(vehicle_id, status)
                return status
                
        except Exception as ex:
            _LOGGER.error(f"Error fetching vehicle status: {str(ex)}")
            return None
            
    async def _process_vehicle_status(self, vehicle_id: str, status: Dict):
        """Process vehicle status updates."""
        try:
            # Extract relevant data for entities
            entity_updates = self._extract_entity_updates(status)
            
            # Schedule entity updates
            for entity_id, state in entity_updates.items():
                await self._entity_manager.async_schedule_update(entity_id, state)
                
        except Exception as ex:
            _LOGGER.error(f"Error processing vehicle status: {str(ex)}")
            
    def _extract_entity_updates(self, status: Dict) -> Dict[str, Any]:
        """Extract entity states from vehicle status."""
        updates = {}
        
        try:
            # Map status fields to entity states
            if 'doors' in status:
                for door, state in status['doors'].items():
                    entity_id = f"binary_sensor.{door}_door"
                    updates[entity_id] = 'on' if state else 'off'
                    
            if 'tires' in status:
                for tire, pressure in status['tires'].items():
                    entity_id = f"sensor.{tire}_pressure"
                    updates[entity_id] = pressure
                    
            # Add more mappings as needed
            
        except Exception as ex:
            _LOGGER.error(f"Error extracting entity updates: {str(ex)}")
            
        return updates
        
    async def _async_check_system_status(self, _now: datetime):
        """Periodic system status check."""
        try:
            # Check if we have too many errors
            if self._error_count > 10:
                _LOGGER.warning("High error count detected, entering recovery mode")
                self._recovery_mode = True
                await self._attempt_system_recovery()
                
            # Check connection health
            if self._connection:
                is_healthy = await self._connection.check_health()
                if not is_healthy:
                    _LOGGER.warning("Connection health check failed")
                    await self._attempt_system_recovery()
                    
        except Exception as ex:
            _LOGGER.error(f"Error in system status check: {str(ex)}")
            
    async def _attempt_system_recovery(self):
        """Attempt to recover system from errors."""
        try:
            _LOGGER.info("Attempting system recovery")
            
            # Reset connection
            if self._connection:
                await self._connection.close()
                await asyncio.sleep(30)  # Wait before reconnecting
                await self._connection.connect()
                
            # Clear caches older than 5 minutes
            now = dt_util.utcnow()
            old_cache = [
                vid for vid, data in self._vehicle_status_cache.items()
                if (now - data.get('last_update', now)).total_seconds() > 300
            ]
            for vid in old_cache:
                del self._vehicle_status_cache[vid]
                
            # Reset error counts if recovery is successful
            self._error_count = 0
            self._recovery_mode = False
            
        except Exception as ex:
            _LOGGER.error(f"Recovery attempt failed: {str(ex)}")
            
    async def _async_monitor_errors(self, _now: datetime):
        """Monitor and log error patterns."""
        if self._error_count > 0:
            _LOGGER.warning(f"Current error count: {self._error_count}")
            
        if self._recovery_mode:
            _LOGGER.warning("System is in recovery mode")
            
    async def async_unload(self):
        """Unload the integration helper."""
        try:
            # Cancel any pending updates
            for task in self._vehicle_update_tasks.values():
                if not task.done():
                    task.cancel()
                    
            # Close connection
            if self._connection:
                await self._connection.close()
                
            # Clear caches
            self._vehicle_status_cache.clear()
            
        except Exception as ex:
            _LOGGER.error(f"Error during unload: {str(ex)}")
