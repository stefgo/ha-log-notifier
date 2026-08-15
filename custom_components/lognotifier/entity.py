"""Shared base for the channel entities and the total entities."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity import Entity

from .const import (
    DOMAIN,
    INTEGRATION_VERSION,
    SIGNAL_CHANNEL_UPDATED,
    SIGNAL_TOTALS_UPDATED,
    TOTALS_KEY,
)
from .models import Channel
from .runtime import LogNotifierRuntime


class ChannelEntity(Entity):
    """Entity that belongs to exactly one channel.

    Updates are not polled but pushed via a dispatcher signal when a message
    arrives or is acknowledged.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(
        self, runtime: LogNotifierRuntime, channel: Channel, key: str
    ) -> None:
        self.runtime = runtime
        self.channel = channel
        self._attr_unique_id = f"{DOMAIN}_{channel.id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, channel.id)},
            name=channel.name,
            manufacturer="Log Notifier",
            model="Channel",
            sw_version=INTEGRATION_VERSION,
        )

    @property
    def available(self) -> bool:
        """A disabled channel does not accept anything."""
        return self.channel.enabled

    async def async_added_to_hass(self) -> None:
        """Listen for changes to our own channel."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass,
                f"{SIGNAL_CHANNEL_UPDATED}_{self.channel.id}",
                self.async_write_ha_state,
            )
        )


class TotalsEntity(Entity):
    """Entity spanning all channels.

    It belongs to its own device so the totals are not filed under some
    arbitrary channel. Identifier and unique ID derive from the ``entry_id``
    rather than from a fixed word: channel IDs are slugs of the channel name, so
    a channel called "Totals" would otherwise collide.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    def __init__(self, runtime: LogNotifierRuntime, key: str) -> None:
        self.runtime = runtime
        entry_id = runtime.entry.entry_id
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{TOTALS_KEY}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Log Notifier",
            manufacturer="Log Notifier",
            model="Totals",
            sw_version=INTEGRATION_VERSION,
        )

    async def async_added_to_hass(self) -> None:
        """Listen for changes in any channel."""
        self.async_on_remove(
            async_dispatcher_connect(
                self.hass, SIGNAL_TOTALS_UPDATED, self.async_write_ha_state
            )
        )
