"""Tests for vehicle-status parsing in ``pymazda/client.py``.

Focus: Mazda's ``OccurrenceDate`` timestamps are not guaranteed to be present. A
vehicle that has not yet reported — e.g. one just re-enrolled after a Connected
Services subscription lapse (issue #63) — returns an alert frame with the field
missing, which used to raise ``TypeError: strptime() argument 1 must be str, not
None`` and trap the config entry in a setup-retry loop.
"""

import datetime
from unittest.mock import AsyncMock

import pytest

from custom_components.mazda_cs.pymazda.client import Client, _parse_occurrence_date

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
