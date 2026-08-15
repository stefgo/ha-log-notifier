"""Level normalization: foreign spellings must land cleanly."""

from __future__ import annotations

import importlib

from conftest import PACKAGE

models = importlib.import_module(f"{PACKAGE}.models")


def test_canonical_names_survive():
    for level in ("ERROR", "WARNING", "INFO", "TRACE"):
        assert models.normalize_level(level) == level


def test_lowercase_and_whitespace():
    assert models.normalize_level(" warn ") == "WARNING"
    assert models.normalize_level("debug") == "TRACE"


def test_aliases_of_foreign_loggers():
    assert models.normalize_level("critical") == "ERROR"
    assert models.normalize_level("fatal") == "ERROR"
    assert models.normalize_level("notice") == "INFO"
    assert models.normalize_level("verbose") == "TRACE"


def test_numeric_scales():
    # Python logging
    assert models.normalize_level(40) == "ERROR"
    assert models.normalize_level(30) == "WARNING"
    assert models.normalize_level(20) == "INFO"
    assert models.normalize_level(10) == "TRACE"
    # syslog
    assert models.normalize_level(3) == "ERROR"
    assert models.normalize_level(4) == "WARNING"
    assert models.normalize_level(6) == "INFO"
    assert models.normalize_level(7) == "TRACE"


def test_unknown_level_is_rejected():
    assert models.normalize_level("bananas") is None
    assert models.normalize_level(True) is None


def test_missing_level_falls_back_to_default():
    assert models.normalize_level(None) == "INFO"
    assert models.normalize_level(None, "ERROR") == "ERROR"
    assert models.normalize_level("") == "INFO"


def test_severity_is_comparable():
    assert models.severity("ERROR") > models.severity("WARNING")
    assert models.severity("INFO") > models.severity("TRACE")
    assert models.severity("unknown") == 0


def test_slugify_creates_unique_ids():
    taken: set[str] = set()
    first = models.slugify_id("Backups & Café", taken)
    taken.add(first)
    second = models.slugify_id("Backups & Café", taken)
    assert first == "backups_cafe"
    assert second == "backups_cafe_2"
