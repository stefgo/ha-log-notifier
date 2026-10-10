# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project overview

`ha-log-notifier` is a Home Assistant integration (domain `lognotifier`) plus
its Lovelace card: a central collection point for messages from your own
services, as a replacement for Discord webhooks. Every channel has its own
ingest URL, every message a log level, and the card shows channels, messages and
unread badges on the dashboard.

## Commands

```bash
# Python tests (no Home Assistant install required)
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_store.py::test_purge_drops_old_messages

# The Home-Assistant-dependent tests, in their own environment
python3 -m venv .venv-ha && .venv-ha/bin/pip install -r requirements_test_ha.txt
.venv-ha/bin/python -m pytest -c pytest_ha.ini

# Card: build, watch, test
npm --prefix card ci
npm --prefix card run build      # writes into custom_components/lognotifier/www/
LOGNOTIFIER_MINIFY=1 npm --prefix card run build   # minified, as the release does
npm --prefix card run watch
npm --prefix card test
npm --prefix card test -- -t "does not link dangerous schemes"   # -t matches a substring
npm --prefix card run lint       # eslint
npm --prefix card run typecheck
```

`ruff` runs through `.pre-commit-config.yaml` (`pre-commit install` once); its
configuration is in `pyproject.toml`. `builddeploy.sh` builds the card and
rsyncs integration + blueprint to a Home Assistant host — it reads the target
from `.env`, see `.env.example`.

## Architecture

### Two build artifacts, one delivery path

The card is a separate TypeScript/lit project under `card/` whose rollup output
goes straight into `custom_components/lognotifier/www/` (gitignored). At setup
the integration registers that directory as a static path and calls
`add_extra_js_url` with a `?v=<version>` query string — so **no Lovelace
resource is ever configured by hand**, and a missing build only produces a
warning at startup. Terser only runs when `LOGNOTIFIER_MINIFY=1` is set — the
release workflow does, local builds and `watch` stay readable so what the
browser shows matches `card/src/`. `tests/test_integrity.py` asserts that
`const.CARD_FILENAME` and the domain path still match `card/rollup.config.js`.

### Distribution and brand images

HACS installs the release asset, not the repository: `hacs.json` sets
`zip_release`, and `.github/workflows/release.yml` builds the card and zips
`custom_components/lognotifier` with `manifest.json` at the archive root. The
blueprint stays outside that zip; HACS handles one category per repository and
this one is registered as an integration.

The release description opens with the text written by hand in
`.release/next.md`, followed by the list of commits; `.release/footer.md` is
the installation part, which is why the text carries only what changed. An
empty `.release/next.md` fails the release — write it **before** releasing. A
release must never go out with nothing but a commit list.

