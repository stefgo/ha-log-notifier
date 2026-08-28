"""Diagnostics — what a user attaches to a bug report.

The channel tokens are credentials: they are ingest URLs in disguise, and
anyone who has one can post into that channel. They must not appear here, not
even truncated, which is what this test is for.
"""

from __future__ import annotations

import json

from homeassistant.core import HomeAssistant

from custom_components.lognotifier.const import (
    ATTR_CHANNEL_ID,
    ATTR_CONTENT,
    DOMAIN,
)
from custom_components.lognotifier.diagnostics import (
    async_get_config_entry_diagnostics,
)
from custom_components.lognotifier.services import SERVICE_SEND

from .conftest import BACKUP_TOKEN, SERVICE_TOKEN


async def test_diagnostics_describe_the_channels(
    hass: HomeAssistant, setup_entry
) -> None:
    """Enough to understand a report: channels, counters, rate limit."""
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {ATTR_CHANNEL_ID: "backups", ATTR_CONTENT: "hello"},
        blocking=True,
    )

    data = await async_get_config_entry_diagnostics(hass, setup_entry)

    assert data["domain"] == DOMAIN
    assert data["version"]
    assert {channel["id"] for channel in data["channels"]} == {"backups", "services"}
    backups = next(c for c in data["channels"] if c["id"] == "backups")
    assert backups["unread"] == 1
    assert "rate_limit" in data


async def test_diagnostics_contain_no_token(hass: HomeAssistant, setup_entry) -> None:
    """Not under a key, not in a URL, not as a substring anywhere."""
    data = await async_get_config_entry_diagnostics(hass, setup_entry)

    dumped = json.dumps(data)
    assert BACKUP_TOKEN not in dumped
    assert SERVICE_TOKEN not in dumped
    assert "token" not in dumped.lower()
