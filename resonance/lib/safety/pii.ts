/**
 * PII detection and rejection at ingest.
 *
 * Resonance analyses marketing copy and aggregate campaign metrics. It has no
 * legitimate use for personal data, so the policy is REJECT rather than store
 * and redact: nothing containing PII is written to disk at all. That is a
 * stronger guarantee than redaction, which still requires the raw value to
 * transit the system and land in logs, backups and error traces.
 *
 * Design notes:
 *
 *  - Detectors are deliberately conservative on the patterns where a false
 *    positive would block legitimate marketing copy. "Save 50% on orders over
 *    $100" must not trip a card detector, so card numbers are Luhn-validated
 *    rather than matched on digit-count alone.
 *
 *  - Personal NAMES are not detected heuristically. Any name detector good
 *    enough to catch "Sarah Chen" also flags "Ray-Ban", "Oscar Health" and half
 *    the brands a marketing tool exists to discuss. Names are handled by
 *    contract and schema (upload accepts no name column) rather than by regex
 *    guesswork that would produce constant false rejections.
 *
 *  - Findings report the KIND and POSITION of what was found, never the value.
 *    Echoing a detected card number back in an error message would leak the
 *    exact data this module exists to keep out.
 */

export type PiiKind =
  | "email"
  | "phone"
  | "credit_card"
  | "ssn"
  | "iban"
  | "ip_address"
  | "postal_address"
  | "date_of_birth";

export interface PiiFinding {
  kind: PiiKind;
  /** Character offset in the scanned string. */
  start: number;
  end: number;
  /** Length only. The matched text is deliberately never retained. */
  length: number;
  /** Human-readable, value-free explanation for the upload UI. */
  message: string;
}

export interface ScanResult {
  clean: boolean;
  findings: PiiFinding[];
}

interface Detector {
  kind: PiiKind;
  pattern: RegExp;
  message: string;
  /** Optional second stage to suppress false positives. */
  validate?: (match: string) => boolean;
}

/** Luhn checksum, distinguishes a real card number from any 16 digits. */
function luhnValid(raw: string): boolean {
  const digits = raw.replace(/[^0-9]/g, "");
  if (digits.length < 13 || digits.length > 19) return false;
  let sum = 0;
  let double = false;
  for (let i = digits.length - 1; i >= 0; i--) {
    let d = digits.charCodeAt(i) - 48;
    if (double) {
      d *= 2;
      if (d > 9) d -= 9;
    }
    sum += d;
    double = !double;
  }
  return sum % 10 === 0;
}

/**
 * Reject strings of digits that are obviously not phone numbers in a marketing
 * context, prices, years, impression counts, percentages.
 */
function plausiblePhone(match: string): boolean {
  const digits = match.replace(/[^0-9]/g, "");
  if (digits.length < 10 || digits.length > 15) return false;
  // "2020-2024", "1,000,000 impressions" and similar are not phone numbers.
  if (/^(19|20)\d{2}$/.test(digits)) return false;
  if (/^0+$/.test(digits)) return false;
  // Require punctuation, a leading +, or a country/area grouping. A bare run
  // of digits inside copy is far more often a metric than a number to call.
  return /[+()\-.\s]/.test(match.trim()) || digits.length >= 11;
}

