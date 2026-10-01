/**
 * Value formats of grid fields and table columns — kept apart from the
 * rendering so it can be tested without a DOM.
 *
 * The integration stores the sender's value as text; the card turns it into a
 * size, a duration, a date or a number in the viewer's language. A value that
 * does not fit its format is left alone: the caller shows the text itself, so a
 * format can never make a message unreadable.
 */

import type { ValueFormat } from "./types";

const BINARY_UNITS = ["B", "KiB", "MiB", "GiB", "TiB", "PiB", "EiB"];
const SI_UNITS = ["B", "kB", "MB", "GB", "TB", "PB", "EB"];

/** Largest unit first, as `Intl` names them. */
const DURATION_UNITS: [unit: string, seconds: number][] = [
  ["day", 86400],
  ["hour", 3600],
  ["minute", 60],
  ["second", 1],
];

/** A plain decimal number, as JSON or Python's `str()` writes one. */
const NUMBER = /^[+-]?(?:\d+\.?\d*|\.\d+)(?:e[+-]?\d+)?$/i;
/** ISO 8601 with a time but no offset — read as UTC, like the ingest does. */
const ISO_WITHOUT_OFFSET = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?$/;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}(?:[T ]|$)/;

/**
 * The value in its format, or `null` when there is nothing to format: no
 * format, one this card does not know (sent by a newer integration), or a
 * value that does not fit it.
 */
export function formatValue(
  value: string,
  format: ValueFormat | string | undefined,
  locale: string,
): string | null {
  switch (format) {
    case "bytes":
      return formatBytes(parseNumber(value), 1024, BINARY_UNITS, locale);
    case "bytes_si":
      return formatBytes(parseNumber(value), 1000, SI_UNITS, locale);
    case "duration":
      return formatDuration(parseNumber(value), locale);
    case "datetime":
      return formatDateTime(value, locale);
    case "number": {
      const number = parseNumber(value);
      return number === null ? null : numberFormat(locale).format(number);
    }
    default:
      return null;
  }
}

function parseNumber(value: string): number | null {
  const text = value.trim();
  if (!NUMBER.test(text)) return null;
  const number = Number(text);
  return Number.isFinite(number) ? number : null;
}

/** A locale HA hands over is trusted, but a broken one must not break the card. */
function numberFormat(locale: string, options?: Intl.NumberFormatOptions): Intl.NumberFormat {
  try {
    return new Intl.NumberFormat(locale, options);
  } catch {
    return new Intl.NumberFormat(undefined, options);
  }
}

/**
 * `1.23 GiB`: the largest unit that keeps the number at one or more, with two
 * decimals below 10, one below 100 and none above — three significant digits,
 * like the Proxmox UI. Plain bytes are always whole.
 */
function formatBytes(
  bytes: number | null,
  base: number,
  units: string[],
  locale: string,
): string | null {
  if (bytes === null) return null;
  let value = bytes;
  let unit = 0;
  while (Math.abs(value) >= base && unit < units.length - 1) {
    value /= base;
    unit++;
  }
  const size = Math.abs(value);
  const digits = unit === 0 ? 0 : size < 10 ? 2 : size < 100 ? 1 : 0;
  // No grouping: a binary unit holds up to 1023, and in German `1.023 B`
  // would read as one byte and a fraction.
  const number = numberFormat(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
    useGrouping: false,
  }).format(value);
  return `${number} ${units[unit]}`;
}

/**
 * `2 h 3 min`: the largest unit and the one below it, rounded to the second;
 * the smaller one is left out when it is zero (`1 d`, not `1 d 0 h`). Below a
 * minute a fraction is kept (`0.5 s`), above it would be noise.
 */
function formatDuration(seconds: number | null, locale: string): string | null {
  if (seconds === null || seconds < 0) return null;
  const unit = (name: string, amount: number, fraction = 0) =>
    numberFormat(locale, {
      style: "unit",
      unit: name,
      unitDisplay: "narrow",
      maximumFractionDigits: fraction,
    }).format(amount);
  if (seconds < 60) return unit("second", seconds, 1);
  let rest = Math.round(seconds);
  const parts: string[] = [];
  for (const [name, size] of DURATION_UNITS) {
    const amount = Math.floor(rest / size);
    rest -= amount * size;
    if (amount > 0 || parts.length > 0) parts.push(amount > 0 ? unit(name, amount) : "");
    if (parts.length === 2) break;
  }
  return parts.filter(Boolean).join(" ");
}

/**
 * Unix seconds or ISO 8601, written like the card's own absolute timestamps.
 * Anything else — a date in some other notation — is left to the sender.
 */
function formatDateTime(value: string, locale: string): string | null {
  const text = value.trim();
  const number = parseNumber(text);
  let date: Date;
  if (number !== null) {
    date = new Date(number * 1000);
  } else if (ISO_DATE.test(text)) {
    date = new Date(ISO_WITHOUT_OFFSET.test(text) ? `${text}Z` : text);
  } else {
    return null;
  }
  if (Number.isNaN(date.getTime())) return null;
  const options: Intl.DateTimeFormatOptions = { dateStyle: "short", timeStyle: "short" };
  try {
    return date.toLocaleString(locale, options);
  } catch {
    return date.toLocaleString(undefined, options);
  }
}
