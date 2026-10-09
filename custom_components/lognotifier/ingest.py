"""Parsing of incoming messages and throttling — without any HA dependency."""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from .const import (
    BLOCK_FIELDS,
    BLOCK_TABLE,
    BLOCK_TEXT,
    FORMAT_MARKDOWN,
    FORMAT_PLAIN,
    FORMATS,
    MAX_CONTENT_CHARS,
    MAX_TAGS,
    RATE_LIMIT_BURST,
    RATE_LIMIT_PER_MINUTE,
    TABLE_ALIGNS,
    VALUE_FORMATS,
)
from .models import Block, Columns, Rows, clamp_blocks, normalize_level


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
    blocks: list[Block] | None = None


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

    # A message made of blocks alone is fine — like a Discord embed without a
    # description.
    has_blocks = bool(data.get("blocks"))
    content = data.get("content", data.get("message", data.get("text")))
    if content is None:
        if not has_blocks:
            raise PayloadError("Field 'content' is missing")
        content = ""
    if not isinstance(content, str):
        content = str(content)
    content = content.strip()
    if len(content) > MAX_CONTENT_CHARS:
        content = content[:MAX_CONTENT_CHARS] + "\n…"
    blocks = parse_blocks(
        data.get("blocks"), text_budget=MAX_CONTENT_CHARS - len(content)
    )
    if not content and not blocks:
        raise PayloadError("Field 'content' is empty")

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
    parsed_ts = parse_timestamp(ts) if ts is not None else None

    return ParsedMessage(
        level=level,
        content=content,
        title=title.strip() if isinstance(title, str) and title.strip() else None,
        source=source.strip() if isinstance(source, str) and source.strip() else None,
        tags=tags,
        format=fmt,
        ts=parsed_ts,
        blocks=blocks or None,
    )


def parse_blocks(value: Any, *, text_budget: int = MAX_CONTENT_CHARS) -> list[Block]:
    """Validate the blocks shown below the content, in their order.

    A block is ``{"type": "text", "text": …}``, ``{"type": "fields",
    "rows": …}`` or ``{"type": "table", "columns": …, "rows": …}``.
    Shorthands: a bare string is a text block; an object without ``type`` is a
    table if it has ``table`` (its rows) or ``columns``, a grid if it has
    ``rows`` and a text block if it has ``text``. A grid's ``rows`` is a list
    of rows, each a list of ``{"label", "value"}`` objects — the row decides
    how many fields sit side by side, and a bare object in place of a row
    counts as a row with one field. A field's optional ``span`` makes it
    several columns wide; a row has as many columns as its spans add up to,
    and its optional ``format`` tells the card how to show the value (see
    ``VALUE_FORMATS``). See ``_parse_table`` for tables.

    Wrong types are refused; empty blocks, rows and fields are dropped, and
    whatever exceeds the limits is cut off, like surplus ``tags``. Text blocks
    share ``text_budget`` — what the content left of ``MAX_CONTENT_CHARS``.
    """
    if value is None:
        return []
    if not isinstance(value, list):
        raise PayloadError("Field 'blocks' must be a list")
    blocks: list[Block] = []
    for item in value:
        if isinstance(item, str):
            item = {"type": BLOCK_TEXT, "text": item}
        if not isinstance(item, dict):
            raise PayloadError("Each block must be a text or an object")
        kind = item.get("type")
        if kind is None and "table" in item:
            item = {**item, "rows": item["table"]}
            kind = BLOCK_TABLE
        if kind is None:
            kind = (
                BLOCK_TABLE
                if "columns" in item
                else BLOCK_FIELDS
                if "rows" in item
                else BLOCK_TEXT
                if "text" in item
                else None
            )
        if kind == BLOCK_TEXT:
            blocks.append({"type": BLOCK_TEXT, "text": _block_text(item.get("text"))})
        elif kind == BLOCK_FIELDS:
            blocks.append({"type": BLOCK_FIELDS, "rows": _parse_rows(item.get("rows"))})
        elif kind == BLOCK_TABLE:
            blocks.append(_parse_table(item))
        else:
            raise PayloadError(f"Unknown block type: {kind!r}")
    return clamp_blocks(blocks, text_budget)


def _parse_rows(value: Any) -> Rows:
    """The rows of one grid block."""
    if not isinstance(value, list):
        raise PayloadError("Block 'rows' must be a list of rows")
    rows: Rows = []
    for raw_row in value:
        row = [raw_row] if isinstance(raw_row, dict) else raw_row
        if not isinstance(row, list):
            raise PayloadError("Each row must be a list of fields")
        parsed_row = []
        for item in row:
            if not isinstance(item, dict):
                raise PayloadError(
                    "Each field must be an object with 'label' and 'value'"
                )
            parsed: dict[str, Any] = {
                "label": _block_text(item.get("label")),
                "value": _block_text(item.get("value")),
            }
            span = item.get("span")
            if span is not None:
                parsed["span"] = _parse_span(span)
            value_format = item.get("format")
            if value_format is not None:
                parsed["format"] = _parse_format(value_format)
            parsed_row.append(parsed)
        rows.append(parsed_row)
    return rows


