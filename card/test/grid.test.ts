import { describe, expect, it } from "vitest";

import { fieldSpans, MAX_GRID_COLUMNS } from "../src/grid";
import type { MessageField } from "../src/types";

const row = (...spans: (number | undefined)[]): MessageField[] =>
  spans.map((span, i) => ({ label: `L${i}`, value: "v", span }));

describe("fieldSpans", () => {
  it("counts a field without span as one column", () => {
    expect(fieldSpans(row(undefined, undefined, undefined))).toEqual([1, 1, 1]);
  });

  it("keeps spans that fit", () => {
    expect(fieldSpans(row(undefined, 2))).toEqual([1, 2]);
    expect(fieldSpans(row(3))).toEqual([3]);
  });

  it("shortens a span so every later field keeps a column", () => {
    expect(fieldSpans(row(10, undefined, undefined))).toEqual([
      MAX_GRID_COLUMNS - 2,
      1,
      1,
    ]);
    expect(fieldSpans(row(4, 4))).toEqual([4, 2]);
  });

  it("treats anything but a whole number above one as one", () => {
    const odd = [1.5, 0, -2, Number.NaN, "3" as unknown as number];
    expect(fieldSpans(row(...odd))).toEqual([1, 1, 1, 1, 1]);
  });
});
