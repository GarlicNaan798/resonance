import { describe, expect, it } from "vitest";
import {
  assessDecidability,
  localCeiling,
  requiredImpressions,
  seLogOddsDiff,
} from "./power";

describe("localCeiling", () => {
  it("lands just below the filtered 0.662 at Upworthy's sample size", () => {
    // Median arm: 3,118 impressions at ~1.25% CTR.
    //
    // This returns ~0.629, not the headline 0.662, and that gap is expected
    // rather than an error. The 0.662 is measured on pairs filtered to
    // |gap| >= 0.05, which excludes the hardest near-ties; this function is
    // unconditional. Sanity bound: the unfiltered ceiling must sit BELOW the
    // filtered one, and within a few points of it.
    const c = localCeiling(3118, 0.0125);
    expect(c).toBeLessThan(0.662);
    expect(c).toBeGreaterThan(0.6);
  });

  it("rises with sample size. The point of the exercise", () => {
    const small = localCeiling(3000, 0.0125);
    const big = localCeiling(30000, 0.0125);
    expect(big).toBeGreaterThan(small + 0.1);
    expect(big).toBeGreaterThan(0.75);
  });

  it("stays within (0.5, 1)", () => {
    for (const n of [500, 5000, 1e6]) {
      const c = localCeiling(n, 0.0125);
      expect(c).toBeGreaterThan(0.5);
      expect(c).toBeLessThan(1);
    }
  });

  it("is higher when the true effects are larger", () => {
    expect(localCeiling(3000, 0.0125, 0.4)).toBeGreaterThan(
      localCeiling(3000, 0.0125, 0.098),
    );
  });
});

describe("requiredImpressions", () => {
  it("needs more impressions for smaller differences", () => {
    expect(requiredImpressions(0.1, 0.0125)).toBeGreaterThan(
      requiredImpressions(0.5, 0.0125),
    );
  });

  it("needs more impressions at lower click rates", () => {
    expect(requiredImpressions(0.2, 0.001)).toBeGreaterThan(
      requiredImpressions(0.2, 0.05),
    );
  });

  it("is infinite for a zero difference", () => {
    expect(requiredImpressions(0, 0.0125)).toBe(Infinity);
  });

  it("gives a sane figure for a typical test", () => {
    // ~0.2 log-odds at 1.25% CTR should land in the tens of thousands,
    // several times what Upworthy actually ran.
    const n = requiredImpressions(0.2, 0.0125);
    expect(n).toBeGreaterThan(10_000);
    expect(n).toBeLessThan(100_000);
  });
});

describe("assessDecidability", () => {
  it("calls a large gap decidable", () => {
    const r = assessDecidability(
      { impressions: 5000, clicks: 150 },
      { impressions: 5000, clicks: 50 },
    );
    expect(r.decidable).toBe(true);
    expect(r.shortfall).toBe(0);
  });

  it("tells you how many more impressions a close call needs", () => {
    const r = assessDecidability(
      { impressions: 3000, clicks: 38 },
      { impressions: 3000, clicks: 40 },
    );
    expect(r.decidable).toBe(false);
    expect(r.shortfall).toBeGreaterThan(0);
    expect(r.message).toMatch(/more impressions per arm/);
  });

  it("says no sample size helps when the arms are identical", () => {
    const r = assessDecidability(
      { impressions: 3000, clicks: 40 },
      { impressions: 3000, clicks: 40 },
    );
    expect(r.shortfall).toBe(Infinity);
    expect(r.message).toMatch(/nothing to separate/);
  });

  it("always reports the ceiling, so accuracy is never read against 100%", () => {
    const r = assessDecidability(
      { impressions: 3000, clicks: 38 },
      { impressions: 3000, clicks: 45 },
    );
    expect(r.message).toMatch(/achievable accuracy/);
    expect(r.ceiling).toBeGreaterThan(0.5);
    expect(r.ceiling).toBeLessThan(1);
  });

  it("handles zero clicks without producing NaN", () => {
    const r = assessDecidability(
      { impressions: 1000, clicks: 0 },
      { impressions: 1000, clicks: 5 },
    );
    expect(Number.isFinite(r.ceiling)).toBe(true);
    expect(Number.isFinite(r.observedDelta)).toBe(true);
  });
});

describe("seLogOddsDiff", () => {
  it("shrinks as 1/sqrt(n). The reason more traffic raises the ceiling", () => {
    const a = seLogOddsDiff(1000, 0.0125);
    const b = seLogOddsDiff(4000, 0.0125);
    expect(a / b).toBeCloseTo(2, 1);
  });
});
