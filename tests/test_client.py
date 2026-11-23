"""Tests for vehicle-status parsing in ``pymazda/client.py``.

Focus: Mazda's ``OccurrenceDate`` timestamps are not guaranteed to be present. A
vehicle that has not yet reported — e.g. one just re-enrolled after a Connected
Services subscription lapse (issue #63) — returns an alert frame with the field
missing, which used to raise ``TypeError: strptime() argument 1 must be str, not
None`` and trap the config entry in a setup-retry loop.
"""

import datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.mazda_cs.pymazda.client import (
    Client,
    _parse_occurrence_date,
    _warn_undocumented_fields,
)
import aiohttp

from custom_components.mazda_cs.api import MazdaAuth
from custom_components.mazda_cs.pymazda import connection as connection_module
from custom_components.mazda_cs.pymazda.connection import (
    MAX_RETRIES,
    REQUEST_IN_PROGRESS_RETRY_SECONDS,
    REQUEST_TIMEOUT_SECONDS,
    Connection,
)
from custom_components.mazda_cs.pymazda.exceptions import (
    MazdaConnectionException,
    MazdaException,
    MazdaRateLimitException,
    MazdaRequestInProgressException,
    MazdaSessionExpiredException,
    MazdaTokenExpiredException,
)

VEHICLE_ID = 12345

# A minimal remoteInfos frame: enough for the fields get_vehicle_status reads.
REMOTE_INFO = {
    "OccurrenceDate": "20260823120000",
    "PositionInfo": {"Latitude": 45.0, "LatitudeFlag": 0, "Longitude": 90.0},
}

# An alert frame from a vehicle that has reported: dated, doors physically unlocked.
ALERT_INFO = {
    "OccurrenceDate": "20260823123000",
    "Door": {"LockLinkSwDrv": 1},
}


def _make_client() -> Client:
    """Build a Client whose controller is mocked out (no network, no attach)."""
    client = Client(
        user_sub="test-sub",
        region="MNAO",
        access_token_provider=AsyncMock(return_value="token"),
        # Supplied so Connection does not open a real aiohttp session it never closes.
        websession=AsyncMock(),
    )
    client.controller = AsyncMock()
    return client


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (
            "20260823123000",
            datetime.datetime(2026, 8, 23, 12, 30, tzinfo=datetime.UTC),
        ),
        (None, None),
        ("", None),
        # getHealthReport emits this shape for the same field name, so a
        # present-but-differently-formatted string must not raise either.
        ("2026-03-04 00:39:46", None),
    ],
)
def test_parse_occurrence_date(value, expected) -> None:
    """Absent or malformed OccurrenceDate values parse to None, never raise."""
    assert _parse_occurrence_date(value) == expected


async def test_vehicle_status_without_alert_date_does_not_raise() -> None:
    """An alert frame with no OccurrenceDate parses instead of raising TypeError."""
    client = _make_client()
    client.controller.get_vehicle_status.return_value = {
        "remoteInfos": [REMOTE_INFO],
        "alertInfos": [{}],
    }

    status = await client.get_vehicle_status(VEHICLE_ID)

    # lastUpdatedTimestamp falls back to the remote frame's date.
    assert status["lastUpdatedTimestamp"] == datetime.datetime(
        2026, 8, 23, 12, 0, tzinfo=datetime.UTC
    )
    # No usable alert timestamp means no cached lock state: the doors dict is
    # empty, so lock_value would otherwise read as "locked" from missing data.
    assert client.get_assumed_lock_state(VEHICLE_ID) is None


async def test_vehicle_status_with_alert_date_caches_lock_state() -> None:
    """A dated alert frame still populates the lock-state cache as before."""
    client = _make_client()
    client.controller.get_vehicle_status.return_value = {
        "remoteInfos": [REMOTE_INFO],
        "alertInfos": [ALERT_INFO],
    }

    status = await client.get_vehicle_status(VEHICLE_ID)

    assert status["lastUpdatedTimestamp"] == datetime.datetime(
        2026, 8, 23, 12, 30, tzinfo=datetime.UTC
    )
    assert status["doorLocks"]["driverDoorUnlocked"] is True
    assert client.get_assumed_lock_state(VEHICLE_ID) is False


