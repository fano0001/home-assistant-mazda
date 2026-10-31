"""Platform for Mazda image integration."""

from __future__ import annotations

import logging

from homeassistant.components.image import Image, ImageEntity, infer_image_type
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.util import dt as dt_util

from . import (
    MazdaAPI as MazdaAPIClient,
    MazdaConfigEntry,
    MazdaEntity,
    bg_image_options,
)
from .const import SIGNAL_BG_IMAGE_SELECTED

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MazdaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the image platform."""
    client = config_entry.runtime_data.client
    coordinator = config_entry.runtime_data.coordinator
    image_coordinator = config_entry.runtime_data.image_coordinator

    async_add_entities(
        MazdaVehicleImage(hass, client, coordinator, image_coordinator, index)
        for index in range(len(coordinator.data))
    )


class MazdaVehicleImage(MazdaEntity, ImageEntity):
    """Vehicle background image from the MyMazda app home screen."""

    _attr_translation_key = "vehicle_image"

    def __init__(
        self,
        hass: HomeAssistant,
        client: MazdaAPIClient,
        coordinator: DataUpdateCoordinator,
        image_coordinator: DataUpdateCoordinator,
        index: int,
    ) -> None:
        """Initialize the vehicle image."""
        MazdaEntity.__init__(self, client, coordinator, index)
        ImageEntity.__init__(self, hass)
        self.image_coordinator = image_coordinator
        self._attr_unique_id = f"{self.vin}_vehicle_image"
        self._attr_image_url = None
        self._selected: str | None = None
        self._options: dict[str, str] = {}

    async def async_added_to_hass(self) -> None:
        """Subscribe to image data and selection changes."""
        await super().async_added_to_hass()
        self.async_on_remove(
            self.image_coordinator.async_add_listener(self._handle_image_update)
        )
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                SIGNAL_BG_IMAGE_SELECTED.format(self.vin),
                self._handle_image_update,
            )
        )
        self._refresh_url()

    @callback
    def _handle_image_update(self) -> None:
        """Handle new image data or a new selection."""
        self._refresh_url()
        self.async_write_ha_state()

    def _refresh_url(self) -> None:
        """Resolve the selected image and reset the cache when its URL changes."""
        data = self.image_coordinator.data
        self._options = bg_image_options(
            data[self.index] if data and self.index < len(data) else None
        )
        selected = self.client.get_home_bg_image(self.vehicle_id)
        if selected not in self._options:
            selected = next(iter(self._options), None)
        self._selected = selected
        url = self._options.get(selected) if selected else None
        if url != self._attr_image_url:
            self._attr_image_url = url
            self._attr_image_last_updated = dt_util.utcnow() if url else None
            self._cached_image = None

    async def _async_load_image_from_url(self, url: str) -> Image | None:
        """Load the image, taking its type from the bytes.

        Mazda's S3 bucket serves these JPEGs as application/octet-stream, which
        ImageEntity rejects; it only sniffs magic numbers when the header is missing.
        """
        if response := await self._fetch_url(url):
            if content_type := infer_image_type(response.content):
                return Image(content_type=content_type, content=response.content)
            _LOGGER.error(
                "%s: Image from %s is not a recognised image type", self.entity_id, url
            )
        return None

    @property
    def available(self) -> bool:
        """Return True when an image URL is available."""
        return super().available and bool(self._attr_image_url)

    @property
    def extra_state_attributes(self) -> dict:
        """Return the selected image and all available images."""
        return {
            "selected": self._selected,
            "images": [
                {"name": name, "url": url} for name, url in self._options.items()
            ],
        }
