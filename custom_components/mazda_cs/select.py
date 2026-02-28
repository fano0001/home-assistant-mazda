"""Platform for Mazda select integration."""
from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import MazdaAPI as MazdaAPIClient, MazdaEntity
from .const import DATA_CLIENT, DATA_COORDINATOR, DOMAIN

FLASH_LIGHT_OPTIONS = ["2", "10", "30"]
DEFAULT_FLASH_LIGHT_COUNT = "10"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    client = hass.data[DOMAIN][config_entry.entry_id][DATA_CLIENT]
    coordinator = hass.data[DOMAIN][config_entry.entry_id][DATA_COORDINATOR]

    async_add_entities(
        MazdaFlashLightCountSelect(client, coordinator, index)
        for index, data in enumerate(coordinator.data)
        if data["hasFlashLight"]
    )


class MazdaFlashLightCountSelect(MazdaEntity, SelectEntity, RestoreEntity):
    """Select entity for choosing how many times to flash the lights."""

    _attr_translation_key = "flash_light_count"
    _attr_icon = "mdi:car-light-high"
    _attr_options = FLASH_LIGHT_OPTIONS

    def __init__(
        self,
        client: MazdaAPIClient,
        coordinator: DataUpdateCoordinator,
        index: int,
    ) -> None:
        """Initialize the flash light count select."""
        super().__init__(client, coordinator, index)
        self._attr_unique_id = f"{self.vin}_flash_light_count"
        self._attr_current_option = DEFAULT_FLASH_LIGHT_COUNT
        self.client.set_flash_light_count(self.vehicle_id, DEFAULT_FLASH_LIGHT_COUNT)

    async def async_added_to_hass(self) -> None:
        """Restore last selected option on HA restart."""
        await super().async_added_to_hass()
        if (last_state := await self.async_get_last_state()) and last_state.state in FLASH_LIGHT_OPTIONS:
            self._attr_current_option = last_state.state
            self.client.set_flash_light_count(self.vehicle_id, last_state.state)

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        self._attr_current_option = option
        self.client.set_flash_light_count(self.vehicle_id, option)
        self.async_write_ha_state()
