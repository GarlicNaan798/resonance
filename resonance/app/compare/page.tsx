"use client";

import { useState } from "react";
import type { AnalysisResult } from "@/lib/analyse";
import type { RankingResult } from "@/lib/inference/ranker";

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

  const filled = variants.filter((v) => v.trim()).length;

  function setAt(i: number, value: string) {
    setVariants((prev) => prev.map((v, j) => (j === i ? value : v)));
  }

  async function run() {
    setBusy(true);
    setError(null);
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
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Compare variants</h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Ranks your variants using the model trained on 32,487 randomised A/B
          tests. It is right about 59% of the time against a 50% baseline — an
          edge worth having before you spend media budget, not a substitute for
          testing.
        </p>
      </div>

      <section className="space-y-3">
        {variants.map((v, i) => (
          <div key={i} className="flex gap-2">
            <span className="mt-2.5 w-6 shrink-0 text-sm text-zinc-500">
              {i + 1}
            </span>
            <textarea
              value={v}
              onChange={(e) => setAt(i, e.target.value)}
              rows={2}
              placeholder={`Variant ${i + 1}`}
              className="w-full rounded-lg border border-zinc-300 bg-white p-3 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
          </div>
        ))}

        <div className="flex items-center gap-3">
          <button
            onClick={() => setVariants((p) => [...p, ""])}
            disabled={variants.length >= 8}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-zinc-700"
          >
            Add variant
          </button>
          <button
            onClick={run}
            disabled={busy || filled < 2}
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
          >
            {busy ? "Ranking…" : "Rank variants"}
          </button>
          {filled < 2 && (
            <span className="text-xs text-zinc-500">
              Enter at least two variants.
            </span>
          )}
        </div>

        {error && (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        )}
      </section>

      {result && (
        <section className="space-y-6">
          <div
            className={`rounded-lg p-4 text-sm ${
              result.ranking.confident
                ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
                : "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
            }`}
          >
            {result.ranking.guidance}
          </div>

          {/* Surfaced ABOVE the ranking: if the top pick is the riskiest, the
              user should see that before reading the recommendation. */}
          {result.caution && (
            <div className="rounded-lg border border-orange-300 bg-orange-50 p-4 text-sm text-orange-900 dark:border-orange-800 dark:bg-orange-950 dark:text-orange-200">
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
                  className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
                >
                  <div className="flex items-baseline justify-between gap-4">
                    <span className="text-sm font-medium">
                      {position === 0 && result.ranking.confident
                        ? "Recommended"
                        : `Rank ${position + 1}`}{" "}
                      · Variant {r.index + 1}
                    </span>
                    <span className="font-mono text-xs tabular-nums text-zinc-500">
                      {r.score.toFixed(3)}
                    </span>
                  </div>
                  <p className="mt-2 text-sm text-zinc-700 dark:text-zinc-300">
                    {r.text}
                  </p>

                  {guard && guard.risks.length > 0 && (
                    <ul className="mt-3 space-y-2 border-t border-zinc-200 pt-3 text-xs dark:border-zinc-800">
                      {guard.risks.map((risk) => (
                        <li key={risk.kind}>
                          <span className="font-medium text-orange-700 dark:text-orange-300">
                            {risk.kind}
                          </span>{" "}
                          <span className="text-zinc-600 dark:text-zinc-400">
                            {risk.message}
                          </span>
                          <span className="mt-0.5 block text-zinc-500">
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
          <div className="space-y-2 rounded-lg border border-zinc-200 p-4 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
            <p className="font-medium text-zinc-800 dark:text-zinc-200">
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

          <details className="rounded-lg border border-zinc-200 p-4 dark:border-zinc-800">
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
                        <span className="text-zinc-600 dark:text-zinc-400">
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
              <p className="text-xs text-zinc-500">
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
