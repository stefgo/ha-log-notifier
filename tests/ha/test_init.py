"""Setting up and unloading the config entry."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntryState
from homeassistant.core import HomeAssistant

from custom_components.lognotifier.const import DOMAIN
from custom_components.lognotifier.services import (
    SERVICE_CLEAR,
    SERVICE_MARK_READ,
    SERVICE_SEND,
)


async def test_setup_registers_everything(hass: HomeAssistant, setup_entry) -> None:
    """A set-up entry brings services, entities and the runtime with it."""
    assert setup_entry.state is ConfigEntryState.LOADED
    assert setup_entry.runtime_data is not None

    for service in (SERVICE_SEND, SERVICE_MARK_READ, SERVICE_CLEAR):
        assert hass.services.has_service(DOMAIN, service)

    # One device per channel, and the entities that belong to it.
    assert {channel.id for channel in setup_entry.runtime_data.channels} == {
        "backups",
        "services",
    }
    entities = hass.states.async_entity_ids()
    assert any(entity.startswith("sensor.") for entity in entities)
    assert any(entity.startswith("binary_sensor.") for entity in entities)


async def test_unload_keeps_the_instance_wide_registrations(
    hass: HomeAssistant, setup_entry
) -> None:
    """Unloading takes the platforms down, not the view or the services.

    They belong to the running instance and are reused on the next setup —
    registering them twice is what the DATA_SETUP_DONE flag prevents.
    """
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()

    assert setup_entry.state is ConfigEntryState.NOT_LOADED
    assert hass.services.has_service(DOMAIN, SERVICE_SEND)


async def test_setup_after_unload_works(hass: HomeAssistant, setup_entry) -> None:
    """A reload must not trip over the registrations of the first setup."""
    assert await hass.config_entries.async_unload(setup_entry.entry_id)
    await hass.async_block_till_done()

    assert await hass.config_entries.async_setup(setup_entry.entry_id)
    await hass.async_block_till_done()
    assert setup_entry.state is ConfigEntryState.LOADED


async def test_changed_channels_reload_the_entry(
    hass: HomeAssistant, setup_entry
) -> None:
    """The update listener reloads, so the entities follow the channels."""
    from custom_components.lognotifier.const import CONF_CHANNELS

    from .conftest import channel_options

    hass.config_entries.async_update_entry(
        setup_entry, options={CONF_CHANNELS: channel_options()}
    )
    await hass.async_block_till_done()

    assert [channel.id for channel in setup_entry.runtime_data.channels] == ["backups"]
