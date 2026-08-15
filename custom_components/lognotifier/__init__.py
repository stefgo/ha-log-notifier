"""The Log Notifier integration for Home Assistant."""

from __future__ import annotations

import logging
from datetime import timedelta
from pathlib import Path

from homeassistant.components.frontend import add_extra_js_url
from homeassistant.components.http import StaticPathConfig
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.event import async_track_time_interval
from homeassistant.helpers.storage import Store

from .api import LogNotifierIngestView
from .const import (
    CARD_FILENAME,
    CARD_URL_PATH,
    DOMAIN,
    INTEGRATION_VERSION,
    STORAGE_KEY,
    STORAGE_VERSION,
)
from .device import async_remove_stale_devices, async_track_device_renames
from .runtime import LogNotifierConfigEntry, LogNotifierRuntime
from .services import async_setup_services
from .store import MessageStore
from .websocket_api import async_register_websocket_api

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]
PURGE_INTERVAL = timedelta(hours=6)

DATA_SETUP_DONE = f"{DOMAIN}_setup_done"


async def async_setup_entry(hass: HomeAssistant, entry: LogNotifierConfigEntry) -> bool:
    """Set up the integration."""
    store = MessageStore(Store(hass, STORAGE_VERSION, STORAGE_KEY))
    await store.async_load()
    runtime = LogNotifierRuntime(hass, entry, store)
    entry.runtime_data = runtime

    # The HTTP view, WebSocket commands, services and the card belong to the
    # running HA instance, not to the entry: register them once, otherwise the
    # second call fails when the entry is reloaded.
    if not hass.data.get(DATA_SETUP_DONE):
        hass.http.register_view(LogNotifierIngestView(hass))
        async_register_websocket_api(hass)
        async_setup_services(hass)
        await _async_register_card(hass)
        hass.data[DATA_SETUP_DONE] = True

    entry.async_on_unload(
        async_track_time_interval(
            hass,
            lambda _now: store.purge_aged(),
            PURGE_INTERVAL,
            cancel_on_shutdown=True,
        )
    )
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    entry.async_on_unload(async_track_device_renames(hass, entry))

    # Before the platforms: a deleted channel leaves its device behind, and it
    # has to be gone before the remaining entities are registered again.
    async_remove_stale_devices(hass, entry)

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # On first start nobody is listening yet; after a reload caused by changed
    # channels the open cards pick up their new state here.
    runtime.notify_channels()
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: LogNotifierConfigEntry
) -> bool:
    """Unload the platforms.

    The view, the services and the card stay registered — they belong to the
    instance and are reused on the next setup.
    """
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(
    hass: HomeAssistant, entry: LogNotifierConfigEntry
) -> None:
    """Reload after channel changes — entities follow the channels."""
    await hass.config_entries.async_reload(entry.entry_id)


async def _async_register_card(hass: HomeAssistant) -> None:
    """Serve the Lovelace card and register it with the frontend.

    This removes the need to maintain a Lovelace resource by hand; if the build
    is missing (a checkout without ``npm run build``), nothing happens at all.
    """
    www_dir = Path(__file__).parent / "www"
    card_file = www_dir / CARD_FILENAME
    if not await hass.async_add_executor_job(card_file.is_file):
        _LOGGER.warning(
            "Card %s not found — please run 'npm run build' in the card/ "
            "directory and deploy again",
            card_file,
        )
        return

    await hass.http.async_register_static_paths(
        [StaticPathConfig(CARD_URL_PATH, str(www_dir), False)]
    )
    # Version in the query string: otherwise the browser keeps holding on to
    # the old card after an update.
    add_extra_js_url(hass, f"{CARD_URL_PATH}/{CARD_FILENAME}?v={INTEGRATION_VERSION}")
