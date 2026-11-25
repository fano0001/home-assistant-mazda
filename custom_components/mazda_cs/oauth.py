"""OAuth2 PKCE implementation for Mazda Connected Services (Azure AD B2C)."""

from __future__ import annotations

import json
import logging
import time
import uuid
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
    OAUTH2_AUTH,
    OAUTH2_HOSTS,
    OAUTH2_POLICY,
    PHONE_NUMBER_LENGTHS,
)
from .locales import resolve_locale
from .pymazda.const import (
    ANDROID_SDK,
    APP_PACKAGE_ID,
    APP_VERSION,
    DEVICE_ABI,
    DEVICE_MODEL,
    MSAL_CLIENT_SKU,
    MSAL_CLIENT_VER,
    USER_AGENT_DALVIK,
)

_LOGGER = logging.getLogger(__name__)

# MSAL sends these as headers on token requests (OAuth2Strategy.performTokenRequest
# in the APK). When authorizing it sends x-client-* as query parameters and x-app-*
# as headers; a browser link cannot set headers, so we send all of them as
# parameters. x-app-name is the package name (CommandParametersAdapter).
MSAL_CLIENT_PARAMS = {
    "x-app-name": APP_PACKAGE_ID,
    "x-app-ver": APP_VERSION,
    "x-client-SKU": MSAL_CLIENT_SKU,
    "x-client-Ver": MSAL_CLIENT_VER,
    "x-client-OS": ANDROID_SDK,
    "x-client-DM": DEVICE_MODEL,
    "x-client-CPU": DEVICE_ABI,
}


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
        locale = resolve_locale(
            self._region,
            self.hass.config.language,
            self.hass.config.country,
        )
        phone_min, phone_max = PHONE_NUMBER_LENGTHS[self._region]
        data = {
            "scope": " ".join(OAUTH2_AUTH[self._region]["scopes"]),
            "ui_locales": locale.ui_locale,
            "country": locale.country,
            "default_international_phone_code": locale.country,
            "email_domain_restrict": "mci" if self._region == "MCI" else "none",
            "international_phone_code_list": self._region.lower(),
            "phone_number_min_length": str(phone_min),
            "phone_number_max_length": str(phone_max),
            "email_verify_flg": "true",
            "login_user_restrict": "true",
            **MSAL_CLIENT_PARAMS,
            "haschrome": "1",
            "return-client-request-id": "true",
            "client_info": "1",
        }
        data.update(super().extra_authorize_data)
        return data

    async def async_resolve_external_data(self, external_data: Any) -> dict:
        """Resolve external data to tokens."""
        return await super().async_resolve_external_data(external_data)

    async def _post_token(self, data: dict) -> tuple[aiohttp.ClientResponse, bytes]:
        """POST to the token endpoint with the headers the app sends."""
        # Mazda's edge (Akamai) answers the default Home Assistant and aiohttp
        # User-Agents with a 403 HTML page on the EU sign-in host (issue #69).
        headers = {
            "User-Agent": USER_AGENT_DALVIK,
            "client-request-id": str(uuid.uuid4()),
            **MSAL_CLIENT_PARAMS,
        }
        # Use a fresh ClientSession (not the shared HA session) to avoid stale
        # persistent connections to B2C which cause repeated HTML responses.
        async with aiohttp.ClientSession() as session:
            resp = await session.post(
                self.token_url,
                data=data,
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=30),
            )
            return resp, await resp.read()

    async def _token_request(self, data: dict) -> dict:
        """Exchange the authorization code for tokens.

        Replaces HA's version, which cannot send custom headers. Refreshes do
        not come through here; see async_refresh_token. HA's config flow
        handles the aiohttp errors raised here.
        """
        resp, body = await self._post_token({**data, "client_id": self.client_id})
        if resp.status >= 400:
            _LOGGER.warning(
                "Token exchange failed — region=%s status=%s body=%s",
                self._region,
                resp.status,
                " ".join(body.decode(errors="replace").split())[:200],
            )
        resp.raise_for_status()
        return await resp.json()

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

        refresh_data: dict = {
            "client_id": self.client_id,
            "grant_type": "refresh_token",
            "refresh_token": token["refresh_token"],
            "scope": " ".join(OAUTH2_AUTH[self._region]["scopes"]),
        }

        resp, body = await self._post_token(refresh_data)
        content_type = resp.headers.get("Content-Type", "")
        _LOGGER.debug(
            "Token refresh response — status=%s Content-Type=%s",
            resp.status,
            content_type,
        )

        # Azure AD B2C transiently returns text/html instead of JSON (e.g. during
        # service hiccups). This is NOT a permanent auth failure — raise a regular
        # exception so the coordinator retries on the next update cycle.
        # ConfigEntryAuthFailed is reserved for confirmed permanent failures (JSON error).
        if "text/html" in content_type:
            # A 403 page comes from Mazda's edge, before the request reaches B2C.
            # It says nothing about the refresh token, so it also just retries.
            if resp.status == 403:
                _LOGGER.warning(
                    "Mazda's sign-in server blocked the token refresh "
                    "(HTTP 403, region=%s). Will retry on next update cycle.",
                    self._region,
                )
                raise Exception(
                    "Mazda's sign-in server blocked the token refresh (HTTP 403) — will retry"
                )
            _LOGGER.warning(
                "B2C returned HTML on token refresh (status=%s token_age=%.1f min). "
                "Treating as transient — will retry on next update cycle.",
                resp.status,
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
            # Azure AD B2C returns these for outages on the token endpoint
            # (RFC 6749 defines them for the authorization endpoint, §4.1.2.1;
            # Microsoft documents temporarily_unavailable for /token as
            # "retry after a small delay"). Same retry path as the HTML case.
            if new_token["error"] in ("server_error", "temporarily_unavailable"):
                raise Exception(
                    f"B2C token refresh failed transiently ({new_token['error']}) — will retry"
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
        # Like HA's own refresh: a response may leave out the refresh token.
        return {**token, **new_token}
