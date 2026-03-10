"""Config flow for Mazda Connected Services integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import jwt
import voluptuous as vol
from homeassistant.config_entries import SOURCE_REAUTH, ConfigFlowResult
from homeassistant.const import CONF_REGION
from homeassistant.helpers import config_entry_oauth2_flow

from .const import DOMAIN, MAZDA_REGIONS
from .oauth import MazdaOAuth2Implementation
from .pymazda.client import Client as MazdaAPI

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOGGER = logging.getLogger(__name__)


class MazdaOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle a config flow for Mazda Connected Services."""

    VERSION = 2
    MINOR_VERSION = 1

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize the Mazda config flow."""
        super().__init__()
        self._region: str | None = None

    @property
    def logger(self) -> logging.Logger:
        """Return logger."""
        return _LOGGER

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the region selection step."""
        if user_input is not None:
            self._region = user_input[CONF_REGION]
            return await self.async_step_pick_implementation()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REGION): vol.In(MAZDA_REGIONS),
                }
            ),
        )

    async def async_step_pick_implementation(
        self, _: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle picking implementation - directly use our implementation."""
        self.flow_impl = MazdaOAuth2Implementation(self.hass, self._region)
        return await self.async_step_auth()

    # Re-enable after removing migration code — 2027 or later
    # async def async_step_reauth(self, _: Mapping[str, Any]) -> ConfigFlowResult:
    #     """Perform reauth upon an API authentication error."""
    #     return await self.async_step_reauth_confirm()
    
    # Migration workflow from v1→v2: if no token, ask for region
    async def async_step_reauth(self, _: Mapping[str, Any]) -> ConfigFlowResult:
        """Perform reauth upon an API authentication error."""
        reauth_entry = self._get_reauth_entry()
        if not reauth_entry.data.get("token"):
            # v1→v2 migration: no OAuth token yet, region may be wrong or missing
            return await self.async_step_reauth_region()
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_region(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle region confirmation during v1→v2 migration reauth."""
        if user_input is not None:
            self._region = user_input[CONF_REGION]
            return await self.async_step_pick_implementation()

        reauth_entry = self._get_reauth_entry()
        return self.async_show_form(
            step_id="reauth_region",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_REGION,
                        default=reauth_entry.data.get(CONF_REGION, "MNAO"),
                    ): vol.In(MAZDA_REGIONS),
                }
            ),
        )

    async def async_step_reauth_confirm(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Confirm reauth dialog."""
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm")

        reauth_entry = self._get_reauth_entry()
        self._region = reauth_entry.data.get(CONF_REGION, "MNAO")
        return await self.async_step_pick_implementation()

    async def async_oauth_create_entry(self, data: dict[str, Any]) -> ConfigFlowResult:
        """Create an entry for the flow."""
        # Extract user info from access_token JWT
        try:
            access_token = data["token"]["access_token"]
            token_data = jwt.decode(access_token, options={"verify_signature": False})
            user_id = token_data.get("sub", "").lower()
        except (KeyError, ValueError, jwt.DecodeError):
            _LOGGER.exception("Failed to decode access token")
            return self.async_abort(reason="oauth_error")

        if not user_id:
            _LOGGER.error("No sub claim in access token")
            return self.async_abort(reason="oauth_error")

        await self.async_set_unique_id(user_id)

        # Store the region alongside the OAuth data
        data[CONF_REGION] = self._region

        if self.source == SOURCE_REAUTH:
            self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                self._get_reauth_entry(),
                data_updates=data,
            )
        self._abort_if_unique_id_configured()

        # Attempt to fetch the account email address for a friendlier title
        title = f"Mazda ({user_id[:8]})"
        try:
            async def _token_provider():
                return data["token"]["access_token"]

            client = MazdaAPI(user_id, self._region, _token_provider)
            await client.attach()
            user_info = await client.get_user_info()
            await client.close()
            email = user_info.get("userInfo", {}).get("contactMailAddress", "")
            if email:
                title = f"Mazda ({email})"
        except Exception:  # noqa: BLE001
            _LOGGER.debug("Could not fetch account email for title; using user_id fallback")

        return self.async_create_entry(title=title, data=data)
