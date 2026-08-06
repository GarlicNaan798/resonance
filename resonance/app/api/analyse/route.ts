/**
 * POST /api/analyse
 *
 * Runs the diagnostic layer. Everything happens in-process — no ML service, no
 * outbound calls — which is what makes the self-hosted no-egress claim true.
 *
 * The copy submitted here is analysed and discarded. Nothing is persisted by
 * this route: campaign copy is the client's commercial property, and the
 * analysis needs no history to work.
 */

import { analyse } from "@/lib/analyse";
import { guardRanking } from "@/lib/guardrails";
import { rankVariants } from "@/lib/inference/ranker";
import { scanText } from "@/lib/safety/pii";
import type { SegmentSpec } from "@/lib/segments";

export const runtime = "nodejs";

/** Long enough for real ad copy, short enough to bound work per request. */
const MAX_CHARS = 5000;
const MAX_VARIANTS = 8;

interface RequestBody {
  variants?: unknown;
  segment?: unknown;
}

function parseSegment(input: unknown): SegmentSpec {
  const s = (input ?? {}) as Record<string, unknown>;
  const oneOf = <T extends string>(v: unknown, allowed: readonly T[], fallback: T): T =>
    typeof v === "string" && (allowed as readonly string[]).includes(v)
      ? (v as T)
      : fallback;

  return {
    gender: oneOf(s.gender, ["male", "female", "all"] as const, "all"),
    age: oneOf(s.age, ["younger", "older", "all"] as const, "all"),
    education: oneOf(s.education, ["lower", "higher", "all"] as const, "all"),
    involvement: oneOf(s.involvement, ["high", "low", "unknown"] as const, "unknown"),
  };
}

export async function POST(request: Request) {
  let body: RequestBody;
  try {
    body = (await request.json()) as RequestBody;
  } catch {
    return Response.json({ error: "Body must be JSON." }, { status: 400 });
  }

  if (!Array.isArray(body.variants)) {
    return Response.json(
      { error: "`variants` must be an array of strings." },
      { status: 400 },
    );
  }

  const variants = body.variants
    .filter((v): v is string => typeof v === "string")
    .map((v) => v.trim())
    .filter(Boolean);

  if (variants.length === 0) {
    return Response.json({ error: "No copy supplied." }, { status: 400 });
  }
  if (variants.length > MAX_VARIANTS) {
    return Response.json(
      { error: `At most ${MAX_VARIANTS} variants per request.` },
      { status: 400 },
    );
  }
  for (const v of variants) {
    if (v.length > MAX_CHARS) {
      return Response.json(
        { error: `Each variant must be under ${MAX_CHARS} characters.` },
        { status: 400 },
      );
    }
  }

  // PII check applies to analysis too, not just uploads. Copy pasted from a CRM
  // export can carry customer details, and this route must not become the way
  // personal data enters logs or error traces.
  for (let i = 0; i < variants.length; i++) {
    const { clean, findings } = scanText(variants[i]);
    if (!clean) {
      const kinds = [...new Set(findings.map((f) => f.kind))];
      return Response.json(
        {
          error:
            `Variant ${i + 1} appears to contain personal data ` +
            `(${kinds.join(", ")}). Remove it before analysing.`,
          // Kinds only — never the matched values.
          kinds,
        },
        { status: 422 },
      );
    }
  }

  const segment = parseSegment(body.segment);

  try {
    if (variants.length === 1) {
      return Response.json({ mode: "single", result: analyse(variants[0], segment) });
    }

    // Two layers, computed separately and reported separately.
    //
    // The RANKING comes from the embedding ranker (0.5942) — the strong model.
    // The PROFILES come from the module model (0.5346) and are diagnostic only.
    // The profile does not explain the ranking: the ranker never sees these
    // features. Presenting one as the other would be post-hoc rationalisation,
    // so the response keeps them as distinct fields.
    const ranking = await rankVariants(variants);
    const profiles = variants.map((v) => analyse(v, segment));

    // The ranker's encoder is uncased, so it cannot see shouting at all. The
    // guardrail applies the evidence it is blind to WITHOUT reordering the
    // result — silently overriding a model makes the system impossible to
    // reason about. The caution is surfaced beside the recommendation instead.
    const { guarded, caution } = guardRanking(ranking.ranked);

    return Response.json({
      mode: "compare",
      result: {
        ranking,
        profiles,
        guardrails: guarded.map((g) => ({
          index: g.item.index,
          risks: g.guardrail.risks,
          maxSeverity: g.guardrail.maxSeverity,
        })),
        caution,
        separation:
          "The ranking comes from a semantic model; the profiles come from a " +
          "separate behavioural model. The profile is not the explanation for " +
          "the ranking.",
      },
    });
  } catch (e) {
    return Response.json(
      { error: e instanceof Error ? e.message : "Analysis failed." },
      { status: 400 },
    );
  }
}