def _parse_span(value: Any) -> int:
    """How many columns a field spans: a whole number from 1. One too wide for
    its row is not refused but shortened by ``clamp_blocks``."""
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise PayloadError("Field 'span' must be a whole number of at least 1")
    return value


def _parse_table(item: dict[str, Any]) -> Block:
    """One table block: a shared head over rows of cells.

    ``columns`` is optional; each column is a label or ``{"label", "align",
    "format"}`` with ``align`` one of ``left``, ``center``, ``right`` and
    ``format`` one of ``VALUE_FORMATS``, applied to every cell of the column. A row is a list of
    cells, or an object whose keys name the columns — without ``columns`` the
    head is then derived from all keys in the order they first appear. Rows
    of lists and no ``columns`` give a table without a head. Cells are text,
    numbers, booleans or null; padding and limits are ``clamp_blocks``' job.
    """
    raw_rows = item.get("rows")
    if not isinstance(raw_rows, list):
        raise PayloadError("Table 'rows' must be a list of rows")
    for raw_row in raw_rows:
        if not isinstance(raw_row, list | dict):
            raise PayloadError("Each table row must be a list of cells or an object")
    raw_columns = item.get("columns")
    columns: Columns = []
    if raw_columns is None:
        labels: list[str] = []
        for raw_row in raw_rows:
            if isinstance(raw_row, dict):
                labels += [str(key) for key in raw_row if str(key) not in labels]
        columns = [{"label": label} for label in labels]
    elif isinstance(raw_columns, list):
        columns = [_parse_column(raw) for raw in raw_columns]
    else:
        raise PayloadError("Table 'columns' must be a list")
    rows = []
    for raw_row in raw_rows:
        if isinstance(raw_row, dict):
            by_label = {str(key): value for key, value in raw_row.items()}
            rows.append([_cell_text(by_label.get(col["label"])) for col in columns])
        else:
            rows.append([_cell_text(cell) for cell in raw_row])
    return {"type": BLOCK_TABLE, "columns": columns, "rows": rows}


def _parse_column(value: Any) -> dict[str, str]:
    """One column of a table head: a bare label or ``{"label", "align", "format"}``."""
    if not isinstance(value, dict):
        return {"label": _block_text(value)}
    column = {"label": _block_text(value.get("label"))}
    align = value.get("align")
    if align is not None:
        if not isinstance(align, str) or align.lower() not in TABLE_ALIGNS:
            raise PayloadError(
                f"Column 'align' must be one of {', '.join(TABLE_ALIGNS)}"
            )
        column["align"] = align.lower()
    value_format = value.get("format")
    if value_format is not None:
        column["format"] = _parse_format(value_format)
    return column


def _parse_format(value: Any) -> str:
    """How the card shows a value: one of ``VALUE_FORMATS``."""
    if not isinstance(value, str) or value.lower() not in VALUE_FORMATS:
        raise PayloadError(f"'format' must be one of {', '.join(VALUE_FORMATS)}")
    return value.lower()


def _cell_text(value: Any) -> str:
    """A table cell as text; booleans are spelled like in JSON."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, dict | list):
        raise PayloadError("Table cells must be text, numbers or booleans")
    return str(value).strip()


def _block_text(value: Any) -> str:
    """Text, label or value as a trimmed string; nested structures are refused."""
    if value is None:
        return ""
    if isinstance(value, dict | list):
        raise PayloadError("Block text, 'label' and 'value' must be text")
    return str(value).strip()


def parse_timestamp(value: Any) -> float:
    """Turn a Unix time or an ISO 8601 string into a Unix time.

    Numbers and numeric strings are taken as Unix seconds. Anything else must
    be ISO 8601 (``2026-09-28T14:03:00+02:00``, ``…Z``); without an offset the
    value is read as UTC — the sender's local zone is unknown here.
    """
    if isinstance(value, int | float) and not isinstance(value, bool):
        return float(value)
    if isinstance(value, str):
        text = value.strip()
        try:
            return float(text)
        except ValueError:
            pass
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            pass
        else:
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=UTC)
            return parsed.timestamp()
    raise PayloadError("Field 'timestamp' is neither a Unix time nor an ISO 8601 date")


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


def parse_body(
    raw: bytes,
    *,
    is_json: bool = False,
    default_level: str | None = None,
    default_source: str | None = None,
    default_title: str | None = None,
) -> ParsedMessage:
    """Turn a raw body into a message — the part every transport shares.

    ``is_json`` is what the transport knows about the body (a content type);
    without it a body that starts with ``{`` is still taken as JSON, anything
    else as plain text.
    """
    try:
        body = raw.decode("utf-8")
    except UnicodeDecodeError as err:
        raise PayloadError("Body is not UTF-8") from err
    if is_json or body.lstrip().startswith("{"):
        try:
            data = json.loads(body)
        except json.JSONDecodeError as err:
            raise PayloadError(f"Invalid JSON: {err.msg}") from err
        return parse_payload(
            data, default_level=default_level, default_source=default_source
        )
    return parse_text(
        body,
        default_level=default_level,
        default_source=default_source,
        default_title=default_title,
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
