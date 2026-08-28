"""The WebSocket commands the card talks to.

The card reads nothing from entity attributes: a message list would blow past
the attribute size limits and land in the recorder. These five commands are
therefore the card's entire interface.
"""

from __future__ import annotations

from homeassistant.core import HomeAssistant

from custom_components.lognotifier.const import (
    ATTR_CHANNEL_ID,
    ATTR_CONTENT,
    ATTR_LEVEL,
    DOMAIN,
    LEVEL_ERROR,
    LEVEL_INFO,
)
from custom_components.lognotifier.services import SERVICE_SEND


async def _send(hass: HomeAssistant, channel: str = "backups", **data) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {ATTR_CHANNEL_ID: channel, ATTR_CONTENT: "hello", **data},
        blocking=True,
    )


async def test_channels_lists_every_channel(
    hass: HomeAssistant, runtime, hass_ws_client
) -> None:
    """The card's first call: what is there, and how much is unread."""
    client = await hass_ws_client(hass)
    await _send(hass)

    await client.send_json({"id": 1, "type": f"{DOMAIN}/channels"})
    response = await client.receive_json()

    assert response["success"]
    channels = response["result"]["channels"]
    assert {channel["id"] for channel in channels} == {"backups", "services"}
    backups = next(c for c in channels if c["id"] == "backups")
    assert backups["unread"] == 1


async def test_messages_returns_a_page_newest_first(
    hass: HomeAssistant, runtime, hass_ws_client
) -> None:
    """The list the card renders, newest at the top."""
    client = await hass_ws_client(hass)
    await _send(hass, **{ATTR_CONTENT: "first"})
    await _send(hass, **{ATTR_CONTENT: "second"})

    await client.send_json(
        {"id": 1, "type": f"{DOMAIN}/messages", "channel_id": "backups"}
    )
    response = await client.receive_json()

    assert response["success"]
    contents = [message["content"] for message in response["result"]["messages"]]
    assert contents == ["second", "first"]


async def test_messages_can_be_filtered_by_level(
    hass: HomeAssistant, runtime, hass_ws_client
) -> None:
    """The card's level filter is applied on this side, not in the browser."""
    client = await hass_ws_client(hass)
    await _send(hass, **{ATTR_CONTENT: "noise", ATTR_LEVEL: LEVEL_INFO})
    await _send(hass, **{ATTR_CONTENT: "trouble", ATTR_LEVEL: LEVEL_ERROR})

    await client.send_json(
        {
            "id": 1,
            "type": f"{DOMAIN}/messages",
            "channel_id": "backups",
            "levels": [LEVEL_ERROR],
        }
    )
    response = await client.receive_json()

    assert [m["content"] for m in response["result"]["messages"]] == ["trouble"]


async def test_messages_of_an_unknown_channel_is_an_error(
    hass: HomeAssistant, runtime, hass_ws_client
) -> None:
    """A card configured for a deleted channel gets a clean error."""
    client = await hass_ws_client(hass)

    await client.send_json(
        {"id": 1, "type": f"{DOMAIN}/messages", "channel_id": "nope"}
    )
    response = await client.receive_json()

    assert not response["success"]
    assert response["error"]["code"] == "not_found"


async def test_mark_read_returns_the_updated_summary(
    hass: HomeAssistant, runtime, hass_ws_client
) -> None:
    """The card updates its badge from the answer, without a second call."""
    client = await hass_ws_client(hass)
    await _send(hass)

    await client.send_json(
        {"id": 1, "type": f"{DOMAIN}/mark_read", "channel_id": "backups"}
    )
    response = await client.receive_json()

    assert response["success"]
    assert response["result"]["unread"] == 0


async def test_clear_requires_an_admin(
    hass: HomeAssistant, runtime, hass_ws_client, hass_admin_user
) -> None:
    """Clearing throws messages away, so it is deliberately admin-only."""
    hass_admin_user.groups = []
    client = await hass_ws_client(hass)
    await _send(hass)

    await client.send_json(
        {"id": 1, "type": f"{DOMAIN}/clear", "channel_id": "backups"}
    )
    response = await client.receive_json()

    assert not response["success"]
    assert response["error"]["code"] == "unauthorized"
    assert len(runtime.store.messages("backups")) == 1


async def test_clear_empties_the_channel_for_an_admin(
    hass: HomeAssistant, runtime, hass_ws_client
) -> None:
    """The admin path itself works and reports the empty channel back."""
    client = await hass_ws_client(hass)
    await _send(hass)

    await client.send_json(
        {"id": 1, "type": f"{DOMAIN}/clear", "channel_id": "backups"}
    )
    response = await client.receive_json()

    assert response["success"]
    assert response["result"]["unread"] == 0
    assert runtime.store.messages("backups") == []


async def test_subscribe_pushes_new_messages(
    hass: HomeAssistant, runtime, hass_ws_client
) -> None:
    """An open card sees a message without polling for it.

    One message produces two events, in this order: `channel` with the new
    counters — which is what redraws the badge — and then `message` with the
    message itself. The card needs both, so both are asserted.
    """
    client = await hass_ws_client(hass)

    await client.send_json({"id": 1, "type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]

    await _send(hass, **{ATTR_CONTENT: "live"})

    first = await client.receive_json()
    assert first["type"] == "event"
    assert first["event"]["event"] == "channel"
    assert first["event"]["channel"]["id"] == "backups"
    assert first["event"]["channel"]["unread"] == 1

    second = await client.receive_json()
    assert second["event"]["event"] == "message"
    assert second["event"]["message"]["content"] == "live"


async def test_subscribe_reports_changed_channels(
    hass: HomeAssistant, runtime, hass_ws_client, setup_entry
) -> None:
    """Renaming a channel reaches an open card without a page reload."""
    from custom_components.lognotifier.const import CONF_CHANNELS, CONF_NAME

    client = await hass_ws_client(hass)
    await client.send_json({"id": 1, "type": f"{DOMAIN}/subscribe"})
    assert (await client.receive_json())["success"]

    options = {CONF_CHANNELS: dict(setup_entry.options[CONF_CHANNELS])}
    options[CONF_CHANNELS]["backups"] = {
        **options[CONF_CHANNELS]["backups"],
        CONF_NAME: "Backups (renamed)",
    }
    hass.config_entries.async_update_entry(setup_entry, options=options)
    await hass.async_block_till_done()

    event = await client.receive_json()
    assert event["event"]["event"] == "channels"
    names = [channel["name"] for channel in event["event"]["channels"]]
    assert "Backups (renamed)" in names
