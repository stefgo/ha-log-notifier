import { describe, expect, it } from "vitest";

import { TEXTS, localize } from "../src/i18n";

describe("localize", () => {
  it("answers in the viewer's language", () => {
    expect(localize("en", "mark_all_read")).toBe("Mark all read");
    expect(localize("de", "mark_all_read")).toBe("Alle gelesen");
  });

  it("treats a regional variant as its base language", () => {
    expect(localize("de-AT", "clear")).toBe("Leeren");
    expect(localize("de_CH", "clear")).toBe("Leeren");
    expect(localize("DE", "clear")).toBe("Leeren");
    expect(localize("en-GB", "clear")).toBe("Clear");
  });

  it("falls back to English for a language without a table", () => {
    expect(localize("fr", "no_messages")).toBe("No messages.");
    expect(localize(undefined, "no_messages")).toBe("No messages.");
    expect(localize("", "no_messages")).toBe("No messages.");
  });

  it("does not mistake an object property for a language", () => {
    expect(localize("constructor", "clear")).toBe("Clear");
    expect(localize("__proto__", "clear")).toBe("Clear");
  });

  it("fills placeholders and leaves unknown ones alone", () => {
    expect(localize("en", "clear_confirm", { name: "Backups" })).toBe(
      'Delete all messages in "Backups"?',
    );
    expect(localize("de", "clear_confirm", { name: "Backups" })).toBe(
      "Alle Meldungen in „Backups“ löschen?",
    );
    expect(localize("en", "clear_confirm")).toBe('Delete all messages in "{name}"?');
  });

  it("inserts a value verbatim, even one that looks like a placeholder", () => {
    expect(localize("en", "error_channels", { error: "{name} $& $1" })).toBe(
      "Could not load channels: {name} $& $1",
    );
  });
});

describe("TEXTS", () => {
  const placeholders = (text: string) => (text.match(/\{\w+\}/g) ?? []).sort();

  it("carries the same keys and placeholders in every language", () => {
    const source = TEXTS.en;
    for (const [language, texts] of Object.entries(TEXTS)) {
      expect(Object.keys(texts).sort(), language).toEqual(Object.keys(source).sort());
      for (const key of Object.keys(source) as (keyof typeof source)[]) {
        expect(texts[key], `${language}.${key}`).not.toBe("");
        expect(placeholders(texts[key]), `${language}.${key}`).toEqual(
          placeholders(source[key]),
        );
      }
    }
  });
});
