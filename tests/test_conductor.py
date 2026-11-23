"""Tests for how the Conductor push registration outcome is reported."""

import json
import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from custom_components.mazda_cs.pymazda.push import MazdaPushClient

_POST = "custom_components.mazda_cs.pymazda.push._conductor._post_conductor"
_OK = (200, json.dumps({"state": "S", "payload": "SECRET"}))
_REJECTED_BODY = json.dumps({"state": "F", "errorCode": 600001, "payload": "SECRET"})
_REJECTED = (200, _REJECTED_BODY)
_HTML = (200, "<html>maintenance</html>")


async def _register(caplog: pytest.LogCaptureFixture, *replies) -> AsyncMock:
    client = MazdaPushClient(
        credentials={"token": "fcm-token"},
        credentials_updated_callback=MagicMock(),
        websession=MagicMock(closed=False),
    )
    with (
        caplog.at_level(logging.DEBUG),
        patch(_POST, AsyncMock(side_effect=replies)) as post,
    ):
        await client.register_with_conductor("MNAO", conductor_device_id="device-1234")
    assert "SECRET" not in caplog.text
    return post


def _warnings(caplog: pytest.LogCaptureFixture) -> list[str]:
    return [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]


@pytest.mark.parametrize("state", ["S", "s"])
async def test_accepted(caplog, state) -> None:
    """Both calls accepted: no warning."""
    accepted = (200, json.dumps({"state": state}))

    post = await _register(caplog, accepted, accepted)

    assert post.await_count == 2
    assert not _warnings(caplog)
    assert "Conductor updateuser succeeded" in caplog.text


@pytest.mark.parametrize(
    ("reply", "detail"),
    [
        (_REJECTED, "(HTTP 200): {'state': 'F', 'errorCode': 600001}"),
        (_HTML, "(HTTP 200): <html>maintenance</html>"),
        ((200, "[]"), "(HTTP 200): []"),
        ((200, ""), "(HTTP 200): (empty)"),
        ((500, _REJECTED_BODY), "(HTTP 500): {'state': 'F', 'errorCode': 600001}"),
        ((500, _OK[1]), "(HTTP 500): {'state': 'S'}"),
    ],
)
async def test_rejected_update_user(caplog, reply, detail) -> None:
    """Anything but HTTP 200 with state S is one warning."""
    await _register(caplog, _OK, reply)

    assert _warnings(caplog) == [f"Conductor updateuser rejected {detail}"]
    assert "succeeded" not in caplog.text


@pytest.mark.parametrize(
    ("reply", "detail"),
    [
        (
            _REJECTED,
            "(HTTP 200) — skipping updateuser: {'state': 'F', 'errorCode': 600001}",
        ),
        (_HTML, "(HTTP 200) — skipping updateuser: <html>maintenance</html>"),
        ((500, "boom"), "(HTTP 500) — skipping updateuser: boom"),
    ],
)
async def test_rejected_init_stops(caplog, reply, detail) -> None:
    """A rejected init is one warning, and updateuser is not sent."""
    post = await _register(caplog, reply)

    assert post.await_count == 1
    assert _warnings(caplog) == [f"Conductor init rejected {detail}"]


async def test_accepted_init_without_keys_continues(caplog) -> None:
    """An accepted init with no readable keys still registers."""
    post = await _register(caplog, _OK, _OK)

    assert post.await_count == 2
    assert not _warnings(caplog)
