"""The release workflow's version bump (.github/scripts/bump_version.py)."""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / ".github" / "scripts" / "bump_version.py"

_spec = importlib.util.spec_from_file_location("bump_version", SCRIPT)
assert _spec is not None and _spec.loader is not None
bump_version = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(bump_version)

CHANGELOG = """\
# Changelog

Intro.

## [Unreleased]

### Added

- Something new.

## [1.0.6] — 2026-09-28

### Added

- Something old.

[1.0.6]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.5...v1.0.6
"""


@pytest.mark.parametrize(
    ("bump", "expected"),
    [("patch", "1.0.7"), ("minor", "1.1.0"), ("major", "2.0.0")],
)
def test_next_version(bump, expected):
    assert bump_version.next_version("1.0.6", bump) == expected


def test_next_version_rejects_prereleases():
    with pytest.raises(ValueError):
        bump_version.next_version("1.0.6-beta", "patch")


def test_close_changelog_opens_a_fresh_unreleased_section():
    text = bump_version.close_changelog(CHANGELOG, "1.0.6", "1.1.0", "2026-10-01")
    assert (
        "## [Unreleased]\n\n## [1.1.0] — 2026-10-01\n\n### Added\n\n- Something new."
        in text
    )
    assert text.index("[1.1.0]: ") < text.index("[1.0.6]: ")
    assert (
        "[1.1.0]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.6...v1.1.0\n"
        in text
    )


def test_close_changelog_refuses_an_empty_entry():
    empty = CHANGELOG.replace("### Added\n\n- Something new.\n\n", "", 1)
    with pytest.raises(ValueError, match="empty"):
        bump_version.close_changelog(empty, "1.0.6", "1.0.7", "2026-10-01")


def test_close_changelog_refuses_a_missing_section():
    missing = CHANGELOG.replace("## [Unreleased]\n", "", 1)
    with pytest.raises(ValueError, match="no '## \\[Unreleased\\]'"):
        bump_version.close_changelog(missing, "1.0.6", "1.0.7", "2026-10-01")


def test_set_version_refuses_disagreeing_files():
    with pytest.raises(ValueError):
        bump_version.set_version('{"version": "1.0.5"}', "1.0.6", "1.0.7", 1)


def test_main_bumps_every_file_of_the_real_repository(tmp_path, monkeypatch, capsys):
    """Run against copies of the real files, so a format change in any of them shows up here."""
    for path in (
        bump_version.MANIFEST,
        bump_version.PACKAGE,
        bump_version.LOCKFILE,
    ):
        (tmp_path / path).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(ROOT / path, tmp_path / path)
    (tmp_path / bump_version.CHANGELOG).write_text(CHANGELOG, encoding="utf-8")
    old = json.loads((ROOT / bump_version.MANIFEST).read_text(encoding="utf-8"))[
        "version"
    ]
    new = bump_version.next_version(old, "minor")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("sys.argv", ["bump_version.py", "minor", "2026-10-01"])
    bump_version.main()

    assert capsys.readouterr().out == f"{new}\n"
    for path in (bump_version.MANIFEST, bump_version.PACKAGE):
        assert json.loads(path.read_text(encoding="utf-8"))["version"] == new
    lock = json.loads(bump_version.LOCKFILE.read_text(encoding="utf-8"))
    assert lock["version"] == new
    assert lock["packages"][""]["version"] == new
