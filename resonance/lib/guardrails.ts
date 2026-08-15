/**
 * Surface guardrails: correcting for what the ranker cannot see.
 *
 * WHY THIS EXISTS
 * ---------------
 * The ranker embeds copy with all-MiniLM-L6-v2, which is UNCASED. Verified
 * directly (scripts/check-encoder-blindness.mjs):
 *
 *     "URGENT SLASH YOUR BILLS TODAY" vs "urgent slash your bills today"
 *      -> cosine 1.000000, identical vectors
 *
 * So the ranker is structurally blind to capitalisation and only partly
 * sensitive to punctuation (cosine 0.83 for "!!!"). It cannot down-rank
 * shouting because it cannot perceive shouting. Left alone, it will happily
 * recommend "URGENT!!! SLASH YOUR BILLS!!!" purely on word choice.
 *
 * Meanwhile we have direct evidence from the SAME 32,487 randomised
 * experiments that exclamation marks hurt: `exclaim_count`, negated, reached
 * 0.5698 pairwise accuracy. The strongest single feature found in the whole
 * project, and stronger than the constrained module model.
 *
 * This module applies that evidence where the ranker is blind. It is not a
 * patch over a model we distrust; it routes a decision to the layer that holds
 * the relevant measurement.
 *
 * WHAT IT DELIBERATELY DOES NOT DO
 * --------------------------------
 * It does not silently reorder the ranking. Overriding a model's output
 * invisibly is how a system becomes impossible to reason about. It raises a
 * flag with its evidence attached, and the UI shows it beside the
 * recommendation.
 */

import { extractFeatures } from "./inference/features";

export type RiskKind = "shouting" | "exclamation" | "punctuation";

export interface SurfaceRisk {
  kind: RiskKind;
  /** 0-1. Higher is more concerning. */
  severity: number;
  message: string;
  evidence: string;
}

export interface GuardrailReport {
  risks: SurfaceRisk[];
  /** Highest severity across risks. */
  maxSeverity: number;
  /**
   * True when the ranker's judgement on this copy should be treated with
   * caution, because the deciding features are ones it cannot see.
   */
  rankerBlind: boolean;
}

/** Above this share of capital letters, copy reads as shouting. */
const CAPS_THRESHOLD = 0.3;
/**
 * Exclamation marks per 100 characters, AND a minimum count.
 *
 * Density alone gives false positives: one exclamation mark in a 60-character
 * headline already exceeds any useful density threshold, and a single "!" is
 * ordinary punctuation rather than shouting. Requiring at least two keeps the
 * guardrail on the behaviour the evidence is actually about, repeated
 * exclamation, and off normal copy. A guardrail that fires on ordinary
 * sentences gets switched off, which helps nobody.
 */
const EXCLAIM_DENSITY = 1.5;
const EXCLAIM_MIN_COUNT = 2;

export function checkSurface(text: string): GuardrailReport {
  const f = extractFeatures(text);
  const risks: SurfaceRisk[] = [];

  const chars = Math.max(f.n_chars, 1);

  if (f.caps_ratio > CAPS_THRESHOLD && f.n_words >= 3) {
    risks.push({
      kind: "shouting",
      severity: Math.min(1, (f.caps_ratio - CAPS_THRESHOLD) / (1 - CAPS_THRESHOLD)),
      message:
        `${Math.round(f.caps_ratio * 100)}% of characters are capitals. The ` +
        "ranking model cannot see capitalisation at all. Its encoder is " +
        "uncased, so its recommendation does not account for this.",
      evidence:
        "Verified: uppercase and lowercase copy produce identical embeddings " +
        "(cosine 1.000000).",
    });
  }

  const exclaimDensity = (f.exclaim_count / chars) * 100;
  if (f.exclaim_count >= EXCLAIM_MIN_COUNT && exclaimDensity > EXCLAIM_DENSITY) {
    risks.push({
      kind: "exclamation",
      severity: Math.min(1, exclaimDensity / (EXCLAIM_DENSITY * 4)),
      message:
        `${f.exclaim_count} exclamation marks. In the training data, fewer ` +
        "exclamation marks predicted higher click-through.",
      evidence:
        "Strongest single feature in this project: exclamation count, negated, " +
        "reached 0.5698 pairwise accuracy on held-out experiments, better " +
        "than the behavioural model's 0.5346.",
    });
  }

  if (f.punct_density > 0.18 && f.n_words >= 3) {
    risks.push({
      kind: "punctuation",
      severity: Math.min(1, (f.punct_density - 0.18) / 0.2),
      message:
        "Unusually dense punctuation, which the encoder represents only weakly.",
      evidence: "Cosine similarity 0.83 between copy with and without '!!!'.",
    });
  }

  const maxSeverity = risks.reduce((m, r) => Math.max(m, r.severity), 0);
  return { risks, maxSeverity, rankerBlind: risks.some((r) => r.kind === "shouting") };
}

export interface GuardedRanking<T> {
  item: T;
  guardrail: GuardrailReport;
}

/**
 * Attach guardrail reports to a ranking and produce an honest caution when the
 * top-ranked item is the riskiest one.
 *
 * The ordering is left untouched. The caller is told what the model could not
 * see and decides for themselves, which is the correct division of labour when
 * the model is right 59% of the time.
 */
export function guardRanking<T extends { text: string }>(
  ranked: T[],
): { guarded: GuardedRanking<T>[]; caution: string | null } {
  const guarded = ranked.map((item) => ({
    item,
    guardrail: checkSurface(item.text),
  }));

  if (guarded.length === 0) return { guarded, caution: null };

  const top = guarded[0];
  const rest = guarded.slice(1);
  const topIsRiskiest =
    top.guardrail.maxSeverity > 0 &&
    rest.every((g) => g.guardrail.maxSeverity < top.guardrail.maxSeverity);

  if (!topIsRiskiest) return { guarded, caution: null };

  const kinds = [...new Set(top.guardrail.risks.map((r) => r.kind))];
  return {
    guarded,
    caution:
      `The top-ranked variant carries the most surface risk (${kinds.join(", ")}) ` +
      "of those compared, and these are properties the ranking model cannot " +
      "fully see. Treat the recommendation with caution, or test it against a " +
      "calmer variant.",
  };
}
