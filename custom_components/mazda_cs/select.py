"""Platform for Mazda select integration."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import (
    MazdaAPI as MazdaAPIClient,
    MazdaConfigEntry,
    MazdaEntity,
    bg_image_options,
)
from .const import SIGNAL_BG_IMAGE_SELECTED

FLASH_LIGHT_OPTIONS = ["2", "10", "30"]
DEFAULT_FLASH_LIGHT_COUNT = "10"


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MazdaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the select platform."""
    client = config_entry.runtime_data.client
    coordinator = config_entry.runtime_data.coordinator
    image_coordinator = config_entry.runtime_data.image_coordinator

    entities: list[SelectEntity] = [
        MazdaFlashLightCountSelect(client, coordinator, index)
        for index, data in enumerate(coordinator.data)
        if data["hasFlashLight"]
    ]
    entities.extend(
        MazdaVehicleImageSelect(client, coordinator, image_coordinator, index)
        for index in range(len(coordinator.data))
    )
    async_add_entities(entities)


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
        if (
            last_state := await self.async_get_last_state()
        ) and last_state.state in FLASH_LIGHT_OPTIONS:
            self._attr_current_option = last_state.state
            self.client.set_flash_light_count(self.vehicle_id, last_state.state)

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        self._attr_current_option = option
        self.client.set_flash_light_count(self.vehicle_id, option)
        self.async_write_ha_state()


class MazdaVehicleImageSelect(MazdaEntity, SelectEntity, RestoreEntity):
    """Select entity for choosing which vehicle background image is shown."""

    _attr_translation_key = "vehicle_image"
    _attr_icon = "mdi:image-multiple"

    def __init__(
        self,
        client: MazdaAPIClient,
        coordinator: DataUpdateCoordinator,
        image_coordinator: DataUpdateCoordinator,
        index: int,
    ) -> None:
        """Initialize the vehicle image select."""
        super().__init__(client, coordinator, index)
        self.image_coordinator = image_coordinator
        self._attr_unique_id = f"{self.vin}_vehicle_image_select"
        self._restored_option: str | None = None

    @property
    def options(self) -> list[str]:
        """Return the image labels for this vehicle."""
        data = self.image_coordinator.data
        if not data or self.index >= len(data):
            return []
        return list(bg_image_options(data[self.index]))

    @property
    def current_option(self) -> str | None:
        """Return the selected image label."""
        return self.client.get_home_bg_image(self.vehicle_id)

    @property
    def available(self) -> bool:
        """Return True when images have been fetched."""
        return super().available and bool(self.options)

    async def async_added_to_hass(self) -> None:
        """Restore last selected image and subscribe to image data."""
        await super().async_added_to_hass()
        if last_state := await self.async_get_last_state():
            self._restored_option = last_state.state
        self.async_on_remove(
            self.image_coordinator.async_add_listener(self._handle_image_update)
        )
        self._resolve_selection()

    @callback
    def _handle_image_update(self) -> None:
        """Handle new image data."""
        self._resolve_selection()
        self.async_write_ha_state()

    def _resolve_selection(self) -> None:
        """Keep the selection valid: restored option first, else the first image."""
        options = self.options
        if not options or self.current_option in options:
            return
        if self._restored_option in options:
            self._set_selection(self._restored_option)
        else:
            self._set_selection(options[0])

    def _set_selection(self, option: str) -> None:
        self.client.set_home_bg_image(self.vehicle_id, option)
        async_dispatcher_send(self.hass, SIGNAL_BG_IMAGE_SELECTED.format(self.vin))

    async def async_select_option(self, option: str) -> None:
        """Handle option selection."""
        self._set_selection(option)
        self.async_write_ha_state()
