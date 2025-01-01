"""Constants for the Mazda Connected Services integration."""
from datetime import timedelta

DOMAIN = "mazda_cs"
DATA_CLIENT = "client"
DATA_COORDINATOR = "coordinator"
DATA_REGION = "region"
DATA_VEHICLES = "vehicles"
DATA_ENTITY_MANAGER = "entity_manager"
DATA_INTEGRATION_HELPER = "integration_helper"

# Update intervals
UPDATE_INTERVAL = timedelta(minutes=5)
HEALTH_CHECK_INTERVAL = timedelta(minutes=15)
HEALTH_CHECK_TIMEOUT = 120  # seconds
HEALTH_CHECK_MAX_FAILURES = 3

# Entity update settings
BATCH_SIZE = 2
BATCH_DELAY = 30  # seconds
REQUEST_DELAY = 10  # seconds
MAX_RETRIES = 5

# Connection settings
MAX_BACKOFF_TIME = 300  # seconds
INITIAL_BACKOFF_TIME = 5  # seconds

# Platform definitions
from homeassistant.const import Platform

PLATFORMS = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.CLIMATE,
    Platform.DEVICE_TRACKER,
    Platform.LOCK,
    Platform.SENSOR,
    Platform.SWITCH
]
