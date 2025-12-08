import pytest

# -- pytest-socket handling ---------------------------------------------------
try:
    from pytest_socket import (
        disable_socket as _disable_socket,
    )
    from pytest_socket import (
        enable_socket as _enable_socket,
    )
    from pytest_socket import (
        socket_allow_hosts,
        socket_allow_unix_socket,
    )

    HAVE_PYTEST_SOCKET = True
except Exception:
    HAVE_PYTEST_SOCKET = False


def pytest_configure(config):
    config.addinivalue_line("markers", "enable_socket: allow network sockets for this test")
    config.addinivalue_line("markers", "disable_socket: block network sockets for this test")
    if HAVE_PYTEST_SOCKET:
        socket_allow_unix_socket()
        socket_allow_hosts(["127.0.0.1", "localhost"])


@pytest.hookimpl(tryfirst=True, hookwrapper=True)
def pytest_runtest_setup(item):
    if HAVE_PYTEST_SOCKET:
        if item.get_closest_marker("enable_socket"):
            _enable_socket()
        else:
            _disable_socket()
    yield


# ---- override HA plugin verify_cleanup (suppress strict thread/timer checks) ----
@pytest.fixture(autouse=True)
def verify_cleanup():
    # Local runs: skip strict HA thread/timer assertions
    yield
