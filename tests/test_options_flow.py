"""Tests for the options flow (the gear icon on the config entry)."""

from unittest.mock import patch

from homeassistant.const import CONF_REGION
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mazda_cs.const import (
    CONF_ENABLE_DEV_SENSORS,
    CONF_ENABLE_PUSH,
    CONF_ENABLE_VEHICLE_IMAGES,
    DOMAIN,
)


def _entry(options: dict) -> MockConfigEntry:
    return MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=4,
        data={CONF_REGION: "MNAO"},
        options=options,
    )


async def test_options_form_defaults(hass: HomeAssistant) -> None:
    """With no stored options, both images and dev sensors default off."""
    entry = _entry({CONF_ENABLE_PUSH: True})
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)

    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "init"
    defaults = {str(key): key.default() for key in result["data_schema"].schema}
    assert defaults == {
        CONF_ENABLE_VEHICLE_IMAGES: False,
        CONF_ENABLE_DEV_SENSORS: False,
    }


async def test_options_saved_and_entry_reloaded(hass: HomeAssistant) -> None:
    """Saving changed options stores them, keeps push, and reloads the entry."""
    entry = _entry({CONF_ENABLE_PUSH: True})
    entry.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ENABLE_VEHICLE_IMAGES: True, CONF_ENABLE_DEV_SENSORS: True},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_ENABLE_PUSH: True,
        CONF_ENABLE_VEHICLE_IMAGES: True,
        CONF_ENABLE_DEV_SENSORS: True,
    }
    reload.assert_called_once_with(entry.entry_id)


async def test_options_unchanged_skips_reload(hass: HomeAssistant) -> None:
    """Saving without changes does not reload (and so does not re-attach)."""
    options = {
        CONF_ENABLE_PUSH: True,
        CONF_ENABLE_VEHICLE_IMAGES: True,
        CONF_ENABLE_DEV_SENSORS: False,
    }
    entry = _entry(options)
    entry.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ENABLE_VEHICLE_IMAGES: True, CONF_ENABLE_DEV_SENSORS: False},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == options
    reload.assert_not_called()


async def test_first_save_with_defaults_skips_reload(hass: HomeAssistant) -> None:
    """Saving the defaults on an entry without the keys stores them, no reload."""
    entry = _entry({CONF_ENABLE_PUSH: True})
    entry.add_to_hass(hass)

    with patch.object(hass.config_entries, "async_schedule_reload") as reload:
        result = await hass.config_entries.options.async_init(entry.entry_id)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"],
            {CONF_ENABLE_VEHICLE_IMAGES: False, CONF_ENABLE_DEV_SENSORS: False},
        )

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert entry.options == {
        CONF_ENABLE_PUSH: True,
        CONF_ENABLE_VEHICLE_IMAGES: False,
        CONF_ENABLE_DEV_SENSORS: False,
    }
    reload.assert_not_called()
