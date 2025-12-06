from __future__ import annotations

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.config_entries import ConfigFlowResult, OptionsFlow
from homeassistant.helpers.selector import selector

# Try to re-use constants from the integration if available, otherwise define fallbacks
try:  # type: ignore
    from .const import (
        DOMAIN as _DOMAIN,
        CONF_EMAIL as _CONF_EMAIL,
        CONF_PASSWORD as _CONF_PASSWORD,
        CONF_REGION as _CONF_REGION,
    )
except Exception:  # pragma: no cover - fallback for standalone usage
    _DOMAIN = "mazda_cs"
    _CONF_EMAIL = "email"
    _CONF_PASSWORD = "password"
    _CONF_REGION = "region"

# Human-readable labels shown in UI; stored value remains the Mazda code
REGION_LABELS = {
    "MME": "Europa",
    "MNA": "Nordamerika",
    "MJP": "Japan",
}
REGION_OPTIONS = [
    {"value": code, "label": label} for code, label in REGION_LABELS.items()
]


DOMAIN = _DOMAIN
CONF_EMAIL = _CONF_EMAIL
CONF_PASSWORD = _CONF_PASSWORD
CONF_REGION = _CONF_REGION


# Human-friendly labels mapped to API region codes
# Only the labels are shown to the user; the stored value is the Mazda backend code.
REGION_SELECT_OPTIONS = [
    {"label": "Europa", "value": "MME"},
    {"label": "Nordamerika", "value": "MNA"},
    {"label": "Japan", "value": "MJP"},
]


def _user_schema(defaults: dict | None = None) -> vol.Schema:
    defaults = defaults or {}
    return vol.Schema(
        {
            vol.Required(CONF_EMAIL, default=defaults.get(CONF_EMAIL, "")): str,
            vol.Required(CONF_PASSWORD, default=defaults.get(CONF_PASSWORD, "")): str,
            vol.Required(
                CONF_REGION, default=defaults.get(CONF_REGION, "MME")
            ): selector(
                {
                    "select": {
                        "options": REGION_SELECT_OPTIONS,
                        "mode": "dropdown",
                        "translation_key": "region",
                    }
                }
            ),
        }
    )


class MazdaConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Mazda Connected Services (Custom)."""

    VERSION = 1

    async def async_step_user(self, user_input: dict | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=_user_schema())

        # unique id per email+region so the same account can exist for multiple regions if needed
        await self.async_set_unique_id(
            f"{user_input[CONF_EMAIL].lower()}::{user_input[CONF_REGION]}"
        )
        self._abort_if_unique_id_configured()

        return self.async_create_entry(
            title=f"Mazda CS ({_label_for_region(user_input[CONF_REGION])})",
            data={
                CONF_EMAIL: user_input[CONF_EMAIL],
                CONF_PASSWORD: user_input[CONF_PASSWORD],
                CONF_REGION: user_input[
                    CONF_REGION
                ],  # stored value is still the code (MME/MNA/MJP)
            },
        )

    @callback
    def async_get_options_flow(self, config_entry):
        return MazdaOptionsFlowHandler(config_entry)


class MazdaOptionsFlowHandler(config_entries.OptionsFlow):
    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict | None = None) -> ConfigFlowResult:
        """Manage the options for the integration. Currently only exposes region with friendly label."""
        if user_input is not None:
            # Keep storing the region code but display the friendly label in the UI
            return self.async_create_entry(title="", data=user_input)

        defaults = {
            CONF_REGION: self.config_entry.data.get(CONF_REGION, "MME"),
        }
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(CONF_REGION, default=defaults[CONF_REGION]): selector(
                        {
                            "select": {
                                "options": REGION_SELECT_OPTIONS,
                                "mode": "dropdown",
                                "translation_key": "region",
                            }
                        }
                    )
                }
            ),
        )


def _label_for_region(code: str) -> str:
    for item in REGION_SELECT_OPTIONS:
        if item["value"].upper() == (code or "").upper():
            return item["label"]
    return code
