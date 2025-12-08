from __future__ import annotations
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DATA_COORDINATOR, DOMAIN


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry: ConfigEntry) -> dict[str, Any]:
    data = hass.data.get(DOMAIN, {}).get(entry.entry_id, {})
    coord = data.get(DATA_COORDINATOR)
    vehicles = coord.vehicles if coord else []
    status = coord.data.get("status", {}) if coord and coord.data else {}
    redacted = {**entry.as_dict()} if hasattr(entry, "as_dict") else {"data": getattr(entry, "data", {})}
    if "data" in redacted and isinstance(redacted["data"], dict):
        red = redacted["data"].copy()
        if "password" in red:
            red["password"] = "***"
        if "email" in red:
            red["email"] = "***"
        redacted["data"] = red
    return {
        "config_entry": redacted,
        "vehicles": [getattr(v, "vin", None) for v in vehicles],
        "status": {k: getattr(v, "vin", None) for k, v in status.items()},
    }
