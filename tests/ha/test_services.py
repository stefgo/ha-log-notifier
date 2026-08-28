"""The three services — the way an automation reaches the integration."""

from __future__ import annotations

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError

from custom_components.lognotifier.const import (
    ATTR_CHANNEL_ID,
    ATTR_CONTENT,
    ATTR_LEVEL,
    ATTR_SOURCE,
    ATTR_TAGS,
    ATTR_TITLE,
    ATTR_UP_TO_ID,
    DOMAIN,
    LEVEL_ERROR,
    LEVEL_INFO,
)
from custom_components.lognotifier.services import (
    SERVICE_CLEAR,
    SERVICE_MARK_READ,
    SERVICE_SEND,
)


async def _send(hass: HomeAssistant, **data) -> None:
    await hass.services.async_call(
        DOMAIN,
        SERVICE_SEND,
        {ATTR_CHANNEL_ID: "backups", ATTR_CONTENT: "hello", **data},
        blocking=True,
    )


async def test_send_stores_the_message(hass: HomeAssistant, runtime) -> None:
    """The service is the automation-facing twin of the ingest URL."""
    await _send(
        hass,
        **{
            ATTR_LEVEL: LEVEL_ERROR,
            ATTR_TITLE: "nightly",
            ATTR_SOURCE: "automation",
            ATTR_TAGS: ["backup"],
        },
    )

    message = runtime.store.messages("backups")[0]
    assert message.content == "hello"
    assert message.level == LEVEL_ERROR
    assert message.title == "nightly"
    assert message.source == "automation"
    assert message.tags == ["backup"]


async def test_send_defaults_to_info(hass: HomeAssistant, runtime) -> None:
    """Without a level the message is INFO — the schema's default."""
    await _send(hass)

    assert runtime.store.messages("backups")[0].level == LEVEL_INFO


async def test_send_to_an_unknown_channel_is_a_validation_error(
    hass: HomeAssistant, runtime
) -> None:
    """A typo in the channel must say so, not disappear silently."""
    with pytest.raises(ServiceValidationError, match="Unknown channel"):
        await _send(hass, **{ATTR_CHANNEL_ID: "nope"})


async def test_mark_read_clears_the_unread_count(hass: HomeAssistant, runtime) -> None:
    """The counter the badge shows is what this service resets."""
    await _send(hass)
    await _send(hass)
    channel = runtime.store.channel("backups")
    assert runtime.store.unread_count(channel) == 2

    await hass.services.async_call(
        DOMAIN, SERVICE_MARK_READ, {ATTR_CHANNEL_ID: "backups"}, blocking=True
    )

    assert runtime.store.unread_count(runtime.store.channel("backups")) == 0


async def test_mark_read_without_a_channel_covers_all_of_them(
    hass: HomeAssistant, runtime
) -> None:
    """ "I have seen everything" is the call without arguments."""
    await _send(hass)
    await _send(hass, **{ATTR_CHANNEL_ID: "services"})

    await hass.services.async_call(DOMAIN, SERVICE_MARK_READ, {}, blocking=True)

    assert runtime.store.unread_count_total() == 0


async def test_mark_read_up_to_an_id_leaves_the_newer_ones(
    hass: HomeAssistant, runtime
) -> None:
    """Reading up to a point is what an open card does while scrolling."""
    await _send(hass)
    await _send(hass)
    first = runtime.store.messages("backups")[-1]

    await hass.services.async_call(
        DOMAIN,
        SERVICE_MARK_READ,
        {ATTR_CHANNEL_ID: "backups", ATTR_UP_TO_ID: first.id},
        blocking=True,
    )

    assert runtime.store.unread_count(runtime.store.channel("backups")) == 1


async def test_clear_empties_only_the_named_channel(
    hass: HomeAssistant, runtime
) -> None:
    """Clearing one channel must not touch the other."""
    await _send(hass)
    await _send(hass, **{ATTR_CHANNEL_ID: "services"})

    await hass.services.async_call(
        DOMAIN, SERVICE_CLEAR, {ATTR_CHANNEL_ID: "backups"}, blocking=True
    )

    assert runtime.store.messages("backups") == []
    assert len(runtime.store.messages("services")) == 1


async def test_clear_of_an_unknown_channel_is_a_validation_error(
    hass: HomeAssistant, runtime
) -> None:
    """Same as send: a wrong channel is reported, not ignored."""
    with pytest.raises(ServiceValidationError, match="Unknown channel"):
        await hass.services.async_call(
            DOMAIN, SERVICE_CLEAR, {ATTR_CHANNEL_ID: "nope"}, blocking=True
        )
