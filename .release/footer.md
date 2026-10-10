## Installation

Home Assistant **2025.2** or newer.

**HACS → ⋮ → Custom repositories** → `stefgo/ha-log-notifier`, category **Integration** →
*Add*. Then install "Log Notifier" and restart Home Assistant.

The blueprint is not part of the HACS install — HACS handles one category per
repository. Import it once under **Settings → Automations & scenes → Blueprints
→ Import blueprint** with this URL:

```
https://github.com/stefgo/ha-log-notifier/blob/main/blueprints/automation/lognotifier/push_notification.yaml
```

Full documentation is in the [README](https://github.com/stefgo/ha-log-notifier#readme).
