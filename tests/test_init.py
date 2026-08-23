"""Tests for the Mazda Connected Services integration setup and migrations.

These target ``custom_components/mazda_cs/__init__.py``. The historical core test
(``test_mazda_repair_issue``) exercised a single-entry "repair issue" that the
current OAuth2-based integration no longer implements, so it has been replaced with
coverage of the behaviour that actually exists today: config-entry migrations, the
v1 -> reauth path, the ``send_poi`` service registration, and the ``MazdaEntity``
base class shared by every platform.
"""

import logging
from unittest.mock import AsyncMock

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import CONF_REGION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator
from homeassistant.setup import async_setup_component

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mazda_cs import (
    MazdaEntity,
    _enable_all_notify_settings,
    async_migrate_entry,
)
from custom_components.mazda_cs.const import CONF_ENABLE_PUSH, DOMAIN

# A minimally-valid OAuth2 token blob, enough for entry.data to carry a "token".
MOCK_TOKEN = {
    "access_token": "mock-access-token",
    "refresh_token": "mock-refresh-token",
    "expires_in": 7200,
    "expires_at": 9999999999,
    "token_type": "Bearer",
}


async def test_async_setup_registers_send_poi_service(hass: HomeAssistant) -> None:
    """Setting up the domain registers the send_poi service."""
    assert await async_setup_component(hass, DOMAIN, {})
    await hass.async_block_till_done()

    assert hass.services.has_service(DOMAIN, "send_poi")


async def test_migrate_entry_v1_to_v2(hass: HomeAssistant) -> None:
    """A v1 (email/password) entry migrates to v2 keeping only the region."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=1,
        data={
            CONF_REGION: "MME",
            "email": "user@example.com",
            "password": "hunter2",
        },
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    # Region is preserved; the stale credentials are dropped so async_setup_entry
    # (no "token" key) will raise ConfigEntryAuthFailed and trigger reauth.
    assert entry.version == 2
    assert entry.minor_version == 1
    assert entry.data == {CONF_REGION: "MME"}


async def test_migrate_entry_v1_defaults_region_to_mnao(hass: HomeAssistant) -> None:
    """A v1 entry with no region defaults to MNAO on migration."""
    entry = MockConfigEntry(domain=DOMAIN, version=1, data={})
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.data == {CONF_REGION: "MNAO"}


async def test_migrate_entry_v2_1_to_v2_2_disables_push(hass: HomeAssistant) -> None:
    """v2.1 -> v2.2 opts existing entries out of push notifications."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=1,
        data={CONF_REGION: "MNAO", "token": MOCK_TOKEN},
        options={},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.minor_version == 2
    assert entry.options[CONF_ENABLE_PUSH] is False


async def test_migrate_entry_current_version_is_noop(hass: HomeAssistant) -> None:
    """A current-version entry is left untouched by the migration hook."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=2,
        data={CONF_REGION: "MNAO", "token": MOCK_TOKEN},
        options={CONF_ENABLE_PUSH: True},
    )
    entry.add_to_hass(hass)

    assert await async_migrate_entry(hass, entry) is True

    assert entry.version == 2
    assert entry.minor_version == 2
    assert entry.options[CONF_ENABLE_PUSH] is True


async def test_setup_entry_without_token_triggers_reauth(
    hass: HomeAssistant,
) -> None:
    """A v2 entry lacking an OAuth2 token fails setup and starts a reauth flow."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        version=2,
        minor_version=2,
        data={CONF_REGION: "MNAO"},
    )
    entry.add_to_hass(hass)

    assert not await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.state is ConfigEntryState.SETUP_ERROR

    flows = hass.config_entries.flow.async_progress()
    assert any(flow["context"]["source"] == "reauth" for flow in flows)


# A representative vehicle dict as produced by the coordinator (client.get_vehicles).
VEHICLE = {
    "id": 12345,
    "vin": "JM1ABCDEFG1234567",
    "modelYear": "2021",
    "carlineName": "CX-5",
    "nickname": "My Mazda",
}


def _make_entity(hass: HomeAssistant, vehicle: dict) -> MazdaEntity:
    """Build a MazdaEntity backed by a coordinator holding a single vehicle."""
    entry = MockConfigEntry(domain=DOMAIN)
    entry.add_to_hass(hass)
    coordinator = DataUpdateCoordinator(
        hass,
        logging.getLogger(__name__),
        name=DOMAIN,
        update_method=AsyncMock(),
        update_interval=None,
        config_entry=entry,
    )
    coordinator.data = [vehicle]
    return MazdaEntity(client=None, coordinator=coordinator, index=0)


async def test_entity_uses_nickname_when_present(hass: HomeAssistant) -> None:
    """vehicle_name and device_info prefer the user-set nickname."""
    entity = _make_entity(hass, VEHICLE)

    assert entity.vin == "JM1ABCDEFG1234567"
    assert entity.vehicle_id == 12345
    assert entity.data is entity.coordinator.data[0]
    assert entity.vehicle_name == "My Mazda"

    device_info = entity.device_info
    assert device_info["identifiers"] == {(DOMAIN, "JM1ABCDEFG1234567")}
    assert device_info["manufacturer"] == "Mazda"
    assert device_info["model"] == "2021 CX-5"
    assert device_info["name"] == "My Mazda"


async def test_entity_falls_back_to_model_without_nickname(
    hass: HomeAssistant,
) -> None:
    """With no nickname key, the name falls back to model year + carline."""
    vehicle = {key: value for key, value in VEHICLE.items() if key != "nickname"}
    entity = _make_entity(hass, vehicle)

    assert entity.vehicle_name == "2021 CX-5"


async def test_entity_falls_back_to_model_with_empty_nickname(
    hass: HomeAssistant,
) -> None:
    """An empty-string nickname is treated as unset."""
    entity = _make_entity(hass, {**VEHICLE, "nickname": ""})

    assert entity.vehicle_name == "2021 CX-5"


async def test_enable_notify_skips_when_all_already_on() -> None:
    """No write is issued when every toggle is already enabled."""
    client = AsyncMock()
    client.get_notify_setting.return_value = {
        "resultCode": "200S00",
        "visitNo": "1700000000000",
        "settingSaveFlag": 0,
        "doorLock": 1,
        "doorOpen": 1,
    }

    await _enable_all_notify_settings(client, [{"id": 1, "vin": "VIN1"}])

    client.get_notify_setting.assert_awaited_once_with(1)
    client.set_notify_setting.assert_not_awaited()


async def test_enable_notify_writes_filtered_all_on_payload() -> None:
    """When a toggle is off, write every setting as 1 with the save flag.

    The metadata keys in ``_NOTIFY_EXCLUDE`` and ``None`` values are dropped, and
    the remaining keys are lower-cased.
    """
    client = AsyncMock()
    client.get_notify_setting.return_value = {
        "resultCode": "200S00",
        "visitNo": "1700000000000",
        "settingSaveFlag": 0,
        "doorLock": 1,
        "doorOpen": 0,
        "tpmsWarning": None,
    }

    await _enable_all_notify_settings(client, [{"id": 2, "vin": "VIN2"}])

    client.set_notify_setting.assert_awaited_once_with(
        2, {"doorlock": 1, "dooropen": 1, "settingsaveflag": 0}
    )


async def test_enable_notify_swallows_errors() -> None:
    """A failure reading one vehicle is caught and does not raise."""
    client = AsyncMock()
    client.get_notify_setting.side_effect = Exception("boom")

    # Must not propagate.
    await _enable_all_notify_settings(client, [{"id": 3, "vin": "VIN3"}])

    client.set_notify_setting.assert_not_awaited()
