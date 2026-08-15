"""Constants for the Log Notifier integration."""

from __future__ import annotations

import json
from pathlib import Path

DOMAIN = "lognotifier"


def _manifest_version() -> str:
    """Read the version from the manifest.

    Single source of truth: a second constant here would sooner or later drift
    apart from the manifest. Home Assistant imports an integration in the
    executor, so the file access does not block the event loop.
    """
    try:
        manifest = json.loads(
            (Path(__file__).parent / "manifest.json").read_text(encoding="utf-8")
        )
    except (OSError, ValueError):
        return "0.0.0"
    version = manifest.get("version")
    return version if isinstance(version, str) and version else "0.0.0"


INTEGRATION_VERSION = _manifest_version()

# --- Log levels -----------------------------------------------------------
# Numeric severity graded like syslog/Python logging: comparisons ("WARNING and
# above") then work on numbers instead of special cases.
LEVEL_ERROR = "ERROR"
LEVEL_WARNING = "WARNING"
LEVEL_INFO = "INFO"
LEVEL_TRACE = "TRACE"

LEVELS: dict[str, int] = {
    LEVEL_ERROR: 40,
    LEVEL_WARNING: 30,
    LEVEL_INFO: 20,
    LEVEL_TRACE: 10,
}

# Descending by severity — the order used for selectors and counters.
LEVEL_ORDER: list[str] = [LEVEL_ERROR, LEVEL_WARNING, LEVEL_INFO, LEVEL_TRACE]

# Common spellings used by other loggers, so services can keep sending their
# own level names without translating them first.
LEVEL_ALIASES: dict[str, str] = {
    "CRITICAL": LEVEL_ERROR,
    "CRIT": LEVEL_ERROR,
    "FATAL": LEVEL_ERROR,
    "EMERG": LEVEL_ERROR,
    "ALERT": LEVEL_ERROR,
    "ERR": LEVEL_ERROR,
    "ERROR": LEVEL_ERROR,
    "WARN": LEVEL_WARNING,
    "WARNING": LEVEL_WARNING,
    "NOTICE": LEVEL_INFO,
    "INFO": LEVEL_INFO,
    "INFORMATION": LEVEL_INFO,
    "DEBUG": LEVEL_TRACE,
    "TRACE": LEVEL_TRACE,
    "VERBOSE": LEVEL_TRACE,
}

# --- Configuration keys ---------------------------------------------------
CONF_CHANNELS = "channels"
CONF_CHANNEL_ID = "channel_id"
CONF_NAME = "name"
CONF_ICON = "icon"
CONF_TOKEN = "token"
CONF_BADGE_LEVELS = "badge_levels"
CONF_MAX_MESSAGES = "max_messages"
CONF_MAX_AGE_DAYS = "max_age_days"
CONF_ENABLED = "enabled"
CONF_ROTATE_TOKEN = "rotate_token"
CONF_DELETE = "delete"

DEFAULT_ICON = "mdi:message-text-outline"
# TRACE stays out of the badge: tracing should not nudge anyone.
DEFAULT_BADGE_LEVELS = [LEVEL_ERROR, LEVEL_WARNING, LEVEL_INFO]
DEFAULT_MAX_MESSAGES = 500
DEFAULT_MAX_AGE_DAYS = 30

# Upper bounds so a misconfigured channel cannot blow up storage.
MAX_MESSAGES_LIMIT = 5000
MAX_AGE_DAYS_LIMIT = 365

# --- Ingest ---------------------------------------------------------------
# 16 KiB is enough for long stack traces and at the same time limits the work
# an unauthenticated call can trigger.
MAX_BODY_BYTES = 16 * 1024
MAX_CONTENT_CHARS = 8000
MAX_TITLE_CHARS = 200
MAX_SOURCE_CHARS = 100
MAX_TAGS = 10
MAX_TAG_CHARS = 40

RATE_LIMIT_PER_MINUTE = 60
RATE_LIMIT_BURST = 20

FORMAT_MARKDOWN = "markdown"
FORMAT_PLAIN = "plain"
FORMATS = (FORMAT_MARKDOWN, FORMAT_PLAIN)

# --- Events, signals, storage ---------------------------------------------
EVENT_MESSAGE = f"{DOMAIN}_message"
SIGNAL_CHANNEL_UPDATED = f"{DOMAIN}_channel_updated"
# One signal for all total entities: they do not care which channel moved, and
# a per-channel subscription would have to be re-wired on every channel
# change.
SIGNAL_TOTALS_UPDATED = f"{DOMAIN}_totals_updated"

# Key component of the total entities (unique ID and device).
TOTALS_KEY = "totals"

# Open cards are tied to the HA instance, not to the config entry: a reload
# after a channel change rebuilds the runtime object, but the WebSocket
# connections survive it and have to keep being served.
DATA_SUBSCRIBERS = f"{DOMAIN}_subscribers"

STORAGE_KEY = f"{DOMAIN}.messages"
STORAGE_VERSION = 1
STORAGE_SAVE_DELAY = 10

# --- Frontend -------------------------------------------------------------
CARD_FILENAME = "log-notifier-card.js"
CARD_URL_PATH = f"/{DOMAIN}_static"

ATTR_CHANNEL_ID = "channel_id"
ATTR_LEVEL = "level"
ATTR_TITLE = "title"
ATTR_CONTENT = "content"
ATTR_SOURCE = "source"
ATTR_TAGS = "tags"
ATTR_FORMAT = "format"
ATTR_MESSAGE_ID = "message_id"
ATTR_UP_TO_ID = "up_to_id"