async def test_undated_alert_does_not_clobber_assumed_lock_state() -> None:
    """A dateless poll must not override a just-issued lock command.

    Stamping the API value with ``now()`` instead of skipping the write would make
    it newer than the assumed value and snap the lock entity back in the UI.
    """
    client = _make_client()
    client.controller.get_vehicle_status.return_value = {
        "remoteInfos": [REMOTE_INFO],
        "alertInfos": [{}],
    }

    await client.lock_doors(VEHICLE_ID)
    assert client.get_assumed_lock_state(VEHICLE_ID) is True

    await client.get_vehicle_status(VEHICLE_ID)

    assert client.get_assumed_lock_state(VEHICLE_ID) is True


async def test_ev_status_without_occurrence_date_does_not_raise() -> None:
    """The EV status path has the same guard as the alert path."""
    client = _make_client()
    client.controller.get_ev_vehicle_status.return_value = {
        "resultData": [
            {
                "PlusBInformation": {
                    "VehicleInfo": {
                        "ChargeInfo": {"SmaphSOC": 80},
                        "RemoteHvacInfo": {"HVAC": 1},
                    }
                }
            }
        ]
    }

    ev_status = await client.get_ev_vehicle_status(VEHICLE_ID)

    assert ev_status["lastUpdatedTimestamp"] is None
    assert ev_status["hvacInfo"]["hvacOn"] is True
    assert client.get_assumed_hvac_mode(VEHICLE_ID) is None


# --- Undocumented-field watch -------------------------------------------------
#
# Pw.PwPos*, Door.SrSlideSignal/SrTiltSignal and DriveInformation.Drv1AmntFuel have
# never been observed as anything but 0. They are no longer exposed as entities, so a
# warning is the only way a real value would ever surface. Deliberately NOT
# deduplicated: a value that persists warns on every poll.


@pytest.mark.parametrize(
    ("alert", "remote", "expected_key"),
    [
        ({"Pw": {"PwPosDrv": 1}}, {}, "PwPosDrv"),
        ({"Pw": {"PwPosPsngr": 2}}, {}, "PwPosPsngr"),
        ({"Door": {"SrSlideSignal": 1}}, {}, "SrSlideSignal"),
        ({"Door": {"SrTiltSignal": 1}}, {}, "SrTiltSignal"),
        ({}, {"DriveInformation": {"Drv1AmntFuel": 12.5}}, "Drv1AmntFuel"),
    ],
)
def test_warn_undocumented_fields_warns_on_non_zero(
    caplog, alert, remote, expected_key
) -> None:
    """A non-zero undocumented field logs a WARNING naming the field and value."""
    with caplog.at_level("WARNING"):
        _warn_undocumented_fields(VEHICLE_ID, alert, remote)

    assert len(caplog.records) == 1
    record = caplog.records[0]
    assert record.levelname == "WARNING"
    assert expected_key in record.getMessage()
    # Only the ID's tail: the message asks people to post it in a public issue.
    assert "…2345" in record.getMessage()
    assert str(VEHICLE_ID) not in record.getMessage()


@pytest.mark.parametrize(
    ("alert", "remote"),
    [
        # All-zero: the only shape ever observed in the wild.
        (
            {"Pw": {"PwPosDrv": 0, "PwPosPsngr": 0, "PwPosRl": 0, "PwPosRr": 0},
             "Door": {"SrSlideSignal": 0, "SrTiltSignal": 0}},
            {"DriveInformation": {"Drv1AmntFuel": 0.0}},
        ),
        # Groups absent entirely.
        ({}, {}),
        # Groups present but null — Mazda does emit this.
        ({"Pw": None, "Door": None}, {"DriveInformation": None}),
    ],
)
def test_warn_undocumented_fields_silent_on_zero_or_missing(
    caplog, alert, remote
) -> None:
    """Zero, absent, and null values are the expected case and log nothing."""
    with caplog.at_level("WARNING"):
        _warn_undocumented_fields(VEHICLE_ID, alert, remote)

    assert caplog.records == []


