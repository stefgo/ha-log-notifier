/**
 * Column spans of a label/value grid row — kept apart from the rendering so
 * the arithmetic can be tested without a DOM.
 */

import type { MessageField } from "./types";

/** Mirrors `MAX_GRID_COLUMNS` of the integration. */
export const MAX_GRID_COLUMNS = 6;

/**
 * How many columns each field of a row takes. The integration already fits
 * the spans into `MAX_GRID_COLUMNS`; the card checks again because the value
 * ends up in a style attribute, and only a small whole number may get there.
 * Anything else counts as 1 — that is also how a message from before spans
 * existed is laid out.
 */
export function fieldSpans(row: MessageField[]): number[] {
  let used = 0;
  return row.map((field, index) => {
    const span = field.span ?? 1;
    const wanted = Number.isInteger(span) && span > 1 ? span : 1;
    const after = row.length - index - 1;
    const fitted = Math.max(1, Math.min(wanted, MAX_GRID_COLUMNS - used - after));
    used += fitted;
    return fitted;
  });
}
