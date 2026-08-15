# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Python tests (no Home Assistant install required)
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest
.venv/bin/python -m pytest tests/test_store.py::test_purge_drops_old_messages

# Card: build, watch, test
npm --prefix card ci
npm --prefix card run build      # writes into custom_components/lognotifier/www/
npm --prefix card run watch
npm --prefix card test
npm --prefix card test -- -t "does not link dangerous schemes"   # -t matches a substring
```

There is no linter configured. `builddeploy.sh` (gitignored, local only) builds
the card and rsyncs integration + blueprint to a Home Assistant host.

## Naming

The repository is `ha-log-notifier`, the Home Assistant domain is `lognotifier`,
the card element is `log-notifier-card`. This mismatch is deliberate — changing
the domain would break existing config entries, entity IDs and ingest URLs.

`custom_components/lognotifier/manifest.json` is the single source of truth for
the version; `const.INTEGRATION_VERSION` reads it at import time. Do not add a
second version constant.

## Architecture

### Two build artifacts, one delivery path

The card is a separate TypeScript/lit project under `card/` whose rollup output
goes straight into `custom_components/lognotifier/www/` (gitignored). At setup
the integration registers that directory as a static path and calls
`add_extra_js_url` with a `?v=<version>` query string — so **no Lovelace
resource is ever configured by hand**, and a missing build only produces a
warning at startup. `tests/test_integrity.py` asserts that
`const.CARD_FILENAME` and the domain path still match `card/rollup.config.js`.

### Distribution and brand images

HACS installs the release asset, not the repository: `hacs.json` sets
`zip_release`, and `.github/workflows/release.yml` builds the card on a `v*`
tag and zips `custom_components/lognotifier` with `manifest.json` at the
archive root. The tag has to match the manifest version — the workflow refuses
otherwise. The blueprint stays outside that zip; HACS handles one category per
repository and this one is registered as an integration.

The release description comes from `CHANGELOG.md`:
`.github/scripts/release_notes.py` cuts out the `## <version>` section and
appends the installation part, which is why an entry carries only what changed.
A tag whose version has no section fails the build — write the entry **before**
tagging. A release must never go out with nothing but a commit list.

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

## Translations

`strings.json` is the source; `translations/en.json` and `translations/de.json`
must carry **identical key sets** — `test_integrity.py` fails otherwise. Service
names in `services.yaml`, the `SERVICE_*` constants in `services.py` and the
`services` block in `strings.json` are cross-checked by the same test.

Code, comments and docs are English. `translations/de.json` is the one
intentional exception (it is a UI translation, not project content). Card UI
strings are hard-coded English — the card has no i18n layer.
