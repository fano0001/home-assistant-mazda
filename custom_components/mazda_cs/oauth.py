"""OAuth2 PKCE implementation for Mazda Connected Services (Azure AD B2C)."""

from __future__ import annotations

import json
import logging
import socket
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
            **({"country": "CA", "email_domain_restrict": "mci", "international_phone_code_list": "mci"} if self._region == "MCI" else {}),
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
        # Do NOT call super().extra_authorize_data — that generates a PKCE
        # code_challenge which Azure B2C would then require in the token exchange.
        # The token exchange is performed by the Chrome extension in the browser
        # (to bypass WAF/TLS fingerprinting), so no code_verifier is available
        # server-side. Plain auth code flow works for Mazda's B2C app registration.
        return data

    async def async_resolve_external_data(self, external_data: Any) -> dict:
        """Return tokens — either pre-exchanged by the browser extension or via server-side exchange."""
        import base64

        code = external_data.get("code", "")

        # The Chrome extension performs the token exchange in the browser to bypass
        # Azure Front Door WAF (which blocks Python's TLS fingerprint / JA3 signature).
        # It encodes the full token JSON as base64url and prefixes it with "MZDPRE_".
        if code.startswith("MZDPRE_"):
            _LOGGER.debug("Mazda token: received pre-exchanged token from browser extension")
            try:
                token_json = base64.urlsafe_b64decode(code[len("MZDPRE_"):] + "==")
                new_token = json.loads(token_json)
            except Exception as exc:
                raise ConfigEntryAuthFailed(
                    f"Failed to decode pre-exchanged token: {exc}"
                ) from exc

            if "error" in new_token:
                raise ConfigEntryAuthFailed(
                    f"Token exchange failed: {new_token.get('error_description', new_token['error'])}"
                )

            new_token["last_saved_at"] = time.time()
            new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
            _LOGGER.debug(
                "Pre-exchanged token accepted — expires_in=%s has_refresh_token=%s",
                new_token.get("expires_in"),
                bool(new_token.get("refresh_token")),
            )
            return new_token

        # Fallback: server-side exchange (will be blocked by WAF for eu.id.mazda.com,
        # kept here for debugging and non-EU regions that may not have WAF restrictions).
        _LOGGER.warning(
            "Mazda token exchange: falling back to server-side exchange — "
            "this will fail for EU region due to WAF. Install the Chrome extension."
        )
        token_data: dict = {
            "client_id": self.client_id,
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "scope": " ".join(OAUTH2_AUTH[self._region]["scopes"]),
        }
        msal_headers = {
            "x-client-SKU": MSAL_CLIENT_SKU,
            "x-client-Ver": MSAL_CLIENT_VER,
            "x-client-OS": "34",
            "x-client-DM": "Pixel 9",
            "x-client-CPU": "arm64-v8a",
            "x-app-name": MSAL_APP_NAME,
            "x-app-ver": MSAL_APP_VER,
            "client-request-id": str(uuid.uuid4()),
            "return-client-request-id": "true",
            "Accept": "application/json",
        }
        try:
            connector = aiohttp.TCPConnector(family=socket.AF_INET)
            async with aiohttp.ClientSession(connector=connector) as session:
                resp = await session.post(
                    self.token_url,
                    data=token_data,
                    headers=msal_headers,
                    timeout=aiohttp.ClientTimeout(connect=5, total=12),
                )
                content_type = resp.headers.get("Content-Type", "")
                body = await resp.read()
        except Exception as exc:
            raise Exception(
                f"Server-side token exchange failed ({type(exc).__name__}): {exc}"
            ) from exc

        if resp.status >= 400 or not body or "html" in content_type.lower():
            raise Exception(
                f"Server-side token exchange HTTP {resp.status} ({content_type}): "
                f"{body[:100].decode(errors='replace')}"
            )

        new_token = json.loads(body)
        if "error" in new_token:
            raise ConfigEntryAuthFailed(
                f"Token exchange failed: {new_token.get('error_description', new_token['error'])}"
            )
        new_token["last_saved_at"] = time.time()
        new_token["expires_at"] = time.time() + new_token.get("expires_in", 3600)
        return new_token

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

        msal_headers = {
            "x-client-SKU": MSAL_CLIENT_SKU,
            "x-client-Ver": MSAL_CLIENT_VER,
            "x-client-OS": "34",
            "x-client-DM": "Pixel 9",
            "x-client-CPU": "arm64-v8a",
            "x-app-name": MSAL_APP_NAME,
            "x-app-ver": MSAL_APP_VER,
            "client-request-id": str(uuid.uuid4()),
            "return-client-request-id": "true",
            "Accept": "application/json",
        }

        try:
            from .pymazda.connection import ssl_context as mazda_ssl_ctx
        except Exception:
            mazda_ssl_ctx = None

        scope_url = OAUTH2_AUTH[self._region]["scopes"][0]
        b2c_host = scope_url.split("/")[2]
        b2c_name = b2c_host.split(".")[0]
        fallback_token_url = (
            f"https://{b2c_name}.b2clogin.com/{b2c_host}/{OAUTH2_POLICY}/oauth2/v2.0/token"
        )

        urls_to_try = [(self.token_url, mazda_ssl_ctx), (fallback_token_url, None)]
        resp = None
        content_type = ""
        body = b""
        last_exc: Exception | None = None

        for token_url, ssl_ctx in urls_to_try:
            _LOGGER.debug(
                "Token refresh attempt — url=%s has_mazda_ssl=%s",
                token_url, ssl_ctx is not None,
            )
            try:
                connector = aiohttp.TCPConnector(family=socket.AF_INET)
                async with aiohttp.ClientSession(connector=connector) as session:
                    resp = await session.post(
                        token_url,
                        data=refresh_data,
                        headers=msal_headers,
                        ssl=ssl_ctx,
                        timeout=aiohttp.ClientTimeout(connect=5, total=30),
                    )
                    content_type = resp.headers.get("Content-Type", "")
                    body = await resp.read()
                _LOGGER.debug(
                    "Token refresh response — url=%s status=%s Content-Type=%s",
                    token_url, resp.status, content_type,
                )
                last_exc = None
                break
            except Exception as exc:
                _LOGGER.warning(
                    "Token refresh FAILED — url=%s type=%s msg=%s",
                    token_url, type(exc).__name__, exc,
                )
                last_exc = exc

        if last_exc is not None:
            raise last_exc

        # Azure AD B2C transiently returns non-JSON (e.g. HTML, plain text) during
        # service hiccups. This is NOT a permanent auth failure — raise a regular
        # exception so the coordinator retries on the next update cycle.
        # ConfigEntryAuthFailed is reserved for confirmed permanent failures (JSON error).
        if resp is not None and resp.status >= 400:
            _LOGGER.warning(
                "B2C token refresh HTTP error — status=%s body=%s",
                resp.status, body[:200],
            )
            raise Exception(f"B2C token refresh HTTP {resp.status}: {body[:100].decode(errors='replace')}")

        if not body or "html" in content_type.lower():
            _LOGGER.warning(
                "B2C returned non-JSON on token refresh (token_age=%.1f min) — "
                "content_type=%s. Treating as transient — will retry on next update cycle.",
                token_age_min if token_age_min is not None else -1,
                content_type,
            )
            raise Exception(
                f"B2C token refresh non-JSON response ({content_type}): "
                f"{body[:100].decode(errors='replace')}"
            )

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
