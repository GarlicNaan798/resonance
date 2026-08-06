/**
 * Feature-extraction parity: TypeScript must match Python exactly.
 *
 * This is the second half of the correctness guarantee. module.test.ts proves
 * the forward pass matches PyTorch given the same features; this proves the
 * features themselves match. Either one drifting produces a product that is
 * confidently wrong with no error surfaced anywhere.
 *
 * The fixtures come from pipeline/export_feature_fixtures.py and deliberately
 * include awkward inputs — empty strings, stopwords only, out-of-vocabulary
 * words, non-ASCII — because those are where two implementations diverge.
 */

import { describe, expect, it } from "vitest";
import fixtures from "./feature_fixtures.json";
import { FEATURE_NAMES, extractFeatures, extractVector, normCoverage } from "./features";

interface Fixture {
  text: string;
  features: Record<string, number>;
}

const data = fixtures as {
  tolerance: number;
  feature_names: string[];
  cases: Fixture[];
};

describe("feature order matches Python", () => {
  it("same names in the same order", () => {
    expect([...FEATURE_NAMES]).toEqual(data.feature_names);
  });

  it("vector length matches the model's expectation", () => {
    expect(extractVector("hello world")).toHaveLength(50);
  });
});

describe("Python parity", () => {
  data.cases.forEach((c, i) => {
    const label = c.text === "" ? "(empty string)" : c.text.slice(0, 42);
    it(`case ${i}: ${label}`, () => {
      const got = extractFeatures(c.text);
      const mismatches: string[] = [];
      for (const name of data.feature_names) {
        const expected = c.features[name];
        const actual = got[name];
        if (!Number.isFinite(actual)) {
          mismatches.push(`${name}: got non-finite ${actual}`);
          continue;
        }
        if (Math.abs(actual - expected) > data.tolerance) {
          mismatches.push(
            `${name}: got ${actual.toFixed(6)}, expected ${expected.toFixed(6)}`,
          );
        }
      }
      expect(mismatches, mismatches.join("\n")).toEqual([]);
    });
  });
});

describe("robustness", () => {
  it("never returns NaN or Infinity, whatever the input", () => {
    const nasty = [
      "", " ", "\n\n", "!!!", "123456", "🙂🙂🙂", "a".repeat(5000),
      "'''\"\"\"", "...", "—–-", "ÄÖÜ", "\t\ttabs\t\t",
    ];
    for (const text of nasty) {
      const v = extractVector(text);
      expect(v).toHaveLength(50);
      for (const x of v) expect(Number.isFinite(x)).toBe(true);
    }
  });

  it("handles stopword-only text without dividing by zero", () => {
    const v = extractVector("the and of to a");
    for (const x of v) expect(Number.isFinite(x)).toBe(true);
  });

  it("reports low coverage for out-of-vocabulary text", () => {
    expect(normCoverage("supercalifragilistic zzzxxxqqq")).toBeLessThan(0.5);
  });

  it("reports high coverage for base-form English", () => {
    expect(normCoverage("happy family dinner music garden")).toBeGreaterThan(0.7);
  });

  it("documents that inflected forms miss the lexicon", () => {
    // Warriner covers ~13,905 mostly base forms. "enjoy" is present; "enjoying"
    // is not. This is a genuine limitation and it is NOT fixed by lemmatising
    // here: the model was trained on unlemmatised lookups, so normalising at
    // inference would feed it inputs it never saw. The right place to address
    // it is a retrain, not a patch in the extractor.
    expect(normCoverage("enjoy")).toBe(1);
    expect(normCoverage("enjoying")).toBe(0);
  });
});

describe("features behave sensibly", () => {
  it("detects exclamation and question marks", () => {
    expect(extractFeatures("Wow! Amazing!").exclaim_count).toBe(2);
    expect(extractFeatures("Really? Sure?").question_count).toBe(2);
  });

  it("scores all-caps as high caps ratio", () => {
    expect(extractFeatures("SHOUTING LOUDLY").caps_ratio).toBeGreaterThan(0.8);
    expect(extractFeatures("quiet speech").caps_ratio).toBe(0);
  });

  it("flags numerals", () => {
    expect(extractFeatures("Save 20% now").has_number).toBe(1);
    expect(extractFeatures("Save money now").has_number).toBe(0);
  });

  it("rates concrete language above abstract language", () => {
    const concrete = extractFeatures("dog table hammer bread").concrete_mean_z;
    const abstract = extractFeatures("justice concept theory essence").concrete_mean_z;
    expect(concrete).toBeGreaterThan(abstract);
  });

  it("rates positive language above negative language", () => {
    const pos = extractFeatures("joy love delight happiness").valence_mean_z;
    const neg = extractFeatures("grief hatred misery despair").valence_mean_z;
    expect(pos).toBeGreaterThan(neg);
  });
});
