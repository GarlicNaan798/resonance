/**
 * The six modules Resonance scores.
 *
 * This replaces an earlier set of eleven ad-hoc constructs backed by
 * hand-written word lists. Every lexical value now comes from published human
 * ratings (Warriner et al. valence/arousal/dominance; Brysbaert et al.
 * concreteness), and the module set is drawn from the constructs that
 * non-invasive methods can actually measure.
 *
 * DELIBERATELY EXCLUDED
 * ---------------------
 * MacLean's triune brain (reptilian / limbic / neocortex) and left-right
 * hemisphere dominance appear throughout popular neuromarketing writing,
 * including one of the source papers for this project. Both are discredited as
 * neuroscience. They are not implemented here and must not appear in any
 * customer-facing copy.
 *
 * WHAT THESE SCORES ARE
 * ---------------------
 * Psychometric measurements computed from human word ratings. Each module is
 * NAMED for the functional system the literature associates with that
 * construct; that is an association, not a measurement of neural activity. No
 * neurotransmitter, hormone or brain state is measured or predicted.
 *
 * WHAT THESE SCORES ARE NOT
 * -------------------------
 * They are not the explanation of the ranking prediction. The ranker operates
 * on semantic embeddings and does not use these features. Presenting the
 * profile as the reason for the prediction would be post-hoc rationalisation.
 * The two layers are reported separately and must stay that way.
 */

export type ModuleId =
  | "salience"
  | "affect"
  | "valuation"
  | "encoding"
  | "approach"
  | "control";

export interface ModuleDefinition {
  id: ModuleId;
  label: string;
  /** One line, plain English, shown beside the score. */
  short: string;
  /** What the number actually reflects. */
  detail: string;
  /**
   * The functional system the literature associates with this construct.
   * An association for naming purposes — not a claim of measurement.
   */
  functionalReferent: string;
  /** Published grounding, shown in the methodology panel. */
  sources: string[];
  /**
   * Whether more is better, or whether there is an optimum beyond which the
   * effect reverses.
   */
  response: "higher-is-better" | "lower-is-better" | "inverted-u";
  /** For inverted-u modules, the band the model currently favours. */
  optimalBand?: [number, number];
  /** Stated limitation. Shown in the UI, not buried in docs. */
  caveat: string;
}

export const MODULES: readonly ModuleDefinition[] = [
  {
    id: "salience",
    label: "Salience",
    short: "How strongly the copy competes for attention.",
    detail:
      "Driven by lexical extremity, surface markers such as capitalisation and " +
      "punctuation, numerals, and the affective weight of opening words. " +
      "Attention is a prerequisite for every downstream effect: copy that is " +
      "never attended to cannot be evaluated.",
    functionalReferent: "anterior insula / dorsal anterior cingulate",
    sources: [
      "Pradeep K et al. (2026), F1000Research — attention as a measurable construct",
      "Warriner et al. (2013) — valence/arousal/dominance norms, 13,915 words",
    ],
    response: "higher-is-better",
    caveat:
      "High salience achieved by shouting (all-caps, exclamation marks) " +
      "correlates with WORSE click-through in our training data. Salience is " +
      "necessary, not sufficient.",
  },
  {
    id: "affect",
    label: "Affective arousal",
    short: "How activating the language is, regardless of positive or negative.",
    detail:
      "Mean and peak arousal of content words against human ratings. Arousal is " +
      "distinct from valence: 'furious' and 'thrilled' are both highly arousing " +
      "and opposite in valence.",
    functionalReferent: "amygdala",
    sources: [
      "Warriner et al. (2013) — arousal norms",
      "Russell (1980) — circumplex model of affect",
      "Yerkes & Dodson (1908) — arousal/performance inverted-U",
    ],
    response: "inverted-u",
    optimalBand: [0.45, 0.65],
    caveat:
      "The inverted-U is enforced structurally, so the model cannot conclude " +
      "that more arousal is always better. The optimum is learned from data and " +
      "is audience-dependent.",
  },
  {
    id: "valuation",
    label: "Valuation",
    short: "How much worth or benefit the copy conveys.",
    detail:
      "Positive valence and dominance of content words, gated by salience — " +
      "value cannot be assigned to something that was never attended to.",
    functionalReferent: "ventromedial prefrontal cortex / ventral striatum",
    sources: [
      "Krajbich et al. (2010) — attentional drift-diffusion; attention gates value",
      "Warriner et al. (2013) — valence and dominance norms",
    ],
    response: "higher-is-better",
    caveat:
      "Measures value LANGUAGE, not whether the offer is genuinely good. Copy " +
      "can score highly here and describe a poor product.",
  },
  {
    id: "encoding",
    label: "Memory encoding",
    short: "How likely the message is to be remembered.",
    detail:
      "Concreteness of content words, enhanced by affective arousal. Concrete, " +
      "imageable language is recalled more reliably than abstract language.",
    functionalReferent: "hippocampus / medial temporal lobe",
    sources: [
      "Brysbaert et al. (2014) — concreteness norms, 39,954 words",
      "Cahill & McGaugh (1998) — emotional arousal enhances consolidation",
      "Paivio (1971) — dual coding theory",
    ],
    response: "higher-is-better",
    caveat: "Memorability is not persuasion. Irritating copy is often highly memorable.",
  },
  {
    id: "approach",
    label: "Approach / avoidance",
    short: "Whether the language pulls toward or pushes away.",
    detail:
      "Signed measure from valence asymmetry across the copy. Negative values " +
      "indicate avoidance-oriented framing.",
    functionalReferent: "left/right prefrontal asymmetry (frontal alpha asymmetry)",
    sources: [
      "Pradeep K et al. (2026) — frontal alpha asymmetry and approach motivation",
      "Davidson (1992) — anterior asymmetry and approach/withdrawal",
    ],
    response: "higher-is-better",
    caveat:
      "The frontal-asymmetry link is taken from the literature and has NOT yet " +
      "been validated against measured EEG in this project. If that validation " +
      "fails, this module will be renamed to a purely behavioural label.",
  },
  {
    id: "control",
    label: "Processing fluency",
    short: "How easily the copy is understood.",
    detail:
      "Word length, sentence length, lexical diversity and dictionary coverage. " +
      "Easily processed text is judged more favourably — an effect independent " +
      "of the content itself.",
    functionalReferent: "dorsolateral prefrontal cortex",
    sources: [
      "Reber, Winkielman & Schwarz (1998) — fluency and positive evaluation",
      "Brysbaert & New (2009) — word frequency and processing speed",
    ],
    response: "higher-is-better",
    caveat:
      "Fluency is measured from surface form. Copy can be perfectly fluent and " +
      "say nothing.",
  },
] as const;

