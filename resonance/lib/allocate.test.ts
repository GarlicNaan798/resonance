import { describe, expect, it } from "vitest";
import { allocate, shouldStop, type Arm } from "./allocate";

const arm = (impressions: number, clicks: number, priorScore?: number): Arm => ({
  impressions,
  clicks,
  priorScore,
});

describe("allocate", () => {
  it("returns weights summing to 1", () => {
    const w = allocate([arm(1000, 12), arm(1000, 15)]);
    expect(w.reduce((a, b) => a + b, 0)).toBeCloseTo(1, 6);
  });

  it("shifts traffic to the arm winning on real data", () => {
    // 3% vs 1% CTR over 5k impressions is unambiguous.
    const [a, b] = allocate([arm(5000, 150), arm(5000, 50)]);
    expect(a).toBeGreaterThan(0.9);
    expect(b).toBeLessThan(0.1);
  });

  it("splits near-evenly when arms are indistinguishable", () => {
    const [a, b] = allocate([arm(5000, 60), arm(5000, 61)]);
    expect(Math.abs(a - b)).toBeLessThan(0.4);
  });

  it("uses the model prior on a cold start", () => {
    const [a, b] = allocate([arm(0, 0, 2.0), arm(0, 0, -2.0)]);
    expect(a).toBeGreaterThan(b);
  });

  it("lets real data overturn a wrong prior", () => {
    // Model prefers arm 0; the data says otherwise. Data must win.
    const [a, b] = allocate([arm(5000, 50, 2.0), arm(5000, 150, -2.0)]);
    expect(b).toBeGreaterThan(a);
  });

  it("handles edge cases", () => {
    expect(allocate([])).toEqual([]);
    expect(allocate([arm(100, 5)])).toEqual([1]);
    expect(allocate([arm(0, 0), arm(0, 0)]).every(Number.isFinite)).toBe(true);
  });
});

describe("shouldStop", () => {
  it("stops when one arm dominates", () => {
    expect(shouldStop(allocate([arm(5000, 200), arm(5000, 50)]))).toEqual({
      stop: true,
      winner: 0,
    });
  });

  it("keeps running when arms are close", () => {
    expect(shouldStop(allocate([arm(2000, 25), arm(2000, 26)])).stop).toBe(false);
  });
});
