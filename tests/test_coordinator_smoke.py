import aiohttp
import asyncio
import pytest


@pytest.fixture
def expected_lingering_timers():
    # Aiohttp TCPConnector Cleanup-Timer tolerieren
    return True
pytestmark = pytest.mark.enable_socket
import pytest_asyncio
from aiohttp import web
from homeassistant.core import HomeAssistant

from custom_components.mazda_cs.coordinator import MazdaDataCoordinator

API_BASE = "/connectedservices/v2"
TENANT = "432b587f-88ad-40aa-9e5d-e6bcf9429e8d"
AUTHORIZE_PATH = f"/{TENANT}/b2c_1a_signin/oauth2/v2.0/authorize"
TOKEN_PATH = f"/{TENANT}/b2c_1a_signin/oauth2/v2.0/token"
SELF_ASSERTED_PATH = f"/{TENANT}/B2C_1A_signin/SelfAsserted"
CONFIRM_PATH = f"/{TENANT}/api/CombinedSigninAndSignup/confirmed"


@pytest_asyncio.fixture
async def server(aiohttp_server):
    app = web.Application()

    async def authorize(request):
        return web.Response(text='<a href="?tx=StateProperties=abc"></a>')

    async def self_asserted(request):
        return web.Response(text="{}")

    async def confirm(request):
        return web.Response(text="{}")

    async def authorize_silent(request):
        raise web.HTTPFound(location="msauth.com.mazdausa.mazdaiphone://auth?code=AUTH_CODE")

    async def token(request):
        return web.json_response({"access_token": "t1", "refresh_token": "r1", "expires_in": 3600})

    async def vehicles(request):
        return web.json_response([{"vin": "JMZTEST", "id": "1", "modelName": "MX-30"}])

    async def status(request):
        return web.json_response({"batteryPercentage": 80})

    app.router.add_get(AUTHORIZE_PATH, authorize)
    app.router.add_post(SELF_ASSERTED_PATH, self_asserted)
    app.router.add_post(CONFIRM_PATH, confirm)
    app.router.add_get(AUTHORIZE_PATH, authorize_silent)
    app.router.add_post(TOKEN_PATH, token)
    app.router.add_get(API_BASE + "/vehicles", vehicles)
    app.router.add_get(API_BASE + "/vehicles/{vin}/status", status)
    return await aiohttp_server(app)


@pytest.mark.asyncio
async def test_coordinator_update(server, tmp_path):
    hass = HomeAssistant(config_dir=str(tmp_path))
    async with aiohttp.ClientSession() as session:
        coord = MazdaDataCoordinator(hass, email="u@example.com", password="pw", region="MME")
        base = str(server.make_url("")).rstrip("/")
        coord.api._oauth_host = base
        coord.api._authorize_url = base + AUTHORIZE_PATH
        coord.api._token_url = base + TOKEN_PATH
        coord.api._self_asserted_base = base + SELF_ASSERTED_PATH
        coord.api._confirm_base = base + CONFIRM_PATH
        coord.api._api_base = str(server.make_url(API_BASE)).rstrip("/")

        await coord.async_login()
        data = await coord._async_update_data()
        assert data["vehicles"][0].vin == "JMZTEST"
        assert "JMZTEST" in data["status"]

    await hass.async_block_till_done()
        # close underlying api session to avoid lingering TCPConnector timers
    try:
        api_obj = getattr(coord, 'api', None) or getattr(coord, '_api', None)
        if api_obj and hasattr(api_obj, 'aclose'):
            await api_obj.aclose()
    except Exception:
        pass
    await hass.async_stop()
    # cleanup API session if coordinator created its own client
    try:
        api_obj = getattr(coord, 'api', None) or getattr(coord, '_api', None)
        if api_obj is not None and hasattr(api_obj, 'aclose'):
            await api_obj.aclose()
    except Exception:
        pass
