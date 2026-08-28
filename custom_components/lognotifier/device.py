"""Keep the channel devices in sync with the channel options.

Two directions: a device rename in the UI becomes the channel name, and a
channel that no longer exists takes its device with it.

A channel has two faces: the name in the integration's options (it appears in
the card and in the message events) and the device that Home Assistant builds
from it. Anyone renaming a device in the UI means the channel — not merely a
label. Instead of letting that gesture run into the void, the integration picks
the name up and makes it the channel name; there is no longer a wrong place to
rename.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import CALLBACK_TYPE, Event, HomeAssistant, callback
from homeassistant.helpers import device_registry as dr

from .const import CONF_CHANNELS, CONF_NAME, DOMAIN


@callback
def async_remove_stale_devices(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Delete the devices of channels that no longer exist.

    Removing a channel only takes it out of the options; its device and the
    entities on it would otherwise stay behind in the registry as an orphan
    nobody can get rid of. Called on every setup, so a reload after a deletion
    cleans up. The totals device identifies itself by the ``entry_id`` and stays
    as long as the entry does.
    """
    registry = dr.async_get(hass)
    known = set(entry.options.get(CONF_CHANNELS, {})) | {entry.entry_id}
    for device in dr.async_entries_for_config_entry(registry, entry.entry_id):
        identifiers = {
            ident for domain, ident in device.identifiers if domain == DOMAIN
        }
        if identifiers & known:
            continue
        # Detach instead of delete: the registry removes the device itself once
        # no config entry is left on it, and takes its entities along.
        registry.async_update_device(device.id, remove_config_entry_id=entry.entry_id)


@callback
def async_track_device_renames(
    hass: HomeAssistant, entry: ConfigEntry
) -> CALLBACK_TYPE:
    """Listen for channel device renames; the return value unsubscribes."""

    async def _handle(event: Event) -> None:
        data: dict[str, Any] = event.data
        if data.get("action") != "update":
            return
        if "name_by_user" not in (data.get("changes") or {}):
            return

        registry = dr.async_get(hass)
        device = registry.async_get(data["device_id"])
        if device is None or entry.entry_id not in device.config_entries:
            return

        new_name = (device.name_by_user or "").strip()
        if not new_name:
            # The user-defined name was removed — the channel name from the
            # options applies again anyway. This is also where the path taken
            # by the update call below when it re-enters here comes to an end.
            return

        channel_id = next(
            (ident for domain, ident in device.identifiers if domain == DOMAIN), None
        )
        if channel_id is None:
            return
        channels = deepcopy(dict(entry.options.get(CONF_CHANNELS, {})))
        channel = channels.get(channel_id)
        if channel is None:
            return

        # First take back HA's own name: it takes precedence over the name from
        # the integration and would otherwise keep masking every later change in
        # the options.
        registry.async_update_device(device.id, name_by_user=None)

        if channel.get(CONF_NAME) == new_name:
            return
        channel[CONF_NAME] = new_name
        channels[channel_id] = channel
        # The update listener reloads the entry; device, entities and card all
        # carry the same name afterwards.
        hass.config_entries.async_update_entry(
            entry, options={**entry.options, CONF_CHANNELS: channels}
        )

    return hass.bus.async_listen(dr.EVENT_DEVICE_REGISTRY_UPDATED, _handle)
