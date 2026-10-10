import { describe, expect, it } from "vitest";

import type { ChannelSummary, LogMessage } from "../src/types";
import {
  ViewState,
  VisibleReadInput,
  countsAsSeen,
  dividerIndex,
  hasUnread,
  isCompact,
  orderChannels,
  previewText,
  summaryLine,
  visibleReadState,
} from "../src/view";

const message = (extra: Partial<LogMessage>): LogMessage => ({
  id: 1,
  ts: 0,
  level: "INFO",
  content: "",
  ...extra,
});

const channel = (id: string, extra: Partial<ChannelSummary> = {}): ChannelSummary => ({
  id,
  name: id,
  icon: "mdi:bell",
  enabled: true,
  badge_levels: ["ERROR"],
  unread: 0,
  unread_by_level: {},
  highest_unread_level: null,
  last_read_id: 0,
  total: 0,
  last_message: null,
  ...extra,
});

describe("orderChannels", () => {
  const ids = (channels: ChannelSummary[]): string[] =>
    channels.map((entry) => entry.id);

  it("keeps the delivered order for all channels", () => {
    const channels = [channel("b"), channel("a"), channel("c")];
    expect(ids(orderChannels(channels, "all"))).toEqual(["b", "a", "c"]);
    expect(ids(orderChannels(channels, undefined))).toEqual(["b", "a", "c"]);
  });

  it("follows the order of a list and skips unknown IDs", () => {
    const channels = [channel("a"), channel("b"), channel("c")];
    expect(ids(orderChannels(channels, ["c", "gone", "a"]))).toEqual(["c", "a"]);
  });

  it("shows a channel once even if the list names it twice", () => {
    const channels = [channel("a"), channel("b")];
    expect(ids(orderChannels(channels, ["b", "a", "b"]))).toEqual(["b", "a"]);
  });

  it("appends the unlisted channels as delivered when asked to", () => {
    const channels = [channel("a"), channel("b"), channel("c"), channel("d")];
    const order = (wanted: "all" | string[]) =>
      ids(orderChannels(channels, wanted, "config", undefined, true));
    expect(order(["c", "gone", "a"])).toEqual(["c", "a", "b", "d"]);
    expect(order("all")).toEqual(["a", "b", "c", "d"]);
  });

  it("sorts listed and unlisted channels alike", () => {
    const channels = [channel("a"), channel("b", { unread: 3 }), channel("c")];
    expect(
      ids(orderChannels(channels, ["c"], "unread", undefined, true)),
    ).toEqual(["b", "c", "a"]);
  });

  it("does not reorder the list it was given", () => {
    const channels = [channel("b"), channel("a")];
    orderChannels(channels, "all", "name");
    expect(ids(channels)).toEqual(["b", "a"]);
  });

  it("sorts by display name, not by ID", () => {
    const channels = [
      channel("x", { name: "zebra" }),
      channel("y", { name: "Backup 10" }),
      channel("z", { name: "backup 2" }),
    ];
    expect(ids(orderChannels(channels, "all", "name", "en"))).toEqual([
      "z",
      "y",
      "x",
    ]);
  });

  it("sorts names even with a language tag Intl rejects", () => {
    const channels = [channel("b"), channel("a")];
    expect(ids(orderChannels(channels, "all", "name", "not a tag"))).toEqual([
      "a",
      "b",
    ]);
  });

  it("puts the most unread first and leaves ties as selected", () => {
    const channels = [
      channel("a"),
      channel("b", { unread: 2 }),
      channel("c"),
      channel("d", { unread: 7 }),
    ];
    expect(ids(orderChannels(channels, "all", "unread"))).toEqual([
      "d",
      "b",
      "a",
      "c",
    ]);
    expect(ids(orderChannels(channels, ["c", "b", "a"], "unread"))).toEqual([
      "b",
      "c",
      "a",
    ]);
  });

  it("puts the newest message first and empty channels last", () => {
    const channels = [
      channel("empty"),
      channel("old", { last_message: message({ ts: 100 }) }),
      channel("new", { last_message: message({ ts: 300 }) }),
      channel("empty2"),
    ];
    expect(ids(orderChannels(channels, "all", "latest"))).toEqual([
      "new",
      "old",
      "empty",
      "empty2",
    ]);
  });
});

describe("hasUnread", () => {
  it("is false when nothing lies above the read position", () => {
    expect(hasUnread({ unread_by_level: {} })).toBe(false);
    expect(hasUnread({ unread_by_level: { ERROR: 0 } })).toBe(false);
  });

  it("counts levels the badge leaves out", () => {
    // A channel badging ERROR only reports `unread: 0` for an unread INFO.
    expect(hasUnread({ unread_by_level: { INFO: 1 } })).toBe(true);
  });
});

describe("isCompact", () => {
  const view = (extra: Partial<ViewState> = {}): ViewState => ({
    readId: 5,
    openedReadId: 5,
    mode: "auto",
    toggled: new Set(),
    ...extra,
  });

  it("shows read messages compact and unread ones in detail by default", () => {
    expect(isCompact(5, view())).toBe(true);
    expect(isCompact(4, view())).toBe(true);
    expect(isCompact(6, view())).toBe(false);
  });

  it("puts every read message into the chosen form", () => {
    expect(isCompact(4, view({ mode: "detail" }))).toBe(false);
    expect(isCompact(4, view({ mode: "compact" }))).toBe(true);
  });

  it("inverts a read message that was toggled individually", () => {
    const toggled = new Set([4]);
    expect(isCompact(4, view({ toggled }))).toBe(false);
    expect(isCompact(4, view({ toggled, mode: "detail" }))).toBe(true);
    expect(isCompact(4, view({ toggled, mode: "compact" }))).toBe(false);
  });

  it("never shows an unread message compact", () => {
    expect(isCompact(6, view({ mode: "compact" }))).toBe(false);
    expect(isCompact(6, view({ toggled: new Set([6]) }))).toBe(false);
    expect(isCompact(6, view({ mode: "detail", toggled: new Set([6]) }))).toBe(false);
  });

  it("keeps what was marked read while open in detail until asked otherwise", () => {
    const marked = { readId: 8, openedReadId: 5 };
    expect(isCompact(7, view(marked))).toBe(false);
    expect(isCompact(7, view({ ...marked, mode: "compact" }))).toBe(true);
  });
});

