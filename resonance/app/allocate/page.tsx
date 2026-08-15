"use client";

import { useState } from "react";
import { allocate, shouldStop, type Arm } from "@/lib/allocate";
import { assessDecidability } from "@/lib/power";

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

  // Power check on the two leading arms. Answers "could ANY model settle this
  // at your sample size", which is a different question from "which is ahead".
  const ranked = weights
    .map((w, i) => ({ w, i }))
    .sort((a, b) => b.w - a.w);
  const hasData = arms.some((a) => a.impressions > 0);
  const power =
    !invalid && ranked.length >= 2 && hasData
      ? assessDecidability(arms[ranked[0].i], arms[ranked[1].i])
      : null;

  const set = (i: number, k: keyof Row, v: string) =>
    setRows((p) => p.map((r, j) => (j === i ? { ...r, [k]: v } : r)));

  return (
    <div className="max-w-3xl space-y-8">
      <div>
        <p className="eyebrow">Allocate</p>
        <h1 className="display text-3xl sm:text-4xl">
          Split your test budget
        </h1>
        <p className="mt-2 text-sm text-muted">
          Enter each variant&apos;s results so far and get the split for the next
          batch of impressions. Measured on 1,894 held-out experiments:{" "}
          <strong>31.8% less budget spent on losing variants</strong> than an
          even 50/50 test.
        </p>
      </div>

      <section className="space-y-3">
        {rows.map((r, i) => (
          <div key={i} className="flex flex-wrap items-center gap-2">
            <span className="w-6 shrink-0 text-sm text-faint">{i + 1}</span>
            <input
              value={r.text}
              onChange={(e) => set(i, "text", e.target.value)}
              placeholder={`Variant ${i + 1} (optional label)`}
              className="min-w-[16rem] flex-1 rounded-lg border border-rule-strong bg-surface p-2 text-sm"
            />
            <input
              value={r.impressions}
              onChange={(e) => set(i, "impressions", e.target.value)}
              inputMode="numeric"
              placeholder="impressions"
              className="w-28 rounded-lg border border-rule-strong bg-surface p-2 text-sm"
            />
            <input
              value={r.clicks}
              onChange={(e) => set(i, "clicks", e.target.value)}
              inputMode="numeric"
              placeholder="clicks"
              className="w-24 rounded-lg border border-rule-strong bg-surface p-2 text-sm"
            />
            <span className="w-16 text-right font-mono text-sm tabular-nums">
              {weights[i] === undefined ? "n/a" : `${(weights[i] * 100).toFixed(0)}%`}
            </span>
          </div>
        ))}

        <div className="flex items-center gap-3">
          <button
            onClick={() => setRows((p) => [...p, { ...BLANK }])}
            disabled={rows.length >= 8}
            className="rounded-md border border-rule-strong px-3 py-1.5 text-sm disabled:opacity-40"
          >
            Add variant
          </button>
          {rows.length > 2 && (
            <button
              onClick={() => setRows((p) => p.slice(0, -1))}
              className="rounded-md border border-rule-strong px-3 py-1.5 text-sm"
            >
              Remove
            </button>
          )}
        </div>

        {invalid && (
          <p className="rounded-md bg-pale-red p-3 text-sm text-pale-red-ink">
            Clicks cannot exceed impressions.
          </p>
        )}
      </section>

      {!invalid && (
        <section
          className={`rounded-lg p-4 text-sm ${
            stop
              ? "bg-pale-green text-pale-green-ink"
              : "bg-sunk text-ink"
          }`}
        >
          {stop ? (
            <>
              <p className="font-medium">
                Stop the test, variant {(winner ?? 0) + 1} wins
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
                in the percentages above, losers still get traffic, because a
                variant that looks weak on 500 impressions may not be.
              </p>
            </>
          )}
        </section>
      )}

      {power && (
        <section className="space-y-2 card p-5 text-sm">
          <p className="font-medium">Can this test be settled at all?</p>
          <p className="text-muted">{power.message}</p>
          {!power.decidable && Number.isFinite(power.shortfall) && (
            <p className="text-xs text-faint">
              This is a property of your sample size, not of our model. At{" "}
              {Math.min(
                arms[ranked[0].i].impressions,
                arms[ranked[1].i].impressions,
              ).toLocaleString()}{" "}
              impressions the best any model could do on a gap this small is{" "}
              {(power.ceiling * 100).toFixed(1)}%. More traffic raises that
              limit; a better model cannot.
            </p>
          )}
        </section>
      )}

      <p className="text-xs text-faint">
        With no results entered, the split is even. That is correct: with no
        data there is no reason to favour any variant. Percentages are each
        variant&apos;s probability of being best given the results so far.
      </p>
    </div>
  );
}
