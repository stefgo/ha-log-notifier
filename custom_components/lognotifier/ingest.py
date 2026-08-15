"""Parsing of incoming messages and throttling — without any HA dependency."""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .const import (
    FORMAT_MARKDOWN,
    FORMAT_PLAIN,
    FORMATS,
    MAX_CONTENT_CHARS,
    MAX_TAGS,
    RATE_LIMIT_BURST,
    RATE_LIMIT_PER_MINUTE,
)
from .models import normalize_level


@dataclass
class ParsedMessage:
    """A validated message, ready for the store."""

    level: str
    content: str
    title: str | None = None
    source: str | None = None
    tags: list[str] | None = None
    format: str = FORMAT_MARKDOWN
    ts: float | None = None


class PayloadError(ValueError):
    """The caller sent something that cannot be interpreted."""


def parse_payload(
    data: Any,
    *,
    default_level: str | None = None,
    default_source: str | None = None,
) -> ParsedMessage:
    """Validate a JSON payload and build a message from it.

    ``default_level``/``default_source`` come from the URL query parameters: a
    shell script can simply append ``?level=ERROR&source=cron`` instead of
    having to build JSON.
    """
    if not isinstance(data, dict):
        raise PayloadError("Object expected")

    content = data.get("content", data.get("message", data.get("text")))
    if content is None:
        raise PayloadError("Field 'content' is missing")
    if not isinstance(content, str):
        content = str(content)
    content = content.strip()
    if not content:
        raise PayloadError("Field 'content' is empty")
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "\n…"

    raw_level = data.get("level", default_level)
    level = normalize_level(raw_level)
    if level is None:
        raise PayloadError(f"Unknown level: {raw_level!r}")

    title = data.get("title")
    if title is not None and not isinstance(title, str):
        title = str(title)
    source = data.get("source", default_source)
    if source is not None and not isinstance(source, str):
        source = str(source)

    tags_raw = data.get("tags")
    tags: list[str] | None = None
    if isinstance(tags_raw, str):
        tags = [tags_raw]
    elif isinstance(tags_raw, list):
        tags = [str(tag) for tag in tags_raw[:MAX_TAGS]]

    fmt = data.get("format", FORMAT_MARKDOWN)
    if fmt not in FORMATS:
        raise PayloadError(f"Unknown format: {fmt!r}")

    ts = data.get("timestamp")
    parsed_ts: float | None = None
    if ts is not None:
        try:
            parsed_ts = float(ts)
        except (TypeError, ValueError):
            raise PayloadError("Field 'timestamp' is not a number") from None

    return ParsedMessage(
        level=level,
        content=content,
        title=title.strip() if isinstance(title, str) and title.strip() else None,
        source=source.strip() if isinstance(source, str) and source.strip() else None,
        tags=tags,
        format=fmt,
        ts=parsed_ts,
    )


def parse_text(
    text: str,
    *,
    default_level: str | None = None,
    default_source: str | None = None,
    default_title: str | None = None,
) -> ParsedMessage:
    """Accept a plain text body (``curl --data-binary @-``).

    Without ``Content-Type: application/json`` every special character would be
    an escaping problem; the text is therefore deliberately left uninterpreted
    and lands in the channel as a plain message.
    """
    content = text.strip()
    if not content:
        raise PayloadError("Empty body")
    level = normalize_level(default_level)
    if level is None:
        raise PayloadError(f"Unknown level: {default_level!r}")
    return ParsedMessage(
        level=level,
        content=content[:MAX_CONTENT_CHARS],
        title=default_title or None,
        source=default_source or None,
        format=FORMAT_PLAIN,
    )


class RateLimiter:
    """Token bucket per channel.

    The ingest endpoint is only protected by the channel token; a service stuck
    in an error loop should neither flush the buffer nor keep HA busy. Short
    bursts (``burst``) stay allowed, sustained throughput is capped.
    """

    def __init__(
        self,
        per_minute: int = RATE_LIMIT_PER_MINUTE,
        burst: int = RATE_LIMIT_BURST,
    ) -> None:
        self._rate = per_minute / 60.0
        self._burst = float(burst)
        self._buckets: dict[str, tuple[float, float]] = {}

    def allow(self, key: str, now: float | None = None) -> bool:
        """May this message pass?"""
        now = now if now is not None else time.monotonic()
        tokens, last = self._buckets.get(key, (self._burst, now))
        tokens = min(self._burst, tokens + (now - last) * self._rate)
        if tokens < 1.0:
            self._buckets[key] = (tokens, now)
            return False
        self._buckets[key] = (tokens - 1.0, now)
        return True

    def state(self) -> dict[str, float]:
        """Remaining tokens per channel — for diagnostics."""
        return {key: round(tokens, 2) for key, (tokens, _) in self._buckets.items()}
