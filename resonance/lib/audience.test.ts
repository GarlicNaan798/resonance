import { describe, expect, it } from "vitest";
import {
  Audience,
  DEFAULT_AUDIENCE,
  audienceDisclosure,
  audienceOffset,
  isDefaultAudience,
  offsetMagnitude,
} from "./audience";

const a = (over: Partial<Audience> = {}): Audience => ({
  ...DEFAULT_AUDIENCE,
  ...over,
});

describe("offsets", () => {
  it("is exactly zero for the default audience", () => {
    const o = audienceOffset(DEFAULT_AUDIENCE);
    expect(o.valence).toBe(0);
    expect(o.arousal).toBe(0);
    expect(o.dominance).toBe(0);
  });

  it("is symmetric between opposing groups", () => {
    const male = audienceOffset(a({ gender: "male" }));
    const female = audienceOffset(a({ gender: "female" }));
    expect(male.arousal).toBeCloseTo(-female.arousal, 10);
    expect(male.valence).toBeCloseTo(-female.valence, 10);
  });

  it("matches the measured gender difference in arousal", () => {
    // Warriner M-F arousal difference is +0.285; half applied per side.
    const male = audienceOffset(a({ gender: "male" }));
    const female = audienceOffset(a({ gender: "female" }));
    expect(male.arousal - female.arousal).toBeCloseTo(0.285, 3);
  });

  it("combines axes additively", () => {
    const both = audienceOffset(a({ gender: "male", age: "younger" }));
    const g = audienceOffset(a({ gender: "male" }));
    const ag = audienceOffset(a({ age: "younger" }));
    expect(both.arousal).toBeCloseTo(g.arousal + ag.arousal, 10);
  });

  it("keeps adjustments small. These are nudges, not personalisation", () => {
    // Even the most extreme selection must stay well under 1 scale point,
    // otherwise the UI would imply a precision the norms do not support.
    const extreme = audienceOffset(
      a({ gender: "male", age: "younger", education: "lower" }),
    );
    expect(Math.abs(extreme.arousal)).toBeLessThan(0.5);
    expect(Math.abs(extreme.valence)).toBeLessThan(0.5);
  });
});

describe("magnitude reporting", () => {
  it("reports sub-threshold selections as imperceptible", () => {
    // Education alone shifts arousal by ~0.07 points = ~0.08 SD.
    expect(offsetMagnitude(a({ education: "higher" })).perceptible).toBe(false);
  });

  it("flags the default audience as no change", () => {
    const m = offsetMagnitude(DEFAULT_AUDIENCE);
    expect(m.valenceSd).toBe(0);
    expect(m.arousalSd).toBe(0);
  });
});

describe("disclosure text", () => {
  it("never claims performance prediction", () => {
    for (const aud of [
      DEFAULT_AUDIENCE,
      a({ gender: "female" }),
      a({ gender: "male", age: "older", education: "higher" }),
    ]) {
      const text = audienceDisclosure(aud).toLowerCase();
      expect(text).not.toContain("will perform");
      expect(text).not.toContain("predicts");
    }
  });

  it("states the descriptive limitation when a segment is chosen", () => {
    const text = audienceDisclosure(a({ gender: "female" }));
    expect(text).toContain("does not predict campaign performance");
  });

  it("warns when the adjustment is below perceptibility", () => {
    expect(audienceDisclosure(a({ education: "higher" }))).toContain("0.2 SD");
  });
});

describe("default detection", () => {
  it("identifies the pooled audience", () => {
    expect(isDefaultAudience(DEFAULT_AUDIENCE)).toBe(true);
    expect(isDefaultAudience(a({ gender: "male" }))).toBe(false);
  });
});
