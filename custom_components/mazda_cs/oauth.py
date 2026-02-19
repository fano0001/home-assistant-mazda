"""OAuth2 PKCE implementation for Mazda Connected Services (Azure AD B2C)."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

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
    OAUTH2_CLIENT_ID,
    OAUTH2_HOSTS,
    OAUTH2_POLICY,
    OAUTH2_SCOPES,
    OAUTH2_TENANT,
)

_LOGGER = logging.getLogger(__name__)


def _build_oauth2_url(region: str, endpoint: str) -> str:
    """Build Azure AD B2C OAuth2 URL for a given region and endpoint."""
    host = OAUTH2_HOSTS[region]
    return f"https://{host}/{OAUTH2_TENANT}/{OAUTH2_POLICY}/oauth2/v2.0/{endpoint}"


class MazdaOAuth2Implementation(LocalOAuth2ImplementationWithPkce):
    """Mazda OAuth2 implementation using Azure AD B2C with PKCE."""

    def __init__(self, hass: HomeAssistant, region: str) -> None:
        """Initialize the Mazda OAuth2 implementation."""
        self._region = region
        super().__init__(
            hass,
            domain=DOMAIN,
            client_id=OAUTH2_CLIENT_ID,
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
            "scope": " ".join(OAUTH2_SCOPES),
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
        """Refresh tokens."""
        return await super().async_refresh_token(token)
