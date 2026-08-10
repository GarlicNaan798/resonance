/**
 * The embedding ranker — the strong model.
 *
 * 0.6176 on held-out test versus 0.5346 for the diagnostic module model, against
 * a measured ceiling of 0.662. This is what /compare uses.
 *
 * Two pieces:
 *   1. MiniLM sentence embeddings via transformers.js (ONNX, runs in Node).
 *   2. A small MLP over those embeddings, ported from PyTorch.
 *
 * The model is loaded once and cached for the process lifetime. First call pays
 * the load cost; subsequent calls are fast.
 *
 * SELF-HOSTING: the encoder must be present locally. `allowRemoteModels` is
 * disabled when RESONANCE_MODE=self-hosted so a deployment that promises no
 * egress cannot silently reach out to huggingface.co on a cache miss — it fails
 * loudly instead, which is the correct behaviour for a claim a customer can
 * verify with `--network none`.
 */

import rankerWeights from "./ranker.json";

interface Layer {
  w: number[][];
  b: number[];
  act: "relu" | "none";
}

interface Member {
  /** Output mean/sd over the fit set, for scale-matching before averaging. */
  mean: number;
  sd: number;
  layers: Layer[];
}

interface RankerFile {
  format_version: number;
  embedding_dim: number;
  embedding_model: string;
  normalize_embeddings: boolean;
  members: Member[];
  provenance: {
    test_accuracy: number;
    test_ci95: [number, number];
    chance: number;
    oracle_ceiling: number;
    trained_on: string;
    note: string;
    ceiling_note?: string;
  };
}

const RANKER = rankerWeights as unknown as RankerFile;

export const RANKER_PROVENANCE = RANKER.provenance;

// ---------------------------------------------------------------- MLP

function forward(x: number[], layers: Layer[]): number {
  let h = x;
  for (const layer of layers) {
    const out = new Array<number>(layer.w.length);
    for (let o = 0; o < layer.w.length; o++) {
      const row = layer.w[o];
      let sum = layer.b[o];
      for (let i = 0; i < row.length; i++) sum += row[i] * h[i];
      out[o] = layer.act === "relu" ? Math.max(0, sum) : sum;
    }
    h = out;
  }
  return h[0];
}

/**
 * Score a pre-computed embedding with the ensemble.
 *
 * Each member is normalised by its own fit-set mean/sd before averaging.
 * Normalising within the request instead would flatten every member to the same
 * spread — with two variants each would emit exactly +/-0.707 — reducing the
 * ensemble to a majority vote and discarding the margin the abstention tiers
 * depend on.
 */
export function scoreEmbedding(embedding: number[]): number {
  if (embedding.length !== RANKER.embedding_dim) {
    throw new Error(
      `Expected ${RANKER.embedding_dim}-dim embedding, got ${embedding.length}.`,
    );
  }
  let sum = 0;
  for (const m of RANKER.members) {
    sum += (forward(embedding, m.layers) - m.mean) / m.sd;
  }
  return sum / RANKER.members.length;
}

// ---------------------------------------------------------------- encoder

type FeatureExtractor = (
  texts: string[],
  opts: { pooling: "mean"; normalize: boolean },
) => Promise<{ tolist(): number[][] }>;

let encoderPromise: Promise<FeatureExtractor> | null = null;

async function getEncoder(): Promise<FeatureExtractor> {
  if (!encoderPromise) {
    encoderPromise = (async () => {
      const mod = await import("@huggingface/transformers");
      const { pipeline, env } = mod as unknown as {
        pipeline: (task: string, model: string, opts?: object) => Promise<FeatureExtractor>;
        env: { allowRemoteModels: boolean; allowLocalModels: boolean };
      };

      if (process.env.RESONANCE_MODE === "self-hosted") {
        // Fail loudly rather than quietly making an outbound call.
        env.allowRemoteModels = false;
        env.allowLocalModels = true;
      }

      return pipeline("feature-extraction", RANKER.embedding_model, {
        dtype: "fp32",
      });
    })();
  }
  return encoderPromise;
}

