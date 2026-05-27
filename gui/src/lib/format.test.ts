import { describe, it, expect } from "vitest";
import { formatBytes, formatDuration, formatPercent, formatMem } from "./format";

describe("formatBytes", () => {
  it("formats GB", () => expect(formatBytes(1_932_735_283)).toBe("1.8 GB"));
  it("formats MB", () => expect(formatBytes(52_428_800)).toBe("50 MB"));
  it("null → dash", () => expect(formatBytes(null)).toBe("—"));
});

describe("formatDuration", () => {
  it("seconds", () => expect(formatDuration(45)).toBe("45s"));
  it("minutes", () => expect(formatDuration(125)).toBe("2m"));
  it("hours+minutes", () => expect(formatDuration(8040)).toBe("2h 14m"));
  it("days", () => expect(formatDuration(180000)).toBe("2d 2h"));
  it("null → dash", () => expect(formatDuration(null)).toBe("—"));
});

describe("formatPercent", () => {
  it("rounds", () => expect(formatPercent(2.1)).toBe("2%"));
  it("null → dash", () => expect(formatPercent(null)).toBe("—"));
});

describe("formatMem", () => {
  it("used / total", () =>
    expect(formatMem(1_932_735_283, 8_589_934_592)).toBe("1.8 / 8 GB"));
  it("null → dash", () => expect(formatMem(null, null)).toBe("—"));
});
