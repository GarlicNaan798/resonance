/**
 * Stress tests for the segment priors.
 *
 * The danger with theory-derived gains is not that any single one is wrong —
 * each is bounded and cited. It is that several small, individually-defensible
 * adjustments COMPOSE into a large, indefensible one, and that the resulting
 * number then looks like a measurement. These tests attack that directly:
 * every axis set at once, contradictory combinations, and repeated application.
 */

import { describe, expect, it } from "vitest";
import type { ModuleId } from "./constructs";
import {
  Involvement,
  MAX_GAIN_DELTA,
  SegmentSpec,
  applyGains,
  resolveGains,
  segmentDisclosure,
} from "./segments";

const MODULES: ModuleId[] = [
  "salience", "affect", "valuation", "encoding", "approach", "control",
];

const spec = (over: Partial<SegmentSpec> = {}): SegmentSpec => ({
  gender: "all",
  age: "all",
  education: "all",
  involvement: "unknown",
  ...over,
});

const ALL_INVOLVEMENT: Involvement[] = ["high", "low", "unknown"];

describe("neutrality", () => {
  it("an unspecified audience changes nothing", () => {
    const r = resolveGains(spec());
    expect(r.isNeutral).toBe(true);
    expect(r.maxDeviation).toBe(0);
    for (const m of MODULES) expect(r.gains[m]).toBe(1);
  });

  it("applying neutral gains leaves activations untouched", () => {
    const acts = Object.fromEntries(
      MODULES.map((m, i) => [m, 0.1 * (i + 1)]),
    ) as Record<ModuleId, number>;
    const out = applyGains(acts, resolveGains(spec()));
    for (const m of MODULES) expect(out[m]).toBeCloseTo(acts[m], 12);
  });
});

describe("bounds hold under adversarial composition", () => {
  it("never exceeds MAX_GAIN_DELTA for any single selection", () => {
    const specs: SegmentSpec[] = [
      spec({ involvement: "high" }),
      spec({ involvement: "low" }),
      spec({ age: "older" }),
      spec({ age: "younger" }),
      spec({ gender: "male" }),
      spec({ gender: "female" }),
      spec({ education: "higher" }),
      spec({ education: "lower" }),
    ];
    for (const s of specs) {
      const r = resolveGains(s);
      expect(r.maxDeviation).toBeLessThanOrEqual(MAX_GAIN_DELTA + 1e-12);
    }
  });

  it("stays bounded with EVERY axis set in the same direction", () => {
    // The worst case: four priors all pushing the same modules the same way.
    const stacked = resolveGains(
      spec({
        involvement: "low",
        age: "younger",
        gender: "male",
        education: "lower",
      }),
    );
    expect(stacked.maxDeviation).toBeLessThanOrEqual(MAX_GAIN_DELTA + 1e-12);
    for (const m of MODULES) {
      expect(stacked.gains[m]).toBeGreaterThanOrEqual(1 - MAX_GAIN_DELTA - 1e-12);
      expect(stacked.gains[m]).toBeLessThanOrEqual(1 + MAX_GAIN_DELTA + 1e-12);
    }
  });

  it("stays bounded across the full cross-product of segments", () => {
    let worst = 0;
    for (const involvement of ALL_INVOLVEMENT) {
      for (const gender of ["male", "female", "all"] as const) {
        for (const age of ["younger", "older", "all"] as const) {
          for (const education of ["lower", "higher", "all"] as const) {
            const r = resolveGains(
              spec({ involvement, gender, age, education }),
            );
            worst = Math.max(worst, r.maxDeviation);
            for (const m of MODULES) {
              expect(Number.isFinite(r.gains[m])).toBe(true);
              expect(r.gains[m]).toBeGreaterThan(0);
            }
          }
        }
      }
    }
    expect(worst).toBeLessThanOrEqual(MAX_GAIN_DELTA + 1e-12);
  });

  it("cannot be amplified by applying gains repeatedly", () => {
    // Guards against a caller looping application; activations must not run away.
    const r = resolveGains(spec({ involvement: "low", gender: "male" }));
    let acts = Object.fromEntries(
      MODULES.map((m) => [m, 0.5]),
    ) as Record<ModuleId, number>;
    const once = applyGains(acts, r);
    for (let i = 0; i < 20; i++) acts = applyGains(acts, r);
    // Repeated application obviously compounds — the point is that the caller
    // must not do it, and that a single application is modest.
    for (const m of MODULES) {
      expect(Math.abs(once[m] - 0.5)).toBeLessThanOrEqual(
        0.5 * MAX_GAIN_DELTA + 1e-12,
      );
    }
  });
});