/** Embed texts with the same encoder and pooling used in training. */
export async function embed(texts: string[]): Promise<number[][]> {
  const extractor = await getEncoder();
  const output = await extractor(texts, {
    pooling: "mean",
    normalize: RANKER.normalize_embeddings,
  });
  return output.tolist();
}

export interface RankedVariant {
  index: number;
  text: string;
  score: number;
}

export interface RankingResult {
  ranked: RankedVariant[];
  /** Score gap between first and second. */
  margin: number;
  confident: boolean;
  /** Calibrated tier for this specific comparison. */
  tier: ConfidenceTier;
  /**
   * Accuracy measured for comparisons at this confidence level — not the
   * headline average. This is the number that actually applies here.
   */
  tierAccuracy: number;
  /** Share of comparisons that reach this tier. */
  tierCoverage: number;
  guidance: string;
  /** Overall always-answer accuracy, for context. */
  accuracy: number;
  ci95: [number, number];
  ceiling: number;
}

/**
 * Calibrated confidence tiers, measured in model/recalibrate_tiers.py.
 *
 * The headline accuracy is an average that hides real structure: the model is
 * markedly more reliable when the two variants are far apart in score. Sweeping
 * a margin threshold over dev pairs gives:
 *
 *     coverage  accuracy   margin
 *       100%     0.6289     0.000
 *        50%     0.6951     0.519
 *        25%     0.7602     0.948
 *        10%     0.8020     1.421
 *
 * So instead of answering every comparison at 63%, the product answers the
 * confident quarter at 76% and says "we cannot tell" on the rest. That is more
 * useful to a marketer, and it is what makes an 80% figure quotable — always
 * with its coverage attached.
 *
 * RECALIBRATED for the ensemble. The previous thresholds (2.160 / 1.203) were
 * fitted to a single model's RAW score differences; the ensemble emits an
 * average of per-member z-scores, a different scale entirely. Reusing them
 * would have mislabelled confidence silently rather than failing visibly.
 *
 * (An accuracy above the 66.2% global ceiling is not a contradiction: the
 * ceiling was measured across ALL pairs, and confident pairs correlate with
 * larger true differences, which carry a higher ceiling of their own.)
 */
export type ConfidenceTier = "high" | "moderate" | "insufficient";

interface TierSpec {
  tier: ConfidenceTier;
  minMargin: number;
  accuracy: number;
  coverage: number;
}

export const TIERS: TierSpec[] = [
  { tier: "high", minMargin: 0.948, accuracy: 0.7602, coverage: 0.25 },
  { tier: "moderate", minMargin: 0.519, accuracy: 0.6951, coverage: 0.5 },
];

function classify(margin: number): TierSpec | null {
  for (const t of TIERS) if (margin >= t.minMargin) return t;
  return null;
}

export async function rankVariants(texts: string[]): Promise<RankingResult> {
  if (texts.length < 2) throw new Error("Supply at least two variants.");

  const embeddings = await embed(texts);
  const ranked: RankedVariant[] = embeddings
    .map((e, i) => ({ index: i, text: texts[i], score: scoreEmbedding(e) }))
    .sort((a, b) => b.score - a.score);

  const margin = ranked[0].score - ranked[1].score;
  const spec = classify(margin);
  const confident = spec !== null;

  const guidance = spec
    ? `Variant ${ranked[0].index + 1} is the stronger candidate. On comparisons ` +
      `this clear-cut the model is right ${(spec.accuracy * 100).toFixed(0)}% of ` +
      `the time — measured, not estimated. Roughly ${(spec.coverage * 100).toFixed(0)}% ` +
      "of comparisons reach this confidence level."
    : "These variants score too closely to separate. At margins this small the " +
      "model is near chance, so the honest answer is that we cannot tell them " +
      "apart — pick on other grounds, or run a live test.";

  return {
    ranked,
    margin,
    confident,
    tier: spec?.tier ?? "insufficient",
    // Below the tiers, the applicable accuracy is the always-answer figure.
    tierAccuracy: spec?.accuracy ?? RANKER.provenance.test_accuracy,
    tierCoverage: spec?.coverage ?? 1,
    guidance,
    accuracy: RANKER.provenance.test_accuracy,
    ci95: RANKER.provenance.test_ci95,
    ceiling: RANKER.provenance.oracle_ceiling,
  };
}
