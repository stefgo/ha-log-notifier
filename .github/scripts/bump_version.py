"""Raise the version and close the CHANGELOG's Unreleased section.

Usage: bump_version.py {patch|minor|major} [<date>]

Prints the new version and nothing else, so the release workflow can capture
it. <date> (YYYY-MM-DD) defaults to today in UTC.

The version lives in three files that have to agree before anything is
written: the integration manifest (the single source of truth), the card's
package.json and its lockfile. The files are edited as text, not re-serialized,
so their formatting survives.

The CHANGELOG stays hand-written. This script only turns the Unreleased
heading into the version's heading, opens a fresh empty Unreleased section
above it and adds the compare link — and refuses when there is nothing under
Unreleased, because a release without an entry says nothing about what
changed.
"""

from __future__ import annotations

import datetime
import json
import re
import sys
from pathlib import Path

REPO = "stefgo/ha-log-notifier"

MANIFEST = Path("custom_components/lognotifier/manifest.json")
PACKAGE = Path("card/package.json")
LOCKFILE = Path("card/package-lock.json")
CHANGELOG = Path("CHANGELOG.md")

BUMPS = ("patch", "minor", "major")

UNRELEASED = re.compile(r"^## \[Unreleased\][^\n]*\n", re.MULTILINE)
NEXT_HEADING = re.compile(r"^## \[|^\[[^\]]+\]: ", re.MULTILINE)
FIRST_LINK = re.compile(r"^\[[^\]]+\]: ", re.MULTILINE)
# The first "version" key of each file is the project's own: top level in
# manifest.json and package.json, top level and then packages[""] in the lock.
VERSION_KEY = re.compile(r'("version":\s*")([^"]+)(")')


def next_version(current: str, bump: str) -> str:
    """The version after ``current`` for a patch, minor or major bump."""
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)", current)
    if not match:
        raise ValueError(f"'{current}' is not a plain x.y.z version")
    major, minor, patch = (int(part) for part in match.groups())
    if bump == "major":
        return f"{major + 1}.0.0"
    if bump == "minor":
        return f"{major}.{minor + 1}.0"
    if bump == "patch":
        return f"{major}.{minor}.{patch + 1}"
    raise ValueError(f"unknown bump '{bump}', expected one of {', '.join(BUMPS)}")


def set_version(text: str, old: str, new: str, count: int) -> str:
    """Replace the first ``count`` version keys, which must all read ``old``."""
    found = [match.group(2) for match in VERSION_KEY.finditer(text)][:count]
    if found != [old] * count:
        raise ValueError(
            f"expected version {old} in the first {count} key(s), found {found}"
        )
    return VERSION_KEY.sub(rf"\g<1>{new}\g<3>", text, count=count)


def close_changelog(text: str, old: str, new: str, date: str) -> str:
    """Turn ``[Unreleased]`` into ``[new] — date`` and add its compare link."""
    heading = UNRELEASED.search(text)
    if heading is None:
        raise ValueError("CHANGELOG.md has no '## [Unreleased]' section")
    following = NEXT_HEADING.search(text, heading.end())
    body = text[heading.end() : following.start() if following else len(text)]
    if not body.strip():
        raise ValueError(
            "The '## [Unreleased]' section in CHANGELOG.md is empty — "
            "write the entry before releasing"
        )
    if re.search(rf"^## \[{re.escape(new)}\]", text, re.MULTILINE):
        raise ValueError(f"CHANGELOG.md already has a section for {new}")

    text = (
        text[: heading.start()]
        + f"## [Unreleased]\n\n## [{new}] — {date}\n"
        + text[heading.end() :]
    )

    link = f"[{new}]: https://github.com/{REPO}/compare/v{old}...v{new}\n"
    first = FIRST_LINK.search(text)
    if first is None:
        return text.rstrip("\n") + "\n\n" + link
    return text[: first.start()] + link + text[first.start() :]


def main() -> None:
    if not 2 <= len(sys.argv) <= 3 or sys.argv[1] not in BUMPS:
        raise SystemExit(__doc__)
    bump = sys.argv[1]
    date = (
        sys.argv[2]
        if len(sys.argv) == 3
        else datetime.datetime.now(datetime.UTC).date().isoformat()
    )
    datetime.date.fromisoformat(date)

    old = json.loads(MANIFEST.read_text(encoding="utf-8"))["version"]
    new = next_version(old, bump)

    # Everything is computed before the first write: a refusal leaves the
    # working tree untouched.
    try:
        updated = {
            MANIFEST: set_version(MANIFEST.read_text(encoding="utf-8"), old, new, 1),
            PACKAGE: set_version(PACKAGE.read_text(encoding="utf-8"), old, new, 1),
            LOCKFILE: set_version(LOCKFILE.read_text(encoding="utf-8"), old, new, 2),
            CHANGELOG: close_changelog(
                CHANGELOG.read_text(encoding="utf-8"), old, new, date
            ),
        }
    except ValueError as err:
        raise SystemExit(str(err)) from None

    for path, text in updated.items():
        path.write_text(text, encoding="utf-8")
    print(new)


if __name__ == "__main__":
    main()