export function getModule(id: ModuleId): ModuleDefinition {
  const m = MODULES.find((x) => x.id === id);
  if (!m) throw new Error(`Unknown module: ${id}`);
  return m;
}

/**
 * Honest performance figures for the methodology panel. Held-out test set, read
 * once. Chance is 0.500; no model can reach 1.0 because the labels themselves
 * are noisy measurements.
 *
 * CEILING CORRECTION. This previously read 0.788, taken from a split-half
 * simulation that used each arm's OBSERVED click rate as its true rate. Since
 * Var(observed) = Var(true) + Var(noise), that spread the arms further apart
 * than reality and inflated the estimate. Deconvolving the noise gives 0.662,
 * and the variance decomposition behind it is stark: of the target's 0.0794
 * variance, 0.0697 is sampling noise and only 0.0097 — about 12% — is signal.
 *
 * A third, analytic estimate gave 0.544, but that is refuted by our own test
 * accuracy of 0.5942: a real ceiling cannot sit below measured performance.
 * See model/ceiling_robustness.py.
 *
 * The correction matters: against 0.662 we capture ~58% of achievable signal,
 * not the ~33% previously claimed.
 */
export const PERFORMANCE = {
  // Listwise ensemble, from the pre-registered read in test_read_listwise.py.
  // This comment previously called it the "third and final test read". By
  // execution order it is the second of two evaluations; reads were not logged
  // at the time, so the ordinal could not be checked. They are logged now —
  // see pipeline/test_lock.py and FUNDAMENTALS.md §10. Was 0.5942 for the single
  // pairwise model; an identically-trained pairwise reference scored 0.6009 in
  // the same run, so ~+0.017 of the gain is attributable to the ensemble and
  // the rest to run-to-run variation in the reference.
  rankerAccuracy: 0.6176,
  rankerCi95: [0.6075, 0.6277] as [number, number],
  moduleModelAccuracy: 0.5346,
  moduleModelCi95: [0.5241, 0.5452] as [number, number],
  chance: 0.5,
  oracleCeiling: 0.662,
  /** Share of the target's variance that is real signal rather than noise. */
  signalFraction: 0.12,
  nExperiments: 2665,
  nPairs: 20452,
  trainingData: "Upworthy Research Archive — 32,487 randomised A/B tests",
} as const;

/** Claims the product must never make. Enforced by review; listed here. */
export const PROHIBITED_CLAIMS = [
  "Predicting conversion rates, revenue, or ROI from copy",
  "Measuring or predicting neurotransmitters, hormones, or brain states",
  "Reading, scanning, or simulating an individual person's brain",
  "Replacing A/B testing",
  "Any accuracy figure above the 0.662 measured ceiling for this task",
] as const;
