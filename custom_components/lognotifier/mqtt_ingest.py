"""MQTT ingest: one topic filter per channel, via Home Assistant's MQTT client."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TYPE_CHECKING

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.importlib import async_import_module

from .const import DOMAIN, MAX_BODY_BYTES
from .ingest import PayloadError, parse_body
from .models import Channel
from .runtime import LogNotifierConfigEntry, LogNotifierRuntime

if TYPE_CHECKING:
    from homeassistant.components.mqtt import ReceiveMessage

_LOGGER = logging.getLogger(__name__)

MQTT_DOMAIN = "mqtt"


@callback
def async_setup_mqtt(hass: HomeAssistant, entry: LogNotifierConfigEntry) -> None:
    """Subscribe the channels that have a topic.

    In a background task: the MQTT client may still be starting, and waiting
    for it must not hold up the entities. Without a topic on any channel the
    MQTT integration is not touched at all — it stays optional.
    """
    runtime = entry.runtime_data
    channels = [
        channel
        for channel in runtime.channels
        if channel.mqtt_topic and channel.enabled
    ]
    if not channels:
        return
    entry.async_create_background_task(
        hass,
        _async_subscribe(hass, entry, runtime, channels),
        name=f"{DOMAIN}_mqtt_subscribe",
    )


async def _async_subscribe(
    hass: HomeAssistant,
    entry: LogNotifierConfigEntry,
    runtime: LogNotifierRuntime,
    channels: list[Channel],
) -> None:
    """Wait for the MQTT client and subscribe every channel's topic filter."""
    if not hass.config_entries.async_entries(MQTT_DOMAIN):
        _LOGGER.warning(
            "%d channel(s) have an MQTT topic, but the MQTT integration is not "
            "set up — reload Log Notifier once it is",
            len(channels),
        )
        return
    # Imported only here: the module pulls in the MQTT client library, which
    # is installed with the MQTT integration and not with this one.
    try:
        mqtt = await async_import_module(hass, "homeassistant.components.mqtt")
    except ImportError:
        _LOGGER.warning("The MQTT integration could not be loaded")
        return
    if not await mqtt.async_wait_for_mqtt_client(hass):
        _LOGGER.warning(
            "The MQTT integration is not available — reload Log Notifier once it is"
        )
        return

    for channel in channels:
        assert channel.mqtt_topic is not None
        # encoding=None hands over the raw bytes: size limit and UTF-8 check
        # are then the same ones the HTTP endpoint applies.
        unsubscribe = await mqtt.async_subscribe(
            hass,
            channel.mqtt_topic,
            _receiver(runtime, channel),
            qos=1,
            encoding=None,
        )
        entry.async_on_unload(unsubscribe)
        runtime.mqtt_topics[channel.id] = channel.mqtt_topic


def _receiver(
    runtime: LogNotifierRuntime, channel: Channel
) -> Callable[[ReceiveMessage], None]:
    """The message callback of one channel."""

    @callback
    def received(msg: ReceiveMessage) -> None:
        # A retained message is the broker repeating itself on every
        # subscribe — each reload and restart would file it once more.
        if msg.retain:
            return
        if not runtime.rate_limiter.allow(channel.id):
            _LOGGER.warning("Channel %s is over the rate limit", channel.id)
            return
        payload = msg.payload
        raw = payload.encode("utf-8") if isinstance(payload, str) else bytes(payload)
        if len(raw) > MAX_BODY_BYTES:
            _LOGGER.warning(
                "Discarded a message for channel %s from %s: too large",
                channel.id,
                msg.topic,
            )
            return
        # There is no response to send an error back in, so the log is the
        # only place the sender's mistake shows up.
        try:
            parsed = parse_body(raw)
        except PayloadError as err:
            _LOGGER.warning(
                "Discarded a message for channel %s from %s: %s",
                channel.id,
                msg.topic,
                err,
            )
            return
        runtime.publish(channel, parsed)

    return received
