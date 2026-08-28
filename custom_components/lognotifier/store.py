"""Message storage: a ring buffer per channel plus the read position.

Deliberately without Home Assistant imports so the logic stays testable on its
own. Persistence goes through a store object passed in from outside (in
production ``homeassistant.helpers.storage.Store``), of which only
``async_load`` and ``async_delay_save`` are required.
"""

from __future__ import annotations

import time
from collections import deque
from collections.abc import Iterable
from typing import Any, Protocol

from .const import (
    MAX_CONTENT_CHARS,
    MAX_SOURCE_CHARS,
    MAX_TAG_CHARS,
    MAX_TAGS,
    MAX_TITLE_CHARS,
    STORAGE_SAVE_DELAY,
)
from .models import Channel, Message, severity


class StoreProtocol(Protocol):
    """The slice of ``helpers.storage.Store`` that we use."""

    async def async_load(self) -> Any: ...

    def async_delay_save(self, data_func: Any, delay: float = 0) -> None: ...


class ChannelBuffer:
    """The messages of one channel together with its read position."""

    def __init__(self, maxlen: int) -> None:
        self.messages: deque[Message] = deque(maxlen=maxlen)
        self.last_read_id: int = 0

    def set_maxlen(self, maxlen: int) -> None:
        """Change the capacity; a smaller limit drops the oldest entries."""
        if self.messages.maxlen == maxlen:
            return
        self.messages = deque(self.messages, maxlen=maxlen)


