/**
 * Parity test: the TypeScript port must agree with PyTorch.
 *
 * This is the most important test in the inference layer. A hand-ported forward
 * pass that is subtly wrong produces plausible-looking numbers forever, no
 * crash, no error, just a product that quietly reports the wrong thing. The
 * fixtures in parity_cases.json are real feature vectors with outputs generated
 * by model/export_weights.py straight from the trained PyTorch model.
 *
 * If this fails after a model retrain, regenerate the fixtures. Do not relax
 * the tolerance.
 */

import { describe, expect, it } from "vitest";
import parity from "./parity_cases.json";
import { arousalOptimum, FEATURE_NAMES, infer, standardise } from "./module";

interface ParityCase {
  features_standardised: number[];
  expected: {
    score: number;
    modules: Record<string, number>;
  };
}

const fixtures = parity as { tolerance: number; cases: ParityCase[] };

describe("PyTorch parity", () => {
  it("has fixtures to check against", () => {
    expect(fixtures.cases.length).toBeGreaterThan(0);
  });

  fixtures.cases.forEach((c, i) => {
    it(`case ${i}: score matches PyTorch within ${fixtures.tolerance}`, () => {
      const got = infer(c.features_standardised);
      expect(Math.abs(got.score - c.expected.score)).toBeLessThan(
        fixtures.tolerance,
      );
    });

    it(`case ${i}: every module activation matches`, () => {
      const got = infer(c.features_standardised);
      for (const [id, expected] of Object.entries(c.expected.modules)) {
        const actual = (got.modules as unknown as Record<string, number>)[id];
        expect(
          Math.abs(actual - expected),
          `module ${id}: got ${actual}, expected ${expected}`,
        ).toBeLessThan(fixtures.tolerance);
      }
    });
  });
});

describe("research constraints survive the port", () => {
  // If a sign flipped during porting, the model would claim (for example) that
  // more cognitive load helps. These assert the documented directions hold.
  const sample = fixtures.cases[0].features_standardised;

  it("arousal optimum is interior, not at a boundary", () => {
    const opt = arousalOptimum();
    expect(opt).toBeGreaterThanOrEqual(0);
    expect(opt).toBeLessThanOrEqual(1);
  });

  it("module activations are in their expected ranges", () => {
    const { modulesRaw } = infer(sample);
    for (const id of ["salience", "affect", "valuation", "encoding", "control"] as const) {
      expect(modulesRaw[id]).toBeGreaterThanOrEqual(0);
      expect(modulesRaw[id]).toBeLessThanOrEqual(1);
    }
    // approach is signed
    expect(modulesRaw.approach).toBeGreaterThanOrEqual(-1);
    expect(modulesRaw.approach).toBeLessThanOrEqual(1);
  });

  it("arousal gating raises encoding above its raw value", () => {
    // C2: encoding is multiplied by (1 + gate * affect), gate >= 0, affect >= 0.
    const { modules, modulesRaw } = infer(sample);
    expect(modules.encoding).toBeGreaterThanOrEqual(modulesRaw.encoding - 1e-9);
  });

  it("salience gating reduces valuation from its raw value", () => {
    // C3: valuation is multiplied by a sigmoid gate in (0, 1).
    const { modules, modulesRaw } = infer(sample);
    expect(modules.valuation).toBeLessThanOrEqual(modulesRaw.valuation + 1e-9);
  });
});

describe("input validation", () => {
  it("rejects a feature vector of the wrong length", () => {
    expect(() => standardise([1, 2, 3])).toThrow(/out of sync/);
  });

  it("exposes the feature order the extractor must produce", () => {
    expect(FEATURE_NAMES.length).toBe(
      fixtures.cases[0].features_standardised.length,
    );
  });

  it("rejects an unknown audience index", () => {
    expect(() => infer(fixtures.cases[0].features_standardised, 999)).toThrow(
      /Unknown audience/,
    );
  });
});
