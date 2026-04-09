"""The Mazda Connected Services integration."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import TYPE_CHECKING

import aiohttp
import jwt
import voluptuous as vol


from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_REGION, Platform
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import (
    ConfigEntryAuthFailed,
    ConfigEntryNotReady,
    HomeAssistantError,
)
from homeassistant.helpers import (
    aiohttp_client,
    config_entry_oauth2_flow,
    config_validation as cv,
    device_registry as dr,
)

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import (
    CoordinatorEntity,
    DataUpdateCoordinator,
    UpdateFailed,
)

from .api import MazdaAuth
from .const import (
    CONF_ENABLE_PUSH,
    CONF_FCM_CREDENTIALS,
    DOMAIN,
    REMOTE_COMMAND_COOLDOWN_SECONDS,
    REMOTE_CONTROL_EVENTS_ENABLED,
    REMOTE_PUSH_TIMEOUT_SECONDS,
)
from .fcm_listener import EVENT_MAZDA_PUSH, MazdaFcmListener
from .pymazda.push._conductor import conductor_device_id_from_user_sub
from .oauth import MazdaOAuth2Implementation
from .pymazda.client import Client as MazdaAPI
from .pymazda.exceptions import MazdaTermsNotAcceptedException

_LOGGER = logging.getLogger(__name__)


@dataclass
class MazdaEntryData:
    """Runtime data stored on the config entry."""

    client: MazdaAPI
    coordinator: DataUpdateCoordinator
    health_coordinator: DataUpdateCoordinator
    fcm_listener: MazdaFcmListener | None
    region: str
    vehicles: list[dict] = field(default_factory=list)


type MazdaConfigEntry = ConfigEntry[MazdaEntryData]

EVENT_REMOTE_SERVICE_RESULT = "mazda_cs_remote_service_result"

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def with_timeout(task, timeout_seconds=30):
    """Run an async task with a timeout."""
    async with asyncio.timeout(timeout_seconds):
        return await task


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the Mazda Connected Services domain."""

    async def async_handle_service_call(service_call: ServiceCall) -> None:
        """Handle a service call."""
        dev_reg = dr.async_get(hass)
        device_id = service_call.data["device_id"]
        device_entry = dev_reg.async_get(device_id)
        if TYPE_CHECKING:
            # For mypy: it has already been checked in validate_mazda_device_id
            assert device_entry

        mazda_identifiers = (
            identifier
            for identifier in device_entry.identifiers
            if identifier[0] == DOMAIN
        )
        vin_identifier = next(mazda_identifiers)
        vin = vin_identifier[1]

        vehicle_id = 0
        api_client = None
        for loaded_entry in hass.config_entries.async_loaded_entries(DOMAIN):
            entry_data: MazdaEntryData = loaded_entry.runtime_data
            for vehicle in entry_data.vehicles:
                if vehicle["vin"] == vin:
                    vehicle_id = vehicle["id"]
                    api_client = entry_data.client
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

    hass.services.async_register(
        DOMAIN,
        "send_poi",
        async_handle_service_call,
        schema=vol.Schema(
            {
                vol.Required("device_id"): vol.All(cv.string, validate_mazda_device_id),
                vol.Required("latitude"): cv.latitude,
                vol.Required("longitude"): cv.longitude,
                vol.Required("poi_name"): cv.string,
            }
        ),
    )

    return True


