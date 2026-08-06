"use client";

import { useState } from "react";
import type { AnalysisResult, VariantComparison } from "@/lib/analyse";

type ApiResponse =
  | { mode: "single"; result: AnalysisResult }
  | { mode: "compare"; result: VariantComparison };

const GENDERS = ["all", "male", "female"] as const;
const AGES = ["all", "younger", "older"] as const;
const EDUCATIONS = ["all", "lower", "higher"] as const;
const INVOLVEMENTS = ["unknown", "high", "low"] as const;

const INVOLVEMENT_HELP: Record<string, string> = {
  unknown: "Not specified — no elaboration adjustment applied.",
  high: "Considered, higher-cost purchases (cars, software, insurance).",
  low: "Habitual, low-cost purchases (snacks, toiletries).",
};

/**
 * Bar scaled to the module's ACTUAL range, supplied by the analysis.
 *
 * Modules do not share a 0-1 range: `approach` is signed, and `encoding` is
 * amplified by constraint C2 so it routinely exceeds 1. Assuming 0-1 clipped
 * encoding to a full bar regardless of value — invisible to unit tests, obvious
 * the moment it rendered.
 */
function ModuleBar({ value, range }: { value: number; range: [number, number] }) {
  const [lo, hi] = range;
  const pct = ((value - lo) / (hi - lo)) * 100;
  return (
    <div className="h-2 w-full overflow-hidden rounded-full bg-zinc-200 dark:bg-zinc-800">
      <div
        className="h-full rounded-full bg-zinc-900 dark:bg-zinc-100"
        style={{ width: `${Math.max(0, Math.min(100, pct))}%` }}
      />
    </div>
  );
}

export default function AnalysePage() {
  const [text, setText] = useState("");
  const [gender, setGender] = useState<(typeof GENDERS)[number]>("all");
  const [age, setAge] = useState<(typeof AGES)[number]>("all");
  const [education, setEducation] = useState<(typeof EDUCATIONS)[number]>("all");
  const [involvement, setInvolvement] =
    useState<(typeof INVOLVEMENTS)[number]>("unknown");
  const [result, setResult] = useState<AnalysisResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function run() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/analyse", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({
          variants: [text],
          segment: { gender, age, education, involvement },
        }),
      });
      const data = (await res.json()) as ApiResponse | { error: string };
      if (!res.ok) {
        setError("error" in data ? data.error : "Analysis failed.");
        setResult(null);
        return;
      }
      if ("mode" in data && data.mode === "single") setResult(data.result);
    } catch {
      setError("Could not reach the analysis service.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Analyse copy</h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Scores your copy on six constructs drawn from published behavioural
          research. Every score traces back to human word ratings, and every
          module carries its own limitation.
        </p>
      </div>

      <section className="space-y-4">
        <textarea
          value={text}
          onChange={(e) => setText(e.target.value)}
          rows={5}
          placeholder="Paste your headline or ad copy…"
          className="w-full rounded-lg border border-zinc-300 bg-white p-3 text-sm dark:border-zinc-700 dark:bg-zinc-900"
        />

        <div className="grid gap-4 sm:grid-cols-4">
          <label className="text-sm">
            <span className="mb-1 block text-zinc-600 dark:text-zinc-400">
              Involvement
            </span>
            <select
              value={involvement}
              onChange={(e) =>
                setInvolvement(e.target.value as (typeof INVOLVEMENTS)[number])
              }
              className="w-full rounded-md border border-zinc-300 bg-white p-2 dark:border-zinc-700 dark:bg-zinc-900"
            >
              {INVOLVEMENTS.map((v) => (
                <option key={v} value={v}>
                  {v}
                </option>
              ))}
            </select>
          </label>

          {(
            [
              ["Gender", gender, setGender, GENDERS],
              ["Age", age, setAge, AGES],
              ["Education", education, setEducation, EDUCATIONS],
            ] as const
          ).map(([label, value, setter, options]) => (
            <label key={label} className="text-sm">
              <span className="mb-1 block text-zinc-600 dark:text-zinc-400">
                {label}
              </span>
              <select
                value={value}
                onChange={(e) => (setter as (v: string) => void)(e.target.value)}
                className="w-full rounded-md border border-zinc-300 bg-white p-2 dark:border-zinc-700 dark:bg-zinc-900"
              >
                {options.map((v) => (
                  <option key={v} value={v}>
                    {v}
                  </option>
                ))}
              </select>
            </label>
          ))}
        </div>

        <p className="text-xs text-zinc-500 dark:text-zinc-400">
          {INVOLVEMENT_HELP[involvement]} Involvement is the best-supported
          adjustment here; the demographic axes move scores less than the noise
          floor and are shown for context rather than prediction.
        </p>

        <button
          onClick={run}
          disabled={busy || !text.trim()}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {busy ? "Analysing…" : "Analyse"}
        </button>

        {error && (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        )}
      </section>

      {result && (
        <section className="space-y-6">
          {result.warnings.length > 0 && (
            <ul className="space-y-2 rounded-lg bg-amber-50 p-4 text-sm text-amber-900 dark:bg-amber-950 dark:text-amber-200">
              {result.warnings.map((w) => (
                <li key={w}>{w}</li>
              ))}
            </ul>
          )}

          <div className="space-y-5">
            {result.modules.map((m) => (
              <div key={m.id} className="space-y-1.5">
                <div className="flex items-baseline justify-between gap-4">
                  <span className="text-sm font-medium">{m.label}</span>
                  <span className="font-mono text-sm tabular-nums">
                    {m.score.toFixed(3)}
                    {m.verdict !== "n/a" && (
                      <span className="ml-2 text-xs text-zinc-500">
                        {m.verdict}
                      </span>
                    )}
                  </span>
                </div>
                <ModuleBar value={m.score} range={m.displayRange} />
                <p className="text-xs text-zinc-600 dark:text-zinc-400">
                  {m.definition.short}
                </p>
                <p className="text-xs text-zinc-500 dark:text-zinc-500">
                  <span className="font-medium">Limitation:</span>{" "}
                  {m.definition.caveat}
                </p>
                <details className="text-xs text-zinc-500">
                  <summary className="cursor-pointer">Sources</summary>
                  <ul className="mt-1 list-disc space-y-0.5 pl-4">
                    {m.definition.sources.map((s) => (
                      <li key={s}>{s}</li>
                    ))}
                  </ul>
                </details>
              </div>
            ))}
          </div>

          <div className="space-y-2 rounded-lg border border-zinc-200 p-4 text-xs text-zinc-600 dark:border-zinc-800 dark:text-zinc-400">
            <p>{result.segment.disclosure}</p>
            <p>
              Dictionary coverage {Math.round(result.coverage * 100)}% ·{" "}
              {result.wordCount} words · diagnostic layer accuracy{" "}
              {(result.provenance.modelAccuracy * 100).toFixed(1)}% (chance{" "}
              {result.provenance.chance * 100}%, measured ceiling{" "}
              {(result.provenance.ceiling * 100).toFixed(1)}%)
            </p>
            <p>Trained on {result.provenance.trainingData}.</p>
          </div>
        </section>
      )}
    </div>
  );
}
