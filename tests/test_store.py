"""Ring buffer, read position and cleanup."""

from __future__ import annotations

import asyncio
import importlib

from conftest import PACKAGE

const = importlib.import_module(f"{PACKAGE}.const")
models = importlib.import_module(f"{PACKAGE}.models")
store_mod = importlib.import_module(f"{PACKAGE}.store")


class FakeStore:
    """Storage stand-in: only remembers the last write request."""

    def __init__(self, initial=None):
        self.initial = initial
        self.saved = None

    async def async_load(self):
        return self.initial

    def async_delay_save(self, data_func, delay=0):
        self.saved = data_func()


def make_channel(**kwargs):
    defaults = dict(
        id="backups",
        name="Backups",
        token="tok",
        badge_levels=list(const.DEFAULT_BADGE_LEVELS),
        max_messages=100,
        max_age_days=30,
    )
    defaults.update(kwargs)
    return models.Channel(**defaults)


def make_store(channels=None):
    fake = FakeStore()
    store = store_mod.MessageStore(fake)
    store.set_channels(channels or [make_channel()])
    return store, fake


def add(store, level, channel_id="backups", ts=None, content="x"):
    return store.add(
        channel_id,
        level=level,
        content=content,
        fmt=const.FORMAT_MARKDOWN,
        ts=ts,
    )


def test_ids_count_up_across_channels():
    store, _ = make_store(
        [make_channel(), make_channel(id="services", name="Services")]
    )
    first = add(store, "INFO")
    second = add(store, "INFO", channel_id="services")
    assert second.id > first.id


def test_ring_buffer_drops_the_oldest():
    store, _ = make_store([make_channel(max_messages=3)])
    for index in range(5):
        add(store, "INFO", content=str(index))
    contents = [m.content for m in store.messages("backups", limit=10)]
    assert contents == ["4", "3", "2"]


def test_smaller_limit_truncates_the_existing_buffer():
    channel = make_channel(max_messages=10)
    store, _ = make_store([channel])
    for index in range(10):
        add(store, "INFO", content=str(index))
    store.set_channels([make_channel(max_messages=3)])
    assert len(store.messages("backups", limit=100)) == 3


def test_badge_only_counts_the_selected_levels():
    # A selection, not a threshold: WARNING does not pull ERROR in with it.
    store, _ = make_store([make_channel(badge_levels=["WARNING", "ERROR"])])
    add(store, "TRACE")
    add(store, "INFO")
    warning = add(store, "WARNING")
    error = add(store, "ERROR")
    channel = store.channel("backups")
    assert store.unread_count(channel) == 2
    assert store.highest_unread_level(channel) == "ERROR"
    # The breakdown deliberately ignores the badge selection.
    assert store.unread_by_level(channel) == {
        "TRACE": 1,
        "INFO": 1,
        "WARNING": 1,
        "ERROR": 1,
    }
    assert [m.id for m in store.unread(channel)] == [warning.id, error.id]


def test_unknown_badge_levels_are_dropped():
    channel = models.Channel.from_dict(
        "backups", {"token": "t", "badge_levels": ["ERROR", "PURPLE"]}
    )
    assert channel.badge_levels == ["ERROR"]
    # Without a value, the default applies.
    assert models.Channel.from_dict("backups", {"token": "t"}).badge_levels == list(
        const.DEFAULT_BADGE_LEVELS
    )


def test_badge_can_count_a_single_level():
    store, _ = make_store([make_channel(badge_levels=["TRACE"])])
    add(store, "ERROR")
    add(store, "TRACE")
    channel = store.channel("backups")
    assert store.unread_count(channel) == 1
    assert store.highest_unread_level(channel) == "TRACE"


def test_mark_read_resets_the_counter():
    store, _ = make_store()
    add(store, "ERROR")
    last = add(store, "ERROR")
    channel = store.channel("backups")
    store.mark_read("backups")
    assert store.unread_count(channel) == 0
    assert store.last_read_id("backups") == last.id


def test_mark_read_up_to_id_leaves_newer_unread():
    store, _ = make_store()
    first = add(store, "ERROR")
    add(store, "ERROR")
    store.mark_read("backups", first.id)
    assert store.unread_count(store.channel("backups")) == 1


def test_read_position_never_moves_backwards():
    store, _ = make_store()
    first = add(store, "ERROR")
    add(store, "ERROR")
    store.mark_read("backups")
    assert store.mark_read("backups", first.id) is False
    assert store.unread_count(store.channel("backups")) == 0


def test_clear_empties_and_acknowledges():
    store, _ = make_store()
    add(store, "ERROR")
    store.clear("backups")
    assert store.messages("backups") == []
    assert store.unread_count(store.channel("backups")) == 0


def test_purge_drops_old_messages():
    store, _ = make_store([make_channel(max_age_days=1)])
    now = 1_000_000.0
    add(store, "INFO", ts=now - 2 * 86400)
    recent = add(store, "INFO", ts=now - 60)
    assert store.purge_aged(now) == 1
    assert [m.id for m in store.messages("backups")] == [recent.id]


