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
from homeassistant.helpers.network import NoURLAvailableError, get_url

from .const import (
    CONF_BADGE_LEVELS,
    CONF_CHANNELS,
    CONF_DELETE,
    CONF_ENABLED,
    CONF_ICON,
    CONF_MAX_AGE_DAYS,
    CONF_MAX_MESSAGES,
    CONF_MQTT_TOPIC,
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
from .models import (
    badge_levels_from_options,
    new_token,
    normalize_topic_filter,
    slugify_id,
)

TITLE = "Log Notifier"

# Multi-select instead of a threshold: every level counts on its own in the badge.
# The labels carry the canonical level names verbatim, so they are given inline
# rather than through a translation key — hassfest requires those keys to be
# lower case, which the level names are deliberately not.
BADGE_LEVEL_SELECTOR = selector.SelectSelector(
    selector.SelectSelectorConfig(
        options=[
            selector.SelectOptionDict(value=level, label=level) for level in LEVEL_ORDER
        ],
        multiple=True,
        mode=selector.SelectSelectorMode.LIST,
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
        # A suggested value instead of a default: a default would come back
        # whenever the field is emptied, and emptying it is how MQTT is
        # switched off for the channel.
        vol.Optional(
            CONF_MQTT_TOPIC,
            description={"suggested_value": defaults.get(CONF_MQTT_TOPIC, "")},
        ): str,
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

    @staticmethod
    def _topic_error(
        user_input: dict[str, Any],
        channels: dict[str, dict[str, Any]],
        channel_id: str | None,
    ) -> str | None:
        """Why the entered MQTT topic cannot be used, if it cannot.

        The same filter on two channels is refused — one message would land
        in both. Filters that merely overlap through wildcards are left alone;
        that can be intended.
        """
        entered = (user_input.get(CONF_MQTT_TOPIC) or "").strip()
        if not entered:
            return None
        if normalize_topic_filter(entered) is None:
            return "invalid_topic"
        if any(
            other.get(CONF_MQTT_TOPIC) == entered
            for other_id, other in channels.items()
            if other_id != channel_id
        ):
            return "duplicate_topic"
        return None

    def _suggested_topic(
        self, channels: dict[str, dict[str, Any]], channel_id: str
    ) -> str | None:
        """The topic to pre-fill for a channel that has none: ``lognotifier/<id>``.

        The ID rather than the name, because it survives a rename. Only for a
        channel whose topic was never decided — one that was emptied on
        purpose keeps its empty string and is left alone — and only while the
        MQTT integration is set up: the pre-filled value is saved with the
        form, and without MQTT it would do nothing but warn at every start.
        """
        if CONF_MQTT_TOPIC in channels[channel_id]:
            return None
        if not self.hass.config_entries.async_entries("mqtt"):
            return None
        topic = f"{DOMAIN}/{channel_id}"
        if any(other.get(CONF_MQTT_TOPIC) == topic for other in channels.values()):
            return None
        return topic

    def _ingest_url(self, token: str) -> str:
        """Ingest URL of a channel, as complete as Home Assistant can tell.

        The address the dialog was opened under comes first — it is the one
        known to work. Without one the configured URL serves, and if there is
        none either, the bare path is left.
        """
        path = f"/api/{DOMAIN}/ingest/{token}"
        for current_request in (True, False):
            try:
                base = get_url(self.hass, require_current_request=current_request)
            except NoURLAvailableError:
                continue
            return f"{base}{path}"
        return path

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Menu: create a channel, edit one or look up the ingest URLs."""
        menu = ["add_channel"]
        if self._channels:
            menu.extend(["select_channel", "show_urls"])
        return self.async_show_menu(step_id="init", menu_options=menu)

    async def async_step_show_urls(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """List the ingest URL of every channel; submitting leads back to the menu."""
        if user_input is not None:
            return await self.async_step_init()
        urls = "\n".join(
            f"- **{data.get(CONF_NAME, channel_id)}**: "
            f"`{self._ingest_url(data.get(CONF_TOKEN, ''))}`"
            + (f" · MQTT `{topic}`" if (topic := data.get(CONF_MQTT_TOPIC)) else "")
            for channel_id, data in self._channels.items()
        )
        return self.async_show_form(
            step_id="show_urls",
            data_schema=vol.Schema({}),
            description_placeholders={"urls": urls},
        )

    async def async_step_add_channel(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Create a new channel; the token is generated along with it."""
        channels = self._channels
        error = self._topic_error(user_input, channels, None) if user_input else None
        if user_input is None or error:
            return self.async_show_form(
                step_id="add_channel",
                data_schema=_channel_schema(user_input or {}, editing=False),
                errors={CONF_MQTT_TOPIC: error} if error else None,
            )
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
        if topic := (user_input.get(CONF_MQTT_TOPIC) or "").strip():
            channels[channel_id][CONF_MQTT_TOPIC] = topic
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
            selector.SelectOptionDict(
                value=channel_id, label=data.get(CONF_NAME, channel_id)
            )
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

        # Deleting comes first: a channel on its way out need not have a
        # valid topic.
        if user_input and user_input.get(CONF_DELETE):
            channels.pop(channel_id, None)
            return self._save(channels)

        error = (
            self._topic_error(user_input, channels, channel_id) if user_input else None
        )
        if user_input is None or error:
            defaults = user_input or current
            if user_input is None and (
                suggested := self._suggested_topic(channels, channel_id)
            ):
                defaults = {**current, CONF_MQTT_TOPIC: suggested}
            return self.async_show_form(
                step_id="edit_channel",
                data_schema=_channel_schema(defaults, editing=True),
                errors={CONF_MQTT_TOPIC: error} if error else None,
                description_placeholders={
                    "name": current.get(CONF_NAME, channel_id),
                    "url": self._ingest_url(current.get(CONF_TOKEN, "")),
                },
            )

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
        # Stored even when empty: that is what tells "switched off" apart
        # from "never decided", which gets a topic suggested.
        current[CONF_MQTT_TOPIC] = (user_input.get(CONF_MQTT_TOPIC) or "").strip()
        if user_input.get(CONF_ROTATE_TOKEN):
            current[CONF_TOKEN] = new_token()
        channels[channel_id] = current
        return self._save(channels)