const DETECTORS: Detector[] = [
  {
    kind: "email",
    pattern: /[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/g,
    message: "An email address was found. Remove it before uploading.",
  },
  {
    kind: "credit_card",
    pattern: /\b(?:\d[ -]*?){13,19}\b/g,
    validate: luhnValid,
    message:
      "A value passing a credit-card checksum was found. Payment data must " +
      "never be uploaded.",
  },
  {
    kind: "ssn",
    // US SSN with separators only; bare 9-digit runs are too often IDs/metrics.
    pattern: /\b(?!000|666|9\d{2})\d{3}[-\s](?!00)\d{2}[-\s](?!0000)\d{4}\b/g,
    message: "A value matching a national insurance / social security number " +
      "format was found.",
  },
  {
    kind: "iban",
    pattern: /\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b/g,
    message: "A bank account (IBAN) format was found.",
  },
  {
    kind: "phone",
    pattern: /(?:\+\d{1,3}[\s.-]?)?(?:\(\d{1,4}\)[\s.-]?)?\d[\d\s.()-]{7,17}\d/g,
    validate: plausiblePhone,
    message: "A phone number was found. Remove it before uploading.",
  },
  {
    kind: "ip_address",
    pattern: /\b(?:(?:25[0-5]|2[0-4]\d|1?\d?\d)\.){3}(?:25[0-5]|2[0-4]\d|1?\d?\d)\b/g,
    message: "An IP address was found. IP addresses are personal data under GDPR.",
  },
  {
    kind: "postal_address",
    pattern:
      /\b\d{1,5}\s+[A-Za-z0-9.'-]+(?:\s+[A-Za-z0-9.'-]+){0,3}\s+(?:street|st|avenue|ave|road|rd|boulevard|blvd|lane|ln|drive|dr|court|ct|way|close|crescent)\b/gi,
    message: "A street address was found.",
  },
  {
    kind: "date_of_birth",
    pattern:
      /\b(?:dob|d\.o\.b\.?|date of birth|born)\b[\s:]*\d{1,4}[\/\-.]\d{1,2}[\/\-.]\d{1,4}/gi,
    message: "A date of birth was found.",
  },
];

/**
 * Scan a single string. Returns every finding rather than stopping at the
 * first, so the uploader can fix all problems in one pass instead of
 * rediscovering them one at a time.
 */
export function scanText(text: string): ScanResult {
  const findings: PiiFinding[] = [];
  if (!text) return { clean: true, findings };

  for (const det of DETECTORS) {
    // Fresh regex per scan: /g patterns carry lastIndex between calls, and a
    // shared instance silently skips matches on the second invocation.
    const re = new RegExp(det.pattern.source, det.pattern.flags);
    let m: RegExpExecArray | null;
    while ((m = re.exec(text)) !== null) {
      if (m[0].length === 0) {
        re.lastIndex++;
        continue;
      }
      if (det.validate && !det.validate(m[0])) continue;
      findings.push({
        kind: det.kind,
        start: m.index,
        end: m.index + m[0].length,
        length: m[0].length,
        message: det.message,
      });
    }
  }

  findings.sort((a, b) => a.start - b.start);
  return { clean: findings.length === 0, findings };
}

export interface RowScan {
  row: number;
  column: string;
  findings: PiiFinding[];
}

/**
 * Scan a parsed upload. Reports location by row and column so a user with a
 * 5,000-row CSV can find the offending cells.
 */
export function scanRows(
  rows: Record<string, unknown>[],
  options: { maxReported?: number } = {},
): { clean: boolean; problems: RowScan[]; scanned: number } {
  const maxReported = options.maxReported ?? 100;
  const problems: RowScan[] = [];

  for (let i = 0; i < rows.length; i++) {
    for (const [column, value] of Object.entries(rows[i])) {
      if (typeof value !== "string") continue;
      const { clean, findings } = scanText(value);
      if (!clean) {
        problems.push({ row: i + 1, column, findings });
        if (problems.length >= maxReported) {
          return { clean: false, problems, scanned: i + 1 };
        }
      }
    }
  }
  return { clean: problems.length === 0, problems, scanned: rows.length };
}

/**
 * Thrown at the ingest boundary. Carries locations and kinds only, never the
 * offending values, so it stays safe to log.
 */
export class PiiRejectedError extends Error {
  readonly problems: RowScan[];

  constructor(problems: RowScan[]) {
    const kinds = new Set(problems.flatMap((p) => p.findings.map((f) => f.kind)));
    super(
      `Upload rejected: personal data detected (${[...kinds].join(", ")}) in ` +
        `${problems.length} location(s). Resonance analyses copy and aggregate ` +
        `metrics only and does not accept personal data.`,
    );
    this.name = "PiiRejectedError";
    this.problems = problems;
  }
}

/** Ingest gate. Call before anything is persisted. */
export function assertNoPii(rows: Record<string, unknown>[]): void {
  const { clean, problems } = scanRows(rows);
  if (!clean) throw new PiiRejectedError(problems);
}