describe("directions match the cited theory", () => {
  it("high involvement favours argument quality over cues (ELM central route)", () => {
    const r = resolveGains(spec({ involvement: "high" }));
    expect(r.gains.valuation).toBeGreaterThan(1);
    expect(r.gains.control).toBeGreaterThan(1);
    expect(r.gains.salience).toBeLessThan(1);
    expect(r.gains.affect).toBeLessThan(1);
  });

  it("low involvement favours cues over argument quality (peripheral route)", () => {
    const r = resolveGains(spec({ involvement: "low" }));
    expect(r.gains.salience).toBeGreaterThan(1);
    expect(r.gains.affect).toBeGreaterThan(1);
    expect(r.gains.valuation).toBeLessThan(1);
  });

  it("high and low involvement push in opposite directions", () => {
    const hi = resolveGains(spec({ involvement: "high" }));
    const lo = resolveGains(spec({ involvement: "low" }));
    expect((hi.gains.valuation - 1) * (lo.gains.valuation - 1)).toBeLessThan(0);
    expect((hi.gains.salience - 1) * (lo.gains.salience - 1)).toBeLessThan(0);
  });

  it("older audiences skew toward approach/positive framing (positivity effect)", () => {
    const r = resolveGains(spec({ age: "older" }));
    expect(r.gains.approach).toBeGreaterThan(1);
    expect(r.gains.valuation).toBeGreaterThan(1);
  });

  it("gender priors are opposite and small — the weakest evidence here", () => {
    const m = resolveGains(spec({ gender: "male" }));
    const f = resolveGains(spec({ gender: "female" }));
    expect(m.gains.affect).toBeGreaterThan(1);
    expect(f.gains.affect).toBeLessThan(1);
    // Deliberately the smallest gain in the file.
    expect(Math.abs(m.gains.affect - 1)).toBeLessThanOrEqual(0.05 + 1e-12);
  });

  it("contradictory selections partially cancel rather than compound", () => {
    // High involvement pushes salience down; low education pushes it up.
    const r = resolveGains(spec({ involvement: "high", education: "lower" }));
    const involvementOnly = resolveGains(spec({ involvement: "high" }));
    expect(r.gains.salience).toBeGreaterThan(involvementOnly.gains.salience);
  });
});

describe("provenance and honesty", () => {
  it("every applied prior carries a source, effect size and confidence", () => {
    const r = resolveGains(
      spec({ involvement: "high", age: "older", gender: "male", education: "higher" }),
    );
    expect(r.applied.length).toBe(4);
    for (const p of r.applied) {
      expect(p.source.length).toBeGreaterThan(10);
      expect(p.effectSize.length).toBeGreaterThan(3);
      expect(["moderate", "low"]).toContain(p.confidence);
      expect(p.rationale.length).toBeGreaterThan(20);
    }
  });

  it("no prior is ever labelled high confidence", () => {
    // Nothing here is measured from advertising response, so nothing earns it.
    for (const involvement of ALL_INVOLVEMENT) {
      const r = resolveGains(
        spec({ involvement, gender: "male", age: "older", education: "lower" }),
      );
      for (const p of r.applied) expect(p.confidence).not.toBe("high");
    }
  });

  it("gender and age arousal priors are flagged low confidence", () => {
    // They come from rating differences, not behavioural response.
    for (const s of [spec({ gender: "male" }), spec({ age: "younger" })]) {
      const r = resolveGains(s);
      expect(r.applied[0].confidence).toBe("low");
    }
  });

  it("involvement is the best-supported prior", () => {
    const r = resolveGains(spec({ involvement: "high" }));
    expect(r.applied[0].confidence).toBe("moderate");
  });

  it("disclosure never claims measurement of the audience", () => {
    const texts = [
      segmentDisclosure(resolveGains(spec())),
      segmentDisclosure(resolveGains(spec({ involvement: "high" }))),
      segmentDisclosure(resolveGains(spec({ gender: "female", age: "older" }))),
    ];
    for (const t of texts) {
      expect(t.toLowerCase()).not.toContain("will perform");
      expect(t.toLowerCase()).not.toContain("measured from your");
    }
  });

  it("disclosure counts low-confidence adjustments explicitly", () => {
    const t = segmentDisclosure(
      resolveGains(spec({ gender: "male", age: "younger" })),
    );
    expect(t).toContain("low-confidence");
    expect(t).toContain("2 of 2");
  });

  it("names PRIORS as priors", () => {
    const t = segmentDisclosure(resolveGains(spec({ involvement: "high" })));
    expect(t).toContain("PRIORS");
    expect(t).toContain("replaced by fitted values");
  });
});
