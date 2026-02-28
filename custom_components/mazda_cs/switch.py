"""Platform for Mazda switch integration."""
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import EntityCategory #For dev switch
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import DeviceInfo #For dev switch
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import MazdaAPI as MazdaAPIClient, MazdaEntity
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    entities = [
        MazdaEnableWindowsSwitch(hass, config_entry, coordinator, index)
        for index in range(len(coordinator.data))
    ]
    entities += [
        MazdaEnableDevSensorsSwitch(hass, config_entry, coordinator, index)
        for index in range(len(coordinator.data))
    ]
    entities += [
        MazdaChargingSwitch(client, coordinator, index)
        for index, data in enumerate(coordinator.data)
        if data["isElectric"]
    ]
    async_add_entities(entities)


class MazdaEnableWindowsSwitch(SwitchEntity):
    """Diagnostic switch to enable/disable window binary sensors."""

    _attr_translation_key = "enable_windows"
    _attr_icon = "mdi:window-open"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        index: int,
    ) -> None:
        """Initialize the enable windows switch."""
        self._hass = hass
        self._config_entry = config_entry
        vin = coordinator.data[index]["vin"]
        self._attr_unique_id = f"{vin}_enable_windows"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, vin)})

    @property
    def is_on(self) -> bool:
        """Return true if windows are enabled."""
        return self._config_entry.options.get("enable_windows", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable window sensors and reload the integration."""
        self._hass.config_entries.async_update_entry(
            self._config_entry,
            options={**self._config_entry.options, "enable_windows": True},
        )
        await self._hass.config_entries.async_reload(self._config_entry.entry_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable window sensors and reload the integration."""
        self._hass.config_entries.async_update_entry(
            self._config_entry,
            options={**self._config_entry.options, "enable_windows": False},
        )
        await self._hass.config_entries.async_reload(self._config_entry.entry_id)


class MazdaEnableDevSensorsSwitch(SwitchEntity):
    """Diagnostic switch to enable/disable dev (δ) sensors."""

    _attr_translation_key = "enable_dev_sensors"
    _attr_icon = "mdi:flask-outline"
    _attr_entity_category = EntityCategory.DIAGNOSTIC
    _attr_has_entity_name = True

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        coordinator: DataUpdateCoordinator,
        index: int,
    ) -> None:
        """Initialize the enable dev sensors switch."""
        self._hass = hass
        self._config_entry = config_entry
        vin = coordinator.data[index]["vin"]
        self._attr_unique_id = f"{vin}_enable_dev_sensors"
        self._attr_device_info = DeviceInfo(identifiers={(DOMAIN, vin)})

    @property
    def is_on(self) -> bool:
        """Return true if dev sensors are enabled."""
        return self._config_entry.options.get("enable_dev_sensors", False)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Enable dev sensors and reload the integration."""
        self._hass.config_entries.async_update_entry(
            self._config_entry,
            options={**self._config_entry.options, "enable_dev_sensors": True},
        )
        await self._hass.config_entries.async_reload(self._config_entry.entry_id)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Disable dev sensors and reload the integration."""
        self._hass.config_entries.async_update_entry(
            self._config_entry,
            options={**self._config_entry.options, "enable_dev_sensors": False},
        )
        await self._hass.config_entries.async_reload(self._config_entry.entry_id)


class MazdaChargingSwitch(MazdaEntity, SwitchEntity):
    """Class for the charging switch."""

    _attr_translation_key = "charging"
    _attr_icon = "mdi:ev-station"

    def __init__(
        self,
        client: MazdaAPIClient,
        coordinator: DataUpdateCoordinator,
        index: int,
    ) -> None:
        """Initialize Mazda charging switch."""
        super().__init__(client, coordinator, index)

        self._attr_unique_id = self.vin

    @property
    def is_on(self):
        """Return true if the vehicle is charging."""
        return self.data["evStatus"]["chargeInfo"]["charging"]

    async def refresh_status_and_write_state(self):
        """Request a status update, retrieve it through the coordinator, and write the state."""
        await self.client.refresh_vehicle_status(self.vehicle_id)

        await self.coordinator.async_request_refresh()

        self.async_write_ha_state()

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start charging the vehicle."""
        await self.client.start_charging(self.vehicle_id)

        await self.refresh_status_and_write_state()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop charging the vehicle."""
        await self.client.stop_charging(self.vehicle_id)

        await self.refresh_status_and_write_state()
