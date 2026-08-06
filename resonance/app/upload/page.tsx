"use client";

import { useState } from "react";

interface Readiness {
  eligible: boolean;
  campaignCount: number;
  required: number;
  shrinkage: number;
  message: string;
}

interface PreviewResponse {
  rows: number;
  issues: { row: number; problem: string }[];
  issueCount: number;
  readiness: Readiness;
  piiProblems: { row: number; column: string; kinds: string[] }[];
  piiCount: number;
}

const SAMPLE = `copy,impressions,clicks,segment
"Cut your heating bill with one simple change",12500,168,25-34 female
"Save 20% on energy this winter",9800,121,25-34 female
"The heating fix most homes miss",11200,171,35-44 male`;

export default function UploadPage() {
  const [csv, setCsv] = useState("");
  const [result, setResult] = useState<PreviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function onFile(file: File) {
    setCsv(await file.text());
    setResult(null);
    setError(null);
  }

  async function check() {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("/api/upload", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ csv, mode: "preview" }),
      });
      const data = await res.json();
      if (!res.ok) {
        setError(data.error ?? "Check failed.");
        setResult(null);
        return;
      }
      setResult(data as PreviewResponse);
    } catch {
      setError("Could not reach the upload service.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Upload campaign results
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          The model is trained on 2013–15 viral media, which is probably not your
          audience. Your own campaign results replace those assumptions with
          measurements. Meta and Google both export the columns needed.
        </p>
      </div>

      <section className="space-y-3 rounded-lg border border-zinc-200 p-4 text-sm dark:border-zinc-800">
        <h2 className="font-medium">Expected columns</h2>
        <ul className="list-disc space-y-1 pl-5 text-zinc-600 dark:text-zinc-400">
          <li>
            <code className="font-mono text-xs">copy</code> — the ad text
            (aliases: headline, text, creative)
          </li>
          <li>
            <code className="font-mono text-xs">impressions</code> — aliases:
            impr, views, reach
          </li>
          <li>
            <code className="font-mono text-xs">clicks</code> — aliases: link
            clicks
          </li>
          <li>
            <code className="font-mono text-xs">segment</code> — optional; age
            bracket or gender, as your platform exports it
          </li>
        </ul>
        <p className="text-zinc-500">
          Rows below 500 impressions are skipped: the click-through estimate on
          fewer is mostly sampling noise.
        </p>
        <p className="rounded bg-zinc-100 p-3 text-xs text-zinc-700 dark:bg-zinc-900 dark:text-zinc-300">
          <strong>No personal data.</strong> Files containing emails, phone
          numbers, addresses, IPs or card numbers are rejected outright — not
          stored and stripped. This tool needs aggregate copy performance and
          nothing about individuals.
        </p>
      </section>

      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <input
            type="file"
            accept=".csv,text/csv"
            onChange={(e) => {
              const f = e.target.files?.[0];
              if (f) void onFile(f);
            }}
            className="text-sm"
          />
          <button
            onClick={() => setCsv(SAMPLE)}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700"
          >
            Use sample
          </button>
        </div>

        <textarea
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
          rows={8}
          placeholder="…or paste CSV here"
          className="w-full rounded-lg border border-zinc-300 bg-white p-3 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-900"
        />

        <button
          onClick={check}
          disabled={busy || !csv.trim()}
          className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900"
        >
          {busy ? "Checking…" : "Check file"}
        </button>

        {error && (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            {error}
          </p>
        )}
      </section>

      {result && (
        <section className="space-y-5">
          {result.piiCount > 0 && (
            <div className="rounded-lg border border-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-200">
              <p className="font-medium">
                Personal data found in {result.piiCount} location
                {result.piiCount === 1 ? "" : "s"} — this file would be rejected
              </p>
              <ul className="mt-2 space-y-1 text-xs">
                {result.piiProblems.map((p) => (
                  <li key={`${p.row}-${p.column}`}>
                    Row {p.row}, column <code>{p.column}</code>:{" "}
                    {p.kinds.join(", ")}
                  </li>
                ))}
              </ul>
              <p className="mt-2 text-xs">
                Locations only — the detected values are never echoed back.
              </p>
            </div>
          )}

          <div
            className={`rounded-lg p-4 text-sm ${
              result.readiness.eligible
                ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
                : "bg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200"
            }`}
          >
            <p className="font-medium">
              {result.rows} usable row{result.rows === 1 ? "" : "s"} ·{" "}
              {result.readiness.campaignCount} campaign
              {result.readiness.campaignCount === 1 ? "" : "s"}
            </p>
            <p className="mt-1">{result.readiness.message}</p>
            {!result.readiness.eligible && (
              <div className="mt-3">
                <div className="h-2 w-full overflow-hidden rounded-full bg-black/10 dark:bg-white/10">
                  <div
                    className="h-full rounded-full bg-current opacity-70"
                    style={{
                      width: `${Math.min(
                        100,
                        (result.readiness.campaignCount /
                          result.readiness.required) *
                          100,
                      )}%`,
                    }}
                  />
                </div>
                <p className="mt-1 text-xs">
                  {result.readiness.campaignCount} of{" "}
                  {result.readiness.required} campaigns toward your own fitted
                  model
                </p>
              </div>
            )}
          </div>

          {result.issueCount > 0 && (
            <details className="rounded-lg border border-zinc-200 p-4 text-sm dark:border-zinc-800">
              <summary className="cursor-pointer font-medium">
                {result.issueCount} row{result.issueCount === 1 ? "" : "s"}{" "}
                skipped
              </summary>
              <ul className="mt-3 space-y-1 text-xs text-zinc-600 dark:text-zinc-400">
                {result.issues.map((i) => (
                  <li key={i.row}>
                    Row {i.row}: {i.problem}
                  </li>
                ))}
              </ul>
            </details>
          )}

          <p className="text-xs text-zinc-500">
            Validation only — nothing has been stored. Persistence and
            recalibration arrive with per-tenant model fitting.
          </p>
        </section>
      )}
    </div>
  );
}
