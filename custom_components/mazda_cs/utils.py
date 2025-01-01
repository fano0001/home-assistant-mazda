"""Utility functions for the Mazda Connected Services integration."""
import asyncio
from asyncio import timeout
import logging

_LOGGER = logging.getLogger(__name__)

async def with_timeout(task, timeout_seconds=120):
    """Run an async task with a timeout."""
    try:
        async with timeout(timeout_seconds):
            return await task
    except asyncio.TimeoutError:
        _LOGGER.warning("Timeout occurred while waiting for Mazda API response")
        return None
    except Exception as ex:
        _LOGGER.warning("Error occurred during Mazda API request: %s", ex)
        return None
