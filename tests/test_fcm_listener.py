"""Tests for how a remote-command result push affects assumed state."""

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.mazda_cs.fcm_listener import MazdaFcmListener
from custom_components.mazda_cs.pymazda.client import Client

VIN = "JM1TESTVIN0001234"
VEHICLE_ID = 7


def _listener(client: Client) -> tuple[MazdaFcmListener, MagicMock, list]:
    """A listener over mocks; records the assumed lock state at refresh time."""
    seen_at_refresh: list = []

    def request_refresh():
        seen_at_refresh.append(client.get_assumed_lock_state(VEHICLE_ID))
        return AsyncMock()()

    coordinator = MagicMock(data=[{"id": VEHICLE_ID, "vin": VIN}])
    coordinator.async_request_refresh = MagicMock(side_effect=request_refresh)
    hass = MagicMock()
    hass.async_create_task = MagicMock(side_effect=lambda coro: coro.close())
    entry = SimpleNamespace(runtime_data=SimpleNamespace(client=client))
    return MazdaFcmListener(hass, entry, coordinator), coordinator, seen_at_refresh


async def _client_with_assumed_lock() -> Client:
    client = Client(
        user_sub="test-sub",
        region="MNAO",
        access_token_provider=AsyncMock(return_value="token"),
        websession=AsyncMock(),
    )
    client.controller = AsyncMock()
    await client.lock_doors(VEHICLE_ID)
    await client.turn_on_hvac(VEHICLE_ID)
    assert client.get_assumed_lock_state(VEHICLE_ID) is True
    return client


async def test_failure_push_clears_assumed_state_before_refresh() -> None:
    """A failed remote command clears the vehicle's assumed values, then refreshes."""
    client = await _client_with_assumed_lock()
    listener, coordinator, seen_at_refresh = _listener(client)

    listener._on_notification({"a": "001", "r": "00120261118011652_02", "v": VIN})

    assert client.get_assumed_lock_state(VEHICLE_ID) is None
    assert client.get_assumed_hvac_mode(VEHICLE_ID) is None
    coordinator.async_request_refresh.assert_called_once()
    assert seen_at_refresh == [None]


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(
            {"a": "001", "r": "00120261118011652_01", "v": VIN}, id="success-push"
        ),
        pytest.param(
            {"a": "001", "r": "00120261118011652_02", "v": "JM1OTHERVIN9999"},
            id="unknown-vin",
        ),
        pytest.param(
            {"a": "003", "r": "00320261118011652_02", "v": VIN},
            id="not-a-remote-result",
        ),
    ],
)
async def test_other_pushes_keep_assumed_state(payload) -> None:
    """Only a failure result for a known vehicle clears its assumed values."""
    client = await _client_with_assumed_lock()
    listener, _, _ = _listener(client)

    listener._on_notification(payload)

    assert client.get_assumed_lock_state(VEHICLE_ID) is True
    assert client.get_assumed_hvac_mode(VEHICLE_ID) is True


@pytest.mark.parametrize("action_code", ["021", "022"])
@pytest.mark.parametrize("suffix", ["_01", "_02"])
async def test_ev_result_pushes_refresh(action_code, suffix) -> None:
    """Charge results (021) and status report results (022) are read."""
    client = await _client_with_assumed_lock()
    listener, coordinator, _ = _listener(client)

    listener._on_notification(
        {"a": action_code, "r": f"{action_code}20261118011652{suffix}", "v": VIN}
    )

    coordinator.async_request_refresh.assert_called_once()
