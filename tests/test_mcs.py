"""Tests for MCS wire-format parsing limits."""

import asyncio

import pytest

from custom_components.mazda_cs.pymazda.push._mcs import (
    HeartbeatAck,
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