async def async_setup_entry(hass: HomeAssistant, entry: MazdaConfigEntry) -> bool:
    """Set up Mazda Connected Services from a config entry."""
    region = entry.data.get(CONF_REGION, "MNAO")

    # Register our OAuth implementation
    config_entry_oauth2_flow.async_register_implementation(
        hass,
        DOMAIN,
        MazdaOAuth2Implementation(hass, region),
    )

    # Check if this is an old entry that needs reauth (v1 with email/password)
    # Chore:remove v1 upgrade logic in 2027 or later.
    if not entry.data.get("token"):
        msg = "Authentication method has changed. Please reauthenticate."
        raise ConfigEntryAuthFailed(msg)

    implementation = (
        await config_entry_oauth2_flow.async_get_config_entry_implementation(
            hass, entry
        )
    )
    session = config_entry_oauth2_flow.OAuth2Session(hass, entry, implementation)

    try:
        await session.async_ensure_token_valid()
    except ConfigEntryAuthFailed:
        raise
    except (aiohttp.ClientConnectionError, TimeoutError) as err:
        raise ConfigEntryNotReady(
            f"Transient connection error during token validation, will retry: {err}"
        ) from err
    except Exception as err:
        raise ConfigEntryNotReady(
            f"Unexpected error during token validation: {err}"
        ) from err

    # Extract JWT sub claim for device identity (used to derive device-id header)
    user_sub = ""
    try:
        token_data = jwt.decode(
            session.token["access_token"], options={"verify_signature": False}
        )
        user_sub = token_data.get("sub", "")
        _LOGGER.debug(
            "Access token claims: sub=%s, scp=%s, tfp=%s, exp=%s, azp=%s",
            token_data.get("sub"),
            token_data.get("scp"),
            token_data.get("tfp"),
            token_data.get("exp"),
            token_data.get("azp"),
        )
    except (jwt.DecodeError, KeyError):
        _LOGGER.warning("Could not decode sub claim from access token")

    if not user_sub:
        _LOGGER.error("No 'sub' claim in access token — cannot identify user")

    _LOGGER.debug("Using sub=%s as device identity for region=%s", user_sub, region)

    auth = MazdaAuth(session)
    websession = aiohttp_client.async_get_clientsession(hass)
    mazda_client = MazdaAPI(
        user_sub,
        region,
        access_token_provider=auth.async_get_access_token,
        websession=websession,
        use_cached_vehicle_list=True,
    )

    async def async_update_data():
        """Fetch data from Mazda API."""
        try:
            vehicles = await with_timeout(mazda_client.get_vehicles())

            # The Mazda API can throw an error when multiple simultaneous requests are
            # made for the same account, so we can only make one request at a time here
            for vehicle in vehicles:
                vehicle["region"] = region
                vehicle["enableWindows"] = entry.options.get("enable_windows", False)
                vehicle["enableDevSensors"] = entry.options.get(
                    "enable_dev_sensors", False
                )

                vehicle["status"] = await with_timeout(
                    mazda_client.get_vehicle_status(vehicle["id"])
                )

                # If vehicle is electric, get additional EV-specific status info
                if vehicle["isElectric"]:
                    vehicle["evStatus"] = await with_timeout(
                        mazda_client.get_ev_vehicle_status(vehicle["id"])
                    )
                    vehicle["hvacSetting"] = await with_timeout(
                        mazda_client.get_hvac_setting(vehicle["id"])
                    )

            entry.runtime_data.vehicles = vehicles

            return vehicles
        except MazdaTermsNotAcceptedException as ex:
            raise UpdateFailed(
                "Please accept the terms of service in the MyMazda app and try again"
            ) from ex
        except TimeoutError as ex:
            raise UpdateFailed(
                "Mazda API request timed out. The server may be temporarily unavailable."
            ) from ex
        except aiohttp.ClientConnectionError as ex:
            _LOGGER.warning("Mazda API client connection error (will retry): %s", ex)
            raise UpdateFailed(f"Cannot connect to Mazda API: {ex}") from ex
        except ConfigEntryAuthFailed:
            raise  # Let HA's coordinator trigger reauthentication
        except Exception as ex:
            _LOGGER.exception(
                "Unknown error occurred during Mazda update request: %s", ex
            )
            raise UpdateFailed(ex) from ex

    coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=DOMAIN,
        update_method=async_update_data,
        update_interval=timedelta(minutes=3),
    )

    async def async_update_health_data():
        """Fetch health report data for each vehicle. Returns a list aligned with coordinator.data."""
        vehicles = coordinator.data or []
        result = []
        for vehicle in vehicles:
            try:
                health = await with_timeout(
                    mazda_client.get_health_report(vehicle["id"])
                )
                _LOGGER.debug("getHealthReport: %s", health)
                result.append(health)
            except Exception as ex:  # noqa: BLE001
                _LOGGER.warning("getHealthReport failed: %s", ex)
                result.append(None)
        return result

    health_coordinator = DataUpdateCoordinator(
        hass,
        _LOGGER,
        name=f"{DOMAIN}_health",
        update_method=async_update_health_data,
        update_interval=timedelta(hours=12),
    )

    # Start FCM listener — coordinator must exist first so it can be passed in.
    # Must complete before attach so we have a token to register with Mazda's backend.
    # Derive Conductor deviceId from the JWT sub claim — same seed as the Mazda API
    # device-id header — so both systems see a consistent device identity.
    conductor_device_id = conductor_device_id_from_user_sub(user_sub) if user_sub else ""

    enable_push = entry.options.get(CONF_ENABLE_PUSH, False)
    fcm_listener = MazdaFcmListener(
        hass,
        entry,
        coordinator,
        region=region,
        conductor_device_id=conductor_device_id,
    )

    # Set runtime_data before starting FCM so any push arriving during setup
    # (e.g. action_code "010") can safely access entry.runtime_data.health_coordinator.
    entry.runtime_data = MazdaEntryData(
        client=mazda_client,
        coordinator=coordinator,
        health_coordinator=health_coordinator,
        fcm_listener=fcm_listener,
        region=region,
    )

    if enable_push:
        fcm_token = await fcm_listener.async_start()
        if fcm_token:
            _LOGGER.debug("FCM listener ready, token will be passed to attach")
        else:
            _LOGGER.debug("FCM unavailable — attach will use fallback device ID")
    else:
        fcm_token = None
        _LOGGER.debug("Push notifications disabled — FCM registration skipped")

    # Register device session with Mazda backend (required before any remoteServices calls)
    _LOGGER.debug("attach: using fcm_token=%s", fcm_token)
    try:
        attach_result = await mazda_client.attach(fcm_token=fcm_token)
        _LOGGER.debug("attach response: %s", attach_result)
    except Exception as ex:
        _LOGGER.warning("Mazda attach failed; vehicle status will be unavailable: %s", ex)

    # Fetch initial data so we have data when entities subscribe
    await coordinator.async_config_entry_first_refresh()

    # Schedule health report fetch in the background — non-critical, must not block setup
    entry.async_create_background_task(
        hass, health_coordinator.async_refresh(), "mazda_cs_health_initial_refresh"
    )

    # Setup components
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to new format."""
    if entry.version == 1:
        # Preserve region; clear old email/password credentials.
        # async_setup_entry will raise ConfigEntryAuthFailed (no "token" key),
        # triggering reauth so the user completes OAuth2.
        new_data = {CONF_REGION: entry.data.get(CONF_REGION, "MNAO")}
        hass.config_entries.async_update_entry(
            entry, data=new_data, minor_version=1, version=2
        )
    elif entry.version == 2 and entry.minor_version == 1:
        # minor_version 2: introduce CONF_ENABLE_PUSH option.
        # Opt existing entries out so they can consciously enable push via Reconfigure.
        hass.config_entries.async_update_entry(
            entry,
            options={**entry.options, CONF_ENABLE_PUSH: False},
            minor_version=2,
        )
        _LOGGER.warning(
            "Migration Successful: Push notification event support disabled by default. "
            "Reconfigure the integration to enable. See the ReadMe for more information."
        )

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MazdaConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)

    if unload_ok:
        entry_data: MazdaEntryData = entry.runtime_data

        # Detach the Mazda API session when unloading while HA is running (covers
        # both reload and explicit removal).  Skip on HA shutdown/restart so we
        # don't race the event loop teardown for a no-op cleanup call.
        if not hass.is_stopping:
            try:
                await entry_data.client.detach()
            except Exception:
                pass

        if entry_data.fcm_listener:
            # Deleting the FID on reload would leave a stale fid in entry.data
            # causing a 404 on next startup when refreshing the FIS auth token.
            await entry_data.fcm_listener.async_stop(unregister=False)

    return unload_ok


async def async_remove_entry(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Called only when the config entry is permanently deleted by the user.

    async_unload_entry runs first (MCS connection closed, session detached).
    hass.data for this entry has already been cleaned up by that point, so
    we read cleanup state directly from entry.data.

    Deletes the Firebase Installation so that Mazda's backend receives
    INVALID_REGISTRATION on its next push delivery attempt and removes the
    stale Conductor entry.  Skipped automatically if no FIS credentials exist
    (legacy GCM-only path or entry never fully set up).
    """
    from .pymazda.push._register import fis_delete_installation  # noqa: PLC0415

    creds = entry.data.get(CONF_FCM_CREDENTIALS) or {}
    fid = creds.get("fid")
    refresh_token = creds.get("refresh_token")
    if fid and refresh_token:
        async with aiohttp.ClientSession() as session:
            await fis_delete_installation(session, fid=fid, refresh_token=refresh_token)