@pytest.mark.parametrize("zero", [0, 0.0, -0.0])
def test_warn_undocumented_fields_treats_int_and_float_zero_alike(caplog, zero) -> None:
    """Drv1AmntFuel reports 0.0, the Pw/Door flags report 0 -- both are silent.

    Guards the `value == 0` comparison against being tightened into an identity or
    type check, which would make the float-valued field warn on every single poll.
    """
    with caplog.at_level("WARNING"):
        _warn_undocumented_fields(
            VEHICLE_ID,
            {"Pw": {"PwPosDrv": zero}},
            {"DriveInformation": {"Drv1AmntFuel": zero}},
        )

    assert caplog.records == []


def test_warn_undocumented_fields_warns_on_small_non_zero_float(caplog) -> None:
    """A tiny but non-zero float is still the observation we are hunting for."""
    with caplog.at_level("WARNING"):
        _warn_undocumented_fields(
            VEHICLE_ID, {}, {"DriveInformation": {"Drv1AmntFuel": 0.1}}
        )

    assert len(caplog.records) == 1
    assert "Drv1AmntFuel" in caplog.records[0].getMessage()


def test_warn_undocumented_fields_is_not_deduplicated(caplog) -> None:
    """A value that persists across polls warns every time, by design."""
    alert = {"Pw": {"PwPosDrv": 1}}

    with caplog.at_level("WARNING"):
        _warn_undocumented_fields(VEHICLE_ID, alert, {})
        _warn_undocumented_fields(VEHICLE_ID, alert, {})

    assert len(caplog.records) == 2


