"""Payload parsing and throttling of the ingest endpoint."""

from __future__ import annotations

import importlib

import pytest
from conftest import PACKAGE

const = importlib.import_module(f"{PACKAGE}.const")
ingest = importlib.import_module(f"{PACKAGE}.ingest")


def test_minimal_payload():
    parsed = ingest.parse_payload({"content": "Hello"})
    assert parsed.level == "INFO"
    assert parsed.content == "Hello"
    assert parsed.format == const.FORMAT_MARKDOWN


def test_alternative_field_names():
    # Existing Discord callers send "content", others "message"/"text".
    assert ingest.parse_payload({"message": "a"}).content == "a"
    assert ingest.parse_payload({"text": "b"}).content == "b"


def test_missing_content_is_rejected():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"level": "ERROR"})
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"content": "   "})


def test_unknown_level_is_rejected():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"content": "a", "level": "purple"})


def test_query_parameters_as_defaults():
    parsed = ingest.parse_payload(
        {"content": "a"}, default_level="ERROR", default_source="cron"
    )
    assert parsed.level == "ERROR"
    assert parsed.source == "cron"
    # The payload wins over the query parameter.
    parsed = ingest.parse_payload(
        {"content": "a", "level": "TRACE"}, default_level="ERROR"
    )
    assert parsed.level == "TRACE"


def test_overlong_content_is_truncated():
    parsed = ingest.parse_payload({"content": "x" * (const.MAX_CONTENT_CHARS + 500)})
    assert len(parsed.content) == const.MAX_CONTENT_CHARS + 2


def test_tags_and_format():
    parsed = ingest.parse_payload(
        {"content": "a", "tags": ["backup", "pbs"], "format": "plain"}
    )
    assert parsed.tags == ["backup", "pbs"]
    assert parsed.format == "plain"
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"content": "a", "format": "html"})


def test_non_object_is_rejected():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload(["not", "an", "object"])


def test_timestamp_must_be_a_number():
    assert (
        ingest.parse_payload({"content": "a", "timestamp": 1700000000}).ts == 1700000000
    )
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"content": "a", "timestamp": "yesterday"})


def test_text_body_lands_as_plain():
    parsed = ingest.parse_text("**do not** interpret", default_level="WARNING")
    assert parsed.level == "WARNING"
    assert parsed.format == const.FORMAT_PLAIN
    assert parsed.content == "**do not** interpret"


def test_empty_text_body_is_rejected():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_text("   ")


def test_ratelimit_allows_a_burst_and_then_throttles():
    limiter = ingest.RateLimiter(per_minute=60, burst=5)
    now = 0.0
    assert all(limiter.allow("channel", now) for _ in range(5))
    assert limiter.allow("channel", now) is False
    # After one second exactly one token is refilled at 60/min.
    assert limiter.allow("channel", now + 1.0) is True
    assert limiter.allow("channel", now + 1.0) is False


def test_ratelimit_separates_channels():
    limiter = ingest.RateLimiter(per_minute=60, burst=1)
    assert limiter.allow("a", 0.0) is True
    assert limiter.allow("a", 0.0) is False
    assert limiter.allow("b", 0.0) is True
