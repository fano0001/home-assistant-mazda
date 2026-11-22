"""Tests for MCS wire-format limits, reconnect backoff and dead-link handling."""

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.mazda_cs.pymazda.push import _mcs
from custom_components.mazda_cs.pymazda.push._mcs import (
    HeartbeatAck,
    LoginResponse,
    McsClient,
    _McsProtocolError,
)

_HEARTBEAT_ACK_TAG = 1


def _client(stream: bytes, *, first_message: bool = False) -> McsClient:
    """Build a client whose reader yields ``stream`` and then EOF."""
    client = McsClient("1234", "token", on_message=lambda _data: None)
    client._do_listen = True
    client._first_message = first_message
    client._reader = asyncio.StreamReader()
    client._reader.feed_data(stream)
    client._reader.feed_eof()
    return client


@pytest.mark.parametrize(
    "length_prefix",
    [b"\x80\x80\x80\x01", b"\x80\x80\x80\x80\x80\x01"],
    ids=["2MiB", "6-byte-varint"],
)
async def test_recv_rejects_oversized_length(length_prefix: bytes) -> None:
    """A huge or overlong length prefix is rejected before the body is read."""
    client = _client(bytes([_HEARTBEAT_ACK_TAG]) + length_prefix)

    with pytest.raises(_McsProtocolError):
        await client._recv()


async def test_recv_accepts_normal_message() -> None:
    """A well-formed stanza within the limits still parses."""
    payload = HeartbeatAck(last_stream_id_received=7).SerializeToString()
    client = _client(
        bytes([_HEARTBEAT_ACK_TAG]) + McsClient._encode_varint(len(payload)) + payload
    )

    msg = await client._recv()

    assert isinstance(msg, HeartbeatAck)
    assert msg.last_stream_id_received == 7


async def test_recv_rejects_unsupported_version() -> None:
    """An old protocol version in the first header is a protocol error."""
    client = _client(bytes([30, _HEARTBEAT_ACK_TAG, 0]), first_message=True)

    with pytest.raises(_McsProtocolError, match="version 30"):
        await client._recv()


class _ModuleAsyncio:
    """Stands in for ``asyncio`` inside _mcs only; records sleeps, stops after N."""

    def __init__(self, client: McsClient, stop_after: int) -> None:
        self.sleeps: list[float] = []
        self._client = client
        self._stop_after = stop_after

    def __getattr__(self, name):
        return getattr(asyncio, name)

    async def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if len(self.sleeps) >= self._stop_after:
            self._client._do_listen = False


def _idle_client(**kwargs) -> McsClient:
    client = McsClient("1234", "token", on_message=lambda _data: None, **kwargs)
    client._do_listen = True
    return client


async def test_failed_login_backs_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """A rejected login tears the link down; reconnect waits double up to 900 s."""
    states: list[bool] = []
    client = _idle_client(on_connection_state=states.append)
    failed = LoginResponse()
    failed.error.code = 401

    monkeypatch.setattr(client, "_connect_with_retry", AsyncMock(return_value=True))
    monkeypatch.setattr(client, "_login", AsyncMock())
    monkeypatch.setattr(client, "_recv", AsyncMock(return_value=failed))
    monkeypatch.setattr(client, "_close_writer", AsyncMock())
    fake = _ModuleAsyncio(client, stop_after=11)
    monkeypatch.setattr(_mcs, "asyncio", fake)

    await client._listen()

    assert fake.sleeps == [3, 6, 12, 24, 48, 96, 192, 384, 768, 900, 900]
    assert True not in states


async def test_connect_failures_back_off(monkeypatch: pytest.MonkeyPatch) -> None:
    """Exhausted connect retries wait with the same backoff, not a fixed 24 h."""
    client = _idle_client()
    monkeypatch.setattr(client, "_connect_with_retry", AsyncMock(return_value=False))
    fake = _ModuleAsyncio(client, stop_after=3)
    monkeypatch.setattr(_mcs, "asyncio", fake)

    await client._listen()

    assert fake.sleeps == [3, 6, 12]


async def test_successful_login_resets_backoff_and_reports_connected() -> None:
    """Connected is reported on the accepted LoginResponse, and the wait resets."""
    states: list[bool] = []
    client = _idle_client(on_connection_state=states.append)
    client._reconnect_delay = 300

    await client._dispatch(LoginResponse())

    assert client._reconnect_delay == 3
    assert states == [True]


async def test_login_sent_does_not_report_connected(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Sending the login alone does not report the connection as up."""
    states: list[bool] = []
    client = _idle_client(on_connection_state=states.append)
    monkeypatch.setattr(client, "_send", AsyncMock())

    await client._login()

    assert states == []


@pytest.mark.parametrize(
    ("silent_heartbeats", "dropped"),
    [(1.9, False), (3, True)],
    ids=["answered-ping", "two-unanswered-pings"],
)
async def test_monitor_dead_link_threshold(
    monkeypatch: pytest.MonkeyPatch, silent_heartbeats: float, dropped: bool
) -> None:
    """A link is dropped only after two unanswered pings; otherwise it is pinged."""
    client = _idle_client()
    client._writer = MagicMock()
    client._last_message_time = time.monotonic() - silent_heartbeats * client._client_hb
    monkeypatch.setattr(client, "_send", AsyncMock())
    monkeypatch.setattr(client, "_close_writer", AsyncMock())
    monkeypatch.setattr(_mcs, "asyncio", _ModuleAsyncio(client, stop_after=2))

    await client._monitor()

    assert client._close_writer.await_count == int(dropped)
    assert client._send.await_count == int(not dropped)


async def test_connect_resets_silence_clock(monkeypatch: pytest.MonkeyPatch) -> None:
    """A new link is not judged dead by the previous link's silence."""
    client = _idle_client()
    client._last_message_time = 0.0
    fake = _ModuleAsyncio(client, stop_after=99)
    fake.open_connection = AsyncMock(return_value=(MagicMock(), MagicMock()))
    monkeypatch.setattr(_mcs, "asyncio", fake)

    assert await client._connect()
    assert time.monotonic() - client._last_message_time < 5
