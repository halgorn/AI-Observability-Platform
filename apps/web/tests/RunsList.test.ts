import { describe, it, expect } from "vitest";
import { formatDuration, formatCost } from "../components/RunsList";

describe("formatDuration", () => {
  it("formats ms under 1s", () => {
    expect(formatDuration(500)).toBe("500ms");
  });
  it("formats s", () => {
    expect(formatDuration(1500)).toBe("1.5s");
    expect(formatDuration(59900)).toBe("59.9s");
  });
  it("formats m", () => {
    expect(formatDuration(60_000)).toBe("1.0m");
    expect(formatDuration(120_000)).toBe("2.0m");
  });
  it("handles null", () => {
    expect(formatDuration(null)).toBe("—");
  });
});

describe("formatCost", () => {
  it("formats sub-cent", () => {
    expect(formatCost(0.0001)).toBe("$0.0001");
  });
  it("formats dollars", () => {
    expect(formatCost(1.5)).toBe("$1.50");
  });
  it("handles null", () => {
    expect(formatCost(null)).toBe("—");
  });
});
