"""Tests that account identifiers stay out of log output."""

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

from custom_components.mazda_cs import (
    _check_service_permissions,
    _enable_all_notify_settings,
)
from custom_components.mazda_cs.diagnostics import TO_REDACT_INFO
from custom_components.mazda_cs.fcm_listener import _summarize_error_body
from custom_components.mazda_cs.pymazda.connection import Connection, _redact, tail
from custom_components.mazda_cs.pymazda.exceptions import MazdaException

VIN = "JM1TESTVIN0001234"


def test_redact_hides_account_identifiers() -> None:
    """Attach, getUserInfo and getCvUserIds identifiers are redacted at any depth."""
    payload = {
        "data": {
            "userinfo": {"sessionId": "sess-1"},
            "customerInfo": {"internalUserId": "iu-1"},
        },
        "userInfo": {"contactMailAddress": "alex@example.com"},
        "custId": "c-1",
        "usherId": "u-1",
        "resultCode": "200S00",
    }

    redacted = str(_redact(payload))

    for secret in ("sess-1", "iu-1", "alex@example.com", "c-1", "u-1"):
        assert secret not in redacted
    assert "200S00" in redacted


@pytest.mark.parametrize(
    ("value", "expected"),
    [(VIN, "…1234"), ("ab", "…ab"), (None, "(MISSING)"), ("", "(MISSING)")],
)
def test_tail(value, expected) -> None:
    """Only the last 4 characters are shown; a missing value stands out."""
    assert tail(value) == expected


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        (
            '{"state": "F", "errorCode": 500, "message": "bad", "payload": "SECRET"}',
            "{'state': 'F', 'errorCode': 500, 'message': 'bad'}",
        ),
        ('{"payload": "SECRET"}', "(no error fields)"),
        ("<html>" + "x" * 200, "<html>" + "x" * 94),
        ("", "(empty)"),
        (None, "(empty)"),
    ],
)
def test_summarize_error_body(text, expected) -> None:
    """Error bodies keep their error fields and never the encrypted payload."""
    assert _summarize_error_body(text) == expected


async def test_check_version_failure_omits_payload(caplog) -> None:
    """A failed checkVersion reports its error code, not the response payload."""
    response = MagicMock(status=200)
    response.json = AsyncMock(
        return_value={"state": "E", "errorCode": 600001, "payload": "SECRETPAYLOAD"}
    )
    session = MagicMock(request=AsyncMock(return_value=response))
    conn = Connection("test-sub", "MNAO", AsyncMock(), websession=session)

    with (
        caplog.at_level(logging.DEBUG),
        pytest.raises(MazdaException, match="600001") as exc,
    ):
        await conn._Connection__api_request_to_url("POST", "https://x/checkVersion")

    assert "SECRETPAYLOAD" not in str(exc.value)
    assert "SECRETPAYLOAD" not in caplog.text


async def test_permission_warnings_show_only_vin_tail(caplog) -> None:
    """Missing-permission warnings name the vehicle by the VIN's last 4 only."""
    client = MagicMock()
    client.get_available_service = AsyncMock(
        return_value={"vehicleStatusAlert": 0, "healthReports": 0, "remoteControl": 0}
    )

    with caplog.at_level(logging.DEBUG):
        result = await _check_service_permissions(client, [{"id": 1, "vin": VIN}])

    assert result == (False, False)
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 3
    assert all("…1234" in r.getMessage() for r in warnings)
    assert VIN not in caplog.text


async def test_notify_settings_logs_only_vin_tail(caplog) -> None:
    """The notify-settings debug lines do not print the full VIN."""
    client = MagicMock()
    client.get_notify_setting = AsyncMock(return_value={"remoteControl": 1})

    with caplog.at_level(logging.DEBUG):
        await _enable_all_notify_settings(client, [{"id": 1, "vin": VIN}])

    assert "…1234" in caplog.text
    assert VIN not in caplog.text


def test_diagnostics_redact_client_info() -> None:
    """B2C client_info encodes the user's object id and is redacted."""
    assert "client_info" in TO_REDACT_INFO
