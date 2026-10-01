"""Payload parsing and throttling of the ingest endpoint."""

from __future__ import annotations

import importlib

import pytest
from conftest import PACKAGE

const = importlib.import_module(f"{PACKAGE}.const")
ingest = importlib.import_module(f"{PACKAGE}.ingest")


def test_minimal_payload():
    parsed = ingest.parse_payload({"content": "Hello"})
    assert parsed.level == "INFO"
    assert parsed.content == "Hello"
    assert parsed.format == const.FORMAT_MARKDOWN


def test_alternative_field_names():
    # Existing Discord callers send "content", others "message"/"text".
    assert ingest.parse_payload({"message": "a"}).content == "a"
    assert ingest.parse_payload({"text": "b"}).content == "b"


def test_missing_content_is_rejected():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"level": "ERROR"})
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"content": "   "})


def test_unknown_level_is_rejected():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"content": "a", "level": "purple"})


def test_query_parameters_as_defaults():
    parsed = ingest.parse_payload(
        {"content": "a"}, default_level="ERROR", default_source="cron"
    )
    assert parsed.level == "ERROR"
    assert parsed.source == "cron"
    # The payload wins over the query parameter.
    parsed = ingest.parse_payload(
        {"content": "a", "level": "TRACE"}, default_level="ERROR"
    )
    assert parsed.level == "TRACE"


def test_overlong_content_is_truncated():
    parsed = ingest.parse_payload({"content": "x" * (const.MAX_CONTENT_CHARS + 500)})
    assert len(parsed.content) == const.MAX_CONTENT_CHARS + 2


def test_tags_and_format():
    parsed = ingest.parse_payload(
        {"content": "a", "tags": ["backup", "pbs"], "format": "plain"}
    )
    assert parsed.tags == ["backup", "pbs"]
    assert parsed.format == "plain"
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"content": "a", "format": "html"})


def test_non_object_is_rejected():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload(["not", "an", "object"])


def test_timestamp_accepts_unix_time():
    assert (
        ingest.parse_payload({"content": "a", "timestamp": 1700000000}).ts == 1700000000
    )
    assert (
        ingest.parse_payload({"content": "a", "timestamp": "1700000000.5"}).ts
        == 1700000000.5
    )


@pytest.mark.parametrize(
    "value",
    [
        "2023-11-14T22:13:20Z",
        "2023-11-14T22:13:20+00:00",
        "2023-11-14T23:13:20+01:00",
        "2023-11-14T22:13:20",
        "2023-11-14 22:13:20.000Z",
    ],
)
def test_timestamp_accepts_iso_8601(value):
    assert ingest.parse_payload({"content": "a", "timestamp": value}).ts == 1700000000


@pytest.mark.parametrize("value", ["yesterday", "", True, [1], {"a": 1}])
def test_timestamp_rejects_garbage(value):
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"content": "a", "timestamp": value})


def test_text_body_lands_as_plain():
    parsed = ingest.parse_text("**do not** interpret", default_level="WARNING")
    assert parsed.level == "WARNING"
    assert parsed.format == const.FORMAT_PLAIN
    assert parsed.content == "**do not** interpret"


def test_empty_text_body_is_rejected():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_text("   ")


def test_ratelimit_allows_a_burst_and_then_throttles():
    limiter = ingest.RateLimiter(per_minute=60, burst=5)
    now = 0.0
    assert all(limiter.allow("channel", now) for _ in range(5))
    assert limiter.allow("channel", now) is False
    # After one second exactly one token is refilled at 60/min.
    assert limiter.allow("channel", now + 1.0) is True
    assert limiter.allow("channel", now + 1.0) is False


def test_ratelimit_separates_channels():
    limiter = ingest.RateLimiter(per_minute=60, burst=1)
    assert limiter.allow("a", 0.0) is True
    assert limiter.allow("a", 0.0) is False
    assert limiter.allow("b", 0.0) is True


