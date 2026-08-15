# Changelog

The section of the version being tagged becomes the body of the GitHub release
— `.github/workflows/release.yml` reads it from here and refuses to publish a
tag that has no section. Installation instructions are appended by the workflow
and do not belong in an entry.

## 1.0.2

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

## 1.0.1

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

## 1.0.0

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
