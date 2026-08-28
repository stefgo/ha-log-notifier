"""Fixtures for the tests that need a real Home Assistant.

These are deliberately separate from ``tests/`` next door: that suite runs on
nothing but pytest and must stay that way, because the modules it covers are
the ones without a framework dependency. Everything here needs the real thing —
the config flow, the ingest view, the service registry and the WebSocket
commands cannot be faked usefully.
"""

from __future__ import annotations

from typing import Any

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.lognotifier.const import (
    CONF_BADGE_LEVELS,
    CONF_CHANNELS,
    CONF_ENABLED,
    CONF_ICON,
    CONF_MAX_AGE_DAYS,
    CONF_MAX_MESSAGES,
    CONF_NAME,
    CONF_TOKEN,
    DEFAULT_BADGE_LEVELS,
    DEFAULT_MAX_AGE_DAYS,
    DEFAULT_MAX_MESSAGES,
    DOMAIN,
)

BACKUP_TOKEN = "token-backups"
SERVICE_TOKEN = "token-services"


def channel_options(
    channel_id: str = "backups",
    *,
    name: str = "Backups",
    token: str = BACKUP_TOKEN,
    enabled: bool = True,
    **overrides: Any,
) -> dict[str, dict[str, Any]]:
    """One channel in the shape the options flow writes it."""
    return {
        channel_id: {
            CONF_NAME: name,
            CONF_TOKEN: token,
            CONF_ICON: "mdi:backup-restore",
            CONF_BADGE_LEVELS: list(DEFAULT_BADGE_LEVELS),
            CONF_MAX_MESSAGES: DEFAULT_MAX_MESSAGES,
            CONF_MAX_AGE_DAYS: DEFAULT_MAX_AGE_DAYS,
            CONF_ENABLED: enabled,
            **overrides,
        }
    }


TWO_CHANNELS = {
    **channel_options(),
    **channel_options("services", name="Services", token=SERVICE_TOKEN),
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Let Home Assistant find custom_components/lognotifier at all."""
    return enable_custom_integrations


@pytest.fixture
def entry_options() -> dict[str, Any]:
    """Options of the config entry — override per test module or test."""
    return {CONF_CHANNELS: TWO_CHANNELS}


@pytest.fixture
def config_entry(hass, entry_options) -> MockConfigEntry:
    """A config entry, added to hass but not set up yet."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="Log Notifier",
        data={},
        options=entry_options,
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def setup_entry(hass, config_entry) -> MockConfigEntry:
    """A config entry that has been set up: view, services and entities live."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


@pytest.fixture
def runtime(setup_entry):
    """The runtime object of the set-up entry."""
    return setup_entry.runtime_data
