/**
 * Ranker parity: the TypeScript MLP must match PyTorch.
 *
 * Ranking only needs the ORDER of scores, so a rank-agreement test would be
 * enough for the product. Checking absolute values is strictly stronger and
 * catches sign flips, scale errors and layer mis-wiring that a rank check on a
 * handful of cases could easily miss.
 *
 * The encoder itself is not exercised here — it is a downloaded ONNX model, and
 * asserting on its weights would be testing HuggingFace rather than our code.
 * What matters is that our MLP consumes its output correctly.
 */

import { describe, expect, it } from "vitest";
import fixtures from "./ranker_fixtures.json";
import { RANKER_PROVENANCE, scoreEmbedding } from "./ranker";

const data = fixtures as {
  tolerance: number;
  cases: { embedding: number[]; expected_score: number }[];
};

describe("PyTorch parity", () => {
  it("has fixtures", () => {
    expect(data.cases.length).toBeGreaterThan(0);
  });

  data.cases.forEach((c, i) => {
    it(`case ${i} matches within ${data.tolerance}`, () => {
      const got = scoreEmbedding(c.embedding);
      expect(Math.abs(got - c.expected_score)).toBeLessThan(data.tolerance);
    });
  });

  it("preserves the ordering PyTorch produced", () => {
    const mine = data.cases.map((c, i) => ({ i, s: scoreEmbedding(c.embedding) }));
    const theirs = data.cases.map((c, i) => ({ i, s: c.expected_score }));
    const orderOf = (xs: { i: number; s: number }[]) =>
      [...xs].sort((a, b) => b.s - a.s).map((x) => x.i);
    expect(orderOf(mine)).toEqual(orderOf(theirs));
  });
});

describe("input validation", () => {
  it("rejects a wrong-sized embedding rather than producing a number", () => {
    expect(() => scoreEmbedding([1, 2, 3])).toThrow(/384-dim/);
  });

  it("is deterministic", () => {
    const e = data.cases[0].embedding;
    expect(scoreEmbedding(e)).toBe(scoreEmbedding(e));
  });

  it("produces finite scores for extreme inputs", () => {
    const dim = data.cases[0].embedding.length;
    for (const fill of [0, 1, -1, 1e3, -1e3]) {
      expect(Number.isFinite(scoreEmbedding(new Array(dim).fill(fill)))).toBe(true);
    }
  });
});

describe("provenance is honest", () => {
  it("reports the real test accuracy, not the biased validation figure", () => {
    expect(RANKER_PROVENANCE.test_accuracy).toBeCloseTo(0.5942, 4);
    // 0.6241 was the val number and must never be the one surfaced.
    expect(RANKER_PROVENANCE.test_accuracy).toBeLessThan(0.6);
  });

  it("carries the ceiling so accuracy is never read against 100%", () => {
    expect(RANKER_PROVENANCE.oracle_ceiling).toBeCloseTo(0.788, 3);
    expect(RANKER_PROVENANCE.chance).toBe(0.5);
  });

  it("beats the diagnostic module model", () => {
    // The whole reason for the two-layer split: this is the stronger model.
    expect(RANKER_PROVENANCE.test_accuracy).toBeGreaterThan(0.5346);
  });

  it("states that scores carry no absolute meaning", () => {
    expect(RANKER_PROVENANCE.note).toMatch(/no absolute meaning/);
  });
});
