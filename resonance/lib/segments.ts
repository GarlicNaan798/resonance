/**
 * Theory-derived segment priors: making the six modules respond to audience.
 *
 * THE PROBLEM THIS SOLVES
 * -----------------------
 * The founding premise is telling a company how a campaign lands with THEIR
 * demographic. But no dataset in this project links copy to outcome by
 * demographic — Upworthy recorded what ran and how it did, never who saw it —
 * so the model's audience gains were never fitted and sit at zero. Without
 * something here, the audience selector is a control that does nothing.
 *
 * These are PRIORS derived from published findings, not parameters learned from
 * data. They are replaced by fitted values per tenant as soon as a client
 * uploads segment-split campaign results (which Meta and Google already provide
 * broken down by age bracket and gender).
 *
 * TWO SCIENTIFIC CORRECTIONS THAT SHAPED THIS FILE
 * ------------------------------------------------
 * 1. ELM is NOT moderated by demographics. Petty & Cacioppo's moderators are
 *    *involvement* and *need for cognition*. The common shortcut of
 *    "higher education -> central route" is unsupported: need for cognition
 *    correlates with education at only r ~ 0.2-0.3. So involvement is a
 *    first-class input the marketer supplies directly — they know whether they
 *    sell cars or chewing gum — and education contributes only a small,
 *    explicitly low-confidence NFC adjustment.
 *
 * 2. A rating difference is not a response difference. Warriner shows men rate
 *    words +0.285 higher on arousal than women. That is a fact about *ratings*,
 *    not evidence that men respond differently to advertising. Treating one as
 *    the other is precisely the inferential leap this project exists to avoid,
 *    so gender and age arousal priors carry LOW confidence and small gains.
 *
 * WHAT IS NOT CLAIMED
 * -------------------
 * Nothing here asserts demographic differences in neural activity. Evidence for
 * behavioural differences is modest; evidence for corresponding neural
 * differences is weaker still. Module names remain functional labels.
 */

import type { ModuleId } from "./constructs";
import type { Audience } from "./audience";

/** How strongly a prior is supported. Surfaced in the UI. */
export type Confidence = "moderate" | "low";

export interface SegmentPrior {
  /** Multiplicative gain per module. 1.0 = no change. */
  gains: Partial<Record<ModuleId, number>>;
  source: string;
  effectSize: string;
  confidence: Confidence;
  rationale: string;
}

/**
 * Purchase involvement — the actual ELM moderator, supplied by the marketer.
 * High: considered, high-cost, high-risk (cars, software, insurance).
 * Low: habitual, low-cost, low-risk (snacks, toiletries).
 */
export type Involvement = "high" | "low" | "unknown";

/**
 * Gains are bounded to +/- this fraction. Published effect sizes here are
 * d ~ 0.2-0.35 — small. A prior that swung scores by 50% would imply a
 * precision the literature does not support.
 */
export const MAX_GAIN_DELTA = 0.15;

function clampGain(g: number): number {
  return Math.min(1 + MAX_GAIN_DELTA, Math.max(1 - MAX_GAIN_DELTA, g));
}

/**
 * ELM (Petty & Cacioppo, 1986). Central route: recipients elaborate on argument
 * quality, so substance-carrying modules matter more. Peripheral route:
 * recipients lean on cues, so attention-grabbing and affective modules matter
 * more. This is the best-supported prior in the file, because involvement is
 * ELM's genuine moderator rather than a demographic stand-in.
 */
const INVOLVEMENT_PRIORS: Record<Exclude<Involvement, "unknown">, SegmentPrior> = {
  high: {
    gains: { valuation: 1.12, control: 1.10, salience: 0.94, affect: 0.94 },
    source: "Petty & Cacioppo (1986), Elaboration Likelihood Model",
    effectSize: "route shift; moderator effects typically d = 0.3-0.5",
    confidence: "moderate",
    rationale:
      "High-involvement purchases are processed via the central route: " +
      "argument quality and clarity dominate, peripheral cues matter less.",
  },
  low: {
    gains: { salience: 1.12, affect: 1.10, valuation: 0.94, control: 0.96 },
    source: "Petty & Cacioppo (1986), Elaboration Likelihood Model",
    effectSize: "route shift; moderator effects typically d = 0.3-0.5",
    confidence: "moderate",
    rationale:
      "Low-involvement purchases are processed via the peripheral route: " +
      "attention capture and affect dominate over argument quality.",
  },
};

/**
 * Positivity effect (Carstensen & Mikels, 2005; meta-analysis Reed, Chan &
 * Mikels, 2014). Older adults preferentially attend to and recall positive over
 * negative material. Modest (d ~ 0.25) and attenuated under cognitive load, so
 * the gain is small.
 */
const AGE_PRIORS: Record<"younger" | "older", SegmentPrior> = {
  older: {
    gains: { approach: 1.10, valuation: 1.06, affect: 0.95 },
    source: "Carstensen & Mikels (2005); Reed, Chan & Mikels (2014) meta-analysis",
    effectSize: "d ~ 0.25 for the age x valence interaction",
    confidence: "moderate",
    rationale:
      "Older adults show a positivity bias in attention and memory, favouring " +
      "positively-framed, approach-oriented messaging.",
  },
  younger: {
    // Warriner arousal difference (+0.182, d = 0.20) — a RATING difference,
    // hence low confidence and a small gain.
    gains: { affect: 1.06, salience: 1.04 },
    source: "Warriner et al. (2013), measured in pipeline/audience_analysis.py",
    effectSize: "+0.182 arousal points, d = 0.20",
    confidence: "low",
    rationale:
      "Younger raters assign higher arousal to the same words. This is a " +
      "rating difference, not a demonstrated behavioural difference.",
  },
};

