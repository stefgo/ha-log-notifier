"""Services: send, mark read, clear — for automations and scripts."""

from __future__ import annotations

import voluptuous as vol
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv

from .const import (
    ATTR_CHANNEL_ID,
    ATTR_CONTENT,
    ATTR_FORMAT,
    ATTR_LEVEL,
    ATTR_SOURCE,
    ATTR_TAGS,
    ATTR_TITLE,
    ATTR_UP_TO_ID,
    DOMAIN,
    FORMAT_MARKDOWN,
    FORMATS,
    LEVEL_INFO,
    LEVEL_ORDER,
)
from .ingest import ParsedMessage
from .runtime import LogNotifierRuntime

SERVICE_SEND = "send"
SERVICE_MARK_READ = "mark_read"
SERVICE_CLEAR = "clear"

SEND_SCHEMA = vol.Schema(
    {
        vol.Required(ATTR_CHANNEL_ID): cv.string,
        vol.Required(ATTR_CONTENT): cv.string,
        vol.Optional(ATTR_LEVEL, default=LEVEL_INFO): vol.In(LEVEL_ORDER),
        vol.Optional(ATTR_TITLE): cv.string,
        vol.Optional(ATTR_SOURCE): cv.string,
        vol.Optional(ATTR_TAGS): vol.All(cv.ensure_list, [cv.string]),
        vol.Optional(ATTR_FORMAT, default=FORMAT_MARKDOWN): vol.In(FORMATS),
    }
)

MARK_READ_SCHEMA = vol.Schema(
    {
        vol.Optional(ATTR_CHANNEL_ID): cv.string,
        vol.Optional(ATTR_UP_TO_ID): cv.positive_int,
    }
)

CLEAR_SCHEMA = vol.Schema({vol.Required(ATTR_CHANNEL_ID): cv.string})


def _runtime(hass: HomeAssistant) -> LogNotifierRuntime:
    """Fetch the runtime object or fail comprehensibly."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if isinstance(runtime, LogNotifierRuntime):
            return runtime
    raise ServiceValidationError("Log Notifier is not set up")


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the services."""

    async def async_send(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        channel = runtime.store.channel(call.data[ATTR_CHANNEL_ID])
        if channel is None:
            raise ServiceValidationError(
                f"Unknown channel: {call.data[ATTR_CHANNEL_ID]}"
            )
        runtime.publish(
            channel,
            ParsedMessage(
                level=call.data[ATTR_LEVEL],
                content=call.data[ATTR_CONTENT],
                title=call.data.get(ATTR_TITLE),
                source=call.data.get(ATTR_SOURCE),
                tags=call.data.get(ATTR_TAGS),
                format=call.data[ATTR_FORMAT],
            ),
        )

    async def async_mark_read(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        channel_id = call.data.get(ATTR_CHANNEL_ID)
        # Without a channel the call applies to all of them — the usual "I have
        # seen everything" request.
        targets = (
            [channel_id] if channel_id else [c.id for c in runtime.channels]
        )
        for target in targets:
            if runtime.store.channel(target) is None:
                raise ServiceValidationError(f"Unknown channel: {target}")
            runtime.mark_read(target, call.data.get(ATTR_UP_TO_ID))

    async def async_clear(call: ServiceCall) -> None:
        runtime = _runtime(hass)
        channel_id = call.data[ATTR_CHANNEL_ID]
        if runtime.store.channel(channel_id) is None:
            raise ServiceValidationError(f"Unknown channel: {channel_id}")
        runtime.clear(channel_id)

    hass.services.async_register(DOMAIN, SERVICE_SEND, async_send, SEND_SCHEMA)
    hass.services.async_register(
        DOMAIN, SERVICE_MARK_READ, async_mark_read, MARK_READ_SCHEMA
    )
    hass.services.async_register(DOMAIN, SERVICE_CLEAR, async_clear, CLEAR_SCHEMA)
