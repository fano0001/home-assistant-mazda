"""The Mazda Connected Services integration."""
from __future__ import annotations

import asyncio
from asyncio import timeout
from datetime import timedelta
import logging
from typing import TYPE_CHECKING
import time

import voluptuous as vol

async def with_timeout(task, timeout_seconds=120):  # Increased timeout to 120 seconds
    """Run an async task with a timeout."""
    try:
        async with timeout(timeout_seconds):
            return await task
    except asyncio.TimeoutError:
        _LOGGER.warning("Timeout occurred while waiting for Mazda API response")
        return None
    except Exception as ex:
        _LOGGER.warning("Error occurred during Mazda API request: %s", ex)
        return None

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

from .entity import MazdaEntity

from .const import DATA_CLIENT, DATA_COORDINATOR, DATA_REGION, DATA_VEHICLES, DOMAIN
from .pymazda.client import Client as MazdaAPI
from .pymazda.exceptions import (
    MazdaAccountLockedException,
    MazdaAPIEncryptionException,
    MazdaAuthenticationException,
    MazdaException,
    MazdaTokenExpiredException,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH,
]

# Health check constants
HEALTH_CHECK_INTERVAL = timedelta(minutes=15)
HEALTH_CHECK_TIMEOUT = 120  # Increased timeout to 120 seconds

# Update batch settings
BATCH_SIZE = 5  # Process 5 vehicles at a time
BATCH_DELAY = 15  # 15 seconds between batches

# Individual vehicle update settings
VEHICLE_RETRIES = 2  # Number of retries for individual vehicle updates
VEHICLE_RETRY_DELAY = 10  # Delay between retries for individual vehicles