def test_purge_without_age_limit_does_nothing():
    store, _ = make_store([make_channel(max_age_days=0)])
    add(store, "INFO", ts=0.0)
    assert store.purge_aged(1_000_000.0) == 0


def test_messages_filters_and_paginates():
    store, _ = make_store()
    ids = [add(store, "INFO").id for _ in range(5)]
    add(store, "ERROR")
    first_page = store.messages("backups", limit=2)
    assert [m.id for m in first_page] == [ids[-1] + 1, ids[-1]]
    second_page = store.messages("backups", before=first_page[-1].id, limit=2)
    assert [m.id for m in second_page] == [ids[-2], ids[-3]]


def test_level_filter_is_a_selection_not_a_threshold():
    store, _ = make_store()
    add(store, "TRACE")
    add(store, "INFO")
    add(store, "WARNING")
    add(store, "ERROR")
    # Only the named levels come back — WARNING does not pull ERROR in with it.
    selected = store.messages("backups", levels=["WARNING", "TRACE"], limit=10)
    assert sorted(m.level for m in selected) == ["TRACE", "WARNING"]
    # Without a value everything, with an empty selection nothing.
    assert len(store.messages("backups", limit=10)) == 4
    assert store.messages("backups", levels=[], limit=10) == []


def test_deleted_channel_loses_its_buffer():
    store, fake = make_store()
    add(store, "INFO")
    store.set_channels([])
    assert fake.saved["channels"] == {}


def test_state_survives_a_restart():
    fake = FakeStore()
    store = store_mod.MessageStore(fake)
    store.set_channels([make_channel()])
    add(store, "ERROR", content="Failure")
    store.mark_read("backups")
    add(store, "WARNING")
    saved = fake.saved

    restored = store_mod.MessageStore(FakeStore(saved))
    asyncio.run(restored.async_load())
    restored.set_channels([make_channel()])
    channel = restored.channel("backups")
    assert restored.unread_count(channel) == 1
    assert len(restored.messages("backups", limit=10)) == 2


def test_broken_row_does_not_cost_the_channel():
    data = {
        "next_id": 5,
        "channels": {
            "backups": {
                "last_read_id": 0,
                "messages": [
                    {"broken": True},
                    {"id": 4, "ts": 1.0, "level": "INFO", "content": "ok"},
                ],
            }
        },
    }
    store = store_mod.MessageStore(FakeStore(data))
    asyncio.run(store.async_load())
    store.set_channels([make_channel()])
    assert [m.content for m in store.messages("backups")] == ["ok"]


def test_summary_provides_the_frontend_fields():
    store, _ = make_store()
    add(store, "ERROR", content="**broken**")
    summary = store.summary(store.channel("backups"))
    assert summary["unread"] == 1
    assert summary["highest_unread_level"] == "ERROR"
    assert summary["last_message"]["content"] == "**broken**"
    assert summary["total"] == 1


def make_multi_store():
    """Three channels: two active ones with different badge levels, one off."""
    return make_store(
        [
            make_channel(badge_levels=["ERROR", "WARNING"]),
            make_channel(
                id="services", name="Services", badge_levels=["WARNING", "INFO"]
            ),
            make_channel(id="legacy", name="Legacy", enabled=False),
        ]
    )[0]


def test_totals_sum_up_the_channel_badges():
    store = make_multi_store()
    add(store, "ERROR")
    add(store, "INFO")  # does not count in "backups" — INFO is no badge there
    add(store, "WARNING", channel_id="services")
    add(store, "INFO", channel_id="services")
    assert store.unread_count_total() == 3
    assert store.highest_unread_level_total() == "ERROR"
    # The breakdown ignores the badge selection, just like on channel level.
    assert store.unread_by_level_total() == {"ERROR": 1, "INFO": 2, "WARNING": 1}
    assert store.unread_per_channel() == {"services": 2, "backups": 1}


def test_disabled_channel_does_not_count():
    store = make_multi_store()
    add(store, "ERROR", channel_id="legacy")
    assert store.unread_count_total() == 0
    assert store.highest_unread_level_total() is None
    assert store.unread_per_channel() == {}
    # The stored messages remain and count again once re-enabled.
    store.set_channels([make_channel(id="legacy", name="Legacy")])
    assert store.unread_count_total() == 1


def test_totals_without_anything_unread():
    store = make_multi_store()
    add(store, "ERROR")
    store.mark_read("backups")
    assert store.unread_count_total() == 0
    assert store.highest_unread_level_total() is None


def test_totals_provide_the_entity_fields():
    store = make_multi_store()
    add(store, "ERROR")
    add(store, "WARNING", channel_id="services")
    add(store, "ERROR", channel_id="legacy")
    totals = store.totals()
    assert totals["unread"] == 2
    assert totals["highest_unread_level"] == "ERROR"
    assert totals["channels_total"] == 2  # the disabled channel is missing
    assert totals["channels_with_unread"] == 2
    assert totals["total_messages"] == 2


