import pytest
import pytest_asyncio
from aiohttp import web

from custom_components.mazda_cs.pymazda.api_v2 import MazdaApiV2

# ---- test-local constants ----
TENANT = "432b587f-88ad-40aa-9e5d-e6bcf9429e8d"
AUTHORIZE_PATH = f"/{TENANT}/b2c_1a_signin/oauth2/v2.0/authorize"
TOKEN_PATH = f"/{TENANT}/b2c_1a_signin/oauth2/v2.0/token"
SELF_ASSERTED_PATH = f"/{TENANT}/B2C_1A_signin/SelfAsserted"
CONFIRM_PATH = f"/{TENANT}/api/CombinedSigninAndSignup/confirmed"
API_BASE = "/connectedservices/v2"

@pytest_asyncio.fixture
async def server(aiohttp_server):
    app = web.Application()
    routes = web.RouteTableDef()

    state = {"code": "code123"}
    hits = {"vehicles": 0}

    @routes.get(AUTHORIZE_PATH)
    async def authorize(request: web.Request):
        if request.query.get("prompt") == "none":
            return web.Response(text='<a href="?tx=StateProperties=abc"></a>', content_type="text/html")
        if request.rel_url.query.get("tx") == "StateProperties=abc":
            redir = request.rel_url.with_query({"code": state["code"]})
            raise web.HTTPFound(location=str(redir))
        return web.Response(text="unexpected", status=400)

    @routes.post(SELF_ASSERTED_PATH)
    async def self_asserted(request: web.Request):
        return web.json_response({})

    @routes.post(CONFIRM_PATH)
    async def confirm(request: web.Request):
        return web.json_response({})

    @routes.post(TOKEN_PATH)
    async def token(request: web.Request):
        data = await request.post()
        if data.get("grant_type") == "authorization_code":
            return web.json_response({"access_token": "a1", "refresh_token": "r1", "expires_in": 3600})
        if data.get("grant_type") == "refresh_token":
            if data.get("refresh_token") == "r1":
                return web.json_response({"access_token": "a2", "refresh_token": "r2", "expires_in": 3600})
            return web.Response(status=400, text="bad refresh")
        return web.Response(status=400, text="bad grant")

    @routes.get(API_BASE + "/vehicles")
    async def vehicles(request: web.Request):
        auth = request.headers.get("Authorization", "")
        if "a1" in auth and hits["vehicles"] == 0:
            hits["vehicles"] += 1
            return web.Response(status=401, text="unauthorized")
        return web.json_response([{"vin": "JMZTEST", "id": "1"}])

    app.add_routes(routes)
    return await aiohttp_server(app)

@pytest.mark.asyncio
async def test_login_and_fetch(server):
    base = str(server.make_url("")).rstrip("/")
    api = MazdaApiV2(
        email="u@example.com",
        password="pw",
        region="MME",
        oauth_host_override=base,
        api_base_override=base + API_BASE,
    )
    try:
        await api.async_login()
        vehicles = await api.fetch_vehicles()
        assert vehicles and vehicles[0]["vin"] == "JMZTEST"
    finally:
        await api.aclose()

@pytest.mark.asyncio
async def test_refresh_and_401_retry(server):
    base = str(server.make_url("")).rstrip("/")
    api = MazdaApiV2(
        email="u@example.com",
        password="pw",
        region="MME",
        oauth_host_override=base,
        api_base_override=base + API_BASE,
    )
    try:
        await api.async_login()
        vehicles = await api.fetch_vehicles()
        assert vehicles and vehicles[0]["id"] == "1"
    finally:
        await api.aclose()