async def perform_health_check(client: MazdaAPI) -> bool:
    """Perform a health check of the Mazda API connection."""
    retries = 3
    retry_delay = 15
    
    for attempt in range(retries):
        try:
            start_time = time.time()
            async with timeout(HEALTH_CHECK_TIMEOUT):
                vehicles = await client.get_vehicles()
                duration = time.time() - start_time
                _LOGGER.debug("Health check completed in %.2f seconds", duration)
                
                if not isinstance(vehicles, list):
                    _LOGGER.warning("Invalid vehicle data received during health check")
                    if attempt < retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return False
                    
                if len(vehicles) > 0 and not all(isinstance(v, dict) for v in vehicles):
                    _LOGGER.warning("Invalid vehicle data format received during health check")
                    if attempt < retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return False
                    
                return True
                
        except MazdaAuthenticationException as ex:
            _LOGGER.error("Authentication failed during health check: %s", ex)
            return False
        except MazdaAPIEncryptionException as ex:
            _LOGGER.error("Encryption error during health check: %s", ex)
            return False
        except MazdaTokenExpiredException as ex:
            _LOGGER.error("Token expired during health check: %s", ex)
            return False
        except MazdaAccountLockedException as ex:
            _LOGGER.error("Account locked during health check: %s", ex)
            return False
        except MazdaException as ex:
            if attempt < retries - 1:
                _LOGGER.warning("Mazda API error during health check (attempt %d/%d): %s", 
                              attempt + 1, retries, ex)
                await asyncio.sleep(retry_delay)
                continue
            _LOGGER.error("Mazda API error during health check: %s", ex)
            return False
        except asyncio.TimeoutError as ex:
            if attempt < retries - 1:
                _LOGGER.warning("Timeout during health check (attempt %d/%d): %s", 
                              attempt + 1, retries, ex)
                await asyncio.sleep(retry_delay)
                continue
            _LOGGER.error("Timeout during health check: %s", ex)
            return False
        except Exception as ex:
            if attempt < retries - 1:
                _LOGGER.warning("Unexpected error during health check (attempt %d/%d): %s", 
                              attempt + 1, retries, ex)
                await asyncio.sleep(retry_delay)
                continue
            _LOGGER.error("Unexpected error during health check: %s", ex)
            return False
            
    return False

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Mazda Connected Services from a config entry."""
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    region = entry.data[CONF_REGION]

    websession = aiohttp_client.async_get_clientsession(hass)
    mazda_client = MazdaAPI(
        email, password, region, websession=websession, use_cached_vehicle_list=True
    )

    retries = 3
    retry_delay = 15
    
    for attempt in range(retries):
        try:
            await mazda_client.validate_credentials()
            break
        except MazdaAuthenticationException as ex:
            raise ConfigEntryAuthFailed from ex
        except (
            MazdaException,
            MazdaAccountLockedException,
            MazdaTokenExpiredException,
            MazdaAPIEncryptionException,
        ) as ex:
            if attempt == retries - 1:
                _LOGGER.error("Error occurred during Mazda login request after %d attempts: %s", retries, ex)
                raise ConfigEntryNotReady from ex
            _LOGGER.warning("Mazda login request failed (attempt %d/%d), retrying in %d seconds: %s", 
                          attempt + 1, retries, retry_delay, ex)
            await asyncio.sleep(retry_delay)

    async def async_update_data():
        """Fetch data from Mazda API."""
        try:
            # Perform health check before updating data
            health_check_result = await perform_health_check(mazda_client)
            if not health_check_result:
                raise UpdateFailed("Health check failed")
                
            vehicles = await with_timeout(mazda_client.get_vehicles(), HEALTH_CHECK_TIMEOUT)
            if vehicles is None:
                _LOGGER.warning("Failed to get vehicle list")
                return hass.data[DOMAIN][entry.entry_id][DATA_VEHICLES] or []

            # Process vehicles in batches
            for i in range(0, len(vehicles), BATCH_SIZE):
                batch = vehicles[i:i + BATCH_SIZE]
                for vehicle in batch:
                    try:
                        start_time = time.time()
                        vehicle["status"] = await with_timeout(
                            mazda_client.get_vehicle_status(vehicle["id"]), HEALTH_CHECK_TIMEOUT
                        )
                        duration = time.time() - start_time
                        _LOGGER.debug("Vehicle status for %s completed in %.2f seconds", vehicle["id"], duration)
                        
                        await asyncio.sleep(5)  # Increased delay between requests
                    except Exception as ex:
                        _LOGGER.warning("Failed to update vehicle %s: %s", vehicle["id"], ex)
                        continue

                # Delay between batches
                if i + BATCH_SIZE < len(vehicles):
                    await asyncio.sleep(BATCH_DELAY)

            hass.data[DOMAIN][entry.entry_id][DATA_VEHICLES] = vehicles
            return vehicles
        except MazdaAuthenticationException as ex:
            raise ConfigEntryAuthFailed("Not authenticated with Mazda API") from ex
        except MazdaAPIEncryptionException as ex:
            _LOGGER.error("Encryption error during update: %s", ex)
            raise UpdateFailed("Encryption error") from ex
        except MazdaTokenExpiredException as ex:
            _LOGGER.error("Token expired during update: %s", ex)
            raise UpdateFailed("Token expired") from ex
        except MazdaException as ex:
            _LOGGER.error("Mazda API error during update: %s", ex)
            raise UpdateFailed("Mazda API error") from ex
        except asyncio.TimeoutError as ex:
            _LOGGER.error("Timeout during update: %s", ex)
            raise UpdateFailed("Timeout") from ex
        except Exception as ex:
            _LOGGER.exception("Unknown error occurred during Mazda update request: %s", ex)
            raise UpdateFailed("Unknown error") from ex

    # Set up coordinator with reduced update frequency
    hass.data.setdefault(DOMAIN, {})
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=HEALTH_CHECK_INTERVAL,
    )

    # Perform initial data refresh with retries
    retries = 3
    for attempt in range(retries):
        try:
            await coordinator.async_refresh()
            break
        except Exception as ex:
            if attempt == retries - 1:
                _LOGGER.error("Failed to perform initial data refresh after %d attempts: %s", retries, ex)
                raise ConfigEntryNotReady from ex
            _LOGGER.warning("Initial data refresh failed (attempt %d/%d), retrying in 15 seconds: %s", 
                          attempt + 1, retries, ex)
            await asyncio.sleep(15)

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_CLIENT: mazda_client,
        DATA_COORDINATOR: coordinator,
        DATA_REGION: region,
        DATA_VEHICLES: coordinator.data or [],
    }

    # Set up platforms only if initial data fetch succeeded
    if coordinator.data is not None:
        await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    else:
        _LOGGER.error("Failed to fetch initial vehicle data")
        raise ConfigEntryNotReady("Failed to fetch initial vehicle data")

    return True
