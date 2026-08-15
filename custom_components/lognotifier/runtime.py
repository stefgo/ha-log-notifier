"""Runtime object of the integration: holds store, throttle and subscribers."""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.dispatcher import async_dispatcher_send

from .const import (
    ATTR_CHANNEL_ID,
    CONF_CHANNELS,
    DATA_SUBSCRIBERS,
    DOMAIN,
    EVENT_MESSAGE,
    SIGNAL_CHANNEL_UPDATED,
    SIGNAL_TOTALS_UPDATED,
)
from .ingest import ParsedMessage, RateLimiter
from .models import Channel, Message
from .store import MessageStore

_LOGGER = logging.getLogger(__name__)

class LogNotifierRuntime:
    """Everything that ingest, entities and frontend need in common."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: ConfigEntry,
        store: MessageStore,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.store = store
        self.rate_limiter = RateLimiter()
        # Deliberately on hass.data instead of on the runtime object: a reload
        # recreates this object, but the subscribed cards should keep running.
        self._subscribers: list[Callable[[str, dict[str, Any]], None]] = (
            hass.data.setdefault(DATA_SUBSCRIBERS, [])
        )
        self.sync_channels()

    # --- Channels ----------------------------------------------------------

    def sync_channels(self) -> None:
        """Take the channels from the options into the store."""
        raw: dict[str, dict[str, Any]] = self.entry.options.get(CONF_CHANNELS, {})
        self.store.set_channels(
            Channel.from_dict(channel_id, data) for channel_id, data in raw.items()
        )

    @property
    def channels(self) -> list[Channel]:
        """Configured channels."""
        return self.store.channels

    def notify_channels(self) -> None:
        """Send the full channel list to all open cards.

        After a change in the options, names, icons and contents are different;
        the card only fetched its list at startup and would otherwise catch up
        no earlier than the next page reload.
        """
        self._notify(
            "channels",
            {"channels": [self.store.summary(channel) for channel in self.channels]},
        )

    # --- Subscribers (WebSocket) -------------------------------------------

    def subscribe(
        self, callback: Callable[[str, dict[str, Any]], None]
    ) -> Callable[[], None]:
        """Subscribe a frontend client; the return value unsubscribes it."""
        self._subscribers.append(callback)

        def unsubscribe() -> None:
            if callback in self._subscribers:
                self._subscribers.remove(callback)

        return unsubscribe

    def _notify(self, event: str, payload: dict[str, Any]) -> None:
        """Send an event to all open cards."""
        for callback in list(self._subscribers):
            try:
                callback(event, payload)
            except Exception:  # noqa: BLE001 - a dead client must not break anything
                _LOGGER.debug("Could not notify subscriber", exc_info=True)

    # --- Write operations ---------------------------------------------------

    def publish(self, channel: Channel, parsed: ParsedMessage) -> Message:
        """Store a message and inform entities, automations and cards."""
        message = self.store.add(
            channel.id,
            level=parsed.level,
            content=parsed.content,
            title=parsed.title,
            source=parsed.source,
            tags=parsed.tags,
            fmt=parsed.format,
            ts=parsed.ts,
        )
        self._changed(channel.id)
        self.hass.bus.async_fire(
            EVENT_MESSAGE,
            {
                ATTR_CHANNEL_ID: channel.id,
                "channel_name": channel.name,
                **message.to_dict(),
                "message_id": message.id,
            },
        )
        self._notify(
            "message",
            {"channel_id": channel.id, "message": message.to_dict()},
        )
        return message

    def mark_read(self, channel_id: str, up_to_id: int | None = None) -> None:
        """Set the read position and refresh badge and cards."""
        if self.store.mark_read(channel_id, up_to_id):
            self._changed(channel_id)

    def clear(self, channel_id: str) -> None:
        """Empty a channel."""
        self.store.clear(channel_id)
        self._changed(channel_id)

    def _changed(self, channel_id: str) -> None:
        """Let the entities recompute and report the channel state to the cards."""
        async_dispatcher_send(self.hass, f"{SIGNAL_CHANNEL_UPDATED}_{channel_id}")
        async_dispatcher_send(self.hass, SIGNAL_TOTALS_UPDATED)
        channel = self.store.channel(channel_id)
        if channel is not None:
            self._notify("channel", {"channel": self.store.summary(channel)})

    # --- Diagnostics --------------------------------------------------------

    def diagnostics(self) -> dict[str, Any]:
        """State without secrets."""
        return {
            "domain": DOMAIN,
            "channels": [
                self.store.summary(channel) for channel in self.store.channels
            ],
            "rate_limit": self.rate_limiter.state(),
            "subscribers": len(self._subscribers),
        }


LogNotifierConfigEntry = ConfigEntry[LogNotifierRuntime]
