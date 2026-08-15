/**
 * Level order, colors and icons — one source for badge and list.
 *
 * The order only determines how the filter chips are arranged; there is no
 * ranking in the card: every level is toggled on and off individually.
 */

import type { Level } from "./types";

export const LEVELS: Level[] = ["ERROR", "WARNING", "INFO", "TRACE"];

/**
 * Colors from the HA theme variables — they carry the light and the dark theme
 * alike, hard-coded hex values would not.
 */
export const levelColor = (level: Level | null | undefined): string => {
  switch (level) {
    case "ERROR":
      return "var(--error-color, #db4437)";
    case "WARNING":
      return "var(--warning-color, #ffa600)";
    case "INFO":
      return "var(--info-color, #039be5)";
    case "TRACE":
      return "var(--secondary-text-color, #727272)";
    default:
      return "var(--secondary-text-color, #727272)";
  }
};

export const levelIcon = (level: Level | null | undefined): string => {
  switch (level) {
    case "ERROR":
      return "mdi:alert-circle";
    case "WARNING":
      return "mdi:alert";
    case "INFO":
      return "mdi:information";
    case "TRACE":
      return "mdi:magnify";
    default:
      return "mdi:message-text-outline";
  }
};