JOB = {"label": "Job", "value": "vm-101"}


def test_blocks_keep_their_order():
    parsed = ingest.parse_payload(
        {
            "content": "Nightly job",
            "blocks": [
                {"type": "fields", "rows": [[JOB, {"label": "Exit", "value": 2}]]},
                {"type": "text", "text": " Datastore **full** "},
                {"type": "fields", "rows": [[{"label": "Free", "value": "0 B"}]]},
            ],
        }
    )
    assert parsed.blocks == [
        {"type": "fields", "rows": [[JOB, {"label": "Exit", "value": "2"}]]},
        {"type": "text", "text": "Datastore **full**"},
        {"type": "fields", "rows": [[{"label": "Free", "value": "0 B"}]]},
    ]


def test_block_shorthands():
    parsed = ingest.parse_payload(
        {
            "content": "a",
            "blocks": ["plain string", {"rows": [JOB]}, {"text": "no type"}],
        }
    )
    assert parsed.blocks == [
        {"type": "text", "text": "plain string"},
        # A bare object in place of a row is a row of one.
        {"type": "fields", "rows": [[JOB]]},
        {"type": "text", "text": "no type"},
    ]


def test_blocks_alone_make_a_message():
    parsed = ingest.parse_payload({"blocks": [{"rows": [[JOB]]}]})
    assert parsed.content == ""
    assert parsed.blocks == [{"type": "fields", "rows": [[JOB]]}]


def test_empty_blocks_do_not_replace_content():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload(
            {"blocks": ["  ", {"rows": [[{"label": " ", "value": ""}], []]}]}
        )


def test_malformed_blocks_are_rejected():
    for blocks in (
        "Job: vm-101",
        [42],
        [{"type": "divider"}],
        [{"label": "Job"}],
        [{"type": "fields", "rows": "Job"}],
        [{"rows": [["Job"]]}],
        [{"rows": [[{"label": "Job", "value": {"nested": 1}}]]}],
        [{"text": ["a", "b"]}],
    ):
        with pytest.raises(ingest.PayloadError):
            ingest.parse_payload({"content": "a", "blocks": blocks})


def test_field_span_widens_a_field():
    parsed = ingest.parse_payload(
        {"blocks": [{"rows": [[JOB, {"label": "Host", "value": "pve1", "span": 2}]]}]}
    )
    assert parsed.blocks == [
        {
            "type": "fields",
            "rows": [[JOB, {"label": "Host", "value": "pve1", "span": 2}]],
        }
    ]


def test_field_span_of_one_is_not_stored():
    parsed = ingest.parse_payload({"blocks": [{"rows": [[{**JOB, "span": 1}]]}]})
    assert parsed.blocks == [{"type": "fields", "rows": [[JOB]]}]


def test_field_spans_are_fitted_into_the_column_cap():
    parsed = ingest.parse_payload(
        {
            "blocks": [
                {
                    "rows": [
                        [{**JOB, "span": 50}, JOB, JOB],
                        [{**JOB, "span": 4}, {**JOB, "span": 4}],
                    ]
                }
            ]
        }
    )
    assert parsed.blocks is not None
    rows = parsed.blocks[0]["rows"]
    # Every field survives; the wide ones give up columns, the later first.
    assert [[f.get("span", 1) for f in row] for row in rows] == [
        [const.MAX_GRID_COLUMNS - 2, 1, 1],
        [4, 2],
    ]


def test_malformed_field_span_is_rejected():
    for span in (0, -1, 1.5, "2", True, [2]):
        with pytest.raises(ingest.PayloadError):
            ingest.parse_payload({"blocks": [{"rows": [[{**JOB, "span": span}]]}]})


def test_field_format_is_kept_for_the_card():
    size = {"label": "Size", "value": 1321205760, "format": "BYTES"}
    parsed = ingest.parse_payload({"blocks": [{"rows": [[JOB, size]]}]})
    # The value stays the sender's text; only the format is normalized.
    assert parsed.blocks == [
        {
            "type": "fields",
            "rows": [
                [JOB, {"label": "Size", "value": "1321205760", "format": "bytes"}]
            ],
        }
    ]


