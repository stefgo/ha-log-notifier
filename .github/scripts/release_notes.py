"""Assemble the body of a GitHub release from CHANGELOG.md.

Usage: release_notes.py <version> <output file>

The changelog only carries what changed; the installation part is the same for
every release and is appended here, so it cannot drift between entries.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

REPO = "stefgo/ha-log-notifier"
BLUEPRINT = (
    f"https://github.com/{REPO}/blob/main/blueprints/automation/lognotifier"
    "/push_notification.yaml"
)

FOOTER = f"""
## Installation

Home Assistant **2025.2** or newer.

**HACS → ⋮ → Custom repositories** → `{REPO}`, category **Integration** →
*Add*. Then install "Log Notifier" and restart Home Assistant.

The blueprint is not part of the HACS install — HACS handles one category per
repository. Import it once under **Settings → Automations & scenes → Blueprints
→ Import blueprint** with this URL:

```
{BLUEPRINT}
```

Full documentation is in the [README](https://github.com/{REPO}#readme).
"""


def section(changelog: str, version: str) -> str:
    """The body of the ``## <version>`` section, without its heading."""
    headings = list(re.finditer(r"^## (.+)$", changelog, re.MULTILINE))
    for index, heading in enumerate(headings):
        if heading.group(1).strip() != version:
            continue
        end = headings[index + 1].start() if index + 1 < len(headings) else len(changelog)
        body = changelog[heading.end() : end].strip()
        if not body:
            raise SystemExit(f"Section '## {version}' in CHANGELOG.md is empty")
        return body
    raise SystemExit(
        f"CHANGELOG.md has no section '## {version}' — add one before tagging"
    )


def main() -> None:
    version, out = sys.argv[1], sys.argv[2]
    changelog = Path("CHANGELOG.md").read_text(encoding="utf-8")
    previous = ""
    versions = [m.group(1).strip() for m in re.finditer(r"^## (.+)$", changelog, re.MULTILINE)]
    if version in versions:
        index = versions.index(version)
        if index + 1 < len(versions):
            previous = versions[index + 1]

    compare = (
        f"https://github.com/{REPO}/compare/v{previous}...v{version}"
        if previous
        else f"https://github.com/{REPO}/commits/v{version}"
    )
    body = f"{section(changelog, version)}\n{FOOTER}\n**Full Changelog**: {compare}\n"
    Path(out).write_text(body, encoding="utf-8")


if __name__ == "__main__":
    main()
