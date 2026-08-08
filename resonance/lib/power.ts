/**
 * Per-comparison ceiling, and how to raise it.
 *
 * The 0.662 oracle ceiling is not a property of the task — it is the ceiling at
 * Upworthy's sample sizes (median 3,118 impressions per arm at ~1.25% CTR). A
 * perfect model cannot beat it THERE. Run the same test at 30,000 impressions
 * and the ceiling is far higher, because the labels are less noisy.
 *
 * That reframes the limit as a measurement question, and makes it actionable:
 * instead of "we cannot tell these apart", the product can say "this test needs
 * 12,000 more impressions per arm to be decidable".
 *
 * Maths. For a click rate p over n impressions, the standard error of the
 * log-odds is approximately
 *
 *     SE_arm = sqrt(1/(n·p) + 1/(n·(1-p)))
 *
 * and comparing two arms gives SE_diff = sqrt(2)·SE_arm. A difference of δ in
 * log-odds is resolvable at confidence z when |δ| > z·SE_diff, so
 *
 *     n_required = 2·(z/δ)² · (1/p + 1/(1-p))
 *
 * ponytail: normal approximation to the binomial. Fine at n·p > ~10, which the
 * 500-impression floor guarantees at realistic click rates. Below that the
 * numbers are indicative only.
 */

/** z for a two-sided 95% interval. */
const Z95 = 1.96;

/** Log-odds of a rate. */
function logOdds(p: number): number {
  const q = Math.min(Math.max(p, 1e-6), 1 - 1e-6);
  return Math.log(q / (1 - q));
}

/** Standard error of the log-odds difference between two arms. */
export function seLogOddsDiff(impressions: number, rate: number): number {
  const p = Math.min(Math.max(rate, 1e-6), 1 - 1e-6);
  const n = Math.max(impressions, 1);
  return Math.sqrt(2 * (1 / (n * p) + 1 / (n * (1 - p))));
}

/**
 * Highest pairwise accuracy any model could reach at this sample size, for
 * comparisons whose true effect is drawn with the given spread.
 *
 * NOT the same quantity as the headline 0.662, and the difference matters.
 * This is the UNCONDITIONAL ceiling — every pair, including the near-ties. The
 * 0.662 from model/ceiling_robustness.py is measured on pairs filtered to
 * |gap| >= 0.05, which drops the hardest comparisons and so sits higher. At
 * Upworthy's median sample size this function returns ~0.629 against that
 * 0.662; both are correct for what they measure.
 *
 * Use 0.662 when comparing against our reported accuracy, since that is
 * measured on the same filtered pairs. Use this when asking "could ANY model
 * settle this particular comparison".
 *
 * @param effectSd spread of true log-odds effects. 0.098 is the value measured
 *   for this corpus in model/ceiling_robustness.py.
 */
export function localCeiling(
  impressions: number,
  rate: number,
  effectSd = 0.098,
): number {
  const noise = seLogOddsDiff(impressions, rate);
  // P(two noisy reads of the same effect agree on sign), integrated over
  // effects ~ N(0, effectSd²). Closed form: 1/2 + (1/π)·atan(effectSd/noise).
  return 0.5 + Math.atan(effectSd / noise) / Math.PI;
}

/** Impressions per arm needed to resolve a log-odds difference of `delta`. */
export function requiredImpressions(
  delta: number,
  rate: number,
  z = Z95,
): number {
  const d = Math.abs(delta);
  if (d < 1e-6) return Infinity;
  const p = Math.min(Math.max(rate, 1e-6), 1 - 1e-6);
  return Math.ceil(2 * (z / d) ** 2 * (1 / p + 1 / (1 - p)));
}

export interface Decidability {
  /** Best accuracy any model could reach at this sample size. */
  ceiling: number;
  /** Observed log-odds difference between the two arms. */
  observedDelta: number;
  /** Impressions per arm needed to call it at 95%. */
  needed: number;
  /** Extra impressions per arm still required. Zero if already decidable. */
  shortfall: number;
  decidable: boolean;
  message: string;
}

/**
 * Can this comparison be settled at its current sample size, and if not, what
 * would it take?
 */
export function assessDecidability(
  a: { impressions: number; clicks: number },
  b: { impressions: number; clicks: number },
): Decidability {
  const pa = a.clicks / Math.max(a.impressions, 1);
  const pb = b.clicks / Math.max(b.impressions, 1);
  const pooled = Math.max(
    (a.clicks + b.clicks) / Math.max(a.impressions + b.impressions, 1),
    1e-6,
  );
  const minImpr = Math.min(a.impressions, b.impressions);

  const observedDelta = logOdds(pa) - logOdds(pb);
  const ceiling = localCeiling(minImpr, pooled);
  const needed = requiredImpressions(observedDelta, pooled);
  const shortfall = Number.isFinite(needed) ? Math.max(0, needed - minImpr) : Infinity;
  const decidable = shortfall === 0;

  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;
  const message = decidable
    ? `Decidable now: the gap is large enough to call at this sample size. ` +
      `Best achievable accuracy here is ${pct(ceiling)}.`
    : Number.isFinite(shortfall)
      ? `Not decidable yet. The arms differ by too little relative to the ` +
        `noise at ${minImpr.toLocaleString()} impressions. About ` +
        `${Math.round(shortfall).toLocaleString()} more impressions per arm ` +
        `would settle it. Best achievable accuracy at the current sample size ` +
        `is ${pct(ceiling)} — no model can beat that here.`
      : `The arms are performing identically. No sample size will separate ` +
        `them, because there is nothing to separate.`;

  return { ceiling, observedDelta, needed, shortfall, decidable, message };
}
