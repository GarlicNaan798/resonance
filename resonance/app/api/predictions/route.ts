/**
 * GET   /api/predictions  — the log and the track record
 * POST  /api/predictions  — seal a prediction before launch
 * PATCH /api/predictions  — record which variant actually won
 *
 * This is the only route in the app that writes to disk. Everything else
 * analyses and discards. It writes locally and nowhere else: see
 * lib/predictions.ts for the storage, and docs/SELF_HOSTING.md for the claim
 * that nothing leaves the machine.
 */

import {
  commitPrediction,
  listPredictions,
  recordOutcome,
  trackRecord,
  verifySeal,
  type ConfidenceTier,
} from "@/lib/predictions";
import { scanText } from "@/lib/safety/pii";

export const runtime = "nodejs";

const MAX_CHARS = 5000;
const MAX_VARIANTS = 8;
const TIERS = ["high", "moderate", "insufficient"] as const;

export async function GET() {
  const predictions = await listPredictions();
  return Response.json({
    // Seal verification is reported per row rather than assumed. If the file
    // was hand-edited the user should see that, not a quietly wrong record.
    predictions: predictions.map((p) => ({ ...p, sealValid: verifySeal(p) })),
    track: trackRecord(predictions),
  });
}

export async function POST(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Body must be JSON." }, { status: 400 });
  }

  const variants = body.variants;
  if (
    !Array.isArray(variants) ||
    variants.length < 2 ||
    variants.length > MAX_VARIANTS ||
    !variants.every((v) => typeof v === "string" && v.trim())
  ) {
    return Response.json(
      { error: `Supply 2–${MAX_VARIANTS} non-empty variants.` },
      { status: 400 },
    );
  }
  if (variants.some((v: string) => v.length > MAX_CHARS)) {
    return Response.json(
      { error: `Each variant must be under ${MAX_CHARS} characters.` },
      { status: 400 },
    );
  }

  // Persistence is a trust boundary the rest of the app does not have. Copy
  // that was previously analysed and thrown away is about to be written to
  // disk, so it gets scanned here even though /api/analyse already scanned it.
  for (const v of variants as string[]) {
    const { clean, findings } = scanText(v);
    if (!clean) {
      return Response.json(
        {
          // Kinds only — the matched values are never echoed back.
          error:
            "Personal data detected in a variant: " +
            `${[...new Set(findings.map((f) => f.kind))].join(", ")}. ` +
            "Nothing was stored.",
        },
        { status: 422 },
      );
    }
  }

  const predictedWinner = body.predictedWinner;
  if (
    typeof predictedWinner !== "number" ||
    !Number.isInteger(predictedWinner) ||
    predictedWinner < 0 ||
    predictedWinner >= variants.length
  ) {
    return Response.json(
      { error: "predictedWinner must be a valid variant index." },
      { status: 400 },
    );
  }

  const userPick = body.userPick;
  if (
    userPick !== null &&
    userPick !== undefined &&
    (typeof userPick !== "number" ||
      !Number.isInteger(userPick) ||
      userPick < 0 ||
      userPick >= variants.length)
  ) {
    return Response.json(
      { error: "userPick must be null or a valid variant index." },
      { status: 400 },
    );
  }

  const tier = TIERS.includes(body.tier as (typeof TIERS)[number])
    ? (body.tier as ConfidenceTier)
    : "insufficient";

  const prediction = await commitPrediction({
    variants: variants as string[],
    predictedWinner,
    tier,
    margin: typeof body.margin === "number" ? body.margin : 0,
    userPick: typeof userPick === "number" ? userPick : null,
    label: typeof body.label === "string" ? body.label.slice(0, 120) : undefined,
  });

  return Response.json({ prediction }, { status: 201 });
}

export async function PATCH(request: Request) {
  let body: Record<string, unknown>;
  try {
    body = await request.json();
  } catch {
    return Response.json({ error: "Body must be JSON." }, { status: 400 });
  }

  if (typeof body.id !== "string" || !body.id) {
    return Response.json({ error: "Supply the prediction `id`." }, { status: 400 });
  }
  if (typeof body.actualWinner !== "number" || !Number.isInteger(body.actualWinner)) {
    return Response.json(
      { error: "actualWinner must be a variant index." },
      { status: 400 },
    );
  }

  try {
    const prediction = await recordOutcome(body.id, body.actualWinner);
    return Response.json({ prediction });
  } catch (err) {
    // Write-once outcomes and unknown ids are user errors, not server faults.
    return Response.json({ error: (err as Error).message }, { status: 409 });
  }
}
