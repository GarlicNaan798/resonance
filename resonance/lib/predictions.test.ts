import { mkdtemp, rm } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { afterEach, beforeEach, describe, expect, it } from "vitest";

import {
  commitPrediction,
  listPredictions,
  outcomesNeeded,
  recordOutcome,
  trackRecord,
  verifySeal,
  wilson,
  type Prediction,
} from "./predictions";

let dir: string;

beforeEach(async () => {
  dir = await mkdtemp(join(tmpdir(), "resonance-pred-"));
  process.env.RESONANCE_DATA_DIR = dir;
});

afterEach(async () => {
  delete process.env.RESONANCE_DATA_DIR;
  await rm(dir, { recursive: true, force: true });
});

const INPUT = {
  variants: ["Cut your heating bill", "Save 20% this winter"],
  predictedWinner: 0,
  tier: "high" as const,
  margin: 1.2,
  userPick: 1,
};

describe("sealing", () => {
  it("round-trips through the store and verifies", async () => {
    const p = await commitPrediction(INPUT);
    const [stored] = await listPredictions();
    expect(stored.id).toBe(p.id);
    expect(verifySeal(stored)).toBe(true);
  });

  it("survives recording an outcome — the seal predates the result", async () => {
    const p = await commitPrediction(INPUT);
    const resolved = await recordOutcome(p.id, 0);
    expect(resolved.hash).toBe(p.hash);
    expect(verifySeal(resolved)).toBe(true);
  });

  it("detects an edited prediction", async () => {
    const p = await commitPrediction(INPUT);
    expect(verifySeal({ ...p, predictedWinner: 1 })).toBe(false);
    expect(verifySeal({ ...p, variants: ["something", "else"] })).toBe(false);
  });

  it("refuses to overwrite a recorded outcome", async () => {
    const p = await commitPrediction(INPUT);
    await recordOutcome(p.id, 0);
    await expect(recordOutcome(p.id, 1)).rejects.toThrow(/cannot be changed/);
  });

  it("rejects an out-of-range winner", async () => {
    const p = await commitPrediction(INPUT);
    await expect(recordOutcome(p.id, 5)).rejects.toThrow(/valid variant index/);
  });

  it("returns an empty history before anything is written", async () => {
    expect(await listPredictions()).toEqual([]);
  });
});

describe("wilson", () => {
  it("stays inside [0,1] where the normal approximation does not", () => {
    // 7/9 with the textbook interval overshoots 1.0; Wilson must not.
    const [lo, hi] = wilson(7, 9);
    expect(hi).toBeLessThanOrEqual(1);
    expect(lo).toBeGreaterThanOrEqual(0);
    expect(hi).toBeGreaterThan(lo);
  });

  it("is maximally uninformative at n=0", () => {
    expect(wilson(0, 0)).toEqual([0, 1]);
  });

  it("narrows as n grows at a fixed rate", () => {
    const small = wilson(6, 10);
    const large = wilson(600, 1000);
    expect(large[1] - large[0]).toBeLessThan(small[1] - small[0]);
  });
});

describe("outcomesNeeded", () => {
  it("returns null at or below chance — more data never rescues it", () => {
    expect(outcomesNeeded(0.5)).toBeNull();
    expect(outcomesNeeded(0.42)).toBeNull();
  });

  it("needs fewer outcomes for a bigger edge", () => {
    expect(outcomesNeeded(0.8)!).toBeLessThan(outcomesNeeded(0.55)!);
  });
});

function resolved(hits: boolean[], userHits?: boolean[]): Prediction[] {
  return hits.map((hit, i) => ({
    id: String(i),
    createdAt: "2026-01-01T00:00:00.000Z",
    hash: "x",
    variants: ["a", "b"],
    predictedWinner: 0,
    tier: "high" as const,
    margin: 1,
    userPick: userHits ? (userHits[i] ? 0 : 1) : null,
    actualWinner: hit ? 0 : 1,
    resolvedAt: "2026-01-02T00:00:00.000Z",
  }));
}

describe("trackRecord", () => {
  it("says nothing has been measured when nothing has", () => {
    const t = trackRecord([]);
    expect(t.model.n).toBe(0);
    expect(t.verdict).toMatch(/No outcomes recorded/);
  });

  it("counts pending predictions separately from resolved ones", () => {
    const pending: Prediction = { ...resolved([true])[0], actualWinner: null, resolvedAt: null };
    const t = trackRecord([...resolved([true, false]), pending]);
    expect(t.total).toBe(3);
    expect(t.pending).toBe(1);
    expect(t.model.n).toBe(2);
  });

  it("refuses to call a small winning streak a result", () => {
    // Wilson's lower bound at 4/4 is 0.51 and excludes chance on its own. The
    // floor is what stops a one-in-sixteen run being reported as an edge.
    const t = trackRecord(resolved([true, true, true, true]));
    expect(t.model.rate).toBe(1);
    expect(t.model.ci95[0]).toBeGreaterThan(0.5);
    expect(t.model.beatsChance).toBe(false);
    expect(t.model.belowFloor).toBe(true);
    expect(t.verdict).toMatch(/too few to tell a real edge/);
    expect(t.stillNeeded).toBeGreaterThan(0);
  });

  it("does not tell the user the interval includes 50% when it does not", () => {
    const t = trackRecord(resolved([true, true, true, true]));
    expect(t.verdict).not.toMatch(/includes 50%/);
  });

  it("clears chance once there is enough evidence", () => {
    const hits = Array.from({ length: 200 }, (_, i) => i % 10 !== 0); // 90%
    const t = trackRecord(resolved(hits));
    expect(t.model.beatsChance).toBe(true);
    expect(t.stillNeeded).toBeNull();
    expect(t.verdict).toMatch(/better than chance/);
  });

  it("scores the user's blind picks separately from the model's", () => {
    // Model right every time, user right half the time.
    const modelHits = Array.from({ length: 200 }, () => true);
    const userHits = Array.from({ length: 200 }, (_, i) => i % 2 === 0);
    const t = trackRecord(resolved(modelHits, userHits));
    expect(t.model.rate).toBe(1);
    expect(t.user!.rate).toBeCloseTo(0.5, 2);
    expect(t.user!.beatsChance).toBe(false);
  });

  it("has no user scoreboard when no blind picks were recorded", () => {
    expect(trackRecord(resolved([true, false])).user).toBeNull();
  });

  it("does not move the goalposts as results arrive", () => {
    // stillNeeded is derived from the global rate, so a lucky run must not
    // shrink the target — otherwise the bar lowers itself into success.
    const lucky = trackRecord(resolved([true, true, true, true, true]));
    const mixed = trackRecord(resolved([true, false, true, false, true]));
    expect(lucky.stillNeeded).toBe(mixed.stillNeeded);
  });
});