class MazdaEntity(CoordinatorEntity):
    """Defines a base Mazda entity."""

    _attr_has_entity_name = True

    def __init__(self, client, coordinator, index):
        """Initialize the Mazda entity."""
        super().__init__(coordinator)
        self.client = client
        self.index = index
        self.vin = self.data["vin"]
        self.vehicle_id = self.data["id"]
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, self.vin)},
            manufacturer="Mazda",
            model=f"{self.data['modelYear']} {self.data['carlineName']}",
            name=self.vehicle_name,
        )

    async def _push_and_unlock(self, action: str) -> None:
        """Wait for a push event confirming the remote command, then reset the command-in-progress flag."""
        try:
            if REMOTE_CONTROL_EVENTS_ENABLED:
                push_event = asyncio.Event()
                push_data: dict = {}

                @callback
                def _on_push(event) -> None:
                    if (
                        event.data.get("vin") == self.vin
                        and event.data.get("action_code") in {"001", "021"}
                    ):
                        push_data.update(event.data)
                        push_event.set()

                unsub = self.hass.bus.async_listen(EVENT_MAZDA_PUSH, _on_push)
                try:
                    async with asyncio.timeout(REMOTE_PUSH_TIMEOUT_SECONDS):
                        await push_event.wait()
                    result_id = push_data.get("result_id", "")
                    self.hass.bus.async_fire(
                        EVENT_REMOTE_SERVICE_RESULT,
                        {
                            "vehicle_id": self.vehicle_id,
                            "vin": self.vin,
                            "action": action,
                            "success": result_id.endswith("_01"),
                            "title": push_data.get("title", ""),
                            "result_id": result_id,
                        },
                    )
                    _LOGGER.debug(
                        "Push result for %s vin=%s: result_id=%s",
                        action,
                        self.vin,
                        result_id,
                    )
                except TimeoutError:
                    _LOGGER.debug(
                        "Push result timed out: action=%s vin=%s", action, self.vin
                    )
                finally:
                    unsub()
            else:
                await asyncio.sleep(REMOTE_COMMAND_COOLDOWN_SECONDS)
        finally:
            self._command_in_progress = False

    @property
    def data(self):
        """Shortcut to access coordinator data for the entity."""
        return self.coordinator.data[self.index]

    @property
    def vehicle_name(self):
        """Return the vehicle name, to be used as a prefix for names of other entities."""
        if "nickname" in self.data and len(self.data["nickname"]) > 0:
            return self.data["nickname"]
        return f"{self.data['modelYear']} {self.data['carlineName']}"
