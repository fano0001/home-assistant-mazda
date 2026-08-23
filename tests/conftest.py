"""Common fixtures for the Mazda Connected Services tests."""

import pytest

# Load the community test harness (vendors HA's ``tests.common`` helpers and the
# ``hass`` / ``enable_custom_integrations`` fixtures for the pinned HA release).
pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading of the ``mazda_cs`` custom integration in every test."""
    yield
