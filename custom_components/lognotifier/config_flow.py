"""Setup and channel management."""

from __future__ import annotations

from copy import deepcopy
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.core import callback
from homeassistant.helpers import selector

from .const import (
    CONF_BADGE_LEVELS,
    CONF_CHANNELS,
    CONF_DELETE,
    CONF_ENABLED,
    CONF_ICON,
    CONF_MAX_AGE_DAYS,
    CONF_MAX_MESSAGES,
    CONF_NAME,
    CONF_ROTATE_TOKEN,
    CONF_TOKEN,
    DEFAULT_ICON,
    DEFAULT_MAX_AGE_DAYS,
    DEFAULT_MAX_MESSAGES,
    DOMAIN,
    LEVEL_ORDER,
    MAX_AGE_DAYS_LIMIT,
    MAX_MESSAGES_LIMIT,
)
from .models import badge_levels_from_options, new_token, slugify_id

TITLE = "Log Notifier"

# Multi-select instead of a threshold: every level counts on its own in the badge.
BADGE_LEVEL_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=LEVEL_ORDER,
        multiple=True,
        mode=selector.SelectSelectorMode.LIST,
        translation_key="level",
    )
)


def _channel_schema(defaults: dict[str, Any], *, editing: bool) -> vol.Schema:
    """Form for creating and editing a channel."""
    schema: dict[Any, Any] = {
        vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, "")): str,
        vol.Optional(
            CONF_ICON, default=defaults.get(CONF_ICON, DEFAULT_ICON)
        ): selector.IconSelector(),
        vol.Required(
            CONF_BADGE_LEVELS,
            default=badge_levels_from_options(defaults),
        ): BADGE_LEVEL_SELECTOR,
        vol.Required(
            CONF_MAX_MESSAGES,
            default=defaults.get(CONF_MAX_MESSAGES, DEFAULT_MAX_MESSAGES),
        ): vol.All(vol.Coerce(int), vol.Range(min=1, max=MAX_MESSAGES_LIMIT)),
        vol.Required(
            CONF_MAX_AGE_DAYS,
            default=defaults.get(CONF_MAX_AGE_DAYS, DEFAULT_MAX_AGE_DAYS),
        ): vol.All(vol.Coerce(int), vol.Range(min=0, max=MAX_AGE_DAYS_LIMIT)),
    }
    if editing:
        schema[vol.Required(CONF_ENABLED, default=defaults.get(CONF_ENABLED, True))] = (
            bool
        )
        schema[vol.Optional(CONF_ROTATE_TOKEN, default=False)] = bool
        schema[vol.Optional(CONF_DELETE, default=False)] = bool
    return vol.Schema(schema)


class LogNotifierConfigFlow(ConfigFlow, domain=DOMAIN):
    """Setup of the integration — a single instance is enough."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """There is nothing to configure; channels are added via the options."""
        self._async_abort_entries_match()
        if user_input is None:
            return self.async_show_form(step_id="user", data_schema=vol.Schema({}))
        return self.async_create_entry(
            title=TITLE, data={}, options={CONF_CHANNELS: {}}
        )

    @staticmethod
    @callback
    def async_get_options_flow(entry: ConfigEntry) -> LogNotifierOptionsFlow:
        """Channel management."""
        return LogNotifierOptionsFlow()


class LogNotifierOptionsFlow(OptionsFlow):
    """Create, edit and delete channels."""

    def __init__(self) -> None:
        self._selected: str | None = None

    @property
    def _channels(self) -> dict[str, dict[str, Any]]:
        """Copy of the channels — deep, not shallow.

        A shallow copy would pass the config entry's inner dicts on unchanged;
        ``current.update(…)`` would then modify the options in place. Home
        Assistant compares old against new when saving, would see no difference
        and would run neither the update listener nor a reload: the new channel
        name would never arrive anywhere.
        """
        return deepcopy(dict(self.config_entry.options.get(CONF_CHANNELS, {})))

    def _save(self, channels: dict[str, dict[str, Any]]) -> ConfigFlowResult:
        return self.async_create_entry(data={CONF_CHANNELS: channels})

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu: create a new channel or edit an existing one."""
        menu = ["add_channel"]
        if self._channels:
            menu.append("select_channel")
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_add_channel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a new channel; the token is generated along with it."""
        if user_input is None:
            return self.async_show_form(
                step_id="add_channel",
                data_schema=_channel_schema({}, editing=False),
            )
        channels = self._channels
        channel_id = slugify_id(user_input[CONF_NAME], set(channels))
        channels[channel_id] = {
            CONF_NAME: user_input[CONF_NAME],
            CONF_TOKEN: new_token(),
            CONF_ICON: user_input.get(CONF_ICON, DEFAULT_ICON),
            CONF_BADGE_LEVELS: user_input[CONF_BADGE_LEVELS],
            CONF_MAX_MESSAGES: user_input[CONF_MAX_MESSAGES],
            CONF_MAX_AGE_DAYS: user_input[CONF_MAX_AGE_DAYS],
            CONF_ENABLED: True,
        }
        return self._save(channels)

    async def async_step_select_channel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Select a channel to edit."""
        channels = self._channels
        if user_input is not None:
            self._selected = user_input["channel"]
            return await self.async_step_edit_channel()
        options = [
            selector.SelectOptionDict(value=channel_id, label=data.get(CONF_NAME, channel_id))
            for channel_id, data in channels.items()
        ]
        return self.async_show_form(
            step_id="select_channel",
            data_schema=vol.Schema(
                {
                    vol.Required("channel"): selector.SelectSelector(
                        selector.SelectSelectorConfig(
                            options=options,
                            mode=selector.SelectSelectorMode.DROPDOWN,
                        )
                    )
                }
            ),
        )

    async def async_step_edit_channel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit a channel, rotate its token or delete it."""
        channels = self._channels
        channel_id = self._selected
        if channel_id is None or channel_id not in channels:
            return await self.async_step_init()
        current = channels[channel_id]

        if user_input is None:
            return self.async_show_form(
                step_id="edit_channel",
                data_schema=_channel_schema(current, editing=True),
                description_placeholders={
                    "name": current.get(CONF_NAME, channel_id),
                    "url": f"/api/{DOMAIN}/ingest/{current.get(CONF_TOKEN, '')}",
                },
            )

        if user_input.get(CONF_DELETE):
            channels.pop(channel_id, None)
            return self._save(channels)

        current.update(
            {
                CONF_NAME: user_input[CONF_NAME],
                CONF_ICON: user_input.get(CONF_ICON, DEFAULT_ICON),
                CONF_BADGE_LEVELS: user_input[CONF_BADGE_LEVELS],
                CONF_MAX_MESSAGES: user_input[CONF_MAX_MESSAGES],
                CONF_MAX_AGE_DAYS: user_input[CONF_MAX_AGE_DAYS],
                CONF_ENABLED: user_input[CONF_ENABLED],
            }
        )
        if user_input.get(CONF_ROTATE_TOKEN):
            current[CONF_TOKEN] = new_token()
        channels[channel_id] = current
        return self._save(channels)
