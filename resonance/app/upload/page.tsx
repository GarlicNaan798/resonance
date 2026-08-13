"use client";

import Link from "next/link";
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
        <p className="eyebrow">Check</p>
        <h1 className="display text-3xl sm:text-4xl">
          Check your campaign export
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-muted">
          Tells you whether a Meta or Google export is readable, how many
          campaigns in it clear the noise floor, and whether it contains
          personal data that would have to be refused. Nothing is uploaded,
          stored or sent anywhere — the file is parsed in place and discarded.
        </p>
        <div className="mt-4 max-w-2xl rounded-lg border border-rule bg-pale-yellow p-4 text-sm text-pale-yellow-ink">
          <strong>This does not fit a model to your data.</strong> Per-tenant
          recalibration is not built, and this page will not pretend otherwise.
          It is a compatibility check, so you can find out now whether your
          exports would be usable later. To measure the model against your own
          campaigns today, use{" "}
          <Link href="/track" className="underline underline-offset-4">
            Track record
          </Link>{" "}
          — that works, and needs no export at all.
        </div>
      </div>

      <section className="space-y-3 card p-5 text-sm">
        <h2 className="font-medium">Drop your export in as-is</h2>
        <p className="text-muted">
          Meta Ads Manager and Google Ads exports are read directly — no
          renaming columns, no reformatting. We look for the ad text,
          impressions and clicks under whatever your platform calls them
          (Meta uses <code className="font-mono text-xs">Title</code> and{" "}
          <code className="font-mono text-xs">Body</code>; Google uses{" "}
          <code className="font-mono text-xs">Headline 1</code> and{" "}
          <code className="font-mono text-xs">Impr.</code>).
        </p>
        <p className="text-muted">
          A hand-made CSV works too: any columns named roughly{" "}
          <code className="font-mono text-xs">copy</code>,{" "}
          <code className="font-mono text-xs">impressions</code> and{" "}
          <code className="font-mono text-xs">clicks</code>, plus an optional{" "}
          <code className="font-mono text-xs">segment</code> for age bracket or
          gender.
        </p>
        <p className="text-faint">
          Rows below 500 impressions are skipped: the click-through estimate on
          fewer is mostly sampling noise.
        </p>
        <p className="rounded bg-sunk p-3 text-xs text-muted">
          <strong>No personal data.</strong> Files containing emails, phone
          numbers, addresses, IPs or card numbers are rejected outright, rather
          than stored and then stripped. This tool needs aggregate copy
          performance and nothing about individuals.
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
            className="rounded-md border border-rule-strong px-3 py-1.5 text-sm-strong"
          >
            Use sample
          </button>
        </div>

        <textarea
          value={csv}
          onChange={(e) => setCsv(e.target.value)}
          rows={8}
          placeholder="…or paste CSV here"
          className="w-full rounded-lg border border-rule-strong bg-surface p-3 font-mono text-xs"
        />

        <button
          onClick={check}
          disabled={busy || !csv.trim()}
          className="btn btn-primary disabled:opacity-40"
        >
          {busy ? "Checking…" : "Check file"}
        </button>

        {error && (
          <p className="rounded-md bg-pale-red p-3 text-sm text-pale-red-ink">
            {error}
          </p>
        )}
      </section>

      {result && (
        <section className="space-y-5">
          {result.piiCount > 0 && (
            <div className="rounded-lg border border-rule bg-pale-red p-4 text-sm text-pale-red-ink">
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
                ? "bg-pale-green text-pale-green-ink"
                : "bg-pale-yellow text-pale-yellow-ink"
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
                <div className="h-2 w-full overflow-hidden rounded-full bg-black/10/10">
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
            <details className="card p-5 text-sm">
              <summary className="cursor-pointer font-medium">
                {result.issueCount} row{result.issueCount === 1 ? "" : "s"}{" "}
                skipped
              </summary>
              <ul className="mt-3 space-y-1 text-xs text-muted">
                {result.issues.map((i) => (
                  <li key={i.row}>
                    Row {i.row}: {i.problem}
                  </li>
                ))}
              </ul>
            </details>
          )}

          <p className="text-xs text-faint">
            Compatibility check only. The file was parsed in memory and
            discarded — nothing was uploaded, stored or sent anywhere.
          </p>
        </section>
      )}
    </div>
  );
}
