# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the
project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

Entries are written under `[Unreleased]`. The release workflow turns that
section into the version's section and uses it as the body of the GitHub
release; it refuses to release when the section is empty. Installation
instructions are appended by the workflow and do not belong in an entry.

## [Unreleased]

### Added

- **Compact and detailed messages in the card** — a message can be shown as
  its head line alone. When a channel is opened, the messages already read are
  compact and the unread ones in detail. "Show detail" / "Show compact" in the
  toolbar switches all read ones, a click on a head line a single one; an
  unread message always stays in detail. A compact message without a title
  shows the first line of its text.
- **"Show URLs" in the integration's menu** — **Configure → Show URLs** lists
  the ingest URL of every channel, so it no longer takes opening each channel
  for editing. The URLs are now shown complete, with the address Home
  Assistant is reached under, instead of the path alone.
- **The card speaks German** — the card and its visual editor now show their
  texts in the language of the Home Assistant user profile. English and German
  are included; every other language gets English as before.

### Changed

- **Unread marker in the card** — a red "New" line now marks the read position
  in a channel's message stream: everything above it is unread. The line stays
  where it is while the channel is open, also after the messages were marked
  read, and is gone the next time the channel is opened. It replaces the thin
  frame around unread messages, which was barely visible in most
  themes.
- **New messages slide in** — a message that arrives while its channel is open
  now slides in from the top and pushes the older ones down instead of
  appearing abruptly. Respects the system's "reduce motion" setting.

## [1.2.0] — 2026-10-06

### Added

- **Value formats** — `"format"` on a grid field, or on a table column for all
  of its cells, has the card write a raw value in the viewer's language:
  `bytes` (binary units, `1.23 GiB`), `bytes_si` (SI units, `1.32 GB`),
  `duration` (seconds, `14m 7s`), `datetime` (Unix seconds or ISO 8601) and
  `number` (grouped digits). The value is stored and sent on in the event as
  it came; one that does not fit its format is shown unchanged. An unknown
  format is refused with `400`.

## [1.1.0] — 2026-09-30

### Added

- **Table blocks** — `{"type": "table", "columns": […], "rows": [[…], …]}`
  shows rows of equal width under one shared head, next to the existing text
  blocks and label/value grids. Columns are labels or
  `{"label", "align"}` objects (`left`, `center`, `right`). Rows are lists of
  cells or objects keyed by column; `{"table": [{…}, …]}` turns a plain list
  of objects into a table whose head comes from the keys. Cells take text,
  numbers, booleans or null and inline markdown; tables span the full width
  of the card, and wider ones scroll sideways. Limits: 10 columns and 50 rows
  per table, 250 cells across all tables, 200 characters per cell.
- **Wider grid fields** — a field with `"span": n` takes `n` columns of its
  row. A row has as many columns as its spans add up to, so rows with the same
  sum line up. At most 6 columns per row; a span that does not fit is
  shortened. Grids without `span` look as before.

### Changed

- The push blueprint falls back to the first table cell, under its column
  label, when a message has neither title, content, text block nor field.

## [1.0.7] — 2026-09-29

### Added

- **`blocks`** — text blocks and label/value grids below the message body, in
  any order. A grid is modeled on the fields of a Discord embed: its `rows` are
  a list of rows, each a list of `{"label", "value"}` objects; every row sets
  its own number of columns, and the card lays all rows of a grid out as one
  block of equal width. Shorthands: a bare string is a text block, an object
  with `rows` is a grid. Accepted by the ingest endpoint and by
  `lognotifier.send`, carried in the `lognotifier_message` event. Limits: 20
  blocks, text shares the 8000 characters of `content`, 25 fields in total.

### Changed

- `content` is optional when `blocks` are given. The push blueprint falls back
  to the first text block, then the first field, when a message has neither
  title nor content.

## [1.0.6] — 2026-09-28

