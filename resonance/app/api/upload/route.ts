/**
 * POST /api/upload, validate a campaign export.
 *
 * This route validates and reports. It does NOT persist: storage requires the
 * tenant context and audit wiring from lib/safety, and a route that writes
 * before that exists is how client data ends up somewhere nobody audited.
 * Persistence lands with Phase 4 recalibration.
 *
 * PII is rejected here, before any storage path is reachable.
 */

import { PiiRejectedError } from "@/lib/safety/pii";
import { previewUpload, validateUpload } from "@/lib/upload";

export const runtime = "nodejs";

/** Roughly 20k rows of typical campaign export. */
const MAX_BYTES = 5_000_000;

export async function POST(request: Request) {
  let body: { csv?: unknown; mode?: unknown };
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Body must be JSON." }, { status: 400 });
  }

  if (typeof body.csv !== "string" || !body.csv.trim()) {
    return Response.json({ error: "Supply a CSV in `csv`." }, { status: 400 });
  }
  if (body.csv.length > MAX_BYTES) {
    return Response.json(
      { error: `File exceeds ${MAX_BYTES / 1_000_000} MB.` },
      { status: 413 },
    );
  }

  // Preview mode reports problems without throwing, so a user can fix a file
  // rather than being told only that it failed.
  if (body.mode === "preview") {
    const r = previewUpload(body.csv);
    return Response.json({
      rows: r.rows.length,
      issues: r.issues.slice(0, 50),
      issueCount: r.issues.length,
      readiness: r.readiness,
      piiProblems: r.piiProblems.slice(0, 50).map((p) => ({
        row: p.row,
        column: p.column,
        // Kinds only, never the matched values.
        kinds: [...new Set(p.findings.map((f) => f.kind))],
      })),
      piiCount: r.piiProblems.length,
    });
  }

  try {
    const r = validateUpload(body.csv);
    return Response.json({
      accepted: true,
      rows: r.rows.length,
      issues: r.issues.slice(0, 50),
      issueCount: r.issues.length,
      readiness: r.readiness,
      note:
        "Compatibility check only. The file was parsed in memory and " +
        "discarded; nothing was stored. This endpoint does not fit a model, " +
        "per-tenant recalibration is not built.",
    });
  } catch (e) {
    if (e instanceof PiiRejectedError) {
      return Response.json(
        {
          error: e.message,
          problems: e.problems.slice(0, 50).map((p) => ({
            row: p.row,
            column: p.column,
            kinds: [...new Set(p.findings.map((f) => f.kind))],
          })),
        },
        { status: 422 },
      );
    }
    return Response.json(
      { error: e instanceof Error ? e.message : "Upload failed." },
      { status: 400 },
    );
  }
}
