/**
 * The analysis pipeline: raw copy in, diagnostic profile out.
 *
 * Composes the pieces that have already been verified individually:
 *   features.ts   text -> 50 norm-derived features   (parity-checked vs Python)
 *   module.ts     features -> six activations + score (parity-checked vs PyTorch)
 *   segments.ts   audience -> bounded, cited gains
 *
 * Everything returned carries enough provenance for the UI to show where a
 * number came from and how far to trust it. Confidence is deliberately
 * pessimistic: it is better for a marketer to ignore a hedged score than to act
 * on a confident one that was never earned.
 */

import { MODULES, PERFORMANCE, type ModuleDefinition, type ModuleId } from "./constructs";
import { extractFeatures, extractVector, FEATURE_NAMES } from "./inference/features";
import { arousalToEncoding, infer, standardise } from "./inference/module";
import {
  applyGains,
  resolveGains,
  segmentDisclosure,
  type ResolvedGains,
  type SegmentSpec,
} from "./segments";

export interface ModuleResult {
  id: ModuleId;
  label: string;
  /** Activation after segment gains, 0-1 (approach is -1..1). */
  score: number;
  /** Activation before segment gains. */
  baseScore: number;
  /** How far the segment moved it, as a proportion. */
  segmentShift: number;
  definition: ModuleDefinition;
  /** Where this sits relative to the module's ideal, if it has one. */
  verdict: "low" | "optimal" | "high" | "n/a";
  /**
   * Range this module's score can actually occupy, for display scaling.
   *
   * Not every module is 0-1. `approach` is signed (-1..1), and `encoding` is
   * multiplied by (1 + arousalToEncoding * affect) under constraint C2, so it
   * can exceed 1. A bar assuming 0-1 silently clips it — which is exactly what
   * happened the first time this ran in a browser, despite every unit test
   * passing.
   */
  displayRange: [number, number];
}

export interface AnalysisResult {
  text: string;
  wordCount: number;
  modules: ModuleResult[];
  /** Diagnostic ranking score. Comparable only within one analysis run. */
  score: number;
  /** Share of content words found in the norm dictionaries. */
  coverage: number;
  warnings: string[];
  segment: {
    applied: boolean;
    disclosure: string;
    gains: ResolvedGains;
  };
  provenance: {
    modelAccuracy: number;
    modelCi95: [number, number];
    chance: number;
    ceiling: number;
    trainingData: string;
  };
}

/** Below this, too few words were found in the norms to trust the profile. */
const LOW_COVERAGE = 0.4;
/** Below this many words, per-word statistics are dominated by single words. */
const MIN_WORDS = 4;

/**
 * The range each module's post-modulation score can occupy.
 *
 * Derived from the architecture rather than hard-coded, so it stays correct if
 * the model is retrained and the C2 gate changes magnitude. The +15% headroom
 * accounts for segment gains (MAX_GAIN_DELTA in segments.ts).
 */
function displayRangeFor(id: ModuleId): [number, number] {
  const GAIN_HEADROOM = 1.15;
  if (id === "approach") return [-GAIN_HEADROOM, GAIN_HEADROOM];
  // C2: encoding *= (1 + arousalToEncoding * affect), affect in [0, 1].
  if (id === "encoding") {
    return [0, (1 + arousalToEncoding()) * GAIN_HEADROOM];
  }
  return [0, GAIN_HEADROOM];
}

function verdictFor(def: ModuleDefinition, score: number): ModuleResult["verdict"] {
  if (def.response === "inverted-u" && def.optimalBand) {
    const [lo, hi] = def.optimalBand;
    if (score < lo) return "low";
    if (score > hi) return "high";
    return "optimal";
  }
  return "n/a";
}

