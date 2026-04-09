"""Config flow for Mazda Connected Services integration."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any

import jwt
import voluptuous as vol
from homeassistant.config_entries import OptionsFlow, SOURCE_REAUTH, ConfigFlowResult
from homeassistant.const import CONF_REGION
from homeassistant.core import callback
from homeassistant.helpers import config_entry_oauth2_flow, selector

from .const import CONF_ENABLE_PUSH, DATA_CLIENT, DATA_COORDINATOR, DOMAIN, MAZDA_REGIONS
from .oauth import MazdaOAuth2Implementation
from .pymazda.client import Client as MazdaAPI

if TYPE_CHECKING:
    from collections.abc import Mapping

# (camelCase response key, lowercase API request key) — settingSaveFlag omitted
# (always sent as 1; not user-facing)
_NOTIFY_ITEMS: list[tuple[str, str]] = [
    ("remoteControlNotify", "remotecontrolnotify"),
    ("openDoorNotify", "opendoornotify"),
    ("unlockDoorNotify", "unlockdoornotify"),
    ("lightHazardNotify", "lighthazardnotify"),
    ("openHoodNotify", "openhoodnotify"),
    ("forgotPlugNotify", "forgotplugnotify"),
    ("powerSaveModeNotify", "powersavemodenotify"),
    ("quickChargeNotify", "quickchargenotify"),
    ("timerChargeNotify", "timerchargenotify"),
    ("fullChargeNotify", "fullchargenotify"),
    ("aftercoolingNotify", "aftercoolingnotify"),
    ("airconTemperatureNotify", "aircontemperaturenotify"),
    ("praiseNotify", "praisenotify"),
]

# Present in getNotifySetting / sent in updateNotifySetting but never shown in the UI.
# Mazda uses these server-side to gate vehicle-level monitoring; the user cannot
# meaningfully change them from the app or this integration.
_VEHICLE_ONLY_KEYS = {
    "quickChargeNotify",
    "timerChargeNotify",
    "fullChargeNotify",
    "aftercoolingNotify",
    "airconTemperatureNotify",
    "praiseNotify",
}

_LOGGER = logging.getLogger(__name__)


class MazdaOAuth2FlowHandler(
    config_entry_oauth2_flow.AbstractOAuth2FlowHandler,
    domain=DOMAIN,
):
    """Handle a config flow for Mazda Connected Services."""

    VERSION = 2
    MINOR_VERSION = 2

    DOMAIN = DOMAIN

    def __init__(self) -> None:
        """Initialize the Mazda config flow."""
        super().__init__()
        self._region: str | None = None
        self._enable_push: bool = True

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
            self._enable_push = user_input.get(CONF_ENABLE_PUSH, False)
            return await self.async_step_pick_implementation()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REGION): vol.In(MAZDA_REGIONS),
                    vol.Optional(CONF_ENABLE_PUSH, default=False): selector.BooleanSelector(),
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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry) -> OptionsFlow:
        """Return the options flow handler."""
        return MazdaOptionsFlowHandler()

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

            # getUserInfo only needs auth + enc keys, not a session ID — 
            # does not need to attach() here.  attach() here may trigger 
            # "multiple devices detected", but needs further evaluation.
            client = MazdaAPI(user_id, self._region, _token_provider)
            user_info = await client.get_user_info()
            await client.close()
            email = user_info.get("userInfo", {}).get("contactMailAddress", "")
            if email:
                title = f"Mazda ({email})"
        except Exception:  # noqa: BLE001
            _LOGGER.debug(
                "Could not fetch account email for title; using user_id fallback"
            )

        return self.async_create_entry(
            title=title,
            data=data,
            options={CONF_ENABLE_PUSH: self._enable_push},
        )


def _applicable_notify_keys(
    notify_raw: dict, vehicle: dict
) -> list[tuple[str, str]]:
    """Return (camel_key, lower_key) pairs applicable to this vehicle."""
    # app checks isSupportRemoteControlForInvitation()
    has_remote = notify_raw.get("remoteControlNotify") is not None
    has_bonnet = vehicle.get("hasBonnet", False)
    has_power_save = notify_raw.get("powerSaveModeNotify") is not None
    is_electric = vehicle.get("isElectric", False)

    result = []
    for camel, lower in _NOTIFY_ITEMS:
        if camel in _VEHICLE_ONLY_KEYS:
            continue
        if camel == "remoteControlNotify" and not has_remote:
            continue
        if camel == "openHoodNotify" and not has_bonnet:
            continue
        if camel == "powerSaveModeNotify" and not has_power_save:
            continue
        if camel == "forgotPlugNotify" and not is_electric:
            continue
        result.append((camel, lower))
    return result


def _vehicle_display_name(vehicle: dict) -> str:
    """Return a human-readable vehicle label."""
    nickname = vehicle.get("nickname", "").strip()
    if nickname:
        return nickname
    year = vehicle.get("modelYear", "")
    model = vehicle.get("carlineName", "")
    return f"{year} {model}".strip() or vehicle.get("vin", "Unknown")


class MazdaOptionsFlowHandler(OptionsFlow):
    """Handle Mazda notification settings via the options flow."""

    def __init__(self) -> None:
        """Initialize."""
        self._vehicle: dict = {}
        self._notify_raw: dict = {}

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Vehicle selector step — skipped automatically for single-vehicle accounts."""
        coordinator = self.hass.data[DOMAIN][self.config_entry.entry_id][DATA_COORDINATOR]
        vehicles = coordinator.data or []

        if not vehicles:
            return self.async_abort(reason="no_vehicles")

        if len(vehicles) == 1:
            self._vehicle = vehicles[0]
            return await self.async_step_notify()

        vehicle_options = {v["vin"]: _vehicle_display_name(v) for v in vehicles}

        if user_input is not None:
            vin = user_input["vin"]
            self._vehicle = next((v for v in vehicles if v["vin"] == vin), vehicles[0])
            return await self.async_step_notify()

        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {vol.Required("vin"): vol.In(vehicle_options)}
            ),
        )

    async def async_step_notify(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Notification toggles step."""
        client = self.hass.data[DOMAIN][self.config_entry.entry_id][DATA_CLIENT]
        vehicle = self._vehicle

        if user_input is None:
            try:
                self._notify_raw = await client.get_notify_setting(vehicle["id"])
            except Exception:  # noqa: BLE001
                return self.async_abort(reason="cannot_connect")

            applicable = _applicable_notify_keys(self._notify_raw, vehicle)
            notify_fields: dict = {
                vol.Optional(camel, default=bool(self._notify_raw.get(camel, 0))): selector.BooleanSelector()
                for camel, _ in applicable
            }
            # Default True regardless of server value (server returns 0 = don't save).
            # Overriding ensures settings persist beyond Mazda's 24-hour reset window.
            notify_fields[
                vol.Optional("settingSaveFlag", default=True)
            ] = selector.BooleanSelector()
            schema = vol.Schema(notify_fields)
            return self.async_show_form(
                step_id="notify",
                data_schema=schema,
                description_placeholders={
                    "vehicle_name": _vehicle_display_name(vehicle)
                },
            )

        # Seed from server state: include every non-null field the API returned.
        # updateNotifySetting is a full-state write; omitting a field that the server
        # returned (even if the UI gates it) may silently reset it server-side.
        settings_dict: dict[str, int] = {
            lower: int(self._notify_raw[camel])
            for camel, lower in _NOTIFY_ITEMS
            if self._notify_raw.get(camel) is not None
        }
        # Override with the user's choices for fields that were shown in the UI.
        applicable = _applicable_notify_keys(self._notify_raw, vehicle)
        for camel, lower in applicable:
            settings_dict[lower] = 1 if user_input.get(camel, False) else 0
        settings_dict["settingsaveflag"] = 1 if user_input.get("settingSaveFlag", True) else 0

        try:
            await client.set_notify_setting(vehicle["id"], settings_dict)
        except Exception:  # noqa: BLE001
            return self.async_abort(reason="cannot_connect")

        # Options storage is Mazda's server — preserve existing entry.options unchanged.
        return self.async_create_entry(data=self.config_entry.options)
