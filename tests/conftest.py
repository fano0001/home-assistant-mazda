# tests/conftest.py
"""
Pytest configuration for local + CI:
- Block sockets by default via pytest-socket.
- Allow localhost (127.0.0.1) + UNIX sockets automatically for tests using `aiohttp_server`.
- Register marks to avoid warnings.
- Keep Home Assistant plugin's strict cleanup in CI, relax locally.
"""

from __future__ import annotations

import os
import pytest

# ---- pytest-socket integration (optional) ----
try:
    from pytest_socket import (
        enable_socket as _enable_socket,
        disable_socket as _disable_socket,
        socket_allow_hosts,
        socket_allow_unix_socket,
    )

    HAVE_PYTEST_SOCKET = True
except Exception:  # plugin not installed
    HAVE_PYTEST_SOCKET = False


def pytest_configure(config: pytest.Config) -> None:
    # Register custom markers to prevent unknown mark warnings
    config.addinivalue_line("markers", "enable_socket: allow network sockets for this test")
    config.addinivalue_line("markers", "disable_socket: block network sockets for this test")

    if HAVE_PYTEST_SOCKET:
        # aiohttp + asyncio need UNIX sockets; our test servers bind on localhost
        socket_allow_unix_socket()
        socket_allow_hosts(["127.0.0.1", "localhost"])


def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Auto-mark tests that use aiohttp_server to allow localhost sockets."""
    for item in items:
        fixturenames = getattr(item, "fixturenames", ()) or ()
        if "aiohttp_server" in fixturenames:
            item.add_marker(pytest.mark.enable_socket)


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_setup(item: pytest.Item):
    """
    Default: sockets OFF (blocked).
    If test is marked with @pytest.mark.enable_socket (set above automatically for aiohttp_server),
    enable sockets for this test.
    """
    if HAVE_PYTEST_SOCKET:
        if item.get_closest_marker("enable_socket"):
            _enable_socket()
        else:
            _disable_socket()
    yield


# ---- Home Assistant plugin strict cleanup handling ----
# Keep strict behavior in CI, but relax locally to avoid flakiness from timers/threads.
if not (os.getenv("CI") or os.getenv("GITHUB_ACTIONS")):
    # Local-only: completely bypass HA's strict verify_cleanup assertions
    @pytest.fixture(autouse=True)
    def verify_cleanup():
        # Skip thread/timer assertions locally
        yield

    # Local-only: if HA plugin still inspects these, mark lingering as expected
    @pytest.fixture
    def expected_lingering_timers():
        return True

    @pytest.fixture
    def expected_lingering_tasks():
        return True