@pytest.mark.parametrize(
    "value_format", ["bytes", "bytes_si", "duration", "datetime", "number"]
)
def test_every_value_format_is_accepted(value_format):
    parsed = ingest.parse_payload(
        {"blocks": [{"rows": [[{**JOB, "format": value_format}]]}]}
    )
    assert parsed.blocks is not None
    assert parsed.blocks[0]["rows"][0][0]["format"] == value_format


@pytest.mark.parametrize("value_format", ["size", "", 1, True, ["bytes"]])
def test_unknown_value_format_is_rejected(value_format):
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload(
            {"blocks": [{"rows": [[{**JOB, "format": value_format}]]}]}
        )


def test_text_blocks_share_the_content_budget():
    content = "c" * (const.MAX_CONTENT_CHARS - 10)
    parsed = ingest.parse_payload(
        {"content": content, "blocks": ["t" * 8, "t" * 8, {"rows": [[JOB]]}, "t"]}
    )
    # The grid survives the exhausted budget, the text after it does not.
    assert parsed.blocks == [
        {"type": "text", "text": "t" * 8},
        {"type": "text", "text": "t" * 2},
        {"type": "fields", "rows": [[JOB]]},
    ]


def test_field_limits_count_across_blocks():
    row = [{"label": "L" * 500, "value": "V" * 5000} for _ in range(8)]
    grid = {"rows": [row] * 20}
    parsed = ingest.parse_payload({"content": "a", "blocks": [grid] * 4})
    assert parsed.blocks is not None
    grids = [block["rows"] for block in parsed.blocks]
    assert all(len(rows) <= const.MAX_FIELD_ROWS for rows in grids)
    assert all(len(r) <= const.MAX_FIELDS_PER_ROW for rows in grids for r in rows)
    assert sum(len(r) for rows in grids for r in rows) == const.MAX_FIELDS
    first = grids[0][0][0]
    assert len(first["label"]) == const.MAX_FIELD_LABEL_CHARS
    assert len(first["value"]) == const.MAX_FIELD_VALUE_CHARS


def test_block_count_is_limited():
    parsed = ingest.parse_payload({"content": "a", "blocks": ["t"] * 50})
    assert parsed.blocks is not None
    assert len(parsed.blocks) == const.MAX_BLOCKS


def test_without_blocks_nothing_changes():
    assert ingest.parse_payload({"content": "a"}).blocks is None


def test_table_normal_form():
    parsed = ingest.parse_payload(
        {
            "content": "Backups",
            "blocks": [
                {
                    "type": "table",
                    "columns": ["Host", {"label": "Duration", "align": "RIGHT"}],
                    "rows": [[" nas ", "12 s"], ["pi", None]],
                }
            ],
        }
    )
    assert parsed.blocks == [
        {
            "type": "table",
            "columns": [{"label": "Host"}, {"label": "Duration", "align": "right"}],
            "rows": [["nas", "12 s"], ["pi", ""]],
        }
    ]


def test_table_left_alignment_is_not_stored():
    parsed = ingest.parse_payload(
        {"blocks": [{"columns": [{"label": "A", "align": "left"}], "rows": [["x"]]}]}
    )
    assert parsed.blocks == [
        {"type": "table", "columns": [{"label": "A"}], "rows": [["x"]]}
    ]


def test_table_rows_as_objects_derive_the_head():
    parsed = ingest.parse_payload(
        {
            "blocks": [
                {"table": [{"host": "nas", "ok": True}, {"ms": 3.5, "host": "pi"}]}
            ]
        }
    )
    # Every key in the order it first appears; missing cells stay empty.
    assert parsed.blocks == [
        {
            "type": "table",
            "columns": [{"label": "host"}, {"label": "ok"}, {"label": "ms"}],
            "rows": [["nas", "true", ""], ["pi", "", "3.5"]],
        }
    ]


