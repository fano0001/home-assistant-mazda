"""Tests for the B2C token requests in ``oauth.py`` (issue #69).

Mazda's edge blocks the default Home Assistant and aiohttp User-Agents in some
regions, so both the code exchange and the refresh must send the app's headers.
"""

import logging
from collections.abc import AsyncGenerator
from typing import Any

import aiohttp
import pytest
from aiohttp import web
from aiohttp.test_utils import TestServer
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.mazda_cs.oauth import (
    MSAL_CLIENT_PARAMS,
    MazdaOAuth2Implementation,
)
from custom_components.mazda_cs.pymazda.const import USER_AGENT_DALVIK

TOKEN = {"access_token": "a2", "refresh_token": "r2", "expires_in": 7200}
EDGE_BLOCK = {
    "status": 403,
    "content_type": "text/html",
    "text": "<HTML><TITLE>Access Denied</TITLE></HTML>",
}


class FakeB2C:
    """Token endpoint that records each request and returns ``reply``."""

    def __init__(self) -> None:
        """Start with a successful reply."""
        self.reply: Any = TOKEN
        self.requests: list[tuple[dict, dict]] = []
        self.url = ""

    async def handle(self, request: web.Request) -> web.Response:
        """Record the request and answer it."""
        self.requests.append((dict(request.headers), dict(await request.post())))
        if "access_token" in self.reply:
            return web.json_response(self.reply)
        return web.Response(**self.reply)


@pytest.fixture
async def b2c(socket_enabled: None) -> AsyncGenerator[FakeB2C]:
    """Run a fake token endpoint."""
    fake = FakeB2C()
    app = web.Application()
    app.router.add_post("/token", fake.handle)
    server = TestServer(app)
    await server.start_server()
    fake.url = str(server.make_url("/token"))
    yield fake
    await server.close()


def _impl(hass: HomeAssistant, b2c: FakeB2C) -> MazdaOAuth2Implementation:
    impl = MazdaOAuth2Implementation(hass, "MME")
    impl.token_url = b2c.url
    return impl


async def _exchange(impl: MazdaOAuth2Implementation) -> dict:
    return await impl.async_resolve_external_data(
        {"code": "c", "state": {"redirect_uri": impl.redirect_uri}}
    )


async def _refresh(impl: MazdaOAuth2Implementation) -> dict:
    return await impl.async_refresh_token(
        {"access_token": "a", "refresh_token": "r", "last_saved_at": 0}
    )


@pytest.mark.parametrize("call", [_exchange, _refresh])
async def test_token_requests_send_app_headers(
    hass: HomeAssistant, b2c: FakeB2C, call: Any
) -> None:
    """Exchange and refresh identify themselves as the app does."""
    result = await call(_impl(hass, b2c))

    assert result["access_token"] == "a2"
    headers, _ = b2c.requests[0]
    assert headers["User-Agent"] == USER_AGENT_DALVIK
    assert headers["client-request-id"]
    assert {key: headers[key] for key in MSAL_CLIENT_PARAMS} == MSAL_CLIENT_PARAMS


async def test_exchange_sends_pkce_request(hass: HomeAssistant, b2c: FakeB2C) -> None:
    """The exchange sends the code and the PKCE verifier."""
    impl = _impl(hass, b2c)
    await _exchange(impl)

    _, form = b2c.requests[0]
    assert form == {
        "grant_type": "authorization_code",
        "code": "c",
        "redirect_uri": impl.redirect_uri,
        "client_id": impl.client_id,
        "code_verifier": impl.extra_token_resolve_data["code_verifier"],
    }


async def test_exchange_error_is_raised_and_logged(
    hass: HomeAssistant, b2c: FakeB2C, caplog: pytest.LogCaptureFixture
) -> None:
    """A rejected exchange raises an error HA's config flow handles."""
    b2c.reply = EDGE_BLOCK
    with pytest.raises(aiohttp.ClientResponseError) as exc_info:
        await _exchange(_impl(hass, b2c))

    assert exc_info.value.status == 403
    assert "status=403" in caplog.text
    assert "Access Denied" in caplog.text


async def test_exchange_html_success_is_a_client_error(
    hass: HomeAssistant, b2c: FakeB2C
) -> None:
    """HTML with a 200 status is also an error HA's config flow handles."""
    b2c.reply = {"status": 200, "content_type": "text/html", "text": "<html></html>"}
    with pytest.raises(aiohttp.ClientError):
        await _exchange(_impl(hass, b2c))


@pytest.mark.parametrize(
    ("status", "message"),
    [(403, "blocked the token refresh (HTTP 403"), (200, "status=200")],
)
async def test_refresh_html_retries_without_reauth(
    hass: HomeAssistant,
    b2c: FakeB2C,
    caplog: pytest.LogCaptureFixture,
    status: int,
    message: str,
) -> None:
    """HTML never starts re-authentication, and the log shows which case it was."""
    b2c.reply = {**EDGE_BLOCK, "status": status}
    with caplog.at_level(logging.WARNING), pytest.raises(Exception) as exc_info:  # noqa: PT011
        await _refresh(_impl(hass, b2c))

    assert not isinstance(exc_info.value, ConfigEntryAuthFailed)
    assert message in caplog.text
