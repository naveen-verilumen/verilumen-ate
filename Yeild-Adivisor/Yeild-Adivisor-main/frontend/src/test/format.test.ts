import { describe, expect, it } from "vitest";
import { formatAnalysisTimestampIst } from "../services/format";

describe("formatAnalysisTimestampIst", () => {
  it("converts a UTC ISO timestamp to Asia/Kolkata without using the host timezone", () => {
    expect(formatAnalysisTimestampIst("2026-09-30T05:48:07Z")).toBe("30 Sep 2026, 11:18 AM IST");
    expect(formatAnalysisTimestampIst("2026-09-24T08:00:00Z")).toBe("24 Sep 2026, 1:30 PM IST");
    expect(formatAnalysisTimestampIst("2026-09-30T19:00:00Z")).toBe("1 Oct 2026, 12:30 AM IST");
  });

  it("does not echo the raw ISO Z timestamp", () => {
    const formatted = formatAnalysisTimestampIst("2026-09-30T05:48:07Z");
    expect(formatted).not.toMatch(/T\d{2}:\d{2}:\d{2}Z/);
    expect(formatted).toContain("IST");
  });

  it("returns null for missing or invalid values", () => {
    expect(formatAnalysisTimestampIst(null)).toBeNull();
    expect(formatAnalysisTimestampIst("not-a-date")).toBeNull();
  });
});