/**
 * Gender. Warriner: men rate words +0.285 higher on arousal (d = 0.32). Again a
 * rating difference. Deliberately the weakest prior here — gender is also the
 * axis where an over-confident model does the most social harm, so the gain is
 * kept minimal and the confidence flag is explicit.
 */
const GENDER_PRIORS: Record<"male" | "female", SegmentPrior> = {
  male: {
    gains: { affect: 1.05 },
    source: "Warriner et al. (2013), measured in pipeline/audience_analysis.py",
    effectSize: "+0.285 arousal points, d = 0.32",
    confidence: "low",
    rationale:
      "Male raters assign higher arousal to the same words. A rating " +
      "difference only; no behavioural claim is made.",
  },
  female: {
    gains: { affect: 0.95 },
    source: "Warriner et al. (2013), measured in pipeline/audience_analysis.py",
    effectSize: "-0.285 arousal points, d = 0.32",
    confidence: "low",
    rationale:
      "Female raters assign lower arousal to the same words. A rating " +
      "difference only; no behavioural claim is made.",
  },
};

/**
 * Education as a weak need-for-cognition proxy. NFC correlates with education
 * at only r ~ 0.2-0.3, so this gain is deliberately tiny — included for
 * completeness, not because it carries much weight.
 */
const EDUCATION_PRIORS: Record<"lower" | "higher", SegmentPrior> = {
  higher: {
    gains: { control: 1.04, valuation: 1.03 },
    source: "Cacioppo & Petty (1982), Need for Cognition; ELM moderator",
    effectSize: "NFC-education correlation r ~ 0.2-0.3 (weak proxy)",
    confidence: "low",
    rationale:
      "Higher education is a weak proxy for need for cognition, which shifts " +
      "processing toward the central route. Use involvement instead where known.",
  },
  lower: {
    gains: { salience: 1.04, affect: 1.03 },
    source: "Cacioppo & Petty (1982), Need for Cognition; ELM moderator",
    effectSize: "NFC-education correlation r ~ 0.2-0.3 (weak proxy)",
    confidence: "low",
    rationale:
      "Weak proxy in the peripheral-route direction. Involvement is the far " +
      "better input where the marketer knows it.",
  },
};

export interface SegmentSpec extends Audience {
  involvement: Involvement;
}

export interface ResolvedGains {
  gains: Record<ModuleId, number>;
  applied: SegmentPrior[];
  /** True when nothing was applied — every gain is exactly 1. */
  isNeutral: boolean;
  /** Largest deviation from 1.0 across modules. */
  maxDeviation: number;
}

const MODULE_IDS: ModuleId[] = [
  "salience", "affect", "valuation", "encoding", "approach", "control",
];

/**
 * Compose the priors for a segment.
 *
 * Composition is MULTIPLICATIVE and then clamped. Multiplying keeps each prior's
 * effect proportional, and the clamp stops several small, individually-defensible
 * priors from stacking into a large, indefensible one.
 */
export function resolveGains(spec: SegmentSpec): ResolvedGains {
  const gains: Record<ModuleId, number> = Object.fromEntries(
    MODULE_IDS.map((m) => [m, 1]),
  ) as Record<ModuleId, number>;
  const applied: SegmentPrior[] = [];

  const add = (p: SegmentPrior | undefined) => {
    if (!p) return;
    applied.push(p);
    for (const [mod, g] of Object.entries(p.gains)) {
      gains[mod as ModuleId] *= g as number;
    }
  };

  if (spec.involvement === "high") add(INVOLVEMENT_PRIORS.high);
  if (spec.involvement === "low") add(INVOLVEMENT_PRIORS.low);
  if (spec.age === "older") add(AGE_PRIORS.older);
  if (spec.age === "younger") add(AGE_PRIORS.younger);
  if (spec.gender === "male") add(GENDER_PRIORS.male);
  if (spec.gender === "female") add(GENDER_PRIORS.female);
  if (spec.education === "higher") add(EDUCATION_PRIORS.higher);
  if (spec.education === "lower") add(EDUCATION_PRIORS.lower);

  let maxDeviation = 0;
  for (const m of MODULE_IDS) {
    gains[m] = clampGain(gains[m]);
    maxDeviation = Math.max(maxDeviation, Math.abs(gains[m] - 1));
  }

  return {
    gains,
    applied,
    isNeutral: maxDeviation === 0,
    maxDeviation,
  };
}

/** Apply resolved gains to module activations. */
export function applyGains(
  activations: Record<ModuleId, number>,
  resolved: ResolvedGains,
): Record<ModuleId, number> {
  const out = { ...activations };
  for (const m of MODULE_IDS) out[m] = activations[m] * resolved.gains[m];
  return out;
}

/** Disclosure shown wherever segment conditioning is active. */
export function segmentDisclosure(resolved: ResolvedGains): string {
  if (resolved.isNeutral) {
    return "No segment adjustment applied; scores are audience-neutral.";
  }
  const lowConf = resolved.applied.filter((p) => p.confidence === "low").length;
  const base =
    "Segment adjustments are PRIORS derived from published research, not " +
    "measurements from your audience. They are replaced by fitted values once " +
    "you upload campaign results split by segment.";
  return lowConf > 0
    ? `${base} ${lowConf} of ${resolved.applied.length} adjustments are ` +
        "low-confidence (derived from word-rating differences rather than " +
        "measured advertising response)."
    : base;
}

export const SEGMENT_LIMITATION =
  "Segment priors encode published findings about how audiences differ in " +
  "processing. They are hypotheses about your audience, not observations of " +
  "it. No dataset in this system links copy to outcome by demographic; that " +
  "arrives with your own segment-split campaign data.";