describe("summaryLine", () => {
  it("takes the first line of the content, not the title", () => {
    expect(summaryLine(message({ title: "Backup", content: "done\nin 3 s" }))).toBe(
      "done",
    );
  });

  it("skips blank lines and strips markdown", () => {
    expect(summaryLine(message({ content: "\n\n**Disk** is `full`\nmore" }))).toBe(
      "Disk is full",
    );
  });

  it("skips a code fence and shows the first line inside it", () => {
    expect(summaryLine(message({ content: "```yaml\nkey: value\n```" }))).toBe(
      "key: value",
    );
  });

  it("falls back to the blocks of a message without content", () => {
    expect(
      summaryLine(
        message({
          blocks: [{ type: "fields", rows: [[{ label: "Host", value: "nas" }]] }],
        }),
      ),
    ).toBe("Host: nas");
  });

  it("is empty for a message that has nothing but a title", () => {
    expect(summaryLine(message({ title: "Backup" }))).toBe("");
  });
});

describe("previewText", () => {
  it("prefers the title over the content", () => {
    expect(previewText(message({ title: "Backup", content: "done" }))).toBe("Backup");
    expect(previewText(message({ content: "done" }))).toBe("done");
  });
});

describe("dividerIndex", () => {
  it("sits in front of the first read message", () => {
    expect(dividerIndex([9, 8, 7, 6], 7, false)).toBe(2);
    expect(dividerIndex([9, 8, 7, 6], 7, true)).toBe(2);
  });

  it("is absent when nothing is unread", () => {
    expect(dividerIndex([9, 8, 7], 9, false)).toBe(-1);
    expect(dividerIndex([], 0, false)).toBe(-1);
  });

  it("closes the list when every message is unread", () => {
    expect(dividerIndex([9, 8, 7], 3, false)).toBe(3);
  });

  it("waits while older messages may still hold the read position", () => {
    expect(dividerIndex([9, 8, 7], 3, true)).toBe(-1);
  });
});

describe("countsAsSeen", () => {
  it("takes half of the message", () => {
    expect(countsAsSeen(0.5, 40, 500)).toBe(true);
    expect(countsAsSeen(0.49, 39, 500)).toBe(false);
  });

  it("takes half of the stream from a message taller than the stream", () => {
    // 4000 px of message in a 500 px stream never shows more than an eighth.
    expect(countsAsSeen(0.07, 280, 500)).toBe(true);
    expect(countsAsSeen(0.05, 200, 500)).toBe(false);
  });

  it("does not count anything while the stream has no height", () => {
    expect(countsAsSeen(0, 0, 0)).toBe(false);
  });
});

describe("visibleReadState", () => {
  const input = (extra: Partial<VisibleReadInput> = {}): VisibleReadInput => ({
    ids: [9, 8, 7, 6],
    readId: 7,
    latestId: 9,
    hasMore: false,
    allLevels: true,
    seen: new Set(),
    ...extra,
  });

  it("is idle when nothing is unread", () => {
    expect(visibleReadState(input({ readId: 9 }))).toEqual({ state: "idle" });
    expect(visibleReadState(input({ ids: [], readId: 0, latestId: 0 }))).toEqual({
      state: "idle",
    });
  });

  it("waits until every unread message was seen", () => {
    expect(visibleReadState(input({ seen: new Set([9]) }))).toEqual({
      state: "unseen",
    });
  });

  it("is ready up to the newest message seen", () => {
    expect(visibleReadState(input({ seen: new Set([8, 9]) }))).toEqual({
      state: "ready",
      upToId: 9,
    });
  });

  it("is suspended by a level filter, even one that hides all unread", () => {
    expect(
      visibleReadState(input({ allLevels: false, seen: new Set([8, 9]) })),
    ).toEqual({ state: "filtered" });
    expect(
      visibleReadState(input({ ids: [7, 6], allLevels: false })),
    ).toEqual({ state: "filtered" });
  });

  it("is suspended while unread messages may lie below the loaded page", () => {
    expect(
      visibleReadState(input({ readId: 3, hasMore: true, seen: new Set([6, 7, 8, 9]) })),
    ).toEqual({ state: "more" });
  });

  it("resumes once a full page turned out to be the last one", () => {
    expect(
      visibleReadState(input({ readId: 3, hasMore: false, seen: new Set([6, 7, 8, 9]) })),
    ).toEqual({ state: "ready", upToId: 9 });
  });

  it("is not held up by older pages when the read position is loaded", () => {
    expect(
      visibleReadState(input({ hasMore: true, seen: new Set([8, 9]) })),
    ).toEqual({ state: "ready", upToId: 9 });
  });

  it("does not vouch for messages the list never received", () => {
    // The channel moved on to 11 while the connection was down.
    expect(
      visibleReadState(input({ latestId: 11, seen: new Set([8, 9]) })),
    ).toEqual({ state: "unseen" });
    expect(visibleReadState(input({ ids: [], latestId: 11 }))).toEqual({
      state: "unseen",
    });
  });
});
