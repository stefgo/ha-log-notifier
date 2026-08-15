"""Shared base for the channel entities and the total entities."""

from __future__ import annotations

from collections.abc import Iterable

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


class LogNotifierEntity(Entity):
    """Everything the channel and the total entities have in common.

    ``default_object_id`` is the object ID this entity asks for when Home
    Assistant first registers it. Without it HA would build the entity ID from
    the device name, so a channel called "Kitchen" would end up as
    ``sensor.kitchen_unread`` — indistinguishable from any other integration's
    entity. Every entity of this integration is therefore prefixed with the
    domain. It is only a suggestion: the registry keeps the entity IDs of
    already known entities, and a rename in the UI still wins.
    """

    _attr_should_poll = False
    _attr_has_entity_name = True

    default_object_id: str


def async_apply_default_entity_ids(
    entities: Iterable[LogNotifierEntity], entity_id_format: str
) -> None:
    """Pre-set the entity IDs with the platform's format before adding.

    Called from every platform's ``async_setup_entry``; the platform is what
    knows its own ``ENTITY_ID_FORMAT`` (``sensor.{}``, ``binary_sensor.{}``).
    """
    for entity in entities:
        entity.entity_id = entity_id_format.format(entity.default_object_id)


class ChannelEntity(LogNotifierEntity):
    """Entity that belongs to exactly one channel.

    Updates are not polled but pushed via a dispatcher signal when a message
    arrives or is acknowledged.
    """

    def __init__(
        self, runtime: LogNotifierRuntime, channel: Channel, key: str
    ) -> None:
        self.runtime = runtime
        self.channel = channel
        self._attr_unique_id = f"{DOMAIN}_{channel.id}_{key}"
        self.default_object_id = f"{DOMAIN}_{channel.id}_{key}"
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


class TotalsEntity(LogNotifierEntity):
    """Entity spanning all channels.

    It belongs to its own device so the totals are not filed under some
    arbitrary channel. Identifier and unique ID derive from the ``entry_id``
    rather than from a fixed word: channel IDs are slugs of the channel name, so
    a channel called "Totals" would otherwise collide. The entity ID leaves the
    ``entry_id`` out — it is a random hex string and has no place in an ID that
    people type into automations.
    """

    def __init__(self, runtime: LogNotifierRuntime, key: str) -> None:
        self.runtime = runtime
        entry_id = runtime.entry.entry_id
        self._attr_unique_id = f"{DOMAIN}_{entry_id}_{TOTALS_KEY}_{key}"
        self.default_object_id = f"{DOMAIN}_{TOTALS_KEY}_{key}"
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
