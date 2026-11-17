"""Tests for B2C token-refresh error classification in ``oauth.py``.

Only a confirmed-permanent JSON error (e.g. ``invalid_grant``) may raise
``ConfigEntryAuthFailed`` and start re-authentication; outage-type errors must
take the same transient path as the text/html case so the coordinator retries.
"""

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed

from custom_components.mazda_cs import oauth
from custom_components.mazda_cs.oauth import MazdaOAuth2Implementation


def _b2c_session(body: dict) -> MagicMock:
    """aiohttp.ClientSession stand-in whose POST returns a JSON body."""
    resp = MagicMock(status=400, headers={"Content-Type": "application/json"})
    resp.read = AsyncMock(return_value=json.dumps(body).encode())
    session = MagicMock()
    session.post = AsyncMock(return_value=resp)
    session.__aenter__ = AsyncMock(return_value=session)
    session.__aexit__ = AsyncMock(return_value=False)
    return session


async def _refresh(hass: HomeAssistant, body: dict) -> None:
    impl = MazdaOAuth2Implementation(hass, "MNAO")
    with patch.object(oauth.aiohttp, "ClientSession", return_value=_b2c_session(body)):
        await impl.async_refresh_token({"refresh_token": "r", "last_saved_at": 0})


@pytest.mark.parametrize("error", ["server_error", "temporarily_unavailable"])
async def test_transient_b2c_error_does_not_force_reauth(
    hass: HomeAssistant, error: str
) -> None:
    """A B2C outage must retry on the next cycle, not start re-authentication."""
    with pytest.raises(Exception) as exc_info:  # noqa: PT011
        await _refresh(hass, {"error": error})
    assert not isinstance(exc_info.value, ConfigEntryAuthFailed)


async def test_invalid_grant_forces_reauth(hass: HomeAssistant) -> None:
    """A revoked refresh token is a permanent failure."""
    with pytest.raises(ConfigEntryAuthFailed):
        await _refresh(hass, {"error": "invalid_grant"})
