/**
 * Client campaign upload: parsing, validation, and the recalibration gate.
 *
 * This is the path that fixes the product's central limitation. The global
 * model was trained on 2013-15 viral media; a client's own campaign results
 * make that distribution irrelevant rather than something we patch around.
 *
 * What is accepted: copy, impressions, clicks, and optionally a demographic
 * segment. Meta and Google both export campaign performance split by age
 * bracket and gender, so `(copy, segment, impressions, clicks)` is a row a
 * marketer already has rather than something they must construct.
 *
 * What is NOT accepted: anything resembling personal data. Rows are rejected at
 * ingest, not stored and redacted. See lib/safety/pii.ts for why.
 */

import { assertNoPii, scanRows } from "./safety/pii";

export interface CampaignRow {
  copy: string;
  impressions: number;
  clicks: number;
  segment?: string;
  campaignId?: string;
}

export interface ParseIssue {
  row: number;
  problem: string;
}

export interface ParseResult {
  rows: CampaignRow[];
  issues: ParseIssue[];
  /** Distinct campaigns, which is what the recalibration floor counts. */
  campaignCount: number;
}

/**
 * Minimum campaigns before a tenant-specific number is shown.
 *
 * Below this, a per-tenant fit is worse than the global model: it would be
 * fitting noise from the client's small sample and presenting it with the
 * authority of a measurement. Under the floor we shrink toward the global model
 * and say so, rather than showing a falsely precise number.
 */
export const MIN_CAMPAIGNS_FOR_RECALIBRATION = 200;

/** Impressions below this make the click-through estimate mostly noise. */
const MIN_IMPRESSIONS = 500;

const REQUIRED = ["copy", "impressions", "clicks"] as const;

/**
 * Resolve a raw CSV header to one of our fields.
 *
 * Pattern matching rather than an alias table, because platform exports name
 * these columns inconsistently and an enumerated list is always one export
 * format behind. Real headers this has to survive:
 *
 *   Meta Ads Manager  "Body" (ad text), "Title" (headline), "Link clicks",
 *                     "Amount spent (GBP)", "Ad name"
 *   Google Ads        "Headline 1", "Description", "Impr." (with the period),
 *                     "Clicks", "Campaign"
 *   Hand-rolled       copy, text, ad_copy, impressions, views
 *
 * Headers are normalised to lowercase alphanumerics first, so "Link clicks",
 * "link_clicks" and "LinkClicks" all collapse to the same key. Order matters:
 * the first matching rule wins, so more specific patterns come first.
 */
const HEADER_RULES: [RegExp, string][] = [
  // Clicks before impressions, "link clicks" contains neither ambiguously,
  // but "clicks" must not be swallowed by a looser rule later.
  [/^(link)?clicks?$/, "clicks"],
  [/^(all|unique|outbound|website)?(link)?clicks?$/, "clicks"],
  // "Impr." loses its period during normalisation.
  [/^(impr|impressions?|views?|reach)$/, "impressions"],
  // Meta calls the headline "Title" and the body text "Body". Google numbers
  // its headlines. Any of them is the copy we score.
  [/^(copy|text|headline\d*|title|body|creative|addcopy|adcopy|description\d*)$/,
    "copy"],
  [/^(segment|audience|agerange|age|gender|sex)$/, "segment"],
  [/^(campaign|campaignid|campaignname|adsetname|adname|adid)$/, "campaignId"],
];

function resolveHeader(raw: string): string {
  const key = raw.toLowerCase().replace(/[^a-z0-9]/g, "");
  for (const [pattern, field] of HEADER_RULES) {
    if (pattern.test(key)) return field;
  }
  return key;
}

