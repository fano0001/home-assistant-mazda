import aiohttp
import pytest
from aiohttp import web

from custom_components.mazda_cs.pymazda.api_v2 import MazdaApiV2

API_BASE = "/connectedservices/v2"
TENANT = "432b587f-88ad-40aa-9e5d-e6bcf9429e8d"
AUTHORIZE_PATH = f"/{TENANT}/b2c_1a_signin/oauth2/v2.0/authorize"
TOKEN_PATH = f"/{TENANT}/b2c_1a_signin/oauth2/v2.0/token"
SELF_ASSERTED_PATH = f"/{TENANT}/B2C_1A_signin/SelfAsserted"
CONFIRM_PATH = f"/{TENANT}/api/CombinedSigninAndSignup/confirmed"


@pytest.fixture
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

    async def cmd(request):
        data = await request.json()
        if data.get("action") in ("start", "stop"):
            return web.json_response({"ok": True})
        return web.Response(status=400, text="bad action")

    app.router.add_get(AUTHORIZE_PATH, authorize)
    app.router.add_post(SELF_ASSERTED_PATH, self_asserted)
    app.router.add_post(CONFIRM_PATH, confirm)
    app.router.add_get(AUTHORIZE_PATH, authorize_silent)
    app.router.add_post(TOKEN_PATH, token)
    app.router.add_post(API_BASE + "/vehicles/{vin}/commands/charging", cmd)
    return await aiohttp_server(app)


@pytest.mark.asyncio
async def test_start_stop_charging(server):
    session = aiohttp.ClientSession()
    try:
        api = MazdaApiV2(
            email="u@example.com",
            password="pw",
            region="MME",
            session=session,
            api_base_override=str(server.make_url(API_BASE)).rstrip("/"),
        )
        base = str(server.make_url("")).rstrip("/")
        api._oauth_host = base
        api._authorize_url = base + AUTHORIZE_PATH
        api._token_url = base + TOKEN_PATH
        api._self_asserted_base = base + SELF_ASSERTED_PATH
        api._confirm_base = base + CONFIRM_PATH
        await api.async_login()
        await api.async_start_charging("JMZTEST")
        await api.async_stop_charging("JMZTEST")
    finally:
        await session.close()
