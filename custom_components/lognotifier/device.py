"""Mirror a channel device rename back into the channel options.

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
