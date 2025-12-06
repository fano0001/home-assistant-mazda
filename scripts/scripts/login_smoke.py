import asyncio
import os
import aiohttp
from custom_components.mazda_cs.pymazda.api_v2 import MazdaApiV2

async def main():
    email = os.environ["MAZDA_EMAIL"]
    password = os.environ["MAZDA_PASSWORD"]
    async with aiohttp.ClientSession() as session:
        api = MazdaApiV2(email=email, password=password, region="MME", session=session)
        await api.async_login()
        cars = await api.async_get_vehicles()
        print("Vehicles:", cars)

if __name__ == "__main__":
    asyncio.run(main())