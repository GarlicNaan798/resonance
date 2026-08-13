"use client";

import { useState } from "react";
import Link from "next/link";
import type { AnalysisResult } from "@/lib/analyse";
import type { RankingResult } from "@/lib/inference/ranker";
import { PERFORMANCE } from "@/lib/constructs";

interface GuardrailEntry {
  index: number;
  risks: { kind: string; severity: number; message: string; evidence: string }[];
  maxSeverity: number;
}

interface CompareResult {
  ranking: RankingResult;
  profiles: AnalysisResult[];
  guardrails: GuardrailEntry[];
  caution: string | null;
  separation: string;
}

const EMPTY = ["", ""];

export default function ComparePage() {
  const [variants, setVariants] = useState<string[]>(EMPTY);
  const [result, setResult] = useState<CompareResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  /** Chosen before the model runs, or it is worthless as a comparison. */
  const [userPick, setUserPick] = useState<number | null>(null);
  const [label, setLabel] = useState("");
  const [sealed, setSealed] = useState<{ hash: string } | null>(null);
  const [sealing, setSealing] = useState(false);

  const filled = variants.filter((v) => v.trim()).length;

  function setAt(i: number, value: string) {
    setVariants((prev) => prev.map((v, j) => (j === i ? value : v)));
  }

  async function seal() {
    if (!result) return;
    setSealing(true);
    setError(null);
    try {
      const res = await fetch("/api/predictions", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          variants: variants.filter((v) => v.trim()),
          predictedWinner: result.ranking.ranked[0].index,
          tier: result.ranking.tier,
          margin:
            result.ranking.ranked[0].score - (result.ranking.ranked[1]?.score ?? 0),
          userPick,
          label: label.trim() || undefined,
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "Could not seal the prediction.");
        return;
      }
      setSealed({ hash: data.prediction.hash });
    } catch {
      setError("Could not seal the prediction.");
    } finally {
      setSealing(false);
    }
  }

  async function run() {
    setBusy(true);
    setError(null);
    setSealed(null);
    try {
      const res = await fetch("/api/analyse", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ variants, segment: {} }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "Comparison failed.");
        setResult(null);
        return;
      }
      setResult(data.result as CompareResult);
    } catch {
      setError("Could not reach the analysis service.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <p className="eyebrow">Rank</p>
        <h1 className="display text-3xl sm:text-4xl">Compare variants</h1>
        <p className="mt-2 text-sm text-muted">
          Ranks your variants using the model trained on 32,487 randomised A/B
          tests. It is right {(PERFORMANCE.rankerAccuracy * 100).toFixed(1)}% of
          the time against a 50% baseline — an edge worth having before you
          spend media budget, not a substitute for testing.
        </p>
      </div>

      <section className="space-y-3">
        {variants.map((v, i) => (
          <div key={i} className="flex gap-2">
            <span className="mt-2.5 w-6 shrink-0 text-sm text-faint">
              {i + 1}
            </span>
            <textarea
              value={v}
              onChange={(e) => setAt(i, e.target.value)}
              rows={2}
              placeholder={`Variant ${i + 1}`}
              className="w-full rounded-lg border border-rule-strong bg-surface p-3 text-sm"
            />
          </div>
        ))}

        {/* Collected BEFORE the model runs and locked afterwards. A pick made
            after seeing the answer measures nothing, so the UI makes the blind
            version the only one available. */}
        <div className="flex flex-wrap items-center gap-2 rounded-lg border border-dashed border-rule-strong p-3 text-sm">
          <span className="text-muted">
            Optional — your own pick first:
          </span>
          {variants.map((_, i) => (
            <button
              key={i}
              disabled={!!result}
              onClick={() => setUserPick(userPick === i ? null : i)}
              className={`rounded-md border px-2.5 py-1 text-xs disabled:opacity-50 ${
                userPick === i
                  ? "border-ink bg-ink text-inverse"
                  : "border-rule-strong"
              }`}
            >
              {i + 1}
            </button>
          ))}
          <span className="text-xs text-faint">
            {result
              ? "Locked — the model has run."
              : "Scored against the model on your track record."}
          </span>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={() => setVariants((p) => [...p, ""])}
            disabled={variants.length >= 8}
            className="rounded-md border border-rule-strong px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Add variant
          </button>
          <button
            onClick={run}
            disabled={busy || filled < 2}
            className="btn btn-primary disabled:opacity-40"
          >
            {busy ? "Ranking…" : "Rank variants"}
          </button>
          {filled < 2 && (
            <span className="text-xs text-faint">
              Enter at least two variants.
            </span>
          )}
        </div>

        {error && (
          <p className="rounded-md bg-pale-red p-3 text-sm text-pale-red-ink">
            {error}
          </p>
        )}
      </section>

      {result && (
        <section className="space-y-6">
          <div
            className={`rounded-lg p-4 text-sm ${
              result.ranking.confident
                ? "bg-pale-green text-pale-green-ink"
                : "bg-pale-yellow text-pale-yellow-ink"
            }`}
          >
            {result.ranking.guidance}
          </div>

          {/* Surfaced ABOVE the ranking: if the top pick is the riskiest, the
              user should see that before reading the recommendation. */}
          {result.caution && (
            <div className="rounded-lg border border-rule bg-pale-yellow p-4 text-sm text-pale-yellow-ink">
              <p className="font-medium">Check this before acting</p>
              <p className="mt-1">{result.caution}</p>
            </div>
          )}

          <ol className="space-y-3">
            {result.ranking.ranked.map((r, position) => {
              const guard = result.guardrails.find((g) => g.index === r.index);
              return (
                <li
                  key={r.index}
                  className="card p-5"
                >
                  <div className="flex items-baseline justify-between gap-4">
                    <span className="text-sm font-medium">
                      {position === 0 && result.ranking.confident
                        ? "Recommended"
                        : `Rank ${position + 1}`}{" "}
                      · Variant {r.index + 1}
                    </span>
                    <span className="font-mono text-xs tabular-nums text-faint">
                      {r.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-muted">
                    {r.text}
                  </p>

                  {guard && guard.risks.length > 0 && (
                    <ul className="mt-3 space-y-2 border-t border-rule pt-3 text-xs">
                      {guard.risks.map((risk) => (
                        <li key={risk.kind}>
                          <span className="font-medium text-pale-red-ink">
                            {risk.kind}
                          </span>{" "}
                          <span className="text-muted">
                            {risk.message}
                          </span>
                          <span className="mt-0.5 block text-faint">
                            {risk.evidence}
                          </span>
                        </li>
                      ))}
                    </ul>
                  )}
                </li>
              );
            })}
          </ol>

          {/* The separation between the two layers is stated, not implied. */}
          <div className="space-y-2 card p-5 text-xs text-muted">
            <p className="font-medium text-ink">
              How to read this
            </p>
            <p>{result.separation}</p>
            <p>
              <strong>Confidence: {result.ranking.tier}.</strong>{" "}
              {result.ranking.tier === "insufficient" ? (
                <>
                  The margin here is too small for a reliable call. Across all
                  comparisons the model averages{" "}
                  {(result.ranking.accuracy * 100).toFixed(1)}%, but that average
                  is carried by the clear-cut cases — not this one.
                </>
              ) : (
                <>
                  Comparisons at this margin are decided correctly{" "}
                  {(result.ranking.tierAccuracy * 100).toFixed(0)}% of the time,
                  measured on held-out experiments. About{" "}
                  {(result.ranking.tierCoverage * 100).toFixed(0)}% of
                  comparisons reach this level; the overall average across all
                  comparisons is {(result.ranking.accuracy * 100).toFixed(1)}%.
                </>
              )}
            </p>
            <p>
              Baseline 50%; measured ceiling{" "}
              {(result.ranking.ceiling * 100).toFixed(1)}% across all pairs. The
              ceiling is below 100% because the training labels are themselves
              noisy measurements.
            </p>
            <p>
              Scores are comparable only within this comparison and carry no
              absolute meaning.
            </p>
          </div>

          {/* The loop-closing step: fix the prediction before the campaign
              runs, so the track record cannot be assembled from hindsight. */}
          <div className="space-y-3 card p-5">
            <h2 className="text-sm font-medium">Seal this prediction</h2>
            {sealed ? (
              <div className="space-y-2 text-sm">
                <p className="text-pale-green-ink">
                  Sealed. Record the winner on your{" "}
                  <Link href="/track" className="underline">
                    track record
                  </Link>{" "}
                  once the campaign resolves.
                </p>
                <p className="text-xs text-muted">
                  Send this hash to your client now and it proves afterwards
                  that the call was made before the result was known:
                </p>
                <code className="block overflow-x-auto rounded bg-sunk p-2 font-mono text-xs">
                  {sealed.hash}
                </code>
              </div>
            ) : (
              <>
                <p className="text-sm text-muted">
                  Stores this comparison locally so you can record the real
                  winner later and find out whether the model is right on your
                  campaigns — not on 2013–15 viral media.
                </p>
                <div className="flex flex-wrap items-center gap-2">
                  <input
                    value={label}
                    onChange={(e) => setLabel(e.target.value)}
                    placeholder="Campaign name (optional)"
                    className="flex-1 rounded-md border border-rule-strong bg-surface px-3 py-1.5 text-sm"
                  />
                  <button
                    onClick={seal}
                    disabled={sealing}
                    className="rounded-md border border-rule-strong px-3 py-1.5 text-sm font-medium disabled:opacity-40"
                  >
                    {sealing ? "Sealing…" : "Seal prediction"}
                  </button>
                </div>
                <p className="text-xs text-faint">
                  Written to disk on this machine only. Nothing is sent
                  anywhere.
                </p>
              </>
            )}
          </div>

          <details className="card p-5">
            <summary className="cursor-pointer text-sm font-medium">
              Behavioural profiles (separate diagnostic layer)
            </summary>
            <div className="mt-4 space-y-4">
              {result.profiles.map((p, i) => (
                <div key={i} className="space-y-1">
                  <p className="text-xs font-medium">Variant {i + 1}</p>
                  <div className="grid grid-cols-2 gap-x-6 gap-y-1 text-xs sm:grid-cols-3">
                    {p.modules.map((m) => (
                      <div key={m.id} className="flex justify-between gap-2">
                        <span className="text-muted">
                          {m.label}
                        </span>
                        <span className="font-mono tabular-nums">
                          {m.score.toFixed(2)}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
              <p className="text-xs text-faint">
                These come from a different, weaker model (53.5% accuracy) and do
                not explain the ranking above.
              </p>
            </div>
          </details>
        </section>
      )}
    </div>
  );
}
