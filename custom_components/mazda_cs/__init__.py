"""Mazda Connected Services v2 setup (OAuth2 + PKCE)."""
from __future__ import annotations

import logging
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import CONF_EMAIL, CONF_PASSWORD, CONF_REGION, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN, DATA_COORDINATOR, DEFAULT_REGION
from .coordinator import MazdaDataCoordinator

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR, Platform.SWITCH]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    hass.data.setdefault(DOMAIN, {})
    email = entry.data[CONF_EMAIL]
    password = entry.data[CONF_PASSWORD]
    region = entry.data.get(CONF_REGION, DEFAULT_REGION)

    coordinator = MazdaDataCoordinator(hass, email=email, password=password, region=region)
    await coordinator.async_login()
    await coordinator.async_config_entry_first_refresh()

    hass.data[DOMAIN][entry.entry_id] = {
        DATA_COORDINATOR: coordinator,
    }

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id, None)
    return unload_ok


async def async_migrate_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Migrate old config entries to version 2."""
    old_version = entry.version or 1
    if old_version >= 2:
        _LOGGER.debug("No migration needed for entry %s (version=%s)", entry.title, old_version)
        return True

    from homeassistant.const import CONF_EMAIL, CONF_REGION
    data = dict(entry.data)
    data.setdefault(CONF_REGION, "MME")
    unique_id = entry.unique_id or f"{data.get(CONF_EMAIL,'').lower()}_{data.get(CONF_REGION)}"
    hass.config_entries.async_update_entry(entry, data=data, unique_id=unique_id, version=2)
    _LOGGER.info("Migrated entry '%s' to version 2", entry.title)
    return True

#async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
#    coord: MazdaDataCoordinator = hass.data[DOMAIN][entry.entry_id]["coordinator"]
#    await coord.api.async_close()
#    return True