`custom_components/lognotifier/brand/` holds `icon.png` (256×256) and
`icon@2x.png` (512×512), which HA 2026.3 and newer serve from
`/api/brands/integration/lognotifier/`; `icon.svg` next to them is their source.
Do **not** open a pull request against `home-assistant/brands` — that repository
auto-closes custom integrations now. The icon in the HACS list stays a
placeholder regardless, because HACS' frontend still resolves it against the
old CDN (hacs/integration#5223).

### HA-free core

`store.py`, `models.py` and `ingest.py` contain no Home Assistant imports. That
is what makes the Python tests runnable without HA installed:
`tests/conftest.py` registers `custom_components/lognotifier` as a synthetic
package named `lognotifier_component` (without executing its `__init__.py`), so
relative imports resolve while `__init__.py` and its HA dependencies stay out.
Keep new pure logic in those three modules; anything touching `homeassistant.*`
belongs elsewhere and will not be unit-testable here.

### Single config entry, channels in options

There is exactly one config entry (`single_config_entry: true`). Channels are
*not* separate entries — they live in `entry.options[CONF_CHANNELS]` as
`{channel_id: {...}}` and each becomes a device plus its entities.

- `LogNotifierRuntime` (on `entry.runtime_data`) ties store, rate limiter and
  subscribers together. It is rebuilt on every reload.
- Frontend subscribers live on `hass.data[DATA_SUBSCRIBERS]`, **not** on the
  runtime — open cards must survive an entry reload.
- HTTP view, WebSocket commands, services and the card are registered once per
  HA instance, guarded by `DATA_SETUP_DONE`; re-registering on reload fails.
- `config_flow.py` deep-copies the options dict. A shallow copy would mutate the
  entry in place, HA would see no diff, and neither the update listener nor the
  reload would run — the change would silently vanish.
- `device.py` mirrors a device rename back into the channel options, then clears
  `name_by_user` so HA's own name stops shadowing the integration's.

### Entity IDs carry the domain prefix

Every entity gets its entity ID pre-set before it is added:
`sensor.lognotifier_<channel_id>_<key>` and
`sensor.lognotifier_totals_<key>`. Left to HA the ID would be built from the
device name (`sensor.kitchen_unread`), which says nothing about where it comes
from. `entity.py` builds the object ID, each platform's `async_setup_entry`
applies its own `ENTITY_ID_FORMAT` through `async_apply_default_entity_ids`.

This is a default for *new* entities only — the registry keeps the IDs of
entities it already knows, and a rename in the UI keeps winning. Displayed
names are unaffected: they still come from the translation keys and the device.
The totals entity ID deliberately drops the `entry_id` that its unique ID
carries; a random hex has no place in an ID people type into automations.

### Ingest is token-authenticated, not HA-authenticated

`LogNotifierIngestView` sets `requires_auth = False`. The token in the URL path
identifies and authorizes exactly one channel, Discord-webhook style; a leaked
token costs that channel only. Token matching uses `hmac.compare_digest`, and
tokens never appear in logs or diagnostics.

### MQTT is a second transport, and optional

A channel may carry an `mqtt_topic` (a topic filter, wildcards allowed);
`mqtt_ingest.py` subscribes it through Home Assistant's MQTT client and feeds
the payload into the same `ingest.parse_body` → `runtime.publish` path the HTTP
view uses, with the same size and rate limits. The manifest lists `mqtt` under
`after_dependencies`, never `dependencies`, and the module is imported only
when a channel has a topic *and* an MQTT entry exists — it pulls in the client
library, which is not installed without that integration. For the same reason
topic filters are validated by `models.normalize_topic_filter`, not by HA's
validator.

Subscriptions are made per entry setup (in a background task, so a slow broker
does not delay the entities) and dropped on unload — unlike the HTTP view they
are *not* behind `DATA_SETUP_DONE`. Retained messages are discarded: the broker
would redeliver them on every reload. There is no token; the broker's ACLs are
the authorization, and with no response channel a refused message is only
logged.

### Levels are a selection, not a threshold

This invariant runs through the whole project: config flow, store queries,
WebSocket `levels` parameter, card filter chips, blueprint inputs. `WARNING`
never implies `ERROR`; a channel may badge `TRACE` exclusively. Severity numbers
(`models.severity`) exist only to pick the *most prominent color* among already
counted messages, never to filter.

`normalize_level` additionally maps foreign spellings (`crit`, `warn`, `notice`)
and both numeric scales (syslog 0–7, Python logging 10–50) onto the four
canonical names.

### Read position is a watermark

`last_read_id` per channel only ever moves forward. Marking message N read
implies every older one is read; partial progress cannot be represented. The
card's `mark_read: visible` mode is all-or-nothing for exactly this reason and
suspends itself when a level filter is active or unread messages lie below the
loaded page.

### Card talks WebSocket, not entity states

Message bodies and paging cannot be expressed through entity states, so the card
uses `lognotifier/channels|messages|mark_read|clear|subscribe`. `subscribe`
pushes three event kinds: `message` (new message), `channel` (one channel's
counters changed), `channels` (channels were reconfigured — full list resent so
open cards pick up renames without a page reload).

### Markdown never becomes HTML

`card/src/markdown.ts` parses a Discord-flavored subset into a typed tree;
`card/src/render.ts` turns that tree into lit templates. There is no
`unsafeHTML` anywhere — foreign message text structurally cannot inject markup.
Link hrefs are allow-listed to `https?:`/`mailto:`. This is the project's main
security boundary; the card test suite covers it.

The card's `height` option goes into a CSS variable and is likewise validated
against an allow-list (`LENGTH` / `CALC` regexes in `log-notifier-card.ts`).

## Testing

Three suites, deliberately kept apart:

- **`tests/`** — the framework-free logic (levels, store, ingest parsing, rate
  limit, manifest/translation consistency). Runs on nothing but pytest, and
  **must stay that way**: it covers exactly the modules without a Home
  Assistant import, which are also the ones mypy checks.
- **`tests/ha/`** — everything that needs the real framework: entry setup and
  unload, the config and options flow, the ingest HTTP view, the MQTT ingest,
  the services, the WebSocket commands and diagnostics. Own environment (`.venv-ha`), own
  configuration (`pytest_ha.ini`), because pytest.ini next door is set up for
  the framework-free suite.
- **`card/test/`** — the card's pure modules (vitest). The elements have no
  DOM-based tests, so `npm --prefix card run typecheck` is what guards them.

`.github/workflows/test.yml` runs all three plus lint, type check and the card
build on every push and pull request, and again before a release.

## Releasing

A release is started by hand, never by pushing a tag: **Actions → Create Release → Run
workflow**, on `main` for a release or on `dev` for a beta (`x.y.z-beta.n`, a prerelease
HACS offers only with beta versions switched on). **Never bump a version or create a
`v*` tag by hand.**

- `dry_run` (on by default) shows the next version and the complete notes in the run
  summary and changes nothing.
- `bump` (`auto` | `patch` | `minor` | `major`): `auto` reads the commit types — `feat`
  raises the minor position, `fix`, `perf` and `revert` the patch position, every other
  type releases nothing — so commit messages follow Conventional Commits. Any other value
  is the step that is taken, whatever the commits say. `major` is the only way a major
  version is created; a `BREAKING CHANGE:` footer raises the minor position.
- **Every release is described by hand in `.release/next.md`** — what is new and what an
  upgrade needs, written for someone who uses the integration. The text goes above the
  generated list of commits, in the GitHub release and in `CHANGELOG.md`; a release
  without it is refused. Write it as part of the change, not at release time. A beta
  keeps the text, the release from `main` empties the file. `.release/footer.md` is the
  installation part appended to every release page.
- **`dev` is merged into `main` with its history — never squashed or rebased** — and
  `main` back into `dev` before the next beta. The workflow checks both.

`.github/workflows/release.yml` calls
[stefgo/release-workflows](https://github.com/stefgo/release-workflows), which carries
semantic-release and its configuration for every stefgo project. It runs `test.yml`, writes the
version to `manifest.json`, `card/package.json` and `card/package-lock.json`, builds the
minified card and zips `custom_components/lognotifier` (manifest at the archive root, as HACS
expects) *before* the release commit and the tag, and attaches the zip to the release.

### Branches and pull requests

There is a single maintainer and no pull-request flow. Small changes go
straight to `main`; larger work happens on a branch that **stays local** (the
`push-main-only` pre-push hook in `.pre-commit-config.yaml` enforces it), is
tested locally and merged with `git merge --no-ff`. Dependabot's pull requests
are merged by `.github/workflows/dependabot-auto-merge.yml` once their Tests
run is green; a red one stays open for a human.

`,
the card element is `log-notifier-card`. This mismatch is deliberate — changing
the domain would break existing config entries, entity IDs and ingest URLs.

`custom_components/lognotifier/manifest.json` is the single source of truth for
the version; `const.INTEGRATION_VERSION` reads it at import time. Do not add a
second version constant.

## Translations

`strings.json` is the source; `translations/en.json` and `translations/de.json`
must carry **identical key sets** — `test_integrity.py` fails otherwise. Service
names in `services.yaml`, the `SERVICE_*` constants in `services.py` and the
`services` block in `strings.json` are cross-checked by the same test.

Code, comments and docs are English. `translations/de.json` is the one
intentional exception (it is a UI translation, not project content).

The card gets nothing from Home Assistant's translations and carries its own:
`card/src/i18n.ts` holds one table per language (English as source and
fallback, German), picked by the language of the HA user profile. The tables
are typed against the English one, so a missing key fails the type check. Not
translated on purpose: the level names, the errors `setConfig` throws and the
entry in the card picker — the last two arise before the card knows a
language.
