import { describe, expect, it } from "vitest";
import { compact, ms, num, pct, timeAgo } from "../lib/format";

describe("formatters", () => {
  it("renders percentages and guards undefined", () => {
    expect(pct(0.9142, 1)).toBe("91.4%");
    expect(pct(undefined)).toBe("—");
    expect(pct(Number.NaN)).toBe("—");
  });

  it("renders fixed-precision numbers", () => {
    expect(num(0.914159)).toBe("0.914");
    expect(num(1, 0)).toBe("1");
    expect(num(undefined)).toBe("—");
  });

  it("switches latency units at one second", () => {
    expect(ms(840)).toBe("840ms");
    expect(ms(1200)).toBe("1.20s");
    expect(ms(undefined)).toBe("—");
  });

  it("compacts large counts", () => {
    expect(compact(3500)).toBe("3.5K");
    expect(compact(12)).toBe("12");
  });

  it("renders relative time", () => {
    const now = new Date().toISOString();
    expect(timeAgo(now)).toMatch(/s ago$/);
  });
});
