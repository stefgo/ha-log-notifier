"""The config flow and the options flow that manages the channels."""

from __future__ import annotations

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.lognotifier.const import (
    CONF_BADGE_LEVELS,
    CONF_CHANNELS,
    CONF_DELETE,
    CONF_ENABLED,
    CONF_MAX_AGE_DAYS,
    CONF_MAX_MESSAGES,
    CONF_MQTT_TOPIC,
    CONF_NAME,
    CONF_ROTATE_TOKEN,
    CONF_TOKEN,
    DEFAULT_BADGE_LEVELS,
    DEFAULT_MAX_AGE_DAYS,
    DEFAULT_MAX_MESSAGES,
    DOMAIN,
    LEVEL_ERROR,
)

CHANNEL_FORM = {
    CONF_NAME: "Backups",
    CONF_BADGE_LEVELS: list(DEFAULT_BADGE_LEVELS),
    CONF_MAX_MESSAGES: DEFAULT_MAX_MESSAGES,
    CONF_MAX_AGE_DAYS: DEFAULT_MAX_AGE_DAYS,
}


async def test_user_flow_creates_the_entry(hass: HomeAssistant) -> None:
    """There is nothing to configure — channels come later, via the options."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"] == {CONF_CHANNELS: {}}


async def test_only_one_entry_is_allowed(hass: HomeAssistant, config_entry) -> None:
    """A second instance would mean a second store for the same messages."""
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )

    assert result["type"] is FlowResultType.ABORT


async def test_add_channel_generates_a_token(hass: HomeAssistant, setup_entry) -> None:
    """A new channel is usable straight away: it gets its own ingest token."""
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert result["type"] is FlowResultType.MENU

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_channel"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**CHANNEL_FORM, CONF_NAME: "Nightly"}
    )
    await hass.async_block_till_done()

    channels = result["data"][CONF_CHANNELS]
    assert "nightly" in channels
    assert channels["nightly"][CONF_TOKEN]
    assert channels["nightly"][CONF_ENABLED] is True


async def test_added_channel_gets_a_distinct_id(
    hass: HomeAssistant, setup_entry
) -> None:
    """A second channel of the same name must not overwrite the first."""
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_channel"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**CHANNEL_FORM, CONF_NAME: "Backups"}
    )
    await hass.async_block_till_done()

    channels = result["data"][CONF_CHANNELS]
    assert len(channels) == 3
    assert channels["backups"][CONF_TOKEN] != channels["backups_2"][CONF_TOKEN]


async def _open_channel_editor(hass: HomeAssistant, entry, channel_id: str):
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "select_channel"}
    )
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"channel": channel_id}
    )


async def test_show_urls_lists_every_channel(hass: HomeAssistant, setup_entry) -> None:
    """The menu leads to the ingest URLs — and from there back to the menu."""
    channels = setup_entry.options[CONF_CHANNELS]
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    assert "show_urls" in result["menu_options"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "show_urls"}
    )

    assert result["type"] is FlowResultType.FORM
    urls = result["description_placeholders"]["urls"]
    assert channels
    for data in channels.values():
        assert data[CONF_NAME] in urls
        assert f"/api/{DOMAIN}/ingest/{data[CONF_TOKEN]}`" in urls

    result = await hass.config_entries.options.async_configure(result["flow_id"], {})

    assert result["type"] is FlowResultType.MENU
    assert setup_entry.options[CONF_CHANNELS] == channels


async def test_edit_channel_changes_the_name(hass: HomeAssistant, setup_entry) -> None:
    """Editing goes through select → edit and keeps the token."""
    before = setup_entry.options[CONF_CHANNELS]["backups"][CONF_TOKEN]
    result = await _open_channel_editor(hass, setup_entry, "backups")
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            **CHANNEL_FORM,
            CONF_NAME: "Backups (nightly)",
            CONF_BADGE_LEVELS: [LEVEL_ERROR],
            CONF_ENABLED: True,
        },
    )
    await hass.async_block_till_done()

    channel = result["data"][CONF_CHANNELS]["backups"]
    assert channel[CONF_NAME] == "Backups (nightly)"
    assert channel[CONF_BADGE_LEVELS] == [LEVEL_ERROR]
    assert channel[CONF_TOKEN] == before


async def test_rotating_the_token_replaces_it(hass: HomeAssistant, setup_entry) -> None:
    """Rotation is what a leaked token is answered with."""
    before = setup_entry.options[CONF_CHANNELS]["backups"][CONF_TOKEN]
    result = await _open_channel_editor(hass, setup_entry, "backups")

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**CHANNEL_FORM, CONF_ENABLED: True, CONF_ROTATE_TOKEN: True},
    )
    await hass.async_block_till_done()

    assert result["data"][CONF_CHANNELS]["backups"][CONF_TOKEN] != before


async def test_deleting_a_channel_removes_it(hass: HomeAssistant, setup_entry) -> None:
    """Deletion takes the channel out of the options entirely."""
    result = await _open_channel_editor(hass, setup_entry, "backups")

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**CHANNEL_FORM, CONF_ENABLED: True, CONF_DELETE: True}
    )
    await hass.async_block_till_done()

    assert "backups" not in result["data"][CONF_CHANNELS]
    assert "services" in result["data"][CONF_CHANNELS]


async def test_mqtt_topic_is_stored_and_removed_again(
    hass: HomeAssistant, setup_entry
) -> None:
    """The topic is optional: entered it is kept, emptied it is gone."""
    result = await _open_channel_editor(hass, setup_entry, "backups")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**CHANNEL_FORM, CONF_ENABLED: True, CONF_MQTT_TOPIC: " logs/backups "},
    )
    await hass.async_block_till_done()
    assert result["data"][CONF_CHANNELS]["backups"][CONF_MQTT_TOPIC] == "logs/backups"

    result = await _open_channel_editor(hass, setup_entry, "backups")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {**CHANNEL_FORM, CONF_ENABLED: True}
    )
    await hass.async_block_till_done()
    assert CONF_MQTT_TOPIC not in result["data"][CONF_CHANNELS]["backups"]


async def test_invalid_mqtt_topic_is_refused(hass: HomeAssistant, setup_entry) -> None:
    """The form comes back with what was entered instead of saving."""
    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "add_channel"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**CHANNEL_FORM, CONF_NAME: "Nightly", CONF_MQTT_TOPIC: "logs/#/more"},
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_MQTT_TOPIC: "invalid_topic"}
    assert "nightly" not in setup_entry.options[CONF_CHANNELS]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**CHANNEL_FORM, CONF_NAME: "Nightly", CONF_MQTT_TOPIC: "logs/#"},
    )
    await hass.async_block_till_done()
    assert result["data"][CONF_CHANNELS]["nightly"][CONF_MQTT_TOPIC] == "logs/#"


async def test_mqtt_topic_of_another_channel_is_refused(
    hass: HomeAssistant, setup_entry
) -> None:
    """One message must not land in two channels by accident."""
    result = await _open_channel_editor(hass, setup_entry, "backups")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**CHANNEL_FORM, CONF_ENABLED: True, CONF_MQTT_TOPIC: "logs/shared"},
    )
    await hass.async_block_till_done()

    result = await _open_channel_editor(hass, setup_entry, "services")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            **CHANNEL_FORM,
            CONF_NAME: "Services",
            CONF_ENABLED: True,
            CONF_MQTT_TOPIC: "logs/shared",
        },
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {CONF_MQTT_TOPIC: "duplicate_topic"}

    # The channel's own topic is not a duplicate of itself.
    result = await _open_channel_editor(hass, setup_entry, "backups")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**CHANNEL_FORM, CONF_ENABLED: True, CONF_MQTT_TOPIC: "logs/shared"},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY


async def test_show_urls_names_the_mqtt_topic(hass: HomeAssistant, setup_entry) -> None:
    result = await _open_channel_editor(hass, setup_entry, "backups")
    await hass.config_entries.options.async_configure(
        result["flow_id"],
        {**CHANNEL_FORM, CONF_ENABLED: True, CONF_MQTT_TOPIC: "logs/backups"},
    )
    await hass.async_block_till_done()

    result = await hass.config_entries.options.async_init(setup_entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "show_urls"}
    )

    assert "MQTT `logs/backups`" in result["description_placeholders"]["urls"]
