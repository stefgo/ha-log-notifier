/**
 * Compact and detailed message display.
 *
 * Pure logic without lit, so it can be tested: which form a message takes and
 * which single line stands for it.
 */

import { toPlainText } from "./markdown";
import type { LogMessage } from "./types";

/**
 * `auto` follows the read position: read messages compact, unread ones in
 * detail. The other two put every message into the same form.
 */
export type ViewMode = "auto" | "compact" | "detail";

/** What decides the form of the messages of the open channel. */
export interface ViewState {
  /** The channel's current read position. */
  readId: number;
  /** The read position at the moment the channel was opened. */
  openedReadId: number;
  mode: ViewMode;
  /** Messages switched individually — each the opposite of what the mode says. */
  toggled: ReadonlySet<number>;
}

/** An unread message is always shown in detail, whatever mode or switch say. */
export function isUnread(id: number, view: ViewState): boolean {
  return id > view.readId;
}

/**
 * Whether a message is shown compact.
 *
 * `auto` goes by the read position from opening the channel, not the live
 * one — marking read must not collapse a message under the reader's eyes.
 */
export function isCompact(id: number, view: ViewState): boolean {
  if (isUnread(id, view)) return false;
  const compact =
    view.mode === "auto" ? id <= view.openedReadId : view.mode === "compact";
  return view.toggled.has(id) ? !compact : compact;
}

/**
 * Where the "New" divider sits in a list of message IDs, newest first.
 *
 * Everything above the divider is unread, so it goes in front of the first
 * read message — the returned index. If every message is unread it closes the
 * list (`ids.length`), but only once nothing older is left to load: until then
 * the read position may lie below the loaded page. `-1` means no divider —
 * nothing is unread, or it is not known yet where the unread ones end.
 */
export function dividerIndex(
  ids: readonly number[],
  openedReadId: number,
  hasMore: boolean,
): number {
  const firstRead = ids.findIndex((id) => id <= openedReadId);
  if (firstRead > 0) return firstRead;
  if (firstRead === -1 && ids.length > 0 && !hasMore) return ids.length;
  return -1;
}

/** Text for the channel preview — a message may consist of blocks alone. */
export function previewText(message: LogMessage): string {
  if (message.title) return message.title;
  if (message.content) return message.content;
  for (const block of message.blocks ?? []) {
    if (block.type === "text") return block.text;
  }
  for (const block of message.blocks ?? []) {
    const first = block.type === "fields" ? block.rows[0]?.[0] : undefined;
    if (first) return [first.label, first.value].filter(Boolean).join(": ");
  }
  for (const block of message.blocks ?? []) {
    if (block.type !== "table" || !block.rows.length) continue;
    return [block.columns[0]?.label, block.rows[0][0]].filter(Boolean).join(": ");
  }
  return "";
}

/**
 * The first line of a message's body as plain text — what a compact message
 * without a title shows in the title's place.
 */
export function summaryLine(message: LogMessage): string {
  const text = previewText({ ...message, title: undefined });
  const line = text
    .split("\n")
    .map((candidate) => candidate.trim())
    // A code fence is markup, not content.
    .find((candidate) => candidate && !candidate.startsWith("```"));
  return toPlainText(line ?? "");
}