def test_table_rows_as_objects_follow_given_columns():
    parsed = ingest.parse_payload(
        {
            "blocks": [
                {
                    "columns": ["b", "a"],
                    "rows": [{"a": 1, "b": 2, "c": 3}, ["x", "y"]],
                }
            ]
        }
    )
    assert parsed.blocks is not None
    assert parsed.blocks[0]["rows"] == [["2", "1"], ["x", "y"]]


def test_table_without_head_is_padded_to_the_widest_row():
    parsed = ingest.parse_payload(
        {"blocks": [{"type": "table", "rows": [[1, 2, 3], [4], [None, "", None]]}]}
    )
    # The empty row is dropped, the short one padded.
    assert parsed.blocks == [
        {"type": "table", "columns": [], "rows": [["1", "2", "3"], ["4", "", ""]]}
    ]


def test_table_rows_are_cut_to_the_head():
    parsed = ingest.parse_payload(
        {"blocks": [{"columns": ["a"], "rows": [["x", "surplus"]]}]}
    )
    assert parsed.blocks is not None
    assert parsed.blocks[0]["rows"] == [["x"]]


def test_empty_table_does_not_replace_content():
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"blocks": [{"columns": ["a"], "rows": [[None]]}]})


def test_table_column_format_applies_to_its_cells():
    parsed = ingest.parse_payload(
        {
            "blocks": [
                {
                    "columns": [
                        "Name",
                        {"label": "Size", "align": "right", "format": "bytes"},
                    ],
                    "rows": [["root.pxar", 4096]],
                }
            ]
        }
    )
    assert parsed.blocks == [
        {
            "type": "table",
            "columns": [
                {"label": "Name"},
                {"label": "Size", "align": "right", "format": "bytes"},
            ],
            "rows": [["root.pxar", "4096"]],
        }
    ]


@pytest.mark.parametrize(
    "block",
    [
        {"type": "table"},
        {"type": "table", "rows": "a|b"},
        {"type": "table", "rows": ["a"]},
        {"type": "table", "rows": [[{"nested": 1}]]},
        {"type": "table", "rows": [[["nested"]]]},
        {"type": "table", "columns": "a", "rows": [["x"]]},
        {"type": "table", "columns": [{"label": "a", "align": "justify"}], "rows": []},
        {"type": "table", "columns": [{"label": "a", "format": "size"}], "rows": []},
        {"table": [{"a": [1]}]},
    ],
)
def test_malformed_tables_are_rejected(block):
    with pytest.raises(ingest.PayloadError):
        ingest.parse_payload({"content": "a", "blocks": [block]})


def test_table_limits_per_table():
    parsed = ingest.parse_payload(
        {
            "content": "a",
            "blocks": [
                {"columns": [f"c{i}" for i in range(15)], "rows": [["x" * 500] * 15]},
                {"columns": ["a"], "rows": [["x"]] * 80},
            ],
        }
    )
    assert parsed.blocks is not None
    wide, long = parsed.blocks
    assert len(wide["columns"]) == const.MAX_TABLE_COLUMNS
    assert wide["rows"] == [
        ["x" * const.MAX_TABLE_CELL_CHARS] * const.MAX_TABLE_COLUMNS
    ]
    assert len(long["rows"]) == const.MAX_TABLE_ROWS


def test_table_cells_count_across_tables():
    table = {"columns": ["a", "b", "c", "d", "e"], "rows": [list("abcde")] * 30}
    parsed = ingest.parse_payload({"content": "a", "blocks": [table] * 3})
    assert parsed.blocks is not None
    # 150 cells for the first, the remaining 100 for the second, none left.
    assert [len(block["rows"]) for block in parsed.blocks] == [30, 20]
    assert const.MAX_TABLE_CELLS == 250
