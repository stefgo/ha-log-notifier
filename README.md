# Log Notifier for Home Assistant

A central collection point for messages from your own services — as a
replacement for Discord webhooks. Every channel has its own ingest URL, every
message a log level, and Home Assistant shows channels, messages and unread
badges right on the dashboard.

Existing Discord callers move over by swapping nothing but the webhook URL.

## Parts

| Part | Location | Purpose |
| --- | --- | --- |
| Integration | `custom_components/lognotifier` | HTTP ingest, storage, entities, services |
| Lovelace card | `card/` → `custom_components/lognotifier/www` | Channel list, badges, message view |
| Blueprint | `blueprints/automation/lognotifier` | Push notification for selected levels |

The card is served by the integration itself and registered with the frontend —
no Lovelace resource has to be maintained by hand.

## Installation

Home Assistant 2025.2 or newer is required.

### Via HACS

The repository is not in the HACS default catalogue, so it is added as a custom
repository once:

**HACS → ⋮ → Custom repositories** → `stefgo/ha-log-notifier`, category
**Integration** → *Add*. Then find "Log Notifier" in HACS, install it and
restart Home Assistant.

HACS installs the release asset, in which the card is already built — nothing
else has to be set up for it, and no Lovelace resource is configured by hand.

The blueprint does not come along: HACS handles exactly one category per
repository, and this one is registered as an integration. It is imported
separately, see [Push notifications](#push-notifications).

### Manually

The card is not committed in built form. The build places it directly into the
integration's `www` directory, from where the integration serves it:

```bash
git clone https://github.com/stefgo/ha-log-notifier
cd ha-log-notifier
npm --prefix card ci && npm --prefix card run build
```

Then copy the integration including its `www` directory and the blueprint onto
the Home Assistant instance — `<ha>` stands for its configuration directory:

```bash
rsync -a --exclude __pycache__ custom_components/lognotifier <ha>/custom_components/
rsync -a blueprints/automation/lognotifier <ha>/blueprints/automation/
```

The build step is not optional: without
`custom_components/lognotifier/www/log-notifier-card.js` the integration reports
at startup that the card is missing and does not register it.

### Setup

After the restart:
**Settings → Devices & services → Add integration → Log Notifier**.
There is only one instance; everything beyond that is channels.

Channels are then created under **Configure**. When editing a channel, the
dialog shows its ingest URL; the token can be regenerated there as well.

Every channel is exposed as a device. Renaming works from both sides: via
**Configure → Edit channel** or directly on the device — the device name then
becomes the channel name and applies to entities and card alike. The channel ID
(and with it entity IDs, ingest URL and `channel_id` in services and
automations) stays unchanged.

## Sending messages

```bash
# JSON with formatting
curl -X POST https://ha.example/api/lognotifier/ingest/$TOKEN \
  -H 'Content-Type: application/json' \
  -d '{
        "level": "ERROR",
        "title": "Backup failed",
        "content": "**proxmox-backup** reports:\n```\nexit code 2\n```",
        "source": "pbs-cron",
        "tags": ["backup", "pbs"]
      }'

# Plain text — level and source as query parameters
journalctl -u myservice -n 20 --no-pager |
  curl -X POST "https://ha.example/api/lognotifier/ingest/$TOKEN?level=WARNING&source=myservice" \
    --data-binary @-
```

Response: `202 {"id": 17, "channel": "backups", "level": "ERROR"}`.

| Field | Required | Meaning |
| --- | --- | --- |
| `content` | yes | Message body (`message`/`text` are accepted as well) |
| `level` | no | `ERROR`, `WARNING`, `INFO`, `TRACE` — default `INFO` |
| `title` | no | Headline, also preferred for the push message |
| `source` | no | Sending service |
| `tags` | no | List of keywords |
| `format` | no | `markdown` (default) or `plain` |
| `timestamp` | no | Unix time, in case the message is submitted after the fact |

Foreign level names are translated: `crit`, `fatal`, `err` → `ERROR`,
`warn` → `WARNING`, `notice` → `INFO`, `debug`/`verbose` → `TRACE`. Numeric
values work too, both on the syslog (0–7) and the Python logging scale (10–50).

Without `Content-Type: application/json` the body counts as plain text and
lands in the channel as `plain`. Level, source and title then come from the
query parameters `?level=`, `?source=` and `?title=`; with JSON, `level` and
`source` serve as defaults that the payload may override.

| Limit | Value | Behavior when exceeded |
| --- | --- | --- |
| Body | 16 KiB | `413`, the message is discarded |
| `content` | 8000 characters | truncated and marked with `…` |
| `title` / `source` | 200 / 100 characters | truncated |
| `tags` | 10 items of 40 characters | the surplus is dropped |
| Throughput | 60/min per channel, bursts up to 20 | `429`, the message is discarded |

Other error cases: `401` unknown or disabled token, `400` unusable payload or
unknown level, `503` integration not ready.

### Formatting

As in Discord: `**bold**`, `*italic*`, `__underline__`, `~~strikethrough~~`,
`` `code` ``, ```` ```code block``` ````, `> quote`, `||spoiler||`, lists,
`#` headings, `[text](url)` and bare URLs. The text is never interpreted as
HTML — the card builds its elements from the parsed tree itself.

`format: "plain"` switches interpretation off; text bodies without JSON
automatically land in the channel as `plain`.

## Entities per channel

| Entity | Purpose |
| --- | --- |
| `sensor.<channel>_unread` | The number for the badge, with a per-level breakdown as an attribute |
| `sensor.<channel>_highest_unread_level` | `ERROR`/`WARNING`/… — colors badges, works as a condition |
| `binary_sensor.<channel>_unread_messages` | Yes/no for automations |

Which levels count towards the badge is configured per channel in the options
("Levels counted by the badge") — a selection, not a threshold: `WARNING` does
not pull `ERROR` in with it, and a channel may count `TRACE` exclusively. The
defaults are `ERROR`, `WARNING` and `INFO`; `TRACE` stays out so tracing does
not nudge anyone.

Attributes of the unread sensor — useful for automations and templates:

| Attribute | Content |
| --- | --- |
| `channel_id`, `channel_name` | Channel identifier and display name |
| `badge_levels` | Levels that feed into the counter |
| `unread_by_level` | Unread per level, **all four**, independent of `badge_levels` |
| `highest_unread_level` | Highest unread level of the selection |
| `total_messages` | Messages in the channel's buffer |
| `last_level`, `last_title`, `last_source` | Key facts about the most recent message |

Disabled channels report `unavailable` — they do not accept anything either.

## Entities across all channels

Besides the channel devices, the integration creates a device "Log Notifier"
with the totals. They sum up what the channels badge themselves — a channel
that does not count `TRACE` therefore does not contribute its `TRACE` messages
here either. **Disabled channels stay out**; their stored messages count again
once re-enabled.

| Entity | Purpose |
| --- | --- |
| `sensor.log_notifier_unread_total` | Sum of all channel badges |
| `sensor.log_notifier_highest_unread_level_total` | Highest unread level overall |
| `binary_sensor.log_notifier_unread_messages_total` | Yes/no overall |

Attributes of the total counter:

| Attribute | Content |
| --- | --- |
| `unread_by_level` | Unread per level across all active channels |
| `unread_per_channel` | `{channel_id: number}`, only channels with a backlog, largest first |
| `unread_by_channel` | The same keyed by display name — for the eye and for cards |
| `channels_total`, `channels_with_unread` | Active channels, of those with a backlog |
| `total_messages` | Messages in all active buffers |
| `highest_unread_level` | Highest unread level overall |

This makes the backlog available in one place — as a badge in the sidebar (see
below) or as a single push automation instead of one per channel:

```yaml
trigger:
  - platform: numeric_state
    entity_id: sensor.log_notifier_unread_total
    above: 0
condition:
  - condition: state
    entity_id: sensor.log_notifier_highest_unread_level_total
    state: "ERROR"
action:
  - service: notify.mobile_app_phone
    data:
      message: >-
        {{ states('sensor.log_notifier_unread_total') }} unread messages
        in {{ state_attr('sensor.log_notifier_unread_total', 'channels_with_unread') }} channels
```

## Badge in the sidebar

Home Assistant has no badge for custom sidebar entries — the counter on the bell
is fed exclusively by `persistent_notification`. If you still want to see the
backlog in the sidebar without opening the dashboard, the HACS frontend module
[custom-sidebar](https://github.com/elchininet/custom-sidebar) gets you there:
it attaches a badge to arbitrary sidebar entries whose content comes from a
template — and that is exactly what `sensor.log_notifier_unread_total` is for.

The integration itself needs nothing for this; the module is installed through
HACS and registered as a Lovelace resource following its own instructions. In
the module's configuration file (`/config/www/sidebar-config.yaml`) a single
entry is then enough. `item` names the sidebar entry that holds the card — for a
dashboard that means its URL path or its displayed name:

```yaml
order:
  - item: lognotifier          # URL path or title of the dashboard
    notification: |
      [[[
        const unread = Number(states('sensor.log_notifier_unread_total'));
        return unread > 0 ? unread : '';
      ]]]
```

The empty string suppresses the badge while nothing is pending — otherwise a
permanent `0` would stick to the entry. `states(…)` is deliberately the function
form: it returns `undefined` while the entity is not available yet, whereas
`states['…'].state` would throw an error at that moment.

### Color by highest level

`notification_color` and `notification_text_color` can be set per entry and,
like `notification`, take a template. The badge then carries the same color as
in the card — both reach for the theme variables and therefore hold up in the
light and the dark theme alike:

```yaml
order:
  - item: lognotifier
    notification: |
      [[[
        const unread = Number(states('sensor.log_notifier_unread_total'));
        return unread > 0 ? unread : '';
      ]]]
    notification_color: |
      [[[
        switch (states('sensor.log_notifier_highest_unread_level_total')) {
          case 'ERROR':   return 'var(--error-color, #db4437)';
          case 'WARNING': return 'var(--warning-color, #ffa600)';
          case 'INFO':    return 'var(--info-color, #039be5)';
          default:        return 'var(--secondary-text-color, #727272)';
        }
      ]]]
    notification_text_color: 'var(--text-primary-color, #fff)'
```

The color values come from [`card/src/levels.ts`](card/src/levels.ts) — if you
change them there, follow up here. For the hover and selected states there are
additionally `notification_color_hover` and `notification_color_selected`
(likewise for the text); without a value `notification_color` simply applies.

If the total is empty, the level sensor's state stays `unknown` and falls into
the `default` branch — the color only becomes visible together with a badge
anyway.

### Counting real errors only

If the sidebar should ignore messages of lower levels, count the level
attribute instead of the total:

```yaml
order:
  - item: lognotifier
    notification: |
      [[[
        const errors = state_attr(
          'sensor.log_notifier_unread_total', 'unread_by_level'
        )?.ERROR ?? 0;
        return errors > 0 ? errors : '';
      ]]]
```

### Without an extra module

Without an extra module the way through `persistent_notification` remains: in
the automation that reacts to `lognotifier_message`, additionally create a
persistent notification and dismiss it again on acknowledgement. Then the
built-in bell counts along — at the cost of a second read position running
alongside the integration's own.

## Card

Via "Add card → Log Notifier" with a visual editor, or in YAML:

```yaml
type: custom:log-notifier-card
title: Messages      # omit = no header
channels: all        # or [backups, services]
levels: [ERROR, WARNING, INFO, TRACE]   # levels enabled initially
layout: auto         # auto | split | stacked
height: 70vh         # 500px, a number (= pixels) or calc(…)
page_size: 50
mark_read: manual    # manual | visible | open
```

| Parameter | Default | Meaning |
| --- | --- | --- |
| `type` | — | Required: `custom:log-notifier-card` |
| `title` | — | Heading of the card. Without it the header is omitted entirely: stacked, the card starts with the channel list, in two columns with both columns |
| `channels` | `all` | `all` or a list of channel IDs. The order of the list determines the display order; unknown IDs are skipped |
| `levels` | all | Levels enabled initially as a list, e.g. `[ERROR, WARNING]`. Every level stands on its own — there is no threshold and no inheritance. In the channel view each one can be toggled individually |
| `layout` | `auto` | `auto`, `split` or `stacked` — see below |
| `height` | `70vh` | Height of the message area: a CSS length (`vh`, `svh`, `dvh`, `lvh`, `vmin`, `vmax`, `px`, `rem`, `em`, `%`), a bare number for pixels, or a `calc(…)` expression. In two columns it is the height of the whole card, stacked the height of the scrolling message stream — there the card itself grows with title and channel list |
| `page_size` | `50` | Messages per load step (10–200). "Load older" fetches one more page each time |
| `mark_read` | `manual` | When messages count as read — `manual`, `visible` or `open`, see below |

An unknown level in `levels` or an invalid value for `layout`, `mark_read` or
`height` makes the card stop with an error message instead of silently showing
something else.

### `layout`

| Value | Behavior |
| --- | --- |
| `auto` | Two columns as soon as the card is at least 700 px wide, below that drill-down (tap a channel → messages → back) |
| `split` | Always two columns |
| `stacked` | Always drill-down, even on a large screen |

With `auto` it is the width of the card itself that counts, not that of the
window: in a narrow dashboard column it therefore stays single-column even on a
desktop.

In the two-column layout the title — if set — spans both columns, below which
they scroll separately. The open channel is highlighted on the left, toolbar and
level filters stay put while paging, and on opening, the first channel is
preselected.

The channel list shows only icon, name and badge there — preview text and
timestamp of the last message are dropped because the message stream sits right
next to it. Stacked, both are kept; there the list is the only overview.

### Full screen without scrolling

The HA header and the view margins come off the viewport. For a card that sits
alone in its view:

```yaml
layout: split
height: calc(100dvh - var(--header-height) - 24px)
```

`dvh` instead of `vh`, because on mobile devices the browser bar sliding in and
out would otherwise not be accounted for and the card would be cut off at the
bottom. The 24 px cover the view margins; with denser themes or several cards
below each other, subtract accordingly more.

Stacked, `height` applies to the message stream only — title and channel list
come on top of it, so subtract roughly another 120 px there.

### `mark_read`

| Value | Behavior |
| --- | --- |
| `manual` | Only the "Mark all read" button moves the read position |
| `visible` | The read position advances once every unread message was visible for at least 400 ms |
| `open` | The channel counts as read when opened, as does every arriving message while it stays open |

`visible` observes the message elements and acknowledges only once every unread
message really appeared on screen — scrolling past quickly does not count
because of the dwell time. It is deliberately all or nothing: the read position
is a watermark, and marking the newest message as read inevitably marks every
older one too. Partial progress could not be represented that way.

Two cases therefore suspend `visible`, because "everything seen" cannot be
proven there: when a level filter is active (unread messages could be hiding
behind it) and while unread messages remain below the loaded page — then use
"Load older" first.

### In the message stream

Above the messages there is one chip per level that can be toggled
individually: `WARNING` does not pull `ERROR` in with it, and whoever only wants
to see `TRACE` switches the other three off. Chips that are off are pale, active
ones carry the level color as a fill. If all are off, the list deliberately
stays empty.

Next to them "Mark all read" (moves the read position to the newest message)
and — for administrators only — "Clear", which empties the channel for good.
Spoilers only reveal their content on click.

### Examples

```yaml
# Only the critical channels, compact in a side column
type: custom:log-notifier-card
title: Failures
channels: [alarm, backups]
levels: [ERROR, WARNING]
layout: stacked
```

```yaml
# Full-width view as its own dashboard, read on actual sight
type: custom:log-notifier-card
layout: split
height: 85vh
page_size: 100
mark_read: visible
```

## Push notifications

The blueprint listens for the `lognotifier_message` event. After a HACS install
it has to be imported once — **Settings → Automations & scenes → Blueprints →
Import blueprint** takes this URL:

```
https://github.com/stefgo/ha-log-notifier/blob/main/blueprints/automation/lognotifier/push_notification.yaml
```

A manual install already carries it along. Either way it then sits under:

**Settings → Automations → Blueprint → Log Notifier — Push notification**

Configurable are channels, levels, notify services, quiet hours and the target
when tapped. As everywhere in this project the levels are a selection and not a
threshold: `WARNING` does not pull `ERROR` in with it, both are enabled by
default. The exception from quiet hours is a selection of its own too (default
`ERROR`) — left empty, quiet hours apply without exception.

Push messages carry `tag: lognotifier_<channel>`, so they replace each other per
channel instead of stacking up. If you want to build your own automations, use
the event directly:

```yaml
triggers:
  - trigger: event
    event_type: lognotifier_message
conditions:
  - "{{ trigger.event.data.level == 'ERROR' }}"
```

Event data: `channel_id`, `channel_name`, `message_id`, `level`, `content`,
`title`, `source`, `tags`, `ts`.

## Services

| Service | Fields | Purpose |
| --- | --- | --- |
| `lognotifier.send` | `channel_id`, `content`, `level`, `title`, `source`, `tags`, `format` | File a message from an HA automation — the same path as the ingest, only without HTTP |
| `lognotifier.mark_read` | `channel_id` (optional), `up_to_id` (optional) | Set the read position; without a channel the call applies to all |
| `lognotifier.clear` | `channel_id` | Empty a channel |

An unknown channel results in an error on the call, not in silently doing
nothing.

## The card's interface

The card does not read entity states but talks to the integration over
WebSocket commands — only that way can message bodies and paging be
represented. If you want to build your own frontend, you will find the same data
there:

| Command | Purpose |
| --- | --- |
| `lognotifier/channels` | Channels with counters and last message |
| `lognotifier/messages` | Load a page: `channel_id`, `before`, `limit` (max. 200), `levels` |
| `lognotifier/mark_read` | `channel_id`, optionally `up_to_id` |
| `lognotifier/clear` | Empty a channel (administrators only) |
| `lognotifier/subscribe` | Stream of new messages and changed channel states |

## Storage

Messages live in memory as a ring buffer and are written to
`.storage/lognotifier.messages` with a delay. Per channel there is a maximum
count (default 500, max. 5000) and a maximum age (default 30 days, `0` =
unlimited); anything older is cleaned up on write and every six hours. When a
channel is deleted, its messages go with it.

The read position is a watermark per channel (`last_read_id`) and never moves
backwards — two clients acknowledging in different orders cannot inflate the
badge again.

The config entry's diagnostics (Settings → Devices & services → Log Notifier →
Download) contain channel states, counters and the state of the throttle — the
ingest tokens deliberately not.

## Tests

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements_test.txt
.venv/bin/python -m pytest       # store, levels, ingest, consistency
npm --prefix card test           # markdown parser
```

The Python tests get by without a running Home Assistant: `store.py`,
`models.py` and `ingest.py` are free of HA imports and are loaded flat (see
`tests/conftest.py`). Covered are the ring buffer, the read position, purging,
level translation, payload parsing and the throttle — plus the consistency of
manifest, translations and services.

The card tests cover the markdown parser, that is, the place where foreign text
meets our own interpretation.
