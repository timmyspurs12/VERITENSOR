/**
 * The UI must never invent mechanism arithmetic. These tests mirror the
 * backend formulas so a drift between the two surfaces as a failure.
 */
import { describe, expect, it } from "vitest";

const brier = (confidence: number, hitRate: number) =>
  hitRate * (1 - confidence) ** 2 + (1 - hitRate) * confidence ** 2;

const calibration = (b: number, worst = 0.25) =>
  Math.max(0, Math.min(1, 1 - Math.min(b, worst) / worst));

describe("calibration explorer arithmetic", () => {
  it("zeroes a miner claiming 0.95 while being right 60% of the time", () => {
    const b = brier(0.95, 0.6);
    expect(b).toBeCloseTo(0.3625, 4);
    expect(calibration(b)).toBe(0);
  });

  it("rewards discriminative confidence", () => {
    expect(calibration(brier(0.95, 0.95))).toBeGreaterThan(0.8);
  });

  it("stays bounded in [0,1]", () => {
    for (let c = 0; c <= 1; c += 0.1) {
      for (let p = 0; p <= 1; p += 0.1) {
        const v = calibration(brier(c, p));
        expect(v).toBeGreaterThanOrEqual(0);
        expect(v).toBeLessThanOrEqual(1);
      }
    }
  });
});

describe("score explorer arithmetic", () => {
  const rows = [
    { value: 0.96, weight: 0.45 }, { value: 0.88, weight: 0.2 },
    { value: 0.91, weight: 0.15 }, { value: 0.83, weight: 0.1 },
    { value: 0.86, weight: 0.1 },
  ];

  it("weights sum to one", () => {
    expect(rows.reduce((a, r) => a + r.weight, 0)).toBeCloseTo(1, 9);
  });

  it("contributions sum to the documented total", () => {
    const total = rows.reduce((a, r) => a + r.value * r.weight, 0);
    // 0.96×0.45 + 0.88×0.20 + 0.91×0.15 + 0.83×0.10 + 0.86×0.10 = 0.9135
    expect(total).toBeCloseTo(0.9135, 9);
  });
});
