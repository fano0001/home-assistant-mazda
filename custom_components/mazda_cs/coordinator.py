from __future__ import annotations

from typing import Any, Dict, List
import logging

import aiohttp
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator

from .const import DOMAIN
from .pymazda.api_v2 import (
    MazdaApiV2,
    MazdaTokenExpired,
    MazdaApiError,
    MazdaVehicle,
    MazdaVehicleStatus,
)

_LOGGER = logging.getLogger(__name__)


class MazdaDataCoordinator(DataUpdateCoordinator[dict[str, Any]]):
    """Coordinator that logs in once and caches the vehicle list, then fetches status."""

    def __init__(self, hass: HomeAssistant, *, email: str, password: str, region: str) -> None:
        super().__init__(hass, _LOGGER, name=DOMAIN)
        self.email = email
        self.password = password
        self.region = region
        # Cache vehicles after first fetch so we don't hit the endpoint repeatedly
        self.vehicles: List[MazdaVehicle] = []
        # Create a session owned by the API client
        self._session = aiohttp.ClientSession()
        self.api = MazdaApiV2(
            email=self.email,
            password=self.password,
            region=self.region,
            session=self._session,
        )

    async def async_login(self) -> None:
        """Perform OAuth login via the API client."""
        await self.api.async_login()

    async def _async_update_data(self) -> dict[str, Any]:
        """Fetch vehicle list (once) and current status for each vehicle."""
        try:
            _LOGGER.debug(
                "BREADCRUMB: coordinator._async_update_data fetch vehicles (existing=%d)",
                len(self.vehicles),
            )

            # Fetch vehicle list only once, then reuse
            if not self.vehicles:
                self.vehicles = await self.api.async_get_vehicles()

            status: Dict[str, MazdaVehicleStatus] = {}
            for v in self.vehicles:
                status[v.vin] = await self.api.async_get_vehicle_status(v.vin)

            # IMPORTANT: return both vehicles and status (tests expect 'vehicles')
            return {"vehicles": self.vehicles, "status": status}

        except MazdaApiError:
            # Let HA/tests handle the domain-specific error upstream
            raise
        except Exception as err:  # pragma: no cover - diagnostic aid
            _LOGGER.exception("Unexpected update error: %s", err)
            raise

    async def async_close(self) -> None:
        """Close the underlying HTTP session."""
        try:
            await self._session.close()
        except Exception:  # pragma: no cover
            pass
