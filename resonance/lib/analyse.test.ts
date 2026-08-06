import { describe, expect, it } from "vitest";
import { analyse, compareVariants } from "./analyse";
import type { SegmentSpec } from "./segments";

const NEUTRAL: SegmentSpec = {
  gender: "all",
  age: "all",
  education: "all",
  involvement: "unknown",
};

const seg = (over: Partial<SegmentSpec> = {}): SegmentSpec => ({
  ...NEUTRAL,
  ...over,
});

describe("analyse", () => {
  it("returns all six modules with definitions attached", () => {
    const r = analyse("Save 20% on your first order today", NEUTRAL);
    expect(r.modules).toHaveLength(6);
    for (const m of r.modules) {
      expect(m.definition.sources.length).toBeGreaterThan(0);
      expect(m.definition.caveat.length).toBeGreaterThan(10);
      expect(Number.isFinite(m.score)).toBe(true);
    }
  });

  it("rejects empty copy rather than returning a meaningless profile", () => {
    expect(() => analyse("   ", NEUTRAL)).toThrow(/No copy/);
  });

  it("warns on low dictionary coverage", () => {
    const r = analyse("zzxq wgblf mrrpt vnnkd", NEUTRAL);
    expect(r.warnings.join(" ")).toMatch(/rating dictionaries/);
  });

  it("warns on very short copy", () => {
    const r = analyse("Buy now", NEUTRAL);
    expect(r.warnings.join(" ")).toMatch(/very short/);
  });

  it("warns that shouting scored worse in training", () => {
    const r = analyse("BUY NOW BEFORE THIS AMAZING OFFER DISAPPEARS", NEUTRAL);
    expect(r.warnings.join(" ")).toMatch(/WORSE on click-through/);
  });

  it("carries honest provenance, including the ceiling", () => {
    const r = analyse("A clear and simple offer for you", NEUTRAL);
    expect(r.provenance.chance).toBe(0.5);
    expect(r.provenance.ceiling).toBe(0.788);
    // The diagnostic layer must never be presented as the strong model.
    expect(r.provenance.modelAccuracy).toBeLessThan(0.6);
  });

  it("reports no segment adjustment for a neutral audience", () => {
    const r = analyse("Save money on groceries", NEUTRAL);
    expect(r.segment.applied).toBe(false);
    for (const m of r.modules) {
      expect(m.segmentShift).toBeCloseTo(0, 10);
      expect(m.score).toBeCloseTo(m.baseScore, 10);
    }
  });

  it("applies bounded shifts when a segment is chosen", () => {
    const r = analyse("Save money on groceries", seg({ involvement: "low" }));
    expect(r.segment.applied).toBe(true);
    for (const m of r.modules) {
      // Bounded to +/-15% by MAX_GAIN_DELTA.
      expect(Math.abs(m.segmentShift)).toBeLessThanOrEqual(0.15 + 1e-9);
    }
  });

  it("labels segment adjustments as priors, not measurements", () => {
    const r = analyse("Save money", seg({ age: "older" }));
    expect(r.segment.disclosure).toContain("PRIORS");
  });
});

describe("compareVariants", () => {
  const A = "Discover the simple way to cut your energy bill this winter";
  const B = "ENERGY SAVINGS!!! ACT NOW!!! LIMITED TIME!!!";

  it("requires at least two variants", () => {
    expect(() => compareVariants(["only one"], NEUTRAL)).toThrow(/at least two/);
  });

  it("ignores blank variants", () => {
    expect(() => compareVariants([A, "   "], NEUTRAL)).toThrow(/at least two/);
  });

  it("ranks every variant", () => {
    const r = compareVariants([A, B], NEUTRAL);
    expect(r.ranking).toHaveLength(2);
    expect([...r.ranking].sort()).toEqual([0, 1]);
  });

  it("declines to call it when the margin is small", () => {
    // Near-identical copy should not produce a confident recommendation.
    const r = compareVariants([
      "Save money on your energy bill today",
      "Save money on your energy bills today",
    ], NEUTRAL);
    expect(r.confident).toBe(false);
    expect(r.guidance).toMatch(/cannot tell them apart/);
  });

  it("states the accuracy caveat when it does make a call", () => {
    const r = compareVariants([A, B], NEUTRAL);
    if (r.confident) {
      expect(r.guidance).toMatch(/53%/);
      expect(r.guidance).toMatch(/tiebreaker/);
    }
  });

  it("never claims to predict revenue or conversions", () => {
    const r = compareVariants([A, B], NEUTRAL);
    const text = r.guidance.toLowerCase();
    expect(text).not.toContain("conversion");
    expect(text).not.toContain("revenue");
    expect(text).not.toContain("roi");
  });

  it("is deterministic", () => {
    const one = compareVariants([A, B], NEUTRAL);
    const two = compareVariants([A, B], NEUTRAL);
    expect(one.ranking).toEqual(two.ranking);
    expect(one.margin).toBeCloseTo(two.margin, 12);
  });
});
