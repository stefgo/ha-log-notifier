"""Consistency of manifest, translations and services."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest

from conftest import COMPONENT, PACKAGE

const = importlib.import_module(f"{PACKAGE}.const")


def load(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def test_manifest_matches_the_domain():
    manifest = load(COMPONENT / "manifest.json")
    assert manifest["domain"] == const.DOMAIN
    assert manifest["version"] == const.INTEGRATION_VERSION
    assert manifest["config_flow"] is True


def collect_keys(data, prefix=""):
    if isinstance(data, dict):
        keys = set()
        for key, value in data.items():
            keys |= collect_keys(value, f"{prefix}.{key}")
        return keys
    return {prefix}


@pytest.mark.parametrize("language", ["de", "en"])
def test_translations_are_complete(language):
    strings = load(COMPONENT / "strings.json")
    translation = load(COMPONENT / "translations" / f"{language}.json")
    assert collect_keys(strings) == collect_keys(translation)


def test_services_yaml_knows_the_same_services():
    import re

    # services.py is read instead of imported: it depends on Home Assistant,
    # which is deliberately not installed for these tests.
    source = (COMPONENT / "services.py").read_text(encoding="utf-8")
    expected = set(re.findall(r'^SERVICE_\w+ = "(\w+)"$', source, re.MULTILINE))
    assert expected, "No SERVICE_ constants found"
    yaml_text = (COMPONENT / "services.yaml").read_text(encoding="utf-8")
    # No YAML parser needed: services are the only lines without indentation.
    defined = set(re.findall(r"^(\w+):$", yaml_text, re.MULTILINE))
    assert defined == expected
    strings = load(COMPONENT / "strings.json")
    assert set(strings["services"]) == expected


def test_level_constants_line_up():
    assert set(const.LEVELS) == set(const.LEVEL_ORDER)
    # Descending by severity — the card relies on it.
    severities = [const.LEVELS[level] for level in const.LEVEL_ORDER]
    assert severities == sorted(severities, reverse=True)
    # Every canonical name must also alias to itself.
    for level in const.LEVEL_ORDER:
        assert const.LEVEL_ALIASES[level] == level


def test_card_constants_match_the_build():
    rollup = (COMPONENT.parents[1] / "card" / "rollup.config.js").read_text(
        encoding="utf-8"
    )
    assert const.CARD_FILENAME in rollup
    assert f"custom_components/{const.DOMAIN}/www" in rollup
