"""The Mazda Connected Services integration."""
from __future__ import annotations

import asyncio
from asyncio import timeout
from datetime import timedelta
import logging
from typing import TYPE_CHECKING

import voluptuous as vol

async def with_timeout(task, timeout_seconds=30):
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
HEALTH_CHECK_INTERVAL = timedelta(minutes=5)
HEALTH_CHECK_TIMEOUT = 30  # seconds

async def perform_health_check(client: MazdaAPI) -> bool:
    """Perform a health check of the Mazda API connection."""
    retries = 3
    retry_delay = 5  # seconds
    
    for attempt in range(retries):
        try:
            # Test API connectivity by getting vehicle list
            async with timeout(HEALTH_CHECK_TIMEOUT):
                vehicles = await client.get_vehicles()
                
                # Verify we received valid vehicle data
                if not isinstance(vehicles, list):
                    _LOGGER.warning("Invalid vehicle data received during health check")
                    if attempt < retries - 1:
                        await asyncio.sleep(retry_delay)
                        continue
                    return False
                    
                # Verify the list contains valid vehicle objects
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

    try:
        await mazda_client.validate_credentials()
    except MazdaAuthenticationException as ex:
        raise ConfigEntryAuthFailed from ex
    except (
        MazdaException,
        MazdaAccountLockedException,
        MazdaTokenExpiredException,
        MazdaAPIEncryptionException,
    ) as ex:
        _LOGGER.error("Error occurred during Mazda login request: %s", ex)
        raise ConfigEntryNotReady from ex

    # Vehicle health monitoring is handled through the sensor platform
    # See sensor.py for implementation details

    async def async_handle_service_call(service_call: ServiceCall) -> None:
        """Handle a service call."""
        # Get device entry from device registry
        dev_reg = dr.async_get(hass)
        device_id = service_call.data["device_id"]
        device_entry = dev_reg.async_get(device_id)
        if TYPE_CHECKING:
            # For mypy: it has already been checked in validate_mazda_device_id
            assert device_entry

        # Get vehicle VIN from device identifiers
        mazda_identifiers = (
            identifier
            for identifier in device_entry.identifiers
            if identifier[0] == DOMAIN
        )
        vin_identifier = next(mazda_identifiers)
        vin = vin_identifier[1]

        # Get vehicle ID and API client from hass.data
        vehicle_id = 0
        api_client = None
        for entry_data in hass.data[DOMAIN].values():
            for vehicle in entry_data[DATA_VEHICLES]:
                if vehicle["vin"] == vin:
                    vehicle_id = vehicle["id"]
                    api_client = entry_data[DATA_CLIENT]
                    break

        if vehicle_id == 0 or api_client is None:
            raise HomeAssistantError("Vehicle ID not found")

        api_method = getattr(api_client, service_call.service)
        try:
            latitude = service_call.data["latitude"]
            longitude = service_call.data["longitude"]
            poi_name = service_call.data["poi_name"]
            await api_method(vehicle_id, latitude, longitude, poi_name)
        except Exception as ex:
            raise HomeAssistantError(ex) from ex

    def validate_mazda_device_id(device_id):
        """Check that a device ID exists in the registry and has at least one 'mazda' identifier."""
        dev_reg = dr.async_get(hass)

        if (device_entry := dev_reg.async_get(device_id)) is None:
            raise vol.Invalid("Invalid device ID")

        mazda_identifiers = [
            identifier
            for identifier in device_entry.identifiers
            if identifier[0] == DOMAIN
        ]
        if not mazda_identifiers:
            raise vol.Invalid("Device ID is not a Mazda vehicle")

        return device_id

    service_schema_send_poi = vol.Schema(
        {
            vol.Required("device_id"): vol.All(cv.string, validate_mazda_device_id),
            vol.Required("latitude"): cv.latitude,
            vol.Required("longitude"): cv.longitude,
            vol.Required("poi_name"): cv.string,
        }
    )

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

            # The Mazda API can throw an error when multiple simultaneous requests are
            # made for the same account, so we can only make one request at a time here
            for vehicle in vehicles:
                vehicle["status"] = await with_timeout(
                    mazda_client.get_vehicle_status(vehicle["id"]), HEALTH_CHECK_TIMEOUT
                )
                
                # If vehicle is electric, get additional EV-specific status info
                if vehicle["isElectric"] and vehicle["status"] is not None:
                    vehicle["evStatus"] = await with_timeout(
                        mazda_client.get_ev_vehicle_status(vehicle["id"]), HEALTH_CHECK_TIMEOUT
                    )
                    vehicle["hvacSetting"] = await with_timeout(
                        mazda_client.get_hvac_setting(vehicle["id"]), HEALTH_CHECK_TIMEOUT
                    )

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

    # Set up coordinator and initial data
    hass.data.setdefault(DOMAIN, {})
    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=5),
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
            _LOGGER.warning("Initial data refresh failed (attempt %d/%d), retrying in 5 seconds: %s", 
                          attempt + 1, retries, ex)
            await asyncio.sleep(5)

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
