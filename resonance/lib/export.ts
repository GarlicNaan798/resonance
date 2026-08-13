/**
 * The shareable track-record payload.
 *
 * Split out of predictions.ts and deliberately free of Node built-ins, because
 * this runs in the BROWSER: the Track page builds and downloads the file
 * client-side, so the app issues no request at all and the `--network none`
 * guarantee stays literally true.
 *
 * predictions.ts imports node:fs and node:crypto. Value-importing it from a
 * client component fails the Turbopack build — "the chunking context does not
 * support external modules (request: node:fs/promises)". `tsc --noEmit` was
 * perfectly happy with it, which is a good reminder that a typecheck is not a
 * build. Only the TYPE is imported here, and types are erased, so nothing from
 * the storage layer reaches the browser bundle.
 */

import type { ConfidenceTier, Prediction } from "./predictions";

/**
 * Schema version. Bump when fields change, so a payload stays readable long
 * after the version of the app that produced it is gone.
 */
export const EXPORT_SCHEMA = 1;

/**
 * One prediction, stripped of everything commercially sensitive.
 *
 * The redaction is the entire point, so it is expressed as an explicit
 * allow-list rather than by deleting fields from the source object. A deny-list
 * silently leaks any field added to Prediction later, and the field most likely
 * to be added later is another piece of the client's copy.
 */
export interface ExportedPrediction {
  /** Sealed hash. One-way, so it identifies the record without revealing it. */
  hash: string;
  /** Date only. The exact minute someone drafted copy is nobody's business. */
  date: string;
  variantCount: number;
  tier: ConfidenceTier;
  margin: number;
  modelCorrect: boolean;
  /** Null when no blind pick was recorded for this comparison. */
  userCorrect: boolean | null;
}

export interface TrackRecordExport {
  schema: number;
  generatedAt: string;
  /** What this file deliberately does not contain. Stated in the file itself. */
  excludes: string[];
  summary: {
    resolved: number;
    modelCorrect: number;
    modelRate: number;
    userScored: number;
    userCorrect: number;
    userRate: number | null;
  };
  predictions: ExportedPrediction[];
}

/**
 * Build the shareable payload.
 *
 * NEVER includes `variants` (the client's copy) or `label` (campaign name —
 * "Nike Q4 launch" identifies an account as surely as the copy does). Without
 * those two the file needs no legal review, which is the only reason anyone
 * would ever send it.
 *
 * Only resolved predictions go in. An unresolved one contributes no evidence
 * and would just be metadata about work in progress.
 */
export function buildExport(all: Prediction[]): TrackRecordExport {
  const resolved = all.filter((p) => p.actualWinner !== null);

  const predictions: ExportedPrediction[] = resolved.map((p) => ({
    hash: p.hash,
    date: p.createdAt.slice(0, 10),
    variantCount: p.variants.length,
    tier: p.tier,
    margin: Number(p.margin.toFixed(4)),
    modelCorrect: p.predictedWinner === p.actualWinner,
    userCorrect: p.userPick === null ? null : p.userPick === p.actualWinner,
  }));

  const scored = predictions.filter((p) => p.userCorrect !== null);
  const userCorrect = scored.filter((p) => p.userCorrect).length;
  const modelCorrect = predictions.filter((p) => p.modelCorrect).length;

  return {
    schema: EXPORT_SCHEMA,
    generatedAt: new Date().toISOString().slice(0, 10),
    excludes: [
      "campaign copy (the text of every variant)",
      "campaign names and labels",
      "impressions, clicks and any spend figure",
      "anything identifying the machine, the user or the organisation",
    ],
    summary: {
      resolved: predictions.length,
      modelCorrect,
      modelRate: predictions.length ? modelCorrect / predictions.length : 0,
      userScored: scored.length,
      userCorrect,
      userRate: scored.length ? userCorrect / scored.length : null,
    },
    predictions,
  };
}
