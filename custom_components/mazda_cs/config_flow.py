"""Config flow for Mazda Connected Services integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import jwt
import voluptuous as vol
from homeassistant.config_entries import (
    SOURCE_REAUTH,
    ConfigEntry,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_REGION
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow, selector
from yarl import URL

from .const import (
    CONF_ENABLE_DEV_SENSORS,
    CONF_ENABLE_PUSH,
    CONF_ENABLE_VEHICLE_IMAGES,
    DOMAIN,
    MAZDA_REGIONS,
)
from .oauth import MazdaOAuth2Implementation
from .pymazda.client import Client as MazdaAPI

if TYPE_CHECKING:
    from collections.abc import Mapping

_LOGGER = logging.getLogger(__name__)

# Options-flow toggles and the value the integration assumes when one is not stored
OPTION_DEFAULTS = {
    CONF_ENABLE_VEHICLE_IMAGES: False,
    CONF_ENABLE_DEV_SENSORS: False,
}

CONF_CALLBACK_URL = "callback_url"

# Translation keys under `config.error` in strings.json
ERROR_AUTHORIZE_REJECTED = "authorize_rejected"
ERROR_INVALID_CALLBACK_URL = "invalid_callback_url"
ERROR_STATE_MISMATCH = "state_mismatch"

STEP_AUTH_MANUAL_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_CALLBACK_URL): selector.TextSelector(
            selector.TextSelectorConfig(type=selector.TextSelectorType.URL)
        )
    }
)


class InvalidCallbackURLError(Exception):
    """Raised when the pasted callback URL cannot be used."""

    def __init__(self, error_key: str) -> None:
        """Initialize with the translation key describing the problem."""
        super().__init__(error_key)
        self.error_key = error_key


class MazdaOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle a config flow for Mazda Connected Services.

    Sign-in starts at a menu with two paths:

    - ``auth``: the stock external step, where the browser extension forwards
      the msauth:// redirect to HA's OAuth callback view, which resumes the flow;
    - ``auth_manual``: the user opens the authorize URL themselves and pastes
      back the msauth:// redirect the browser could not launch.

    They must be separate steps chosen up front: an external step can only
    transition to another external step, so it cannot fall back to a form.
    """

    VERSION = 2
    MINOR_VERSION = 4

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize the Mazda config flow."""
        super().__init__()
        self._region: str | None = None
        self._enable_push: bool = True
        self._authorize_url: str | None = None
        self._expected_state: str | None = None

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MazdaOptionsFlow:
        """Return the options flow (gear icon) handler."""
        return MazdaOptionsFlow()

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
        # Create the implementation once per flow: it holds the PKCE verifier
        # that the token exchange must send, so replacing it after an authorize
        # URL was issued would fail the exchange with invalid_grant.
        if self.flow_impl is None:
            self.flow_impl = MazdaOAuth2Implementation(self.hass, self._region)
        return await self.async_step_pick_method()

    async def async_step_pick_method(
        self, _: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Offer the browser extension or the manual paste sign-in."""
        return self.async_show_menu(
            step_id="pick_method",
            menu_options=["auth", "auth_manual"],
        )

    async def async_step_auth_manual(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Show the authorize URL and accept the pasted msauth:// redirect."""
        if self._authorize_url is None:
            self._authorize_url = await self.async_generate_authorize_url()
            self._expected_state = URL(self._authorize_url).query.get("state")

        errors: dict[str, str] = {}
        if user_input is not None:
            try:
                self.external_data = self._parse_callback_url(
                    user_input[CONF_CALLBACK_URL]
                )
            except InvalidCallbackURLError as err:
                errors["base"] = err.error_key
            else:
                return await self.async_step_creation()

        return self.async_show_form(
            step_id="auth_manual",
            data_schema=STEP_AUTH_MANUAL_SCHEMA,
            description_placeholders={"authorize_url": self._authorize_url},
            errors=errors,
        )

    def _parse_callback_url(self, raw_url: str) -> dict[str, Any]:
        """Turn the pasted msauth:// redirect into OAuth2 external data.

        Returns a mapping shaped like the one the OAuth callback view hands the
        flow: the authorization code plus the decoded state.

        Raises:
            InvalidCallbackURLError: If the URL is unusable, carries an
                authorization error, lacks a code, or does not match the state
                issued for this flow.

        """
        try:
            query = URL(raw_url.strip()).query
        except ValueError as err:
            raise InvalidCallbackURLError(ERROR_INVALID_CALLBACK_URL) from err

        if "error" in query:
            raise InvalidCallbackURLError(ERROR_AUTHORIZE_REJECTED)

        if not (code := query.get("code")):
            raise InvalidCallbackURLError(ERROR_INVALID_CALLBACK_URL)

        if not self._expected_state or query.get("state") != self._expected_state:
            raise InvalidCallbackURLError(ERROR_STATE_MISMATCH)

        return {
            "code": code,
            "state": {
                "flow_id": self.flow_id,
                "redirect_uri": self.flow_impl.redirect_uri,
            },
        }

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
                        CONF_REGION, default=reauth_entry.data[CONF_REGION]
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
        self._region = reauth_entry.data[CONF_REGION]
        return await self.async_step_pick_implementation()

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Allow changing the push notification preference without re-authenticating."""
        entry = self._get_reconfigure_entry()

        if user_input is not None:
            self.hass.config_entries.async_update_entry(
                entry,
                options={**entry.options, CONF_ENABLE_PUSH: user_input[CONF_ENABLE_PUSH]},
            )
            return self.async_update_reload_and_abort(entry)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=vol.Schema(
                {
                    vol.Optional(
                        CONF_ENABLE_PUSH,
                        default=entry.options.get(CONF_ENABLE_PUSH, False),
                    ): selector.BooleanSelector(),
                }
            ),
        )

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
            reauth_entry = self._get_reauth_entry()
            is_v1_migration = not reauth_entry.data.get("token")
            if not is_v1_migration:
                self._abort_if_unique_id_mismatch(reason="wrong_account")
            return self.async_update_reload_and_abort(
                reauth_entry,
                unique_id=user_id,
                data_updates=data,
            )
        self._abort_if_unique_id_configured()

        # Attempt to fetch the account email address for a friendlier title
        title = f"Mazda ({user_id[:8]})"
        try:

            async def _token_provider():
                return data["token"]["access_token"]

            # getUserInfo only needs auth + enc keys, not a session ID — 
            # does not need to attach() here.  attach() here may trigger 
            # "multiple devices detected", but needs further evaluation.
            client = MazdaAPI(user_id, self._region, _token_provider)
            user_info = await client.get_user_info()
            await client.close()
            email = user_info.get("userInfo", {}).get("contactMailAddress", "")
            if email:
                title = f"Mazda ({email})"
            cust_id = user_info.get("custId", "")
            if cust_id:
                data["conductor_customer_id"] = cust_id
            usher_id = user_info.get("usherId", "")
            if usher_id:
                data["conductor_usher_id"] = usher_id
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Could not fetch account email for title; using user_id fallback"
            )

        # non-MNAO regions use internalUserId (partner2Id) for Conductor userId
        if self._region != "MNAO":
            try:
                client = MazdaAPI(user_id, self._region, _token_provider)
                cv_ids = await client.get_cv_user_ids()
                await client.close()
                internal_user_id = str(
                    cv_ids.get("data", {}).get("customerInfo", {}).get("internalUserId", "")
                )
                if internal_user_id:
                    data["conductor_internal_id"] = internal_user_id
            except Exception:  # noqa: BLE001
                _LOGGER.debug("Could not fetch internalUserId for non-MNAO region")

        return self.async_create_entry(
            title=title,
            data=data,
            options={CONF_ENABLE_PUSH: self._enable_push},
        )


class MazdaOptionsFlow(OptionsFlow):
    """Handle the options flow for Mazda Connected Services."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Toggle the optional entity groups."""
        entry = self.config_entry

        if user_input is not None:
            options = {**entry.options, **user_input}
            # Both flags change which entities exist, so the entry has to reload.
            # Store the options first so the reload sees them, and skip the reload
            # (and its re-attach) when no effective value changed. Compare with
            # defaults filled in: a first save only writes keys that were missing.
            if _effective_options(options) != _effective_options(entry.options):
                self.hass.config_entries.async_update_entry(entry, options=options)
                self.hass.config_entries.async_schedule_reload(entry.entry_id)
            return self.async_create_entry(data=options)

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Optional(key, default=value): selector.BooleanSelector()
                    for key, value in _effective_options(entry.options).items()
                }
            ),
        )


def _effective_options(options: Mapping[str, Any]) -> dict[str, Any]:
    """Return the options-flow toggles as the integration sees them."""
    return {key: options.get(key, default) for key, default in OPTION_DEFAULTS.items()}
