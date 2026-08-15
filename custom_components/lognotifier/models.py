"""Data models for channels and messages."""

from __future__ import annotations

import secrets
import unicodedata
from dataclasses import dataclass, field
from typing import Any

from .const import (
    CONF_BADGE_LEVELS,
    CONF_ENABLED,
    CONF_ICON,
    CONF_MAX_AGE_DAYS,
    CONF_MAX_MESSAGES,
    CONF_NAME,
    CONF_TOKEN,
    DEFAULT_BADGE_LEVELS,
    DEFAULT_ICON,
    DEFAULT_MAX_AGE_DAYS,
    DEFAULT_MAX_MESSAGES,
    FORMAT_MARKDOWN,
    FORMAT_PLAIN,
    LEVEL_ALIASES,
    LEVEL_INFO,
    LEVEL_ORDER,
    LEVELS,
    MAX_AGE_DAYS_LIMIT,
    MAX_MESSAGES_LIMIT,
)

TOKEN_BYTES = 24


def new_token() -> str:
    """Create a channel token.

    ``token_urlsafe`` yields URL-safe characters — the token sits in the path
    of the ingest URL and must not need any encoding there.
    """
    return secrets.token_urlsafe(TOKEN_BYTES)


def normalize_level(value: Any, default: str = LEVEL_INFO) -> str | None:
    """Map a level value onto one of the four supported names.

    Foreign services write ``warn``, ``critical`` or a syslog number; as long
    as the intent is unambiguous it gets translated instead of rejected.
    Returning ``None`` means: not interpretable (the caller answers with 400
    rather than silently assigning a wrong level).
    """
    if value is None:
        return default
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return level_from_severity(int(value))
    if not isinstance(value, str):
        return None
    text = value.strip().upper()
    if not text:
        return default
    if text.isdigit():
        return level_from_severity(int(text))
    return LEVEL_ALIASES.get(text)


def level_from_severity(severity: int) -> str:
    """Map a numeric severity onto the closest level.

    Covers both the Python logging scale (10–50, ascending) and syslog
    priorities (0–7, descending): values up to 7 are read as syslog, everything
    above as the logging scale.
    """
    if severity <= 7:
        # syslog: 0 emerg … 3 err, 4 warning, 5 notice, 6 info, 7 debug
        if severity <= 3:
            return "ERROR"
        if severity == 4:
            return "WARNING"
        if severity <= 6:
            return "INFO"
        return "TRACE"
    if severity >= 40:
        return "ERROR"
    if severity >= 30:
        return "WARNING"
    if severity >= 20:
        return "INFO"
    return "TRACE"


def severity(level: str) -> int:
    """Numeric severity of a level (unknown → 0, so it never counts)."""
    return LEVELS.get(level, 0)


def slugify_id(name: str, taken: set[str]) -> str:
    """Derive a stable, unique channel ID from the display name."""
    normalized = unicodedata.normalize("NFKD", name)
    ascii_only = "".join(c for c in normalized if not unicodedata.combining(c))
    slug = "".join(c if c.isalnum() else "_" for c in ascii_only.lower())
    slug = "_".join(part for part in slug.split("_") if part)
    slug = slug[:40] or "channel"
    candidate = slug
    suffix = 2
    while candidate in taken:
        candidate = f"{slug}_{suffix}"
        suffix += 1
    return candidate


def badge_levels_from_options(data: dict[str, Any]) -> list[str]:
    """Read the badge levels from a channel's options data.

    Unknown entries are dropped and the order comes from ``LEVEL_ORDER``: the
    selection is a set, yet its representation should stay stable.
    """
    raw = data.get(CONF_BADGE_LEVELS)
    if not isinstance(raw, list):
        return list(DEFAULT_BADGE_LEVELS)
    selected = {level for level in raw if level in LEVELS}
    return [level for level in LEVEL_ORDER if level in selected]


@dataclass
class Channel:
    """A channel: target of an ingest token and reference point of the badge."""

    id: str
    name: str
    token: str
    icon: str = DEFAULT_ICON
    #: Levels that count towards the badge — a selection, not a threshold.
    badge_levels: list[str] = field(default_factory=lambda: list(DEFAULT_BADGE_LEVELS))
    max_messages: int = DEFAULT_MAX_MESSAGES
    max_age_days: int = DEFAULT_MAX_AGE_DAYS
    enabled: bool = True

    @classmethod
    def from_dict(cls, channel_id: str, data: dict[str, Any]) -> Channel:
        """Build a channel from the config entry options data."""
        return cls(
            id=channel_id,
            name=str(data.get(CONF_NAME) or channel_id),
            token=str(data.get(CONF_TOKEN) or ""),
            icon=str(data.get(CONF_ICON) or DEFAULT_ICON),
            badge_levels=badge_levels_from_options(data),
            max_messages=_clamp(
                data.get(CONF_MAX_MESSAGES), DEFAULT_MAX_MESSAGES, 1, MAX_MESSAGES_LIMIT
            ),
            max_age_days=_clamp(
                data.get(CONF_MAX_AGE_DAYS), DEFAULT_MAX_AGE_DAYS, 0, MAX_AGE_DAYS_LIMIT
            ),
            enabled=bool(data.get(CONF_ENABLED, True)),
        )

    def to_dict(self) -> dict[str, Any]:
        """Options representation (without the ID — that one is the key)."""
        return {
            CONF_NAME: self.name,
            CONF_TOKEN: self.token,
            CONF_ICON: self.icon,
            CONF_BADGE_LEVELS: list(self.badge_levels),
            CONF_MAX_MESSAGES: self.max_messages,
            CONF_MAX_AGE_DAYS: self.max_age_days,
            CONF_ENABLED: self.enabled,
        }


def _clamp(value: Any, default: int, minimum: int, maximum: int) -> int:
    """Keep a numeric value within its bounds; nonsense falls back to the default."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(maximum, number))


@dataclass
class Message:
    """A single message in a channel."""

    id: int
    ts: float
    level: str
    content: str
    title: str | None = None
    source: str | None = None
    tags: list[str] = field(default_factory=list)
    format: str = FORMAT_MARKDOWN

    def to_dict(self) -> dict[str, Any]:
        """Compact representation for storage, WebSocket and event."""
        data: dict[str, Any] = {
            "id": self.id,
            "ts": self.ts,
            "level": self.level,
            "content": self.content,
        }
        if self.title:
            data["title"] = self.title
        if self.source:
            data["source"] = self.source
        if self.tags:
            data["tags"] = list(self.tags)
        if self.format != FORMAT_MARKDOWN:
            data["format"] = self.format
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Message:
        """Read a message back from storage."""
        fmt = data.get("format")
        return cls(
            id=int(data["id"]),
            ts=float(data["ts"]),
            level=str(data.get("level") or LEVEL_INFO),
            content=str(data.get("content") or ""),
            title=data.get("title"),
            source=data.get("source"),
            tags=list(data.get("tags") or []),
            format=fmt if fmt in (FORMAT_MARKDOWN, FORMAT_PLAIN) else FORMAT_MARKDOWN,
        )
