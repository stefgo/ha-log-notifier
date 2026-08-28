"""WebSocket commands for the Lovelace card."""

from __future__ import annotations

from typing import Any

import voluptuous as vol
from homeassistant.components import websocket_api
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv

from .const import DOMAIN, LEVEL_ORDER
from .runtime import LogNotifierRuntime


@callback
def _runtime(hass: HomeAssistant) -> LogNotifierRuntime | None:
    """Runtime object of the (single) config entry."""
    for entry in hass.config_entries.async_entries(DOMAIN):
        runtime = getattr(entry, "runtime_data", None)
        if isinstance(runtime, LogNotifierRuntime):
            return runtime
    return None


@callback
def async_register_websocket_api(hass: HomeAssistant) -> None:
    """Register all commands."""
    websocket_api.async_register_command(hass, ws_channels)
    websocket_api.async_register_command(hass, ws_messages)
    websocket_api.async_register_command(hass, ws_mark_read)
    websocket_api.async_register_command(hass, ws_clear)
    websocket_api.async_register_command(hass, ws_subscribe)


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/channels"})
@callback
def ws_channels(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """All channels with counters and last message."""
    runtime = _runtime(hass)
    if runtime is None:
        connection.send_error(msg["id"], "not_ready", "Integration not ready")
        return
    connection.send_result(
        msg["id"],
        {"channels": [runtime.store.summary(channel) for channel in runtime.channels]},
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/messages",
        vol.Required("channel_id"): str,
        vol.Optional("before"): int,
        vol.Optional("limit", default=50): vol.All(int, vol.Range(min=1, max=200)),
        # Enumeration instead of a threshold: the card picks every level individually.
        vol.Optional("levels"): vol.All(cv.ensure_list, [vol.In(LEVEL_ORDER)]),
    }
)
@callback
def ws_messages(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """One page of messages, newest first."""
    runtime = _runtime(hass)
    if runtime is None or runtime.store.channel(msg["channel_id"]) is None:
        connection.send_error(msg["id"], "not_found", "Unknown channel")
        return
    messages = runtime.store.messages(
        msg["channel_id"],
        before=msg.get("before"),
        limit=msg["limit"],
        levels=msg.get("levels"),
    )
    connection.send_result(
        msg["id"], {"messages": [message.to_dict() for message in messages]}
    )


@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/mark_read",
        vol.Required("channel_id"): str,
        vol.Optional("up_to_id"): int,
    }
)
@callback
def ws_mark_read(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Set the read position."""
    runtime = _runtime(hass)
    if runtime is None or runtime.store.channel(msg["channel_id"]) is None:
        connection.send_error(msg["id"], "not_found", "Unknown channel")
        return
    runtime.mark_read(msg["channel_id"], msg.get("up_to_id"))
    channel = runtime.store.channel(msg["channel_id"])
    connection.send_result(msg["id"], runtime.store.summary(channel))


@websocket_api.require_admin
@websocket_api.websocket_command(
    {
        vol.Required("type"): f"{DOMAIN}/clear",
        vol.Required("channel_id"): str,
    }
)
@callback
def ws_clear(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Clear a channel — deliberately restricted to administrators."""
    runtime = _runtime(hass)
    if runtime is None or runtime.store.channel(msg["channel_id"]) is None:
        connection.send_error(msg["id"], "not_found", "Unknown channel")
        return
    runtime.clear(msg["channel_id"])
    channel = runtime.store.channel(msg["channel_id"])
    connection.send_result(msg["id"], runtime.store.summary(channel))


@websocket_api.websocket_command({vol.Required("type"): f"{DOMAIN}/subscribe"})
@callback
def ws_subscribe(
    hass: HomeAssistant,
    connection: websocket_api.ActiveConnection,
    msg: dict[str, Any],
) -> None:
    """Live stream: new messages and changed channel states."""
    runtime = _runtime(hass)
    if runtime is None:
        connection.send_error(msg["id"], "not_ready", "Integration not ready")
        return

    @callback
    def forward(event: str, payload: dict[str, Any]) -> None:
        connection.send_message(
            websocket_api.event_message(msg["id"], {"event": event, **payload})
        )

    connection.subscriptions[msg["id"]] = runtime.subscribe(forward)
    connection.send_result(msg["id"])