A small feature release. Storage, entities, services and the card behave exactly
as in 1.0.5; the ingest endpoint accepts one more timestamp format.

### Added

- **`timestamp` accepts ISO 8601** at the JSON ingest endpoint, next to Unix
  time: `2026-09-28T14:03:00+02:00`, `2026-09-28T12:03:00Z` or a date without
  offset, which is read as UTC. Numeric strings still count as Unix seconds.

### Changed

- The card's build and test tooling was updated (vitest 5, rollup, eslint,
  typescript-eslint). The shipped bundle is unaffected.

## [1.0.5] — 2026-08-29

A maintenance release. Ingest, storage, entities, services and the card behave
exactly as in 1.0.4 — with one visible exception, the version the card reports.

### Fixed

- **The card reported version 1.0.0**, four releases after 1.0.0: `CARD_VERSION`
  was a constant in the source that nobody remembered to bump. The version now
  comes from `manifest.json` at build time, so it cannot go stale again. The
  console line of a deployed card is therefore trustworthy from here on.

### Added

- **A Home Assistant test suite** (`tests/ha`, 40 tests): entry setup and
  unload, the config and options flow, the ingest HTTP view — including unknown
  tokens, disabled channels, oversized bodies and the rate limit —, the three
  services, the five WebSocket commands and the diagnostics, which are checked
  to contain no channel token anywhere. The framework-free suite in `tests/`
  stays exactly as it was: runnable with nothing but pytest.
- ruff and mypy in CI, ESLint for the card, and pre-commit hooks. mypy covers
  the four Home-Assistant-free modules under the same strict settings
  ha-crowdsec-integration uses.
- A local build counter: `builddeploy.sh` builds with
  `LOGNOTIFIER_BUILD_COUNTER=1`, so the deployed card reports
  `<version>+build.<n>` and a cached bundle is recognisable by its number.
- dependabot for actions and npm, plus the weekly probe that watches whether the
  TypeScript 7 hold can come off.

### Changed

- `builddeploy.sh` is part of the repository now. It used to carry the target
  host in the script itself and was therefore git-ignored; it reads `.env` with
  the shared `HA_HOST` / `HA_SSH_PORT` / `HA_CONFIG` / `HA_TARGET` names instead
  (see `.env.example`).
- The Python code was brought under the shared ruff configuration — formatting
  only, no behaviour change.
- The release refuses a tag whose `card/package.json` disagrees with it; until
  now only `manifest.json` was checked, which is how the card version drifted.
- CHANGELOG headings follow Keep a Changelog (`## [x.y.z] — date`) with compare
  links, and the release notes come from the script shared by all four projects.

## [1.0.4] — 2026-08-23

A packaging release. The integration itself is unchanged — same ingest, storage,
entities, services and card behaviour as 1.0.3.

- **The card ships minified.** The bundle in the release asset is run through
  terser now, which takes it from roughly 65 kB down to 43 kB — that is what
  every dashboard loads on the first visit after an update. Its source map
  travels with it, so the card stays debuggable in the browser. Builds from a
  checkout stay unminified; only the release workflow minifies.

## [1.0.3] — 2026-08-15

A bug fix release. Nothing about ingest, storage, services or the card changes.

- **Deleting a channel now deletes its device.** Removing a channel in the
  options took it out of the configuration and threw its messages away, but the
  device Home Assistant had built from it stayed behind in the registry — with
  its entities on it, unavailable and impossible to get rid of by hand. The
  integration now removes the devices of channels that no longer exist; the
  reload following the deletion cleans up right away, and leftovers from
  earlier deletions disappear on the next start.

## [1.0.2] — 2026-08-15

New entities now carry the integration in their entity ID. Nothing changes for
an existing installation — no entity is renamed, no automation breaks.

