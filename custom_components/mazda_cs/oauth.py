"""OAuth2 PKCE implementation for Mazda Connected Services (Azure AD B2C)."""

from __future__ import annotations

import json
import logging
import time
from typing import TYPE_CHECKING, Any

import aiohttp

from homeassistant.exceptions import ConfigEntryAuthFailed
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
            "ui_locales": self.hass.config.language,
            **({"email_domain_restrict": "mci"} if self._region == "MCI" else {}),
            "x-app-name": MSAL_APP_NAME,
            "x-app-ver": MSAL_APP_VER,
            "x-client-SKU": MSAL_CLIENT_SKU,
            "x-client-Ver": MSAL_CLIENT_VER,
            "x-client-OS": "34",                    # Android SDK_INT 
            "x-client-DM": "Pixel 9",               # Android device model
            "x-client-CPU": "arm64-v8a",            # Android ABI
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
        issued_at = token.get("last_saved_at", 0)
        token_age_min = (time.time() - issued_at) / 60 if issued_at else None
        _LOGGER.debug(
            "Token refresh attempt — region=%s token_age=%.1f min has_refresh_token=%s",
            self._region,
            token_age_min if token_age_min is not None else -1,
            bool(token.get("refresh_token")),
        )

        # Use a fresh ClientSession (not the shared HA session) to avoid stale
        # persistent connections to B2C which cause repeated HTML responses.
        refresh_data: dict = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "scope": " ".join(OAUTH2_AUTH[self._region]["scopes"]),
        }

        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                self.token_url,
                data=refresh_data,
                timeout=aiohttp.ClientTimeout(total=30),
            )
            content_type = resp.headers.get("Content-Type", "")
            _LOGGER.debug(
                "Token refresh response — status=%s Content-Type=%s",
                resp.status,
                content_type,
            )
            body = await resp.read()

        # Azure AD B2C transiently returns text/html instead of JSON (e.g. during
        # service hiccups). This is NOT a permanent auth failure — raise a regular
        # exception so the coordinator retries on the next update cycle.
        # ConfigEntryAuthFailed is reserved for confirmed permanent failures (JSON error).
        if "text/html" in content_type:
            _LOGGER.warning(
                "B2C returned HTML on token refresh (token_age=%.1f min). "
                "Treating as transient — will retry on next update cycle.",
                token_age_min if token_age_min is not None else -1,
            )
            raise Exception("B2C token refresh returned HTML — transient, will retry")

        new_token = json.loads(body)
        if "error" in new_token:
            _LOGGER.warning(
                "Token refresh JSON error — error=%s description=%s",
                new_token.get("error"),
                new_token.get("error_description", ""),
            )
            raise ConfigEntryAuthFailed(
                f"Token refresh failed: {new_token.get('error_description', new_token['error'])}"
            )

        new_token["last_saved_at"] = time.time()
        new_token["expires_at"] = time.time() + new_token["expires_in"]
        _LOGGER.debug(
            "Token refresh SUCCESS — new expires_in=%s new_has_refresh_token=%s",
            new_token.get("expires_in"),
            bool(new_token.get("refresh_token")),
        )
        return new_token
