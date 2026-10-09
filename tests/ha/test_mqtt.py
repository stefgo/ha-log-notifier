"""MQTT ingest — the second way into a channel, next to the HTTP view.

There is no token here and no response either: the broker decides who may
publish, and a refused message shows up in the log alone. What is tested is
that a message takes the same path as over HTTP, and what is kept out.
"""

from __future__ import annotations

import json
from typing import Any

import pytest
from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import async_fire_mqtt_message

from custom_components.lognotifier.const import (
    CONF_CHANNELS,
    CONF_MQTT_TOPIC,
    LEVEL_ERROR,
    LEVEL_INFO,
    MAX_BODY_BYTES,
    RATE_LIMIT_BURST,
)
from custom_components.lognotifier.diagnostics import (
    async_get_config_entry_diagnostics,
)

from .conftest import SERVICE_TOKEN, channel_options

TOPIC = "logs/backups"


@pytest.fixture
def entry_options() -> dict[str, Any]:
    """Backups listens on MQTT, Services does not."""
    return {
        CONF_CHANNELS: {
            **channel_options(**{CONF_MQTT_TOPIC: TOPIC}),
            **channel_options("services", name="Services", token=SERVICE_TOKEN),
        }
    }


@pytest.fixture
async def mqtt_entry(hass: HomeAssistant, mqtt_mock, config_entry):
    """The entry set up with MQTT available and the subscriptions in place."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)
    return config_entry


def _messages(entry, channel_id: str = "backups"):
    return entry.runtime_data.store.messages(channel_id)


async def test_json_message_lands_in_the_channel(
    hass: HomeAssistant, mqtt_entry
) -> None:
    """The payload is the one the HTTP view takes."""
    async_fire_mqtt_message(
        hass,
        TOPIC,
        json.dumps({"content": "Backup failed", "level": "ERROR", "source": "borg"}),
    )
    await hass.async_block_till_done()

    messages = _messages(mqtt_entry)
    assert len(messages) == 1
    assert messages[0].content == "Backup failed"
    assert messages[0].level == LEVEL_ERROR
    assert messages[0].source == "borg"
    assert _messages(mqtt_entry, "services") == []


async def test_plain_text_lands_as_info(hass: HomeAssistant, mqtt_entry) -> None:
    """Without JSON there is nowhere to put a level."""
    async_fire_mqtt_message(hass, TOPIC, "disk almost full")
    await hass.async_block_till_done()

    messages = _messages(mqtt_entry)
    assert [(m.content, m.level, m.format) for m in messages] == [
        ("disk almost full", LEVEL_INFO, "plain")
    ]


async def test_retained_message_is_ignored(hass: HomeAssistant, mqtt_entry) -> None:
    """The broker repeats a retained message on every subscribe."""
    async_fire_mqtt_message(hass, TOPIC, "stale", retain=True)
    await hass.async_block_till_done()

    assert _messages(mqtt_entry) == []


async def test_other_topics_are_ignored(hass: HomeAssistant, mqtt_entry) -> None:
    async_fire_mqtt_message(hass, "logs/services", "not for us")
    await hass.async_block_till_done()

    assert _messages(mqtt_entry) == []
    assert _messages(mqtt_entry, "services") == []


@pytest.mark.parametrize(
    "payload",
    [
        pytest.param(b"\xff\xfe", id="not-utf8"),
        pytest.param(b'{"content": ', id="broken-json"),
        pytest.param(b'{"content": "a", "level": "purple"}', id="unknown-level"),
        pytest.param(b"x" * (MAX_BODY_BYTES + 1), id="too-large"),
        pytest.param(b"", id="empty"),
    ],
)
async def test_unusable_payload_is_discarded(
    hass: HomeAssistant, mqtt_entry, caplog: pytest.LogCaptureFixture, payload: bytes
) -> None:
    """Refused like over HTTP — only that the log is the whole answer."""
    async_fire_mqtt_message(hass, TOPIC, payload)
    await hass.async_block_till_done()

    assert _messages(mqtt_entry) == []
    assert "Discarded a message for channel backups" in caplog.text


async def test_rate_limit_applies(hass: HomeAssistant, mqtt_entry) -> None:
    """A sender stuck in a loop must not flush the channel."""
    for index in range(RATE_LIMIT_BURST + 5):
        async_fire_mqtt_message(hass, TOPIC, f"message {index}")
    await hass.async_block_till_done()

    assert len(_messages(mqtt_entry)) == RATE_LIMIT_BURST


@pytest.mark.parametrize(
    "entry_options",
    [{CONF_CHANNELS: channel_options(**{CONF_MQTT_TOPIC: "logs/+/backup/#"})}],
)
async def test_wildcards_collect_several_topics(
    hass: HomeAssistant, mqtt_entry
) -> None:
    async_fire_mqtt_message(hass, "logs/nas/backup/nightly", "a")
    async_fire_mqtt_message(hass, "logs/pve/backup", "b")
    async_fire_mqtt_message(hass, "logs/pve/restore", "c")
    await hass.async_block_till_done()

    assert sorted(m.content for m in _messages(mqtt_entry)) == ["a", "b"]


@pytest.mark.parametrize(
    "entry_options",
    [{CONF_CHANNELS: channel_options(enabled=False, **{CONF_MQTT_TOPIC: TOPIC})}],
)
async def test_disabled_channel_does_not_listen(
    hass: HomeAssistant, mqtt_entry
) -> None:
    async_fire_mqtt_message(hass, TOPIC, "hello")
    await hass.async_block_till_done()

    assert _messages(mqtt_entry) == []
    assert mqtt_entry.runtime_data.mqtt_topics == {}


async def test_reload_does_not_double_the_subscription(
    hass: HomeAssistant, mqtt_entry
) -> None:
    """The old subscription goes with the old runtime."""
    assert await hass.config_entries.async_reload(mqtt_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    async_fire_mqtt_message(hass, TOPIC, "once")
    await hass.async_block_till_done()

    assert [m.content for m in _messages(mqtt_entry)] == ["once"]


async def test_changed_topic_moves_the_subscription(
    hass: HomeAssistant, mqtt_entry
) -> None:
    """Changing the options reloads the entry, and with it the topics."""
    hass.config_entries.async_update_entry(
        mqtt_entry,
        options={CONF_CHANNELS: channel_options(**{CONF_MQTT_TOPIC: "logs/new"})},
    )
    await hass.async_block_till_done(wait_background_tasks=True)

    async_fire_mqtt_message(hass, TOPIC, "old topic")
    async_fire_mqtt_message(hass, "logs/new", "new topic")
    await hass.async_block_till_done()

    assert [m.content for m in _messages(mqtt_entry)] == ["new topic"]


async def test_unloaded_entry_no_longer_listens(
    hass: HomeAssistant, mqtt_entry
) -> None:
    runtime = mqtt_entry.runtime_data
    assert await hass.config_entries.async_unload(mqtt_entry.entry_id)
    await hass.async_block_till_done()

    async_fire_mqtt_message(hass, TOPIC, "late")
    await hass.async_block_till_done()

    assert runtime.store.messages("backups") == []


async def test_setup_works_without_mqtt(
    hass: HomeAssistant, config_entry, caplog: pytest.LogCaptureFixture
) -> None:
    """MQTT is optional: a topic without the integration costs a warning."""
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done(wait_background_tasks=True)

    assert config_entry.runtime_data.mqtt_topics == {}
    assert "the MQTT integration is not set up" in caplog.text
    assert "mqtt" not in hass.config.components


async def test_diagnostics_show_the_subscriptions(
    hass: HomeAssistant, mqtt_entry
) -> None:
    data = await async_get_config_entry_diagnostics(hass, mqtt_entry)

    assert data["mqtt"] == {
        "configured": {"backups": TOPIC},
        "subscribed": {"backups": TOPIC},
    }
