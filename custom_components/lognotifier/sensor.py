"""Sensors per channel and across all channels: unread counters and highest level."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    ENTITY_ID_FORMAT,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import LEVEL_ORDER
from .entity import ChannelEntity, TotalsEntity, async_apply_default_entity_ids
from .models import Channel
from .runtime import LogNotifierConfigEntry, LogNotifierRuntime


async def async_setup_entry(
    hass: HomeAssistant,
    entry: LogNotifierConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Create the sensors for every channel, plus the total sensors."""
    runtime = entry.runtime_data
    entities: list[SensorEntity] = []
    for channel in runtime.channels:
        entities.append(UnreadSensor(runtime, channel))
        entities.append(HighestUnreadLevelSensor(runtime, channel))
    entities.append(UnreadTotalSensor(runtime))
    entities.append(HighestUnreadLevelTotalSensor(runtime))
    async_apply_default_entity_ids(entities, ENTITY_ID_FORMAT)
    async_add_entities(entities)


class UnreadSensor(ChannelEntity, SensorEntity):
    """Number of unread messages in the channel's badge levels."""

    _attr_translation_key = "unread"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, runtime: LogNotifierRuntime, channel: Channel) -> None:
        super().__init__(runtime, channel, "unread")
        self._attr_icon = channel.icon

    @property
    def native_value(self) -> int:
        """Unread counter."""
        return self.runtime.store.unread_count(self.channel)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Breakdown and last message — material for automations."""
        store = self.runtime.store
        by_level = store.unread_by_level(self.channel)
        last = store.last_message(self.channel.id)
        return {
            "channel_id": self.channel.id,
            "channel_name": self.channel.name,
            "badge_levels": list(self.channel.badge_levels),
            "highest_unread_level": store.highest_unread_level(self.channel),
            "unread_by_level": {level: by_level.get(level, 0) for level in LEVEL_ORDER},
            "total_messages": store.summary(self.channel)["total"],
            "last_level": last.level if last else None,
            "last_title": last.title if last else None,
            "last_source": last.source if last else None,
        }


class HighestUnreadLevelSensor(ChannelEntity, SensorEntity):
    """Highest unread level — colors badges and drives automations."""

    _attr_translation_key = "highest_unread_level"
    _attr_device_class = None

    def __init__(self, runtime: LogNotifierRuntime, channel: Channel) -> None:
        super().__init__(runtime, channel, "highest_unread_level")
        self._attr_icon = "mdi:alert-circle-outline"

    @property
    def native_value(self) -> str | None:
        """Level, or ``None`` if nothing unread is pending."""
        return self.runtime.store.highest_unread_level(self.channel)


class UnreadTotalSensor(TotalsEntity, SensorEntity):
    """Unread messages across all active channels combined."""

    _attr_translation_key = "unread_total"
    _attr_state_class = SensorStateClass.MEASUREMENT

    def __init__(self, runtime: LogNotifierRuntime) -> None:
        super().__init__(runtime, "unread")
        self._attr_icon = "mdi:message-badge-outline"

    @property
    def native_value(self) -> int:
        """Sum of the channel badges."""
        return self.runtime.store.unread_count_total()

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        """Breakdown by level and by channel."""
        store = self.runtime.store
        totals = store.totals()
        by_level = totals["unread_by_level"]
        per_channel = totals["unread_per_channel"]
        return {
            "highest_unread_level": totals["highest_unread_level"],
            "unread_by_level": {level: by_level.get(level, 0) for level in LEVEL_ORDER},
            "unread_per_channel": per_channel,
            "unread_by_channel": {
                channel.name: per_channel[channel.id]
                for channel in store.active_channels()
                if channel.id in per_channel
            },
            "channels_total": totals["channels_total"],
            "channels_with_unread": totals["channels_with_unread"],
            "total_messages": totals["total_messages"],
        }


class HighestUnreadLevelTotalSensor(TotalsEntity, SensorEntity):
    """Highest unread level across all active channels."""

    _attr_translation_key = "highest_unread_level_total"
    _attr_device_class = None

    def __init__(self, runtime: LogNotifierRuntime) -> None:
        super().__init__(runtime, "highest_unread_level")
        self._attr_icon = "mdi:alert-circle-outline"

    @property
    def native_value(self) -> str | None:
        """Level, or ``None`` if nothing unread is pending anywhere."""
        return self.runtime.store.highest_unread_level_total()
