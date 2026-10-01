import { describe, expect, it } from "vitest";

import { formatValue } from "../src/format";

describe("formatValue", () => {
  describe("bytes", () => {
    it("uses binary units with three significant digits", () => {
      expect(formatValue("1321205760", "bytes", "en")).toBe("1.23 GiB");
      expect(formatValue("4096", "bytes", "en")).toBe("4.00 KiB");
      expect(formatValue("52428800", "bytes", "en")).toBe("50.0 MiB");
      expect(formatValue("524288000", "bytes", "en")).toBe("500 MiB");
    });

    it("keeps plain bytes whole and switches units at 1024", () => {
      expect(formatValue("0", "bytes", "en")).toBe("0 B");
      expect(formatValue("1023", "bytes", "en")).toBe("1023 B");
      expect(formatValue("1024", "bytes", "en")).toBe("1.00 KiB");
    });

    it("does not group the digits of a number below the next unit", () => {
      expect(formatValue("1023", "bytes", "de")).toBe("1023 B");
      expect(formatValue(String(1023 * 1024), "bytes", "de")).toBe("1023 KiB");
    });

    it("writes the number in the viewer's language", () => {
      expect(formatValue("1321205760", "bytes", "de")).toBe("1,23 GiB");
    });
  });

  describe("bytes_si", () => {
    it("uses SI units and switches at 1000", () => {
      expect(formatValue("999", "bytes_si", "en")).toBe("999 B");
      expect(formatValue("1000", "bytes_si", "en")).toBe("1.00 kB");
      expect(formatValue("1321205760", "bytes_si", "de")).toBe("1,32 GB");
    });
  });

  describe("duration", () => {
    it("keeps a fraction below a minute", () => {
      expect(formatValue("7", "duration", "en")).toBe("7s");
      expect(formatValue("0.5", "duration", "en")).toBe("0.5s");
    });

    it("shows the largest unit and the one below it", () => {
      expect(formatValue("847", "duration", "en")).toBe("14m 7s");
      expect(formatValue("7385", "duration", "en")).toBe("2h 3m");
      expect(formatValue("90000", "duration", "en")).toBe("1d 1h");
    });

    it("leaves out a smaller unit that is zero", () => {
      expect(formatValue("3600", "duration", "en")).toBe("1h");
      expect(formatValue("86580", "duration", "en")).toBe("1d");
    });

    it("names the units in the viewer's language", () => {
      expect(formatValue("847", "duration", "de")).toBe("14 Min. 7 Sek.");
    });

    it("refuses a negative duration", () => {
      expect(formatValue("-5", "duration", "en")).toBeNull();
    });
  });

  describe("datetime", () => {
    const expected = new Date(Date.UTC(2026, 9, 1, 1, 0)).toLocaleString("de", {
      dateStyle: "short",
      timeStyle: "short",
    });

    it("reads ISO 8601 with an offset", () => {
      expect(formatValue("2026-10-01T01:00:00.000Z", "datetime", "de")).toBe(expected);
      expect(formatValue("2026-10-01T03:00:00+02:00", "datetime", "de")).toBe(expected);
    });

    it("reads ISO 8601 without an offset as UTC, like the ingest", () => {
      expect(formatValue("2026-10-01T01:00:00", "datetime", "de")).toBe(expected);
    });

    it("reads Unix seconds", () => {
      expect(formatValue(String(Date.UTC(2026, 9, 1, 1, 0) / 1000), "datetime", "de")).toBe(
        expected,
      );
    });

    it("leaves other notations to the sender", () => {
      expect(formatValue("01.10.2026", "datetime", "de")).toBeNull();
      expect(formatValue("2026-13-45T99:00:00", "datetime", "de")).toBeNull();
    });
  });

  describe("number", () => {
    it("groups digits in the viewer's language", () => {
      expect(formatValue("1321205760", "number", "en")).toBe("1,321,205,760");
      expect(formatValue("1321205760", "number", "de")).toBe("1.321.205.760");
      expect(formatValue("2.5", "number", "de")).toBe("2,5");
    });
  });

  it("leaves a value alone that does not fit its format", () => {
    for (const format of ["bytes", "bytes_si", "duration", "number"]) {
      expect(formatValue("–", format, "en")).toBeNull();
      expect(formatValue("12 GB", format, "en")).toBeNull();
      expect(formatValue("", format, "en")).toBeNull();
      expect(formatValue("Infinity", format, "en")).toBeNull();
    }
  });

  it("leaves a value alone without a format or with an unknown one", () => {
    expect(formatValue("4096", undefined, "en")).toBeNull();
    expect(formatValue("4096", "from-the-future", "en")).toBeNull();
  });

  it("survives a broken locale", () => {
    expect(formatValue("4096", "bytes", "not a locale!")).toMatch(/KiB$/);
  });
});
