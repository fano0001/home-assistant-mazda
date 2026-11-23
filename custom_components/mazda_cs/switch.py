"""Platform for Mazda switch integration."""

import logging
from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from . import MazdaAPI as MazdaAPIClient, MazdaConfigEntry, MazdaEntity
from .pymazda.exceptions import MazdaException

_LOGGER = logging.getLogger(__name__)


async def async_setup_entry(
    hass: HomeAssistant,
    config_entry: MazdaConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the switch platform."""
    client = config_entry.runtime_data.client
    coordinator = config_entry.runtime_data.coordinator

    async_add_entities(
        MazdaChargingSwitch(client, coordinator, index)
        for index, data in enumerate(coordinator.data)
        if data["isElectric"]
    )


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

    async def _request_status_report(self) -> None:
        """Ask the vehicle for a new EV status report after an accepted charge command.

        Mazda's reply only means the request was accepted. The report is read on
        the next push (022 is its result) or poll.
        """
        try:
            await self.client.refresh_vehicle_status(self.vehicle_id)
        except MazdaException as ex:
            _LOGGER.warning(
                "Charge command accepted, but requesting a new status report failed: %s",
                ex,
            )

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Start charging the vehicle."""
        try:
            await self.client.start_charging(self.vehicle_id)
        except MazdaException as ex:
            raise HomeAssistantError(ex) from ex
        await self._request_status_report()

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Stop charging the vehicle."""
        try:
            await self.client.stop_charging(self.vehicle_id)
        except MazdaException as ex:
            raise HomeAssistantError(ex) from ex
        await self._request_status_report()
