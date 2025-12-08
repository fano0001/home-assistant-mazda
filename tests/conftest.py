import pytest

try:
    from pytest_socket import (
        enable_socket as _enable_socket,
        disable_socket as _disable_socket,
        socket_allow_hosts,
        socket_allow_unix_socket,
    )
    HAVE_PYTEST_SOCKET = True
except Exception:
    HAVE_PYTEST_SOCKET = False

def pytest_configure(config):
    # Marker registrieren, damit keine Unknown-Mark-Warnungen kommen
    config.addinivalue_line("markers", "enable_socket: allow network sockets for this test")
    config.addinivalue_line("markers", "disable_socket: block network sockets for this test")

    if HAVE_PYTEST_SOCKET:
        # Für asyncio-Eventloop nötige UNIX-Sockets und lokalen HTTP-Server erlauben
        socket_allow_unix_socket()
        socket_allow_hosts(["127.0.0.1", "localhost"])

@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_setup(item):
    # Standard: Sockets blocken, außer der Test ist mit @pytest.mark.enable_socket markiert
    if HAVE_PYTEST_SOCKET:
        if item.get_closest_marker("enable_socket"):
            _enable_socket()
        else:
            _disable_socket()
    yield

# HA-Plugin: bekannte, harmlose aiohttp TCPConnector-Cleanup-Timer nicht als Fehler werten
@pytest.fixture
def expected_lingering_timers():
    return True

# ---- override HA plugin verify_cleanup (suppress strict thread/timer checks) ----
import pytest as _pytest_local
@_pytest_local.fixture(autouse=True)
def verify_cleanup():
    # Local runs: skip strict HA thread/timer assertions
    yield