async def test_get_vehicle_status_warns_on_undocumented_field(caplog) -> None:
    """The watch is wired into the real get_vehicle_status parse path."""
    client = _make_client()
    client.controller.get_vehicle_status.return_value = {
        "alertInfos": [{**ALERT_INFO, "Pw": {"PwPosRl": 1}}],
        "remoteInfos": [REMOTE_INFO],
    }

    with caplog.at_level("WARNING"):
        await client.get_vehicle_status(VEHICLE_ID)

    assert any("PwPosRl" in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------------------
# Connection retry / 600100 recovery
# ---------------------------------------------------------------------------


def _connection(response: MagicMock) -> tuple[Connection, MagicMock]:
    """Build a Connection over a mocked aiohttp session returning ``response``."""
    session = MagicMock()
    session.request = AsyncMock(return_value=response)
    return Connection("test-sub", "MNAO", AsyncMock(), websession=session), session


async def test_persistent_600100_gives_up_after_max_retries() -> None:
    """A re-attach that did not help is retried MAX_RETRIES times, then given up."""
    conn, _ = _connection(MagicMock(status=200))
    conn.session_refresh_provider = AsyncMock()
    send = AsyncMock(side_effect=MazdaSessionExpiredException("conflict"))
    conn._Connection__send_api_request = send

    with pytest.raises(MazdaException, match="max number of retries"):
        await conn.api_request("POST", "x", needs_keys=False)

    assert send.await_count == MAX_RETRIES + 1
    assert conn.session_refresh_provider.await_count == MAX_RETRIES + 1


async def test_600100_on_attach_raises_without_reattaching() -> None:
    """A 600100 answering attach itself must not call attach again (recursion)."""
    conn, _ = _connection(MagicMock(status=200))
    conn.session_refresh_provider = AsyncMock()
    send = AsyncMock(side_effect=MazdaSessionExpiredException("conflict"))
    conn._Connection__send_api_request = send

    with pytest.raises(MazdaSessionExpiredException):
        await conn.api_request("POST", "remoteServices/attach/v4", needs_keys=False)

    assert send.await_count == 1
    conn.session_refresh_provider.assert_not_awaited()


async def test_600100_on_detach_still_reattaches() -> None:
    """The attach guard must not match the detach endpoint."""
    conn, _ = _connection(MagicMock(status=200))
    conn.session_refresh_provider = AsyncMock()
    send = AsyncMock(
        side_effect=[MazdaSessionExpiredException("conflict"), {"resultCode": "200S00"}]
    )
    conn._Connection__send_api_request = send

    result = await conn.api_request(
        "POST", "remoteServices/detach/v4", needs_keys=False
    )

    assert result == {"resultCode": "200S00"}
    assert send.await_count == 2
    conn.session_refresh_provider.assert_awaited_once()


async def test_rate_limited_response_is_released() -> None:
    """A 429 raises without reading the body, so it must release its connection."""
    resp = MagicMock(status=429)
    conn, _ = _connection(resp)

    with pytest.raises(MazdaRateLimitException):
        await conn._Connection__send_api_request("POST", "service/checkVersion")

    resp.release.assert_called_once()
    resp.json.assert_not_called()


async def test_requests_carry_a_timeout() -> None:
    """Both request sites pass a ClientTimeout (HA's shared session has none)."""
    resp = MagicMock(status=200)
    resp.json = AsyncMock(return_value={"state": "S", "payload": "x"})
    conn, session = _connection(resp)

    with pytest.raises(MazdaException):  # payload is not decryptable; irrelevant here
        await conn._Connection__api_request_to_url("POST", "https://x/checkVersion")
    assert session.request.call_args.kwargs["timeout"].total == REQUEST_TIMEOUT_SECONDS

    session.request.reset_mock()
    with pytest.raises(MazdaException):
        # checkVersion signs with app_code only, so no enc/sign keys are needed.
        await conn._Connection__send_api_request("POST", "service/checkVersion")
    session.request.assert_awaited_once()
    assert session.request.call_args.kwargs["timeout"].total == REQUEST_TIMEOUT_SECONDS


@pytest.mark.parametrize(
    "error",
    [TimeoutError(), aiohttp.ClientConnectionError("refused")],
    ids=["timeout", "connection"],
)
async def test_transport_errors_become_mazda_exceptions(error: Exception) -> None:
    """Entity platforms only catch MazdaException, so transport errors must map to it."""
    conn, session = _connection(MagicMock(status=200))
    session.request.side_effect = error

    with pytest.raises(MazdaConnectionException) as exc_info:
        await conn.api_request("POST", "service/checkVersion")

    assert isinstance(exc_info.value, MazdaException)
    assert exc_info.value.__cause__ is error
    assert session.request.await_count == 1  # transport errors are not retried


async def test_non_json_body_becomes_mazda_exception() -> None:
    """A proxy/HTML body (ContentTypeError) is a transport failure, not a crash."""
    resp = MagicMock(status=502)
    resp.json = AsyncMock(
        side_effect=aiohttp.ContentTypeError(MagicMock(), (), message="not json")
    )
    conn, _ = _connection(resp)

    with pytest.raises(MazdaConnectionException):
        await conn.api_request("POST", "service/checkVersion")


async def test_access_token_provider_runs_before_every_request() -> None:
    """The provider is asked per request, so a refreshed token is used at once."""
    conn, _ = _connection(MagicMock(status=200))
    conn.access_token_provider = AsyncMock(side_effect=["token-1", "token-2"])
    sent_tokens = []

    async def send(*args, **kwargs):
        sent_tokens.append(conn.access_token)

    conn._Connection__send_api_request = send
    await conn.api_request("POST", "x", needs_keys=False, needs_auth=True)
    await conn.api_request("POST", "x", needs_keys=False, needs_auth=True)

    assert sent_tokens == ["token-1", "token-2"]


async def test_600002_retries_with_token_from_provider() -> None:
    """After a 600002 the retry sends whatever token the provider returns next."""
    conn, _ = _connection(MagicMock(status=200))
    conn.access_token_provider = AsyncMock(side_effect=["stale", "fresh"])
    sent_tokens = []

    async def send(*args, **kwargs):
        sent_tokens.append(conn.access_token)
        if conn.access_token == "stale":
            raise MazdaTokenExpiredException("Token expired")
        return {"ok": True}

    conn._Connection__send_api_request = send
    result = await conn.api_request("POST", "x", needs_keys=False, needs_auth=True)

    assert result == {"ok": True}
    assert sent_tokens == ["stale", "fresh"]


async def test_mazda_auth_logs_token_state_only_when_token_changes(caplog) -> None:
    """Per-request calls must not log the token state every time."""
    oauth_session = MagicMock(async_ensure_token_valid=AsyncMock())
    oauth_session.token = {"access_token": "a", "expires_at": 100.0}
    auth = MazdaAuth(oauth_session)

    with caplog.at_level("DEBUG", logger="custom_components.mazda_cs.api"):
        assert await auth.async_get_access_token() == "a"
        assert await auth.async_get_access_token() == "a"
        oauth_session.token = {"access_token": "b", "expires_at": 200.0}
        assert await auth.async_get_access_token() == "b"

    assert caplog.text.count("Token state") == 2
    assert oauth_session.async_ensure_token_valid.await_count == 3


def _utc(hour: int, minute: int, second: int) -> datetime.datetime:
    return datetime.datetime(2026, 11, 22, hour, minute, second, tzinfo=datetime.UTC)


def _position_frame(lat, lon, acquired=None, *, lat_flag=0, lon_flag=0) -> dict:
    info = {
        "Latitude": lat,
        "LatitudeFlag": lat_flag,
        "Longitude": lon,
        "LongitudeFlag": lon_flag,
    }
    if acquired is not None:
        info["AcquisitionDatetime"] = acquired
    return {"OccurrenceDate": "20261122180000", "PositionInfo": info}


async def _status_position(remote: dict, alert: dict) -> tuple:
    client = _make_client()
    client.controller.get_vehicle_status.return_value = {
        "remoteInfos": [remote],
        "alertInfos": [alert],
    }
    status = await client.get_vehicle_status(VEHICLE_ID)
    return status["latitude"], status["longitude"], status["positionTimestamp"]


@pytest.mark.parametrize(
    ("remote", "alert", "expected"),
    [
        pytest.param(
            _position_frame(10.0, 20.0, "20261122181828"),
            _position_frame(11.0, 21.0, "20261122193811"),
            (11.0, -21.0, _utc(19, 38, 11)),
            id="alert-newer",
        ),
        pytest.param(
            _position_frame(10.0, 20.0, "20261122193811"),
            _position_frame(11.0, 21.0, "20261122181828"),
            (10.0, -20.0, _utc(19, 38, 11)),
            id="remote-newer",
        ),
        pytest.param(
            _position_frame(10.0, 20.0, "20261122181828"),
            {"OccurrenceDate": "20261122193855"},
            (10.0, -20.0, _utc(18, 18, 28)),
            id="alert-without-position",
        ),
        pytest.param(
            _position_frame(10.0, 20.0, "not-a-date"),
            _position_frame(11.0, 21.0, "20261122181828"),
            (11.0, -21.0, _utc(18, 18, 28)),
            id="dated-beats-malformed",
        ),
        pytest.param(
            _position_frame(10.0, 20.0, "20261122181828"),
            _position_frame(11.0, 21.0, "20261122181828"),
            (10.0, -20.0, _utc(18, 18, 28)),
            id="tie-keeps-remote",
        ),
        pytest.param(
            _position_frame(10.0, 20.0),
            _position_frame(11.0, 21.0),
            (10.0, -20.0, None),
            id="both-undated-keeps-remote",
        ),
        pytest.param({}, {}, (None, None, None), id="no-position"),
    ],
)
async def test_vehicle_status_uses_newest_position(remote, alert, expected) -> None:
    """Coordinates and positionTimestamp come from the frame with the newer fix."""
    assert await _status_position(remote, alert) == expected


async def test_position_flags_set_hemisphere() -> None:
    """LatitudeFlag 1 is south (negative); LongitudeFlag 1 is east (positive)."""
    remote = _position_frame(10.0, 20.0, "20261122181828", lat_flag=1, lon_flag=1)

    lat, lon, _ = await _status_position(remote, {})

    assert (lat, lon) == (-10.0, 20.0)


# ---------------------------------------------------------------------------
# MSG400101: another remote command is still running (fail fast)
# ---------------------------------------------------------------------------


_IN_PROGRESS = MazdaRequestInProgressException("in progress")
_OK = {"resultCode": "200S00"}


@pytest.mark.parametrize(
    ("responses", "outcome", "sends"),
    [
        pytest.param([_IN_PROGRESS, _OK], _OK, 2, id="resend-succeeds"),
        pytest.param(
            [_IN_PROGRESS, _IN_PROGRESS], _IN_PROGRESS, 2, id="still-in-progress-raises"
        ),
        pytest.param(
            [_IN_PROGRESS, MazdaTokenExpiredException("600002"), _OK],
            _OK,
            3,
            id="600002-on-resend-still-handled",
        ),
        pytest.param(
            [_IN_PROGRESS, MazdaTokenExpiredException("600002"), _IN_PROGRESS],
            _IN_PROGRESS,
            3,
            id="only-one-in-progress-resend",
        ),
    ],
)
async def test_request_in_progress_is_resent_once(
    monkeypatch: pytest.MonkeyPatch, responses, outcome, sends
) -> None:
    """MSG400101 gets one re-send after REQUEST_IN_PROGRESS_RETRY_SECONDS, separate
    from MAX_RETRIES; a second MSG400101 raises."""
    sleep = AsyncMock()
    monkeypatch.setattr(connection_module.asyncio, "sleep", sleep)
    conn, _ = _connection(MagicMock(status=200))
    send = AsyncMock(side_effect=responses)
    conn._Connection__send_api_request = send
    request = conn.api_request("POST", "remoteServices/doorLock/v4", needs_keys=False)

    if isinstance(outcome, Exception):
        with pytest.raises(type(outcome)):
            await request
    else:
        assert await request == outcome

    assert send.await_count == sends
    sleep.assert_awaited_once_with(REQUEST_IN_PROGRESS_RETRY_SECONDS)


def test_request_in_progress_is_a_mazda_exception() -> None:
    """Entity platforms catch MazdaException, so this surfaces as a HomeAssistantError."""
    assert issubclass(MazdaRequestInProgressException, MazdaException)


@pytest.mark.parametrize(
    ("command", "controller_method", "getter", "expected"),
    [
        ("lock_doors", "door_lock", "get_assumed_lock_state", True),
        ("unlock_doors", "door_unlock", "get_assumed_lock_state", False),
        ("turn_on_hvac", "hvac_on", "get_assumed_hvac_mode", True),
        ("turn_off_hvac", "hvac_off", "get_assumed_hvac_mode", False),
    ],
)
async def test_assumed_value_saved_only_when_command_accepted(
    command, controller_method, getter, expected
) -> None:
    """A rejected command leaves no assumed value; an accepted one sets it."""
    client = _make_client()
    send = getattr(client.controller, controller_method)
    send.side_effect = MazdaRequestInProgressException("in progress")

    with pytest.raises(MazdaRequestInProgressException):
        await getattr(client, command)(VEHICLE_ID)
    assert getattr(client, getter)(VEHICLE_ID) is None

    send.side_effect = None
    await getattr(client, command)(VEHICLE_ID)
    assert getattr(client, getter)(VEHICLE_ID) is expected


async def test_assumed_hvac_setting_saved_only_when_accepted() -> None:
    """set_hvac_setting stores the assumed setting only after Mazda accepts it."""
    client = _make_client()
    client.controller.set_hvac_setting.side_effect = MazdaException("rejected")

    with pytest.raises(MazdaException):
        await client.set_hvac_setting(VEHICLE_ID, 21.0, "C", True, False)
    assert client.get_assumed_hvac_setting(VEHICLE_ID) is None

    client.controller.set_hvac_setting.side_effect = None
    await client.set_hvac_setting(VEHICLE_ID, 21.0, "C", True, False)
    assert client.get_assumed_hvac_setting(VEHICLE_ID)["temperature"] == 21.0
