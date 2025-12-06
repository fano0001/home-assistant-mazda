# tests/conftest.py
import pytest
from aiohttp import web

print(">>> USING custom tests/conftest.py <<<")

AUTHORIZE_PATH = "/432b587f-88ad-40aa-9e5d-e6bcf9429e8d/b2c_1a_signin/oauth2/v2.0/authorize"
TOKEN_PATH = "/432b587f-88ad-40aa-9e5d-e6bcf9429e8d/b2c_1a_signin/oauth2/v2.0/token"
SELF_ASSERTED_PATH = "/432b587f-88ad-40aa-9e5d-e6bcf9429e8d/B2C_1A_signin/SelfAsserted"
CONFIRM_PATH = "/432b587f-88ad-40aa-9e5d-e6bcf9429e8d/api/CombinedSigninAndSignup/confirmed"
API_BASE = "/connectedservices/v2"


def _build_app() -> web.Application:
    app = web.Application()
    app["custom_get"] = {}  # für nachträglich registrierte GET-Routen

    async def authorize(request: web.Request) -> web.StreamResponse:
        q = request.rel_url.query
        # Silent authorize -> IMMER 302 mit Code zurückgeben
        if "prompt" in q:  # prompt=none (ggf. zusätzlich tx)
            raise web.HTTPFound(location="/cb?code=test_code")
        # Erster Aufruf ohne prompt: HTML mit tx-Anker, damit der Client tx extrahiert
        return web.Response(
            text='<html><a href="?tx=StateProperties=abc"></a></html>',
            content_type="text/html",
        )

    async def self_asserted(request: web.Request) -> web.Response:
        return web.Response(text="{}", content_type="application/json")

    async def confirm(request: web.Request) -> web.Response:
        return web.Response(text="{}", content_type="application/json")

    async def token(request: web.Request) -> web.Response:
        return web.json_response(
            {
                "access_token": "AT_ok",
                "refresh_token": "RT_ok",
                "expires_in": 3600,
                "token_type": "Bearer",
            }
        )

    # Basisrouten normal registrieren
    app.router.add_get(AUTHORIZE_PATH, authorize)
    app.router.add_post(SELF_ASSERTED_PATH, self_asserted)
    app.router.add_post(CONFIRM_PATH, confirm)
    app.router.add_post(TOKEN_PATH, token)

    # Catch-All Dispatcher:
    # - bedient nachträglich "registrierte" Routen aus app["custom_get"]
    # - liefert Defaults für die API
    async def api_dispatch(request: web.Request) -> web.Response:
        path = request.rel_url.path

        # Nachträglich via add_get "registrierte" Routen bedienen
        if request.method == "GET" and path in app["custom_get"]:
            # Handler aus dem Test aufrufen (z.B. um 401->200 zu simulieren)
            return await app["custom_get"][path](request)

        # Defaults
        if request.method == "GET" and path == f"{API_BASE}/vehicles":
            return web.json_response([{"vin": "JMZTEST", "id": "1"}])

        if request.method == "POST" and path.startswith(API_BASE):
            return web.json_response({"status": "ok"})

        if request.method == "GET" and path.startswith(API_BASE):
            return web.json_response({})

        return web.Response(status=404, text="not found")

    # Catch-All ganz zuletzt
    app.router.add_route("*", "/{tail:.*}", api_dispatch)

    # Router-Patch: erlaubt dem Test nach Start des Servers noch "add_get" aufzurufen
    # Wir registrieren nicht wirklich im aiohttp-Router, sondern merken den Handler
    def _lazy_add_get(path, handler, *args, **kwargs):
        app["custom_get"][path] = handler

        class _Dummy:
            def __init__(self, p):
                self.path = p

        return _Dummy(path)

    app.router.add_get = _lazy_add_get  # type: ignore[assignment]

    return app


@pytest.fixture
async def test_server(aiohttp_server):
    return await aiohttp_server(_build_app())


@pytest.fixture
async def server(aiohttp_server):
    return await aiohttp_server(_build_app())
