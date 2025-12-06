#!/usr/bin/env python3
"""
Echter OAuth2+PKCE-Login gegen Mazda EU (MME) mit Ausgabe der Fahrzeuge & eines Status-Samples.
Nutzung:
  export MAZDA_EMAIL="you@example.com"
  export MAZDA_PASSWORD="secret"
  export MAZDA_REGION="MME"
  python scripts/run_oauth_debug.py
"""

import asyncio
import logging
import os

import aiohttp

from custom_components.mazda_cs.pymazda.api_v2 import (
    MazdaApiError,
    MazdaApiV2,
    MazdaAuthError,
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("oauth_debug")

EMAIL = os.getenv("MAZDA_EMAIL") or input("Email: ").strip()
PASSWORD = os.getenv("MAZDA_PASSWORD") or input("Password: ").strip()
REGION = os.getenv("MAZDA_REGION") or "MME"


async def main() -> None:
    async with aiohttp.ClientSession() as session:
        api = MazdaApiV2(
            email=EMAIL,
            password=PASSWORD,
            region=REGION,
            session=session,
        )
        try:
            await api.async_login()
            vehicles = await api.async_get_vehicles()
            log.info("Vehicles: %s", [v.vin for v in vehicles])
            if vehicles:
                vin = vehicles[0].vin
                status = await api.async_get_vehicle_status(vin)
                log.info(
                    "Status vin=%s soc=%s%% range=%s km",
                    status.vin,
                    status.battery_percent,
                    status.remaining_range_km,
                )
        except (MazdaAuthError, MazdaApiError) as e:
            log.error("Failure: %s", e)


if __name__ == "__main__":
    asyncio.run(main())
