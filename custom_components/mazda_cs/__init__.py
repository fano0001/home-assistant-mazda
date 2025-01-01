"""The Mazda Connected Services integration."""
from __future__ import annotations

import asyncio
from asyncio import timeout
from datetime import timedelta
import logging
from typing import TYPE_CHECKING
import time

import voluptuous as vol

from .utils import with_timeout

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION, Platform
from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import (
    aiohttp_client,
    config_validation as cv,
    device_registry as dr,
    event as event_helper,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .const import (
    DATA_CLIENT,
    DATA_COORDINATOR,
    DATA_REGION,
    DATA_VEHICLES,
    DATA_ENTITY_MANAGER,
    DATA_INTEGRATION_HELPER,
    DOMAIN
)
from .pymazda.client import Client as MazdaAPI
from .pymazda.exceptions import (
    MazdaAccountLockedException,
    MazdaAPIEncryptionException,
    MazdaAuthenticationException,
    MazdaException,
    MazdaTokenExpiredException,
)
from .entity_manager import EntityUpdateManager
from .integration_helper import MazdaIntegrationHelper
from .connection import EnhancedConnection

_LOGGER = logging.getLogger(__name__)

from .const import PLATFORMS

from .const import HEALTH_CHECK_INTERVAL, HEALTH_CHECK_TIMEOUT

from .const import BATCH_SIZE, BATCH_DELAY, REQUEST_DELAY, MAX_RETRIES

class ConnectionState:
    """Track connection state and handle backoff."""
    
    def __init__(self):
        self.consecutive_failures = 0
        self.last_success = time.time()
        self.last_attempt = 0
        self.backoff_time = 0
        self.is_recovering = False

    def record_failure(self):
        """Record a failure and calculate backoff time."""
        self.consecutive_failures += 1
        self.last_attempt = time.time()
        from .const import MAX_BACKOFF_TIME, INITIAL_BACKOFF_TIME
        self.backoff_time = min(MAX_BACKOFF_TIME, (2 ** self.consecutive_failures) * INITIAL_BACKOFF_TIME)
        self.is_recovering = True

    def record_success(self):
        """Record a successful connection."""
        self.consecutive_failures = 0
        self.last_success = time.time()
        self.backoff_time = 0
        self.is_recovering = False

    async def wait_before_retry(self):
        """Wait according to backoff schedule if needed."""
        if self.backoff_time > 0:
            _LOGGER.info(f"Backing off for {self.backoff_time} seconds before retry")
            await asyncio.sleep(self.backoff_time)

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mazda Connected Services from a config entry."""
    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN].setdefault(entry.entry_id, {})

    # Initialize enhanced connection
    connection = EnhancedConnection(
        email=entry.data[CONF_EMAIL],
        password=entry.data[CONF_PASSWORD],
        region=entry.data[CONF_REGION]
    )

    try:
        # Initialize entity manager
        entity_manager = EntityUpdateManager(hass)
        await entity_manager.async_setup()
        
        # Initialize integration helper
        helper = MazdaIntegrationHelper(hass, entry.entry_id)
        await helper.async_setup(connection)

        # Store references
        hass.data[DOMAIN][entry.entry_id].update({
            DATA_ENTITY_MANAGER: entity_manager,
            DATA_INTEGRATION_HELPER: helper
        })

        # Initial data fetch
        vehicles = await helper.async_get_vehicles()
        if not vehicles:
            raise ConfigEntryNotReady("Failed to fetch initial vehicle data")

        hass.data[DOMAIN][entry.entry_id][DATA_VEHICLES] = vehicles

        # Set up platforms
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

        return True

    except Exception as ex:
        _LOGGER.error("Failed to set up Mazda integration: %s", str(ex))
        raise ConfigEntryNotReady from ex

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    try:
        # Unload platforms
        unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
        
        if unload_ok:
            # Clean up components
            helper = hass.data[DOMAIN][entry.entry_id].get(DATA_INTEGRATION_HELPER)
            if helper:
                await helper.async_unload()

            entity_manager = hass.data[DOMAIN][entry.entry_id].get(DATA_ENTITY_MANAGER)
            if entity_manager:
                await entity_manager.async_unload()

            hass.data[DOMAIN].pop(entry.entry_id)

        return unload_ok

    except Exception as ex:
        _LOGGER.error("Error unloading Mazda integration: %s", str(ex))
        return False
