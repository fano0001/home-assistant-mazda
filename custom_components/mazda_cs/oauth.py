"""OAuth2 PKCE implementation for Mazda Connected Services (Azure AD B2C)."""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING, Any

import aiohttp

from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.config_entry_oauth2_flow import (
    LocalOAuth2ImplementationWithPkce,
)

if TYPE_CHECKING:
    from homeassistant.core import HomeAssistant

from .const import (
    DOMAIN,
    MOBILE_REDIRECT_URI,
    MSAL_APP_NAME,
    MSAL_APP_VER,
    MSAL_CLIENT_SKU,
    MSAL_CLIENT_VER,
    OAUTH2_AUTH,
    OAUTH2_HOSTS,
    OAUTH2_POLICY,
)

_LOGGER = logging.getLogger(__name__)


def _build_oauth2_url(region: str, endpoint: str) -> str:
    """Build Azure AD B2C OAuth2 URL for a given region and endpoint."""
    host = OAUTH2_HOSTS[region]
    tenant_id = OAUTH2_AUTH[region]["tenant_id"]
    return f"https://{host}/{tenant_id}/{OAUTH2_POLICY}/oauth2/v2.0/{endpoint}"


class MazdaOAuth2Implementation(LocalOAuth2ImplementationWithPkce):
    """Mazda OAuth2 implementation using Azure AD B2C with PKCE."""

    def __init__(self, hass: HomeAssistant, region: str) -> None:
        """Initialize the Mazda OAuth2 implementation."""
        self._region = region
        super().__init__(
            hass,
            domain=DOMAIN,
            client_id=OAUTH2_AUTH[region]["client_id"],
            client_secret="",  # PKCE flow, no client secret needed
            authorize_url=_build_oauth2_url(region, "authorize"),
            token_url=_build_oauth2_url(region, "token"),
        )

    @property
    def name(self) -> str:
        """Return the name of the implementation."""
        return "Mazda Connected Services"

    @property
    def redirect_uri(self) -> str:
        """Return the redirect URI for Mazda mobile app OAuth flow."""
        return MOBILE_REDIRECT_URI

    @property
    def extra_authorize_data(self) -> dict:
        """Extra data for the authorize request."""
        data = {
            "scope": " ".join(OAUTH2_AUTH[self._region]["scopes"]),
            "x-app-name": MSAL_APP_NAME,
            "x-app-ver": MSAL_APP_VER,
            "x-client-SKU": MSAL_CLIENT_SKU,       # "MSAL.Android" (was "MSAL.iOS")
            "x-client-Ver": MSAL_CLIENT_VER,        # "5.4.0" (was "1.6.3")
            "x-client-OS": "34",                    # Android 14 SDK_INT (was "26.2.1" iOS)
            "x-client-DM": "Pixel 9",               # Android device model (was "iPhone")
            "x-client-CPU": "arm64-v8a",            # Android ABI (was "64")
            "haschrome": "1",
            "return-client-request-id": "true",
            "client_info": "1",
        }
        data.update(super().extra_authorize_data)
        return data

    async def async_resolve_external_data(self, external_data: Any) -> dict:
        """Resolve external data to tokens."""
        return await super().async_resolve_external_data(external_data)

    async def async_refresh_token(self, token: dict) -> dict:
        """Refresh tokens, handling B2C which returns text/html on session expiry."""
        session = async_get_clientsession(self.hass)
        refresh_data: dict = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "scope": " ".join(OAUTH2_AUTH[self._region]["scopes"]),
        }
        # Option A: include id_token_hint so B2C can silently re-establish the
        # server-side session without requiring user interaction.  B2C supports
        # this for custom policies that have the id_token_hint technical profile.
        if id_token := token.get("id_token"):
            refresh_data["id_token_hint"] = id_token

        resp = await session.post(
            self.token_url,
            data=refresh_data,
            timeout=aiohttp.ClientTimeout(total=30),
        )

        # Azure AD B2C returns text/html (login page redirect) instead of a JSON
        # error when the underlying session has expired — signal reauthentication.
        if "text/html" in resp.headers.get("Content-Type", ""):
            _LOGGER.warning(
                "B2C returned HTML on token refresh (session expired). "
                "id_token_hint was %s. Triggering reauthentication.",
                "present" if token.get("id_token") else "absent",
            )
            raise ConfigEntryAuthFailed(
                "Mazda session expired, please reauthenticate"
            )

        new_token = await resp.json(content_type=None)
        if "error" in new_token:
            raise ConfigEntryAuthFailed(
                f"Token refresh failed: {new_token.get('error_description', new_token['error'])}"
            )

        new_token["last_saved_at"] = time.time()
        new_token["expires_at"] = time.time() + new_token["expires_in"]
        return new_token