function splitCsvLine(line: string): string[] {
  const out: string[] = [];
  let cur = "";
  let inQuotes = false;
  for (let i = 0; i < line.length; i++) {
    const ch = line[i];
    if (ch === '"') {
      // Doubled quote inside a quoted field is a literal quote.
      if (inQuotes && line[i + 1] === '"') {
        cur += '"';
        i++;
      } else {
        inQuotes = !inQuotes;
      }
    } else if (ch === "," && !inQuotes) {
      out.push(cur);
      cur = "";
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out.map((s) => s.trim());
}

function toNumber(raw: string): number | null {
  // Exports carry thousands separators, currency symbols and percent signs.
  const cleaned = raw.replace(/[,\s$£€%]/g, "");
  if (!cleaned) return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

export function parseCampaignCsv(csv: string): ParseResult {
  const lines = csv.split(/\r?\n/).filter((l) => l.trim());
  if (lines.length < 2) {
    return { rows: [], issues: [{ row: 0, problem: "File has no data rows." }], campaignCount: 0 };
  }

  const header = splitCsvLine(lines[0]).map(resolveHeader);

  const missing = REQUIRED.filter((r) => !header.includes(r));
  if (missing.length) {
    return {
      rows: [],
      issues: [{
        row: 0,
        problem:
          `Missing required column(s): ${missing.join(", ")}. ` +
          `Found: ${header.join(", ")}.`,
      }],
      campaignCount: 0,
    };
  }

  const rows: CampaignRow[] = [];
  const issues: ParseIssue[] = [];
  const campaigns = new Set<string>();

  for (let i = 1; i < lines.length; i++) {
    const cells = splitCsvLine(lines[i]);
    const get = (name: string) => cells[header.indexOf(name)] ?? "";

    const copy = get("copy");
    const impressions = toNumber(get("impressions"));
    const clicks = toNumber(get("clicks"));

    if (!copy) {
      issues.push({ row: i + 1, problem: "Empty copy." });
      continue;
    }
    if (impressions === null || clicks === null) {
      issues.push({ row: i + 1, problem: "Impressions or clicks not numeric." });
      continue;
    }
    if (impressions < MIN_IMPRESSIONS) {
      issues.push({
        row: i + 1,
        problem:
          `Only ${impressions} impressions. Below ${MIN_IMPRESSIONS} the ` +
          "click-through estimate is mostly sampling noise.",
      });
      continue;
    }
    if (clicks < 0 || clicks > impressions) {
      issues.push({
        row: i + 1,
        problem: `Clicks (${clicks}) must be between 0 and impressions (${impressions}).`,
      });
      continue;
    }

    const campaignId = get("campaignId") || undefined;
    if (campaignId) campaigns.add(campaignId);

    rows.push({
      copy,
      impressions,
      clicks,
      segment: get("segment") || undefined,
      campaignId,
    });
  }

  return {
    rows,
    issues,
    // Without explicit campaign ids, each row counts as its own campaign.
    campaignCount: campaigns.size > 0 ? campaigns.size : rows.length,
  };
}

export interface RecalibrationReadiness {
  eligible: boolean;
  campaignCount: number;
  required: number;
  shrinkage: number;
  message: string;
}

/**
 * Whether a tenant's data WOULD support its own fitted model.
 *
 * Conditional throughout, and deliberately so: per-tenant recalibration is not
 * built. This is an eligibility check that tells someone in advance whether
 * their exports would be usable, which is genuinely useful and is not the same
 * as fitting anything. The messages were previously written in the present
 * tense ("your results replace the global priors") and described a feature that
 * does not exist.
 *
 * Below the floor the design is to shrink toward the global model in proportion
 * to how much data exists and report the shrinkage, more honest than refusing
 * the client or pretending 50 campaigns is enough. That remains the plan, not a
 * description of current behaviour.
 */
export function assessReadiness(campaignCount: number): RecalibrationReadiness {
  const required = MIN_CAMPAIGNS_FOR_RECALIBRATION;
  const eligible = campaignCount >= required;
  // Linear shrinkage: 0 campaigns = fully global, `required` = fully local.
  const shrinkage = Math.max(0, 1 - campaignCount / required);

  return {
    eligible,
    campaignCount,
    required,
    shrinkage,
    message: eligible
      ? `${campaignCount} campaigns would be enough to fit a model on your own ` +
        "audience, once per-tenant recalibration exists. It does not yet, so " +
        "this file changes nothing today."
      : `${campaignCount} of the ${required} campaigns that a model fitted to ` +
        "your own audience would need. Recalibration is not built yet; when it " +
        `is, this much data would be blended ${Math.round(shrinkage * 100)}% ` +
        "toward the global model, which is trained on 2013-15 viral media and " +
        "may not resemble your audience.",
  };
}

export interface ValidatedUpload {
  rows: CampaignRow[];
  issues: ParseIssue[];
  readiness: RecalibrationReadiness;
}

/**
 * Full ingest gate. Throws PiiRejectedError before anything is persisted.
 */
export function validateUpload(csv: string): ValidatedUpload {
  const parsed = parseCampaignCsv(csv);

  // PII check runs on the parsed rows, before any storage path is touched.
  assertNoPii(parsed.rows as unknown as Record<string, unknown>[]);

  return {
    rows: parsed.rows,
    issues: parsed.issues,
    readiness: assessReadiness(parsed.campaignCount),
  };
}

/** Non-throwing variant for previewing a file before committing to it. */
export function previewUpload(csv: string): ValidatedUpload & {
  piiProblems: ReturnType<typeof scanRows>["problems"];
} {
  const parsed = parseCampaignCsv(csv);
  const { problems } = scanRows(parsed.rows as unknown as Record<string, unknown>[]);
  return {
    rows: parsed.rows,
    issues: parsed.issues,
    readiness: assessReadiness(parsed.campaignCount),
    piiProblems: problems,
  };
}
