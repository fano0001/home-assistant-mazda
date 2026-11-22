"""API auth bridge for Mazda Connected Services bound to Home Assistant OAuth."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from homeassistant.helpers.config_entry_oauth2_flow import OAuth2Session

_LOGGER = logging.getLogger(__name__)


class MazdaAuth:
    """Provide Mazda authentication tied to an OAuth2 based config entry."""

    def __init__(self, oauth_session: OAuth2Session) -> None:
        """Initialize Mazda auth."""
        self._oauth_session = oauth_session
        self._logged_expires_at: float | None = None

    async def async_get_access_token(self) -> str:
        """Return a valid access token.

        Called before every Mazda API request, so the token state is logged
        only when the token changes (first use or after a refresh).
        """
        await self._oauth_session.async_ensure_token_valid()
        token = self._oauth_session.token
        if token.get("expires_at") == self._logged_expires_at:
            return token["access_token"]
        self._logged_expires_at = token.get("expires_at")
        _LOGGER.debug(
            "Token state: expires_in=%s, token_type=%s, has_access_token=%s, has_refresh_token=%s, has_id_token=%s",
            token.get("expires_in"),
            token.get("token_type"),
            bool(token.get("access_token")),
            bool(token.get("refresh_token")),
            bool(token.get("id_token")),
        )
        return token["access_token"]
