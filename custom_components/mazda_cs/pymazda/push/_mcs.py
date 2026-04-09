"""MCS (Mobile Connection Server) TCP listener for Android FCM push notifications.

Connects to mtalk.google.com:5228 using the GCM android_id + security_token
obtained from check-in.  Incoming DataMessageStanza messages carry the FCM
data payload as plain key-value pairs in app_data — no web-push encryption.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import ssl
import struct
import time
from collections.abc import Callable
from typing import Any

from ._proto.mcs_pb2 import (  # pylint: disable=no-name-in-module
    Close,
    DataMessageStanza,
    HeartbeatAck,
    HeartbeatPing,
    IqStanza,
    LoginRequest,
    LoginResponse,
    SelectiveAck,
    StreamAck,
    StreamErrorStanza,
)

_LOGGER = logging.getLogger(__name__)

MCS_HOST = "mtalk.google.com"
MCS_PORT = 5228
MCS_VERSION = 41
MCS_SELECTIVE_ACK_ID = 12

# Maps protobuf message type to its integer tag in the MCS wire format
_TAG_BY_TYPE: dict[type, int] = {
    HeartbeatPing: 0,
    HeartbeatAck: 1,
    LoginRequest: 2,
    LoginResponse: 3,
    Close: 4,
    IqStanza: 7,
    DataMessageStanza: 8,
    StreamErrorStanza: 10,
    StreamAck: 11,
}
_TYPE_BY_TAG: dict[int, type] = {v: k for k, v in _TAG_BY_TYPE.items()}

MessageCallback = Callable[[dict[str, Any]], None]

class _McsServerClose(Exception):
    """Raised when the MCS server sends a Close stanza (expected periodic reconnect)."""


class McsClient:
    """Persistent MCS connection that delivers FCM data payloads via callback.

    Usage::

        client = McsClient(android_id, security_token, on_message=my_callback)
        await client.start()
        # ... runs until stop() is called
        await client.stop()
    """

    def __init__(
        self,
        android_id: str,
        security_token: str,
        on_message: MessageCallback,
        *,
        server_heartbeat_interval: int = 10,
        client_heartbeat_interval: int = 20,
        connection_retry_count: int = 5,
    ) -> None:
        self._android_id = android_id
        self._security_token = security_token
        self._on_message = on_message
        self._server_hb = server_heartbeat_interval
        self._client_hb = client_heartbeat_interval
        self._retry_count = connection_retry_count

        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._tasks: list[asyncio.Task] = []
        self._do_listen = False
        self._first_message = True
        self._input_stream_id = 0
        self._last_stream_id_reported = -1
        self._last_message_time: float | None = None
        self._persistent_ids: list[str] = []

    def is_started(self) -> bool:
        return self._do_listen and bool(self._tasks) and not all(t.done() for t in self._tasks)

    async def start(self) -> None:
        """Start the MCS listener as background tasks."""
        self._do_listen = True
        self._tasks = [
            asyncio.create_task(self._listen(), name="mazda_mcs_listen"),
            asyncio.create_task(self._monitor(), name="mazda_mcs_monitor"),
        ]

    async def stop(self) -> None:
        """Stop the MCS listener and close the connection."""
        self._do_listen = False
        # Cancel tasks before closing the writer so readers unblock immediately.
        # Awaiting _close_writer() first could block for 30-60 s if the SSL/TCP
        # teardown stalls (no response to FIN from mtalk.google.com), which would
        # delay task cancellation for the full OS TCP timeout.
        for task in self._tasks:
            task.cancel()
        for task in self._tasks:
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        self._tasks = []
        await self._close_writer()

    # ------------------------------------------------------------------
    # Wire protocol helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _encode_varint(x: int) -> bytes:
        if x == 0:
            return b"\x00"
        buf = bytearray()
        while x:
            b = x & 0x7F
            x >>= 7
            if x:
                b |= 0x80
            buf.append(b)
        return bytes(buf)

    async def _read_varint(self) -> int:
        res = shift = 0
        while True:
            (b,) = struct.unpack("B", await self._reader.readexactly(1))  # type: ignore[union-attr]
            res |= (b & 0x7F) << shift
            if not (b & 0x80):
                break
            shift += 7
        return res

    async def _send(self, msg: Any) -> None:
        tag = _TAG_BY_TYPE[type(msg)]
        header = bytes([MCS_VERSION, tag]) if self._first_message else bytes([tag])
        payload = msg.SerializeToString()
        buf = header + self._encode_varint(len(payload)) + payload
        self._writer.write(buf)  # type: ignore[union-attr]
        await self._writer.drain()  # type: ignore[union-attr]

    async def _recv(self) -> Any | None:
        if self._first_message:
            hdr = await self._reader.readexactly(2)  # type: ignore[union-attr]
            version, tag = struct.unpack("BB", hdr)
            if version < MCS_VERSION and version != 38:
                raise RuntimeError(f"MCS protocol version {version} unsupported")
            self._first_message = False
        else:
            (tag,) = struct.unpack("B", await self._reader.readexactly(1))  # type: ignore[union-attr]

        size = await self._read_varint()
        buf = await self._reader.readexactly(size)

        msg_class = _TYPE_BY_TAG.get(tag)
        if msg_class is None:
            _LOGGER.debug("MCS: unknown tag %d, skipping %d bytes", tag, size)
            return None

        msg = msg_class()
        msg.ParseFromString(buf)
        return msg

    async def _close_writer(self) -> None:
        writer, self._writer = self._writer, None
        if writer:
            writer.close()
            with contextlib.suppress(Exception):
                # Cap the wait to 3 s — if the remote end (mtalk.google.com) doesn't
                # echo back the SSL close_notify / TCP FIN-ACK promptly, the OS TCP
                # state machine can hold the connection open for 30-60+ seconds.
                async with asyncio.timeout(3):
                    await writer.wait_closed()

    # ------------------------------------------------------------------
    # Connection / login
    # ------------------------------------------------------------------

    async def _connect(self) -> bool:
        try:
            loop = asyncio.get_running_loop()
            ssl_ctx = await loop.run_in_executor(None, ssl.create_default_context)
            self._reader, self._writer = await asyncio.open_connection(
                host=MCS_HOST, port=MCS_PORT, ssl=ssl_ctx
            )
            self._first_message = True
            self._input_stream_id = 0
            self._last_stream_id_reported = -1
            _LOGGER.debug("MCS: connected to %s:%d", MCS_HOST, MCS_PORT)
            return True
        except OSError as ex:
            _LOGGER.warning("MCS: connection failed: %s", ex)
            return False

    async def _connect_with_retry(self) -> bool:
        for attempt in range(self._retry_count):
            if not self._do_listen:
                return False
            if await self._connect():
                return True
            wait = 3.0 * (attempt + 1) ** 2
            _LOGGER.info("MCS: retry %d/%d in %.0fs", attempt + 1, self._retry_count, wait)
            await asyncio.sleep(wait)
        return False

    async def _login(self) -> None:
        android_id = self._android_id
        req = LoginRequest()
        req.adaptive_heartbeat = False
        req.auth_service = LoginRequest.ANDROID_ID  # 2
        req.auth_token = self._security_token
        req.id = "android-0"  # protocol requires a non-empty string
        req.domain = "mcs.android.com"
        req.device_id = f"android-{int(android_id):x}"
        req.network_type = 1
        req.resource = android_id
        req.user = android_id
        req.use_rmq2 = True
        req.setting.add(name="new_vc", value="1")
        req.received_persistent_id.extend(self._persistent_ids)
        if self._server_hb and self._server_hb > 0:
            req.heartbeat_stat.ip = ""
            req.heartbeat_stat.timeout = True
            req.heartbeat_stat.interval_ms = 1000 * self._server_hb
        await self._send(req)
        _LOGGER.debug("MCS: login request sent")

    # ------------------------------------------------------------------
    # Message handling
    # ------------------------------------------------------------------

    def _has_new_stream_id(self) -> bool:
        return self._last_stream_id_reported != self._input_stream_id

    def _consume_stream_id(self) -> int:
        self._last_stream_id_reported = self._input_stream_id
        return self._input_stream_id

    async def _handle_ping(self, msg: HeartbeatPing) -> None:
        ack = HeartbeatAck()
        if self._has_new_stream_id():
            ack.last_stream_id_received = self._consume_stream_id()
        await self._send(ack)
        _LOGGER.debug("MCS: heartbeat ping → ack sent")

    async def _send_selective_ack(self, persistent_id: str) -> None:
        iqs = IqStanza()
        iqs.type = IqStanza.SET  # type: ignore[attr-defined]
        iqs.id = ""
        iqs.extension.id = MCS_SELECTIVE_ACK_ID
        sa = SelectiveAck()
        sa.id.extend([persistent_id])
        iqs.extension.data = sa.SerializeToString()
        await self._send(iqs)

    def _parse_data_message(self, msg: DataMessageStanza) -> dict[str, Any]:
        """Extract payload from a DataMessageStanza.

        Android FCM data-only messages carry their payload as plain key-value
        pairs in app_data.  There is no web-push encryption layer.
        """
        data: dict[str, Any] = {item.key: item.value for item in msg.app_data}
        raw_len = len(msg.raw_data) if msg.raw_data else 0
        app_data_len = len(msg.app_data)
        raw_preview = ""
        if msg.raw_data:
            raw_preview = msg.raw_data[:64].hex()
        _LOGGER.debug(
            "MCS: data stanza payload sizes app_data=%d raw_data=%d raw_preview=%s",
            app_data_len,
            raw_len,
            raw_preview,
        )

        # Fallback: some FCM backends put the payload in raw_data as JSON
        if not data and msg.raw_data:
            with contextlib.suppress(json.JSONDecodeError, UnicodeDecodeError):
                raw_parsed = json.loads(msg.raw_data.decode("utf-8"))
                if isinstance(raw_parsed, dict):
                    data = raw_parsed

        _LOGGER.debug(
            "MCS: data message id=%s category=%s data_keys=%s",
            msg.persistent_id,
            msg.category,
            list(data.keys()),
        )
        return data

    async def _dispatch(self, msg: Any) -> None:
        self._last_message_time = time.monotonic()
        self._input_stream_id += 1

        if isinstance(msg, LoginResponse):
            has_error = msg.HasField("error")
            error_code = msg.error.code if has_error else 0
            error_msg = msg.error.message if has_error else ""
            _LOGGER.info(
                "MCS LoginResponse: id=%r jid=%r stream_id=%d server_timestamp=%d error_code=%d error_msg=%r",
                msg.id, msg.jid, msg.stream_id, msg.server_timestamp, error_code, error_msg,
            )
            if has_error and error_code != 0:
                _LOGGER.error("MCS: login failed — error_code=%d message=%r", error_code, error_msg)
            else:
                _LOGGER.info("MCS: logged in successfully")
                self._persistent_ids = []
            return

        if isinstance(msg, Close):
            _LOGGER.debug("MCS: server sent Close — reconnecting")
            raise _McsServerClose()

        if isinstance(msg, StreamErrorStanza):
            _LOGGER.error("MCS: stream error %s: %s", msg.type, msg.text)
            raise ConnectionResetError(f"MCS stream error: {msg.type}")

        if isinstance(msg, DataMessageStanza):
            data = self._parse_data_message(msg)
            self._persistent_ids.append(msg.persistent_id)
            await self._send_selective_ack(msg.persistent_id)
            try:
                self._on_message(data)
            except Exception:  # noqa: BLE001
                _LOGGER.exception("MCS: exception in on_message callback")
            return

        if isinstance(msg, HeartbeatPing):
            await self._handle_ping(msg)
        elif isinstance(msg, HeartbeatAck):
            _LOGGER.debug("MCS: heartbeat ack received")
        elif isinstance(msg, StreamAck):
            _LOGGER.debug("MCS: stream ack received")
        elif isinstance(msg, IqStanza):
            pass  # SelectiveAck responses — no action needed

    # ------------------------------------------------------------------
    # Main tasks
    # ------------------------------------------------------------------

    async def _listen(self) -> None:
        while self._do_listen:
            if not await self._connect_with_retry():
                _LOGGER.error("MCS: could not connect after %d retries, giving up", self._retry_count)
                return

            try:
                await self._login()
                while self._do_listen:
                    msg = await self._recv()
                    if msg is not None:
                        await self._dispatch(msg)

            except asyncio.CancelledError:
                return
            except _McsServerClose:
                if not self._do_listen:
                    return
            except (OSError, EOFError, asyncio.IncompleteReadError, ConnectionResetError, ssl.SSLError) as ex:
                if not self._do_listen:
                    return
                _LOGGER.warning("MCS: connection lost (%s), reconnecting", ex)
            except Exception:
                if not self._do_listen:
                    return
                _LOGGER.exception("MCS: unexpected error, reconnecting")
            finally:
                await self._close_writer()

            if self._do_listen:
                await asyncio.sleep(3)

    async def _monitor(self) -> None:
        """Send client heartbeats when the server goes quiet."""
        while self._do_listen:
            await asyncio.sleep(self._client_hb)
            if (
                self._do_listen
                and self._last_message_time is not None
                and self._writer is not None
            ):
                age = time.monotonic() - self._last_message_time
                if age >= self._client_hb:
                    try:
                        ping = HeartbeatPing()
                        if self._has_new_stream_id():
                            ping.last_stream_id_received = self._consume_stream_id()
                        await self._send(ping)
                        _LOGGER.debug("MCS: sent client heartbeat ping")
                    except Exception as ex:  # noqa: BLE001
                        _LOGGER.debug("MCS: heartbeat send failed: %s", ex)
