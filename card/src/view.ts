/**
 * Compact and detailed message display.
 *
 * Pure logic without lit, so it can be tested: which form a message takes and
 * which single line stands for it.
 */

import { toPlainText } from "./markdown";
import type { ChannelSort, ChannelSummary, LogMessage } from "./types";

export const CHANNEL_SORTS: readonly ChannelSort[] = [
  "config",
  "name",
  "unread",
  "latest",
];

/** Compares names in the viewer's language; an unusable tag falls back to the default. */
function nameCollator(language: string | undefined): Intl.Collator {
  const options: Intl.CollatorOptions = { sensitivity: "base", numeric: true };
  try {
    return new Intl.Collator(language, options);
  } catch {
    return new Intl.Collator(undefined, options);
  }
}

/**
 * The channels a card shows, in the order it shows them.
 *
 * `wanted` selects: a list keeps its own order and skips unknown IDs, anything
 * else takes every channel as delivered. With `showUnlisted` the list only
 * arranges — the channels it leaves out follow as delivered. `sort` then
 * rearranges that selection; the sort is stable, so channels that tie stay in
 * the selection's order.
 */
export function orderChannels(
  channels: readonly ChannelSummary[],
  wanted: "all" | readonly string[] | undefined,
  sort: ChannelSort = "config",
  language?: string,
  showUnlisted = false,
): ChannelSummary[] {
  let selected: ChannelSummary[];
  if (!wanted || wanted === "all") {
    selected = [...channels];
  } else {
    // A Set, so an ID listed twice does not show its channel twice.
    selected = [...new Set(wanted)]
      .map((id) => channels.find((channel) => channel.id === id))
      .filter((channel): channel is ChannelSummary => Boolean(channel));
    if (showUnlisted) {
      selected.push(...channels.filter((channel) => !selected.includes(channel)));
    }
  }
  if (sort === "name") {
    const collator = nameCollator(language);
    return selected.sort((a, b) => collator.compare(a.name, b.name));
  }
  if (sort === "unread") {
    return selected.sort((a, b) => b.unread - a.unread);
  }
  if (sort === "latest") {
    // A channel without a message has nothing to be recent with.
    const ts = (channel: ChannelSummary) => channel.last_message?.ts ?? -Infinity;
    return selected.sort((a, b) => {
      const [left, right] = [ts(a), ts(b)];
      return left === right ? 0 : right > left ? 1 : -1;
    });
  }
  return selected;
}

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
 * Whether anything in the channel lies above the read position — in any
 * level. `unread` would not do: it is the badge's number and only counts the
 * channel's badge levels.
 */
export function hasUnread(
  channel: Pick<ChannelSummary, "unread_by_level">,
): boolean {
  return Object.values(channel.unread_by_level).some((count) => count > 0);
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

/**
 * Whether a message is on screen far enough to count as seen: half of it, or —
 * for one taller than the stream, which can never show half of itself — enough
 * to fill half of the stream.
 */
export function countsAsSeen(
  ratio: number,
  visibleHeight: number,
  areaHeight: number,
): boolean {
  if (ratio >= 0.5) return true;
  return areaHeight > 0 && visibleHeight >= areaHeight / 2;
}

/** What `mark_read: visible` needs to know about the open channel. */
export interface VisibleReadInput {
  /** IDs of the loaded messages, newest first. */
  ids: readonly number[];
  /** The channel's current read position. */
  readId: number;
  /** ID of the channel's newest message, whatever the level filter shows. */
  latestId: number;
  /** Whether older messages are left to load. */
  hasMore: boolean;
  /** Whether every level is switched on. */
  allLevels: boolean;
  /** IDs that stayed on screen long enough to count as seen. */
  seen: ReadonlySet<number>;
}

/**
 * Where `mark_read: visible` stands.
 *
 * `idle`: nothing is unread. `filtered`: a level filter may hide unread
 * messages. `more`: unread messages remain below the loaded page. `unseen`:
 * not every unread message appeared on screen yet. `ready`: all of them did —
 * `upToId` is the newest one seen, and the read position may move there.
 */
export type VisibleReadState =
  | { state: "idle" | "filtered" | "more" | "unseen" }
  | { state: "ready"; upToId: number };

/**
 * Decides whether everything unread was seen.
 *
 * The read position is a watermark: marking the newest seen message also
 * marks every older one as read. Partial progress cannot be represented that
 * way — hence the all-or-nothing rule, and the two states in which the proof
 * is out of reach.
 */
export function visibleReadState(input: VisibleReadInput): VisibleReadState {
  const { ids, readId, seen } = input;
  const unread = ids.filter((id) => id > readId);
  if (unread.length === 0 && input.latestId <= readId) return { state: "idle" };
  if (!input.allLevels) return { state: "filtered" };
  if (input.hasMore && ids.length > 0 && ids[ids.length - 1] > readId) {
    return { state: "more" };
  }
  // The channel has unread messages the list does not hold — it is stale or
  // still loading.
  if (unread.length === 0 || unread[0] < input.latestId) return { state: "unseen" };
  if (!unread.every((id) => seen.has(id))) return { state: "unseen" };
  return { state: "ready", upToId: unread[0] };
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