export function analyse(text: string, segment: SegmentSpec): AnalysisResult {
  const trimmed = text.trim();
  if (!trimmed) throw new Error("No copy supplied.");

  const raw = extractVector(trimmed);
  const std = standardise(raw);
  const result = infer(std);

  const gains = resolveGains(segment);
  const gained = applyGains(
    result.modules as unknown as Record<ModuleId, number>,
    gains,
  );

  const features = extractFeatures(trimmed);
  const coverage = features.vad_coverage;
  const wordCount = features.n_words;

  const warnings: string[] = [];
  if (coverage < LOW_COVERAGE) {
    warnings.push(
      `Only ${Math.round(coverage * 100)}% of content words were found in the ` +
        "rating dictionaries, so this profile rests on few words. Treat it as " +
        "indicative only.",
    );
  }
  if (wordCount < MIN_WORDS) {
    warnings.push(
      `${wordCount} words is very short. Per-word statistics on this little ` +
        "text are dominated by individual word choices.",
    );
  }
  if (features.caps_ratio > 0.5 && wordCount > 3) {
    warnings.push(
      "Mostly capitals. In the training data, shouted copy scored high on " +
        "salience and WORSE on click-through.",
    );
  }

  const modules: ModuleResult[] = MODULES.map((def) => {
    const base = (result.modules as unknown as Record<ModuleId, number>)[def.id];
    const score = gained[def.id];
    return {
      id: def.id,
      label: def.label,
      score,
      baseScore: base,
      segmentShift: base === 0 ? 0 : score / base - 1,
      definition: def,
      verdict: verdictFor(def, score),
      displayRange: displayRangeFor(def.id),
    };
  });

  return {
    text: trimmed,
    wordCount,
    modules,
    score: result.score,
    coverage,
    warnings,
    segment: {
      applied: !gains.isNeutral,
      disclosure: segmentDisclosure(gains),
      gains,
    },
    provenance: {
      modelAccuracy: PERFORMANCE.moduleModelAccuracy,
      modelCi95: PERFORMANCE.moduleModelCi95,
      chance: PERFORMANCE.chance,
      ceiling: PERFORMANCE.oracleCeiling,
      trainingData: PERFORMANCE.trainingData,
    },
  };
}

export interface VariantComparison {
  variants: AnalysisResult[];
  /** Indices into `variants`, best first. */
  ranking: number[];
  /** Score gap between first and second. */
  margin: number;
  /**
   * Whether the gap is large enough to act on. The model is right ~53% of the
   * time on this layer, so a narrow margin means "we do not know".
   */
  confident: boolean;
  guidance: string;
}

/**
 * Margin below which the diagnostic layer should decline to call it.
 *
 * Chosen to be deliberately conservative: the module model scores 0.5346 on
 * held-out data, only ~3.5 points above chance, so most close calls are noise.
 * Saying "we cannot tell these apart" is more useful than a coin flip dressed
 * up as a recommendation.
 */
const CONFIDENT_MARGIN = 0.25;

export function compareVariants(
  texts: string[],
  segment: SegmentSpec,
): VariantComparison {
  const cleaned = texts.map((t) => t.trim()).filter(Boolean);
  if (cleaned.length < 2) {
    throw new Error("Supply at least two variants to compare.");
  }

  const variants = cleaned.map((t) => analyse(t, segment));
  const ranking = variants
    .map((v, i) => ({ i, score: v.score }))
    .sort((a, b) => b.score - a.score)
    .map((x) => x.i);

  const margin = variants[ranking[0]].score - variants[ranking[1]].score;
  const confident = margin >= CONFIDENT_MARGIN;

  const guidance = confident
    ? `Variant ${ranking[0] + 1} scores highest on the diagnostic profile. ` +
      "This layer is correct about 53% of the time on held-out data, so treat " +
      "it as a tiebreaker, not a verdict."
    : "These variants score too closely to separate. The honest answer is that " +
      "we cannot tell them apart — run a live test rather than picking on this.";

  return { variants, ranking, margin, confident, guidance };
}

export { FEATURE_NAMES };
