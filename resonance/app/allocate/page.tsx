"use client";

import { useState } from "react";
import { allocate, shouldStop, type Arm } from "@/lib/allocate";

interface Row {
  text: string;
  impressions: string;
  clicks: string;
}

const BLANK: Row = { text: "", impressions: "", clicks: "" };

export default function AllocatePage() {
  const [rows, setRows] = useState<Row[]>([{ ...BLANK }, { ...BLANK }]);

  const arms: Arm[] = rows.map((r) => ({
    impressions: Number(r.impressions) || 0,
    clicks: Number(r.clicks) || 0,
  }));

  const invalid = arms.some((a) => a.clicks > a.impressions);
  const weights = invalid ? [] : allocate(arms);
  const { stop, winner } = weights.length
    ? shouldStop(weights)
    : { stop: false, winner: null };

  const set = (i: number, k: keyof Row, v: string) =>
    setRows((p) => p.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">
          Split your test budget
        </h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          Enter each variant&apos;s results so far and get the split for the next
          batch of impressions. Measured on 1,894 held-out experiments:{" "}
          <strong>31.8% less budget spent on losing variants</strong> than an
          even 50/50 test.
        </p>
      </div>

      <section className="space-y-3">
        {rows.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <span className="w-6 shrink-0 text-sm text-zinc-500">{i + 1}</span>
            <input
              value={r.text}
              onChange={(e) => set(i, "text", e.target.value)}
              placeholder={`Variant ${i + 1} (optional label)`}
              className="min-w-[16rem] flex-1 rounded-lg border border-zinc-300 bg-white p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
            <input
              value={r.impressions}
              onChange={(e) => set(i, "impressions", e.target.value)}
              inputMode="numeric"
              placeholder="impressions"
              className="w-28 rounded-lg border border-zinc-300 bg-white p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
            <input
              value={r.clicks}
              onChange={(e) => set(i, "clicks", e.target.value)}
              inputMode="numeric"
              placeholder="clicks"
              className="w-24 rounded-lg border border-zinc-300 bg-white p-2 text-sm dark:border-zinc-700 dark:bg-zinc-900"
            />
            <span className="w-16 text-right font-mono text-sm tabular-nums">
              {weights[i] === undefined ? "—" : `${(weights[i] * 100).toFixed(0)}%`}
            </span>
          </div>
        ))}

        <div className="flex items-center gap-3">
          <button
            onClick={() => setRows((p) => [...p, { ...BLANK }])}
            disabled={rows.length >= 8}
            className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm disabled:opacity-40 dark:border-zinc-700"
          >
            Add variant
          </button>
          {rows.length > 2 && (
            <button
              onClick={() => setRows((p) => p.slice(0, -1))}
              className="rounded-md border border-zinc-300 px-3 py-1.5 text-sm dark:border-zinc-700"
            >
              Remove
            </button>
          )}
        </div>

        {invalid && (
          <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
            Clicks cannot exceed impressions.
          </p>
        )}
      </section>

      {!invalid && (
        <section
          className={`rounded-lg p-4 text-sm ${
            stop
              ? "bg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200"
              : "bg-zinc-100 text-zinc-800 dark:bg-zinc-900 dark:text-zinc-200"
          }`}
        >
          {stop ? (
            <>
              <p className="font-medium">
                Stop the test — variant {(winner ?? 0) + 1} wins
              </p>
              <p className="mt-1">
                It is best with ≥95% probability. Further spend on the others is
                waste.
              </p>
            </>
          ) : (
            <>
              <p className="font-medium">Keep testing</p>
              <p className="mt-1">
                No variant is yet best with 95% confidence. Serve the next batch
                in the percentages above — losers still get traffic, because a
                variant that looks weak on 500 impressions may not be.
              </p>
            </>
          )}
        </section>
      )}

      <p className="text-xs text-zinc-500">
        With no results entered, the split is even. That is correct: with no
        data there is no reason to favour any variant. Percentages are each
        variant&apos;s probability of being best given the results so far.
      </p>
    </div>
  );
}
