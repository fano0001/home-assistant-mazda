#import asyncio
#import json
import time
from typing import Dict

import pytest
from aiohttp import web

from custom_components.mazda_cs.pymazda.api_v2 import MazdaApiV2, AuthTokens


API_BASE = "/connectedservices/v2"
AUTHORIZE_PATH = "/432b587f-88ad-40aa-9e5d-e6bcf9429e8d/b2c_1a_signin/oauth2/v2.0/authorize"
TOKEN_PATH = "/432b587f-88ad-40aa-9e5d-e6bcf9429e8d/b2c_1a_signin/oauth2/v2.0/token"
SELF_ASSERTED_PATH = "/432b587f-88ad-40aa-9e5d-e6bcf9429e8d/B2C_1A_signin/SelfAsserted"
CONFIRM_PATH = "/432b587f-88ad-40aa-9e5d-e6bcf9429e8d/api/CombinedSigninAndSignup/confirmed"


@pytest.fixture
async def server(aiohttp_server):
    app = web.Application()
    routes = web.RouteTableDef()

    # State for tests
    state: Dict[str, str] = {"tx": "abc", "code": "code123", "refresh_ok": "r2"}

    @routes.get(AUTHORIZE_PATH)
    async def authorize(request: web.Request):
        # First call with prompt=none -> return HTML anchor with tx only
        if request.query.get("prompt") == "none":
            return web.Response(text='<a href="?tx=StateProperties=abc"></a>', content_type="text/html")
        # Follow call without prompt should deliver redirect with code
        q = request.rel_url.query
        if q.get("tx") == "StateProperties=abc":
            redir = request.rel_url.with_query({"code": state["code"]})
            raise web.HTTPFound(location=str(redir))
        return web.Response(text="unexpected", status=400)

    @routes.post(TOKEN_PATH)
    async def token(request: web.Request):
        data = await request.post()
        if data.get("grant_type") == "authorization_code":
            return web.json_response(
                {"access_token": "a1", "refresh_token": "r1", "expires_in": 3600}
            )
        if data.get("grant_type") == "refresh_token":
            if data.get("refresh_token") == "r1":
                return web.json_response(
                    {"access_token": "a2", "refresh_token": "r2", "expires_in": 3600}
                )
            return web.Response(status=400, text="bad refresh")
        return web.Response(status=400, text="bad grant")

    # Vehicles endpoint that first returns 401, then success
    hits = {"v": 0}

    @routes.get(API_BASE + "/vehicles")
    async def vehicles(request: web.Request):
        auth = request.headers.get("Authorization", "")
        if "a1" in auth and hits["v"] == 0:
            hits["v"] += 1
            return web.Response(status=401, text="unauthorized")
        return web.json_response([{"vin": "JMZTEST", "id": "1"}])

    app.add_routes(routes)
    return await aiohttp_server(app)


@pytest.mark.asyncio
async def test_login_and_fetch(server):
    api = MazdaApiV2(email="u@example.com", password="pw", region="MME",
                     api_base_override=str(server.make_url(API_BASE)).rstrip("/"))
    base = str(server.make_url("")).rstrip("/")
    api._oauth_host = base
    api._authorize_url = base + AUTHORIZE_PATH
    api._token_url = base + TOKEN_PATH
    api._self_asserted_base = base + SELF_ASSERTED_PATH
    api._confirm_base = base + CONFIRM_PATH

    await api.async_login()
    vs = await api.fetch_vehicles()
    assert isinstance(vs, list) and vs and vs[0]["vin"] == "JMZTEST"


@pytest.mark.asyncio
async def test_refresh_and_401_retry(server):
    api = MazdaApiV2(email="u@example.com", password="pw", region="MME",
                     api_base_override=str(server.make_url(API_BASE)).rstrip("/"))
    base = str(server.make_url("")).rstrip("/")
    api._oauth_host = base
    api._authorize_url = base + AUTHORIZE_PATH
    api._token_url = base + TOKEN_PATH
    api._self_asserted_base = base + SELF_ASSERTED_PATH
    api._confirm_base = base + CONFIRM_PATH

    # Login first
    await api.async_login()
    # Force token "a1" to be used and valid a little while
    api._tokens = AuthTokens(access_token="a1", refresh_token="r1", expires_at_epoch=time.time() + 3600)

    vs = await api.fetch_vehicles()  # should trigger 401 -> refresh -> retry
    assert isinstance(vs, list) and vs[0]["id"] == "1"
