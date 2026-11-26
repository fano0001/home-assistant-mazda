"""Tests that account identifiers stay out of log output."""

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.mazda_cs import (
    _check_service_permissions,
    _enable_all_notify_settings,
)
from custom_components.mazda_cs.diagnostics import TO_REDACT_INFO
from custom_components.mazda_cs.pymazda.connection import (
    Connection,
    _redact,
    mask_email,
    tail,
)
from custom_components.mazda_cs.pymazda.exceptions import MazdaException
from custom_components.mazda_cs.pymazda.push import _register
from custom_components.mazda_cs.pymazda.push._conductor import summarize_error_body

VIN = "JM1TESTVIN0001234"


@pytest.mark.parametrize(
    ("email", "expected"),
    [
        ("a@example.com", "•••@ex•••.com"),
        # 2 to 8 characters look the same.
        ("al@example.com", "al•••@ex•••.com"),
        ("abc@example.com", "ab•••@ex•••.com"),
        ("alex@example.com", "al•••@ex•••.com"),
        ("alexande@example.com", "al•••@ex•••.com"),
        ("alexander@example.com", "al•••er@ex•••.com"),
        # Two plus-addresses of one mailbox stay distinguishable.
        ("alex+mazda@example.com", "al•••da@ex•••.com"),
        ("alex+home@example.com", "al•••me@ex•••.com"),
        (" alex@example.com ", "al•••@ex•••.com"),
        # A personal domain can identify its owner, so it is masked too.
        ("alex@12345678.xyz", "al•••@12•••.xyz"),
        ("alex@mail.example.co.uk", "al•••@ma•••.uk"),
        ("alex@alexandersmith.com", "al•••@al•••.com"),
        ("alex@gmail.com", "al•••@gm•••.com"),
        ("alex@x.org", "al•••@x•••.org"),
        ("alex@localhost", ""),
        ("alex@.com", ""),
        ("not-an-email", ""),
        ("@example.com", ""),
        ("alex@", ""),
        ("", ""),
    ],
)
def test_mask_email(email: str, expected: str) -> None:
    """Local part and domain are masked; anything but an address gives nothing."""
    assert mask_email(email) == expected


def test_redact_treats_every_listed_key() -> None:
    """Each listed key is masked or cut to its tail at any depth; others are kept."""
    # Spelled out here, so dropping a key in connection.py fails this test.
    masked = (
        "vin",
        "internalVin",
        "imei",
        "iccId",
        "visitNo",
        "sessionId",
        "contactMailAddress",
        "custId",
        "usherId",
        "firstName",
        "familyName",
    )
    tailed = ("rucId", "rccId", "internalUserId", "mazdaId")
    ids = dict.fromkeys(masked + tailed, "value-1234")

    # Attach's lowercase "userinfo" is not a listed key: each ID matches by itself.
    redacted = _redact({"resultCode": "200S00", "data": [{"userinfo": ids}]})

    expected = dict.fromkeys(masked, "**REDACTED**") | dict.fromkeys(tailed, "…1234")
    assert redacted == {"resultCode": "200S00", "data": [{"userinfo": expected}]}


def test_redact_masks_whole_values_keeping_blanks_and_signs() -> None:
    """All of userInfo and coordinates is masked; blanks and a minus sign remain."""
    redacted = _redact(
        {
            "userInfo": {
                "mailAddress": "alex@example.com",
                "streetAddress2": "",
                "state": None,
                "optIn": 0,
                "phones": [{"e164": "+15550100"}, {"e164": ""}],
            },
            "Longitude": -20.5,
            "Latitude": 10.5,
        }
    )

    hidden = "**REDACTED**"
    assert redacted == {
        "userInfo": {
            "mailAddress": hidden,
            "streetAddress2": "",
            "state": None,
            "optIn": hidden,
            "phones": [{"e164": hidden}, {"e164": ""}],
        },
        "Longitude": f"-{hidden}",
        "Latitude": hidden,
    }


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
    assert summarize_error_body(text) == expected


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


async def test_failed_permission_check_shows_only_vin_tail(caplog) -> None:
    """A failed getAvailableService names the vehicle like the other warnings."""
    client = MagicMock()
    client.get_available_service = AsyncMock(side_effect=Exception("boom"))

    await _check_service_permissions(client, [{"id": 201106933, "vin": VIN}])

    assert "…1234" in caplog.text
    assert VIN not in caplog.text
    assert "201106933" not in caplog.text


@pytest.mark.parametrize("via_fis", [True, False])
async def test_push_registration_logs_only_android_id_tail(caplog, via_fis) -> None:
    """Neither the FIS nor the fallback path prints the full android_id."""
    device = {"androidId": "4567890123456789", "securityToken": "1"}
    creds = {"android_id": device["androidId"], "token": "fcm-token"}

    with (
        caplog.at_level(logging.DEBUG),
        patch.object(_register, "gcm_check_in", AsyncMock(return_value=device)),
        patch.object(
            _register,
            "fcm_get_token_via_fis",
            AsyncMock(return_value=creds if via_fis else None),
        ),
        patch.object(_register, "gcm_register", AsyncMock(return_value="fcm-token")),
    ):
        assert await _register.checkin_and_register(MagicMock())

    assert "android_id=…6789" in caplog.text
    assert device["androidId"] not in caplog.text


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
