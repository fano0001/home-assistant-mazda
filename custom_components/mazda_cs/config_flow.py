from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant import config_entries
from homeassistant.core import callback
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult

from .const import DOMAIN

# Anzeigenamen -> interne Regionscodes
REGION_LABELS: dict[str, str] = {
    "Europa": "MME",
    "Nordamerika": "MNAO",
    "Japan": "JAPAN",
    "Australien/Neuseeland": "MDA",
}

USER_SCHEMA = vol.Schema(
    {
        vol.Required("email"): str,
        vol.Required("password"): str,
        vol.Required("region", default="Europa"): vol.In(list(REGION_LABELS.keys())),
    }
)


class MazdaConfigFlow(ConfigFlow, domain=DOMAIN):
    """Config flow für Mazda Connected Services."""

    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=USER_SCHEMA)

        # Mappe Anzeigenamen auf Code
        label = user_input["region"]
        region_code = REGION_LABELS.get(label, label)

        data = {
            "email": user_input["email"],
            "password": user_input["password"],
            "region": region_code,
        }

        await self.async_set_unique_id(f"{data['email']}::{region_code}")
        self._abort_if_unique_id_configured()

        return self.async_create_entry(title="Mazda Connected Services", data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: config_entries.ConfigEntry) -> config_entries.OptionsFlow:
        return MazdaOptionsFlow(config_entry)


class MazdaOptionsFlow(config_entries.OptionsFlow):
    """Optionen-Flow (aktuell ohne Optionen, nur Platzhalter)."""

    def __init__(self, config_entry: config_entries.ConfigEntry) -> None:
        self.config_entry = config_entry

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        # Keine Optionen – direkt abschließen.
        return self.async_create_entry(title="", data={})
