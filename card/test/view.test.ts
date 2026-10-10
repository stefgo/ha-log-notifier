import { describe, expect, it } from "vitest";

import type { LogMessage } from "../src/types";
import {
  ViewState,
  dividerIndex,
  isCompact,
  previewText,
  summaryLine,
} from "../src/view";

const message = (extra: Partial<LogMessage>): LogMessage => ({
  id: 1,
  ts: 0,
  level: "INFO",
  content: "",
  ...extra,
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
