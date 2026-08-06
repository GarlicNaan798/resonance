/**
 * Audience segmentation.
 *
 * WHAT THE EVIDENCE SUPPORTS (and what it does not)
 * -------------------------------------------------
 * Warriner et al. rated every word separately by gender, age band and education
 * level, which looks like a licence to compute per-audience word scores. It is
 * not, and `pipeline/audience_analysis.py` shows why:
 *
 *   per-word gender difference in valence:  mean +0.127, SD 0.874
 *   SD predicted by rating noise alone:     0.57 - 0.90
 *
 * The observed spread is fully explained by each subgroup having only a handful
 * of raters per word. So the per-word differences are overwhelmingly SAMPLING
 * NOISE, not men and women genuinely disagreeing about individual words. Looking
 * up "how did women rate THIS word" returns mostly noise wearing a demographic
 * label.
 *
 * What survives is the lexicon-wide MEAN shift. Averaged over 13,905 words the
 * standard error is ~0.007, so these offsets are real and precisely estimated:
 *
 *   gender    (male - female)   arousal +0.285  (Cohen's d = 0.32)
 *   age       (younger - older) arousal +0.182  (d = 0.20)
 *   education (lower - higher)  arousal -0.139  (d = 0.16)
 *
 * Hence: apply a systematic per-segment OFFSET; never a per-word lookup.
 *
 * CONTINGENCY C5 APPLIES
 * ----------------------
 * The Upworthy archive carries no per-arm demographic labels, so there is no
 * data anywhere in this project from which "this copy performs better with
 * women aged 55+" could be learned. The model's audience-gain parameters were
 * initialised to zero and never fitted.
 *
 * Therefore this is DESCRIPTIVE SEGMENTATION, not predictive personalisation.
 * The honest claim is "this wording rates as more arousing among male raters
 * than female raters" — a fact about published norms. The dishonest claim is
 * "this will perform better with men". The UI must say the former.
 */

export type Gender = "male" | "female" | "all";
export type AgeBand = "younger" | "older" | "all";
export type Education = "lower" | "higher" | "all";

export interface Audience {
  gender: Gender;
  age: AgeBand;
  education: Education;
}

export const DEFAULT_AUDIENCE: Audience = {
  gender: "all",
  age: "all",
  education: "all",
};

/** Offsets in Warriner scale points (1-9), relative to the overall mean. */
export interface NormOffset {
  valence: number;
  arousal: number;
  dominance: number;
}

const ZERO: NormOffset = { valence: 0, arousal: 0, dominance: 0 };

/**
 * Half the measured between-group difference is applied to each side, so
 * selecting "all" recovers the overall mean exactly.
 *
 * Derived in pipeline/audience_analysis.py from Warriner et al. (2013).
 */
const GENDER_HALF: NormOffset = {
  valence: 0.0635,
  arousal: 0.1425,
  dominance: -0.008,
};
const AGE_HALF: NormOffset = {
  valence: 0.027,
  arousal: 0.091,
  dominance: -0.04,
};
const EDUCATION_HALF: NormOffset = {
  valence: -0.0295,
  arousal: -0.0695,
  dominance: 0.013,
};

function scale(o: NormOffset, k: number): NormOffset {
  return {
    valence: o.valence * k,
    arousal: o.arousal * k,
    dominance: o.dominance * k,
  };
}

function add(a: NormOffset, b: NormOffset): NormOffset {
  return {
    valence: a.valence + b.valence,
    arousal: a.arousal + b.arousal,
    dominance: a.dominance + b.dominance,
  };
}

/**
 * Net offset for an audience. Additive across the three axes: the norms give no
 * basis for interaction terms, so inventing them would be fabrication.
 */
export function audienceOffset(a: Audience): NormOffset {
  let out = ZERO;
  if (a.gender === "male") out = add(out, GENDER_HALF);
  if (a.gender === "female") out = add(out, scale(GENDER_HALF, -1));
  if (a.age === "younger") out = add(out, AGE_HALF);
  if (a.age === "older") out = add(out, scale(AGE_HALF, -1));
  if (a.education === "lower") out = add(out, EDUCATION_HALF);
  if (a.education === "higher") out = add(out, scale(EDUCATION_HALF, -1));
  return out;
}

/** True when every axis is "all" — the offset is exactly zero. */
export function isDefaultAudience(a: Audience): boolean {
  return a.gender === "all" && a.age === "all" && a.education === "all";
}

/**
 * How large is this adjustment relative to the lexicon's own spread?
 * Surfaced in the UI so nobody mistakes a small nudge for personalisation.
 * Lexicon SDs: valence 1.275, arousal 0.897.
 */
export function offsetMagnitude(a: Audience): {
  valenceSd: number;
  arousalSd: number;
  perceptible: boolean;
} {
  const o = audienceOffset(a);
  const valenceSd = Math.abs(o.valence) / 1.275;
  const arousalSd = Math.abs(o.arousal) / 0.897;
  return {
    valenceSd,
    arousalSd,
    // 0.2 SD is a conventional floor for a "small" effect.
    perceptible: Math.max(valenceSd, arousalSd) >= 0.2,
  };
}

/**
 * Text shown wherever an audience is selected. Deliberately worded as a
 * statement about raters, not a prediction about buyers.
 */
export function audienceDisclosure(a: Audience): string {
  if (isDefaultAudience(a)) {
    return "Scores use ratings pooled across all rater groups.";
  }
  const { perceptible } = offsetMagnitude(a);
  const base =
    "Scores are adjusted using how this audience's demographic group rated " +
    "words in published norms (Warriner et al., 2013). This describes rater " +
    "differences; it does not predict campaign performance for this group.";
  return perceptible
    ? base
    : `${base} For this selection the adjustment is smaller than 0.2 SD, so ` +
        "expect little visible change.";
}

export const AUDIENCE_LIMITATION =
  "Audience selection reflects measured differences in how demographic groups " +
  "rate words. It is descriptive segmentation, not predictive personalisation: " +
  "no data in this system links copy to outcomes by demographic group.";