class MessageStore:
    """All channels with their messages."""

    def __init__(self, store: StoreProtocol) -> None:
        self._store = store
        self._buffers: dict[str, ChannelBuffer] = {}
        self._channels: dict[str, Channel] = {}
        self._next_id: int = 1

    # --- Loading and saving -----------------------------------------------

    async def async_load(self) -> None:
        """Read the last state from storage."""
        data = await self._store.async_load()
        if not data:
            return
        self._next_id = int(data.get("next_id", 1))
        for channel_id, raw in (data.get("channels") or {}).items():
            buffer = ChannelBuffer(maxlen=self._maxlen(channel_id))
            for item in raw.get("messages") or []:
                try:
                    buffer.messages.append(Message.from_dict(item))
                except (KeyError, TypeError, ValueError):
                    continue  # one broken row must not cost the whole channel
            buffer.last_read_id = int(raw.get("last_read_id", 0))
            self._buffers[channel_id] = buffer

    def _data(self) -> dict[str, Any]:
        """Serialization for the storage write."""
        return {
            "next_id": self._next_id,
            "channels": {
                channel_id: {
                    "last_read_id": buffer.last_read_id,
                    "messages": [message.to_dict() for message in buffer.messages],
                }
                for channel_id, buffer in self._buffers.items()
            },
        }

    def _schedule_save(self) -> None:
        """Trigger a delayed write — a burst of messages then costs one file."""
        self._store.async_delay_save(self._data, STORAGE_SAVE_DELAY)

    # --- Channel management ------------------------------------------------

    def set_channels(self, channels: Iterable[Channel]) -> None:
        """Take over the configured channels.

        Buffers of removed channels are discarded: a deleted channel should not
        live on as a dead record in storage.
        """
        self._channels = {channel.id: channel for channel in channels}
        for channel_id, channel in self._channels.items():
            buffer = self._buffers.get(channel_id)
            if buffer is None:
                self._buffers[channel_id] = ChannelBuffer(maxlen=channel.max_messages)
            else:
                buffer.set_maxlen(channel.max_messages)
        for stale in set(self._buffers) - set(self._channels):
            del self._buffers[stale]
        self._schedule_save()

    @property
    def channels(self) -> list[Channel]:
        """Configured channels in configuration order."""
        return list(self._channels.values())

    def channel(self, channel_id: str) -> Channel | None:
        """Channel by ID, or ``None``."""
        return self._channels.get(channel_id)

    def channel_by_token(self, token: str) -> Channel | None:
        """Channel by ingest token (constant-time compare is up to the caller)."""
        for channel in self._channels.values():
            if channel.token == token:
                return channel
        return None

    def _maxlen(self, channel_id: str) -> int:
        channel = self._channels.get(channel_id)
        return channel.max_messages if channel else 500

    def _buffer(self, channel_id: str) -> ChannelBuffer:
        buffer = self._buffers.get(channel_id)
        if buffer is None:
            buffer = ChannelBuffer(maxlen=self._maxlen(channel_id))
            self._buffers[channel_id] = buffer
        return buffer

    # --- Writing -----------------------------------------------------------

    def add(
        self,
        channel_id: str,
        *,
        level: str,
        content: str,
        title: str | None = None,
        source: str | None = None,
        tags: list[str] | None = None,
        fmt: str,
        ts: float | None = None,
    ) -> Message:
        """Store a message and return it with its assigned ID."""
        message = Message(
            id=self._next_id,
            ts=ts if ts is not None else time.time(),
            level=level,
            content=content[:MAX_CONTENT_CHARS],
            title=title[:MAX_TITLE_CHARS] if title else None,
            source=source[:MAX_SOURCE_CHARS] if source else None,
            tags=[str(tag)[:MAX_TAG_CHARS] for tag in (tags or [])][:MAX_TAGS],
            format=fmt,
        )
        self._next_id += 1
        self._buffer(channel_id).messages.append(message)
        self._schedule_save()
        return message

    def mark_read(self, channel_id: str, up_to_id: int | None = None) -> bool:
        """Set the read position; without ``up_to_id`` everything counts as read.

        The position never moves backwards — two clients acknowledging in
        different orders must not inflate the badge again.
        """
        buffer = self._buffer(channel_id)
        target = up_to_id if up_to_id is not None else self._latest_id(buffer)
        if target <= buffer.last_read_id:
            return False
        buffer.last_read_id = target
        self._schedule_save()
        return True

    def clear(self, channel_id: str) -> None:
        """Empty a channel completely."""
        buffer = self._buffer(channel_id)
        buffer.last_read_id = self._latest_id(buffer)
        buffer.messages.clear()
        self._schedule_save()

    def purge_aged(self, now: float | None = None) -> int:
        """Drop messages that are older than the channel limit."""
        now = now if now is not None else time.time()
        removed = 0
        for channel_id, channel in self._channels.items():
            if not channel.max_age_days:
                continue
            cutoff = now - channel.max_age_days * 86400
            buffer = self._buffers.get(channel_id)
            if buffer is None:
                continue
            while buffer.messages and buffer.messages[0].ts < cutoff:
                buffer.messages.popleft()
                removed += 1
        if removed:
            self._schedule_save()
        return removed

    # --- Reading -----------------------------------------------------------

    @staticmethod
    def _latest_id(buffer: ChannelBuffer) -> int:
        return buffer.messages[-1].id if buffer.messages else buffer.last_read_id

    def messages(
        self,
        channel_id: str,
        *,
        before: int | None = None,
        limit: int = 50,
        levels: Iterable[str] | None = None,
    ) -> list[Message]:
        """Messages newest first, optionally filtered and paginated.

        ``levels`` is an enumeration, not a threshold: every level is picked
        individually, ``None`` means "all". An empty selection therefore
        returns nothing.
        """
        buffer = self._buffer(channel_id)
        wanted = None if levels is None else set(levels)
        result: list[Message] = []
        for message in reversed(buffer.messages):
            if before is not None and message.id >= before:
                continue
            if wanted is not None and message.level not in wanted:
                continue
            result.append(message)
            if len(result) >= limit:
                break
        return result

    def last_message(self, channel_id: str) -> Message | None:
        """Most recent message of a channel."""
        buffer = self._buffer(channel_id)
        return buffer.messages[-1] if buffer.messages else None

    def last_read_id(self, channel_id: str) -> int:
        """Current read position."""
        return self._buffer(channel_id).last_read_id

    def unread(self, channel: Channel) -> list[Message]:
        """Unread messages in the channel's badge levels."""
        buffer = self._buffer(channel.id)
        badge_levels = set(channel.badge_levels)
        return [
            message
            for message in buffer.messages
            if message.id > buffer.last_read_id and message.level in badge_levels
        ]

    def unread_count(self, channel: Channel) -> int:
        """The number for the badge."""
        return len(self.unread(channel))

    def unread_by_level(self, channel: Channel) -> dict[str, int]:
        """Unread per level — independent of the channel's badge selection.

        The badge only counts the selected levels; for automations and the card
        the full breakdown is more useful.
        """
        buffer = self._buffer(channel.id)
        counts: dict[str, int] = {}
        for message in buffer.messages:
            if message.id > buffer.last_read_id:
                counts[message.level] = counts.get(message.level, 0) + 1
        return counts

    def highest_unread_level(self, channel: Channel) -> str | None:
        """Highest unread level of the badge selection (it colors the badge).

        Severity is still in play here — not for filtering, but to pick the most
        prominent color among the counted messages.
        """
        highest: str | None = None
        for message in self.unread(channel):
            if highest is None or severity(message.level) > severity(highest):
                highest = message.level
        return highest

    # --- Aggregates across all channels ------------------------------------
    # Disabled channels stay out: they no longer accept anything, so their
    # leftovers should not keep the totals permanently high. The stored
    # messages themselves are untouched and count again once re-enabled.

    def active_channels(self) -> list[Channel]:
        """Channels that feed into the totals."""
        return [channel for channel in self.channels if channel.enabled]

    def unread_count_total(self) -> int:
        """Unread across all active channels — each in its own badge levels."""
        return sum(self.unread_count(channel) for channel in self.active_channels())

    def unread_by_level_total(self) -> dict[str, int]:
        """Breakdown per level across all active channels."""
        counts: dict[str, int] = {}
        for channel in self.active_channels():
            for level, count in self.unread_by_level(channel).items():
                counts[level] = counts.get(level, 0) + count
        return counts

    def highest_unread_level_total(self) -> str | None:
        """Highest unread level across all active channels."""
        highest: str | None = None
        for channel in self.active_channels():
            level = self.highest_unread_level(channel)
            if level is not None and (
                highest is None or severity(level) > severity(highest)
            ):
                highest = level
        return highest

    def unread_per_channel(self) -> dict[str, int]:
        """``{channel_id: unread}`` for channels with a backlog, largest first."""
        counts = {
            channel.id: self.unread_count(channel) for channel in self.active_channels()
        }
        return dict(
            sorted(
                ((cid, n) for cid, n in counts.items() if n),
                key=lambda item: item[1],
                reverse=True,
            )
        )

    def totals(self) -> dict[str, Any]:
        """Overall state as the total entities need it."""
        active = self.active_channels()
        per_channel = self.unread_per_channel()
        return {
            "unread": self.unread_count_total(),
            "unread_by_level": self.unread_by_level_total(),
            "unread_per_channel": per_channel,
            "highest_unread_level": self.highest_unread_level_total(),
            "channels_total": len(active),
            "channels_with_unread": len(per_channel),
            "total_messages": sum(
                len(self._buffer(channel.id).messages) for channel in active
            ),
        }

    def summary(self, channel: Channel) -> dict[str, Any]:
        """Channel state as the card and the entities need it."""
        last = self.last_message(channel.id)
        return {
            "id": channel.id,
            "name": channel.name,
            "icon": channel.icon,
            "enabled": channel.enabled,
            "badge_levels": list(channel.badge_levels),
            "unread": self.unread_count(channel),
            "unread_by_level": self.unread_by_level(channel),
            "highest_unread_level": self.highest_unread_level(channel),
            "last_read_id": self.last_read_id(channel.id),
            "total": len(self._buffer(channel.id).messages),
            "last_message": last.to_dict() if last else None,
        }