- **Entity IDs are prefixed with `lognotifier`.** A channel called "Kitchen"
  used to produce `sensor.kitchen_unread`, because Home Assistant builds the
  entity ID from the device name and nothing in it pointed back here. The
  integration now proposes the ID itself: `sensor.lognotifier_kitchen_unread`,
  `binary_sensor.lognotifier_kitchen_has_unread`, and
  `sensor.lognotifier_totals_unread` for the totals across all channels.

  This is a suggestion made at registration time. **Entities that already
  exist keep their entity ID** — Home Assistant's registry remembers it, and
  renaming in the UI keeps precedence. Only channels you add from now on get
  the new scheme; to move an older one over, rename it under
  *Settings → Devices & services → Entities*. Displayed names are untouched.

## [1.0.1] — 2026-08-15

A maintenance release. Nothing about ingest, storage, entities, services or the
card changes — upgrading is optional unless the missing icon bothers you.

- **The integration brings its own icon.** Home Assistant 2026.3 lets custom
  integrations ship brand images, so `brand/icon.png` and `brand/icon@2x.png`
  now travel inside the integration and Home Assistant serves them from
  `/api/brands/integration/lognotifier/`, ahead of the brands CDN. On older
  Home Assistant versions the folder simply sits unused.
- **The badge level selector carries its labels inline.** The `selector` block
  in `strings.json` mapped every level onto itself (`"ERROR": "ERROR"`) and
  tripped hassfest, which requires lower-case translation keys — the level
  names deliberately are not. Nothing changes visually.

Known limitation: the icon in the **HACS list** stays a grey placeholder for
now. HACS' frontend still resolves integration icons against the old CDN path
instead of the local proxy — see
[hacs/integration#5223](https://github.com/hacs/integration/issues/5223).
Inside Home Assistant itself the icon shows up.

## [1.0.0] — 2026-08-15

First release. A central collection point in Home Assistant for messages from
your own services — as a replacement for Discord webhooks. Every channel has its
own ingest URL, every message a log level, and Home Assistant shows channels,
messages and unread badges right on the dashboard.

Existing Discord callers move over by swapping nothing but the webhook URL.

- **Token-authenticated ingest** — `POST /api/lognotifier/ingest/<token>`, JSON
  or plain text. One token per channel, Discord-webhook style; a leaked token
  costs that channel only.
- **Lovelace card** with a visual editor, channel list, unread badges, paging
  and per-level filter chips. It ships built inside the integration and is
  registered with the frontend automatically — no Lovelace resource to maintain
  by hand.
- **Entities per channel and across all channels** — unread count with a
  per-level breakdown, highest unread level, and a binary sensor for
  automations.
- **Services** `lognotifier.send`, `mark_read` and `clear`, plus the
  `lognotifier_message` event for your own automations.
- **Blueprint** for push notifications with channel and level selection, quiet
  hours and a tap target.

Four levels — `ERROR`, `WARNING`, `INFO`, `TRACE` — and everywhere they are a
selection, never a threshold: `WARNING` does not pull `ERROR` in with it, and a
channel may badge `TRACE` exclusively. Foreign spellings (`crit`, `warn`,
`notice`) and both numeric scales (syslog 0–7, Python logging 10–50) are mapped
onto the four canonical names.

Message text is never turned into HTML. The card parses a Discord-flavored
markdown subset into a typed tree and builds its elements from it, so foreign
text structurally cannot inject markup.

[1.2.0]: https://github.com/stefgo/ha-log-notifier/compare/v1.1.0...v1.2.0
[1.1.0]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.7...v1.1.0
[1.0.7]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.6...v1.0.7
[1.0.6]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.5...v1.0.6
[1.0.5]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.4...v1.0.5
[1.0.4]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.3...v1.0.4
[1.0.3]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.2...v1.0.3
[1.0.2]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.1...v1.0.2
[1.0.1]: https://github.com/stefgo/ha-log-notifier/compare/v1.0.0...v1.0.1
[1.0.0]: https://github.com/stefgo/ha-log-notifier/releases/tag/v1.0.0
