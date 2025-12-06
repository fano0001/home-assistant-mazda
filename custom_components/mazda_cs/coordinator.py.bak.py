from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD

from .const import DOMAIN
from .pymazda.api_v2 import MazdaApiV2, MazdaTokenExpired, MazdaApiError

_LOGGER = logging.getLogger(__name__)


class MazdaDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    def __init__(
        self, hass: HomeAssistant, *, email: str, password: str, region: str = "MME"
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            name=f"{DOMAIN}_data",
            update_interval=timedelta(minutes=5),
        )
        self.email = email
        self.password = password
        self.region = region
        self.vehicles = []
        self.api = MazdaApiV2(
            email=email,
            password=password,
            region=region,
            session=aiohttp.ClientSession(),
        )

    async def async_login(self) -> None:
        await self.api.async_login()

    async def _async_update_data(self) -> dict[str, Any]:
        _LOGGER.debug(
            "BREADCRUMB: coordinator._async_update_data fetch vehicles (existing=%d)",
            len(self.vehicles),
        )
        try:
            if not self.vehicles:
                self.vehicles = await self.api.async_get_vehicles()
            status = {}
            for v in self.vehicles:
                try:
                    status[v.vin] = await self.api.async_get_vehicle_status(v.vin)
                except (MazdaTokenExpired, MazdaApiError) as ex:
                    _LOGGER.warning("Vehicle status failed for %s: %s", v.vin, ex)
            return {"vehicles": self.vehicles, "status": status}
        except MazdaTokenExpired as ex:
            from homeassistant.exceptions import ConfigEntryAuthFailed

            _LOGGER.warning(
                "BREADCRUMB: token expired -> creating repair issue + raising ConfigEntryAuthFailed"
            )
            _LOGGER.warning("BREADCRUMB: auth error -> ConfigEntryAuthFailed")
            raise ConfigEntryAuthFailed(str(ex)) from ex