BLOCKS = [
    {
        "type": "fields",
        "rows": [
            [
                {"label": "Job", "value": "vm-101", "span": 2},
                {"label": "Exit", "value": "2"},
            ]
        ],
    },
    {"type": "text", "text": "Datastore full"},
    {
        "type": "table",
        "columns": [{"label": "Host"}, {"label": "Duration", "align": "right"}],
        "rows": [["nas", "12 s"]],
    },
]


def test_blocks_survive_a_restart():
    fake = FakeStore()
    store = store_mod.MessageStore(fake)
    store.set_channels([make_channel()])
    store.add(
        "backups", level="ERROR", content="", fmt=const.FORMAT_MARKDOWN, blocks=BLOCKS
    )

    restored = store_mod.MessageStore(FakeStore(fake.saved))
    asyncio.run(restored.async_load())
    restored.set_channels([make_channel()])
    message = restored.messages("backups", limit=1)[0]
    assert message.blocks == BLOCKS
    assert message.to_dict()["blocks"] == BLOCKS


def test_messages_without_blocks_stay_compact():
    store, _ = make_store()
    message = add(store, "INFO")
    assert message.blocks == []
    assert "blocks" not in message.to_dict()
    # Rows stored before blocks existed simply have none.
    assert models.Message.from_dict({"id": 1, "ts": 0, "content": "x"}).blocks == []


def test_unknown_stored_block_types_are_skipped():
    # Written by a newer version, read by this one: keep what is understood.
    data = {
        "id": 1,
        "ts": 0,
        "content": "x",
        "blocks": [{"type": "divider"}, "junk", *BLOCKS],
    }
    assert models.Message.from_dict(data).blocks == BLOCKS


def test_store_enforces_the_block_limits():
    store, _ = make_store()
    row = [{"label": "a", "value": "b"}] * 9
    message = store.add(
        "backups",
        level="INFO",
        content="c" * const.MAX_CONTENT_CHARS,
        fmt=const.FORMAT_MARKDOWN,
        blocks=[
            {"type": "text", "text": "over budget"},
            {"type": "fields", "rows": [row] * 3},
        ],
    )
    assert [block["type"] for block in message.blocks] == ["fields"]
    assert [len(r) for r in message.blocks[0]["rows"]] == [const.MAX_FIELDS_PER_ROW] * 3


def test_stored_tables_are_repaired_leniently():
    data = {
        "id": 1,
        "ts": 0,
        "content": "x",
        "blocks": [
            {
                "type": "table",
                "columns": [{"label": "a", "align": "justify"}, "junk", {"label": "b"}],
                "rows": [["1", {"x": 1}, "surplus"], "junk", [None], ["2"]],
            },
            {"type": "table", "columns": [{"label": "empty"}], "rows": []},
        ],
    }
    # A broken align and non-dict columns are dropped, rows fitted to the
    # head, nested cells blanked; a table without rows disappears.
    assert models.Message.from_dict(data).blocks == [
        {
            "type": "table",
            "columns": [{"label": "a"}, {"label": "b"}],
            "rows": [["1", ""], ["2", ""]],
        }
    ]


def test_stored_value_formats_are_repaired_leniently():
    data = {
        "id": 1,
        "ts": 0,
        "content": "x",
        "blocks": [
            {
                "type": "fields",
                "rows": [
                    [
                        {"label": "a", "value": "1", "format": "bytes"},
                        {"label": "b", "value": "2", "format": "from-the-future"},
                    ]
                ],
            },
            {
                "type": "table",
                "columns": [
                    {"label": "c", "format": "duration"},
                    {"label": "d", "format": 3},
                ],
                "rows": [["1", "2"]],
            },
        ],
    }
    # A format this version does not know is dropped, not refused: the value
    # is still shown, just unformatted.
    assert models.Message.from_dict(data).blocks == [
        {
            "type": "fields",
            "rows": [
                [
                    {"label": "a", "value": "1", "format": "bytes"},
                    {"label": "b", "value": "2"},
                ]
            ],
        },
        {
            "type": "table",
            "columns": [{"label": "c", "format": "duration"}, {"label": "d"}],
            "rows": [["1", "2"]],
        },
    ]


def test_stored_field_spans_are_repaired_leniently():
    field = {"label": "a", "value": "b"}
    data = {
        "id": 1,
        "ts": 0,
        "content": "x",
        "blocks": [
            {
                "type": "fields",
                "rows": [
                    [
                        {**field, "span": "3"},
                        {**field, "span": True},
                        {**field, "span": 9},
                    ]
                ],
            }
        ],
    }
    # Storage is never refused: a broken span counts as one, a wide one is fitted.
    assert models.Message.from_dict(data).blocks == [
        {
            "type": "fields",
            "rows": [[field, field, {**field, "span": const.MAX_GRID_COLUMNS - 2}]],
        }
    ]
