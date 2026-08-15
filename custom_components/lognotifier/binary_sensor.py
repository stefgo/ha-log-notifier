"""Binary sensors per channel and in total: are there unread messages?"""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    ENTITY_ID_FORMAT,
    BinarySensorDeviceClass,
    BinarySensorEntity,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .entity import ChannelEntity, TotalsEntity, async_apply_default_entity_ids
from .models import Channel
from .runtime import LogNotifierConfigEntry, LogNotifierRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogNotifierConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the binary sensor for every channel, plus the total one."""
    runtime = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        UnreadBinarySensor(runtime, channel) for channel in runtime.channels
    ]
    entities.append(UnreadTotalBinarySensor(runtime))
    async_apply_default_entity_ids(entities, ENTITY_ID_FORMAT)
    async_add_entities(entities)


class UnreadBinarySensor(ChannelEntity, BinarySensorEntity):
    """A yes/no suitable for automations and sidebar badges."""

    _attr_translation_key = "has_unread"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, runtime: LogNotifierRuntime, channel: Channel) -> None:
        super().__init__(runtime, channel, "has_unread")

    @property
    def is_on(self) -> bool:
        """True as soon as at least one message in a badge level is unread."""
        return self.runtime.store.unread_count(self.channel) > 0


class UnreadTotalBinarySensor(TotalsEntity, BinarySensorEntity):
    """Yes/no across all active channels — one trigger for every case."""

    _attr_translation_key = "has_unread_total"
    _attr_device_class = BinarySensorDeviceClass.PROBLEM

    def __init__(self, runtime: LogNotifierRuntime) -> None:
        super().__init__(runtime, "has_unread")

    @property
    def is_on(self) -> bool:
        """True as soon as any channel has something unread."""
        return self.runtime.store.unread_count_total() > 0
