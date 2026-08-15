"""Diagnostics data — channel states without tokens."""

from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import INTEGRATION_VERSION
from .runtime import LogNotifierConfigEntry


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: LogNotifierConfigEntry
) -> dict[str, Any]:
    """State of the integration.

    The channel tokens are credentials and deliberately do not appear here
    anywhere — not even truncated.
    """
    runtime = entry.runtime_data
    return {"version": INTEGRATION_VERSION, **runtime.diagnostics()}
