"use client";

import { useCallback, useEffect, useState } from "react";
import type { Prediction, TrackRecord, Scoreboard } from "@/lib/predictions";

interface Row extends Prediction {
  sealValid: boolean;
}

interface Payload {
  predictions: Row[];
  track: TrackRecord;
}

const pct = (x: number) => `${(x * 100).toFixed(0)}%`;

function Bar({ board, label }: { board: Scoreboard; label: string }) {
  const [lo, hi] = board.ci95;
  return (
    <div className="space-y-1.5">
      <div className="flex items-baseline justify-between text-sm">
        <span className="font-medium">{label}</span>
        <span className="font-mono tabular-nums">
          {pct(board.rate)}{" "}
          <span className="text-xs text-zinc-500">
            ({board.correct}/{board.n})
          </span>
        </span>
      </div>
      {/* The interval is the point, so it is drawn rather than the point
          estimate. A wide bar crossing the 50% line is the honest picture at
          small n, and it should look wide. */}
      <div className="relative h-6 w-full rounded bg-zinc-100 dark:bg-zinc-900">
        <div
          className={`absolute inset-y-0 rounded ${
            board.beatsChance
              ? "bg-emerald-400/50"
              : "bg-zinc-400/40 dark:bg-zinc-600/40"
          }`}
          style={{ left: `${lo * 100}%`, width: `${Math.max(hi - lo, 0.01) * 100}%` }}
        />
        <div
          className="absolute inset-y-0 w-px bg-zinc-900 dark:bg-zinc-100"
          style={{ left: `${board.rate * 100}%` }}
        />
        <div className="absolute inset-y-0 left-1/2 w-px border-l border-dashed border-zinc-500" />
      </div>
      <div className="flex justify-between font-mono text-xs text-zinc-500">
        <span>0%</span>
        <span>
          95% CI {pct(lo)}–{pct(hi)} · dashed line is chance
        </span>
        <span>100%</span>
      </div>
    </div>
  );
}

export default function TrackPage() {
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const res = await fetch("/api/predictions");
      if (!res.ok) {
        setError("Could not read the prediction log.");
        return;
      }
      setData((await res.json()) as Payload);
      setError(null);
    } catch {
      setError("Could not read the prediction log.");
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function resolve(id: string, actualWinner: number) {
    setBusy(id);
    try {
      const res = await fetch("/api/predictions", {
        method: "PATCH",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ id, actualWinner }),
      });
      if (!res.ok) {
        setError((await res.json()).error ?? "Could not record the outcome.");
        return;
      }
      await load();
    } finally {
      setBusy(null);
    }
  }

  const pending = data?.predictions.filter((p) => p.actualWinner === null) ?? [];
  const done = data?.predictions.filter((p) => p.actualWinner !== null) ?? [];

  return (
    <div className="space-y-10">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Track record</h1>
        <p className="mt-2 max-w-2xl text-sm text-zinc-600 dark:text-zinc-400">
          The global 61.8% was measured on 2013–15 viral media. This page
          measures the model on <em>your</em> campaigns instead. Seal a
          prediction before launch, record the winner when you know it, and the
          numbers below are yours.
        </p>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
          {error}
        </p>
      )}

      {data && (
        <>
          <section className="space-y-5 rounded-lg border border-zinc-200 p-5 dark:border-zinc-800">
            <p className="text-sm">{data.track.verdict}</p>

            {data.track.model.n > 0 && (
              <div className="space-y-5">
                <Bar board={data.track.model} label="Model" />
                {data.track.user ? (
                  <Bar board={data.track.user} label="Your blind picks" />
                ) : (
                  <p className="text-xs text-zinc-500">
                    No blind picks recorded yet. On the Compare page you can
                    choose your own favourite before running the model — that is
                    the only way to find out how your own judgement scores, and
                    it has to be chosen before you see the answer to mean
                    anything.
                  </p>
                )}
              </div>
            )}

            <dl className="grid grid-cols-3 gap-4 border-t border-zinc-200 pt-4 text-sm dark:border-zinc-800">
              <div>
                <dt className="text-xs text-zinc-500">Sealed</dt>
                <dd className="font-mono tabular-nums">{data.track.total}</dd>
              </div>
              <div>
                <dt className="text-xs text-zinc-500">Awaiting outcome</dt>
                <dd className="font-mono tabular-nums">{data.track.pending}</dd>
              </div>
              <div>
                <dt className="text-xs text-zinc-500">Resolved</dt>
                <dd className="font-mono tabular-nums">{data.track.model.n}</dd>
              </div>
            </dl>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium">Awaiting an outcome</h2>
            {pending.length === 0 ? (
              <p className="text-sm text-zinc-500">
                Nothing open. Seal a prediction from the Compare page.
              </p>
            ) : (
              <ul className="space-y-3">
                {pending.map((p) => (
                  <li
                    key={p.id}
                    className="space-y-3 rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-zinc-500">
                      <span>
                        {p.label ? `${p.label} · ` : ""}
                        sealed {new Date(p.createdAt).toLocaleDateString()} ·
                        confidence {p.tier}
                      </span>
                      <code className="font-mono">{p.hash.slice(0, 16)}…</code>
                    </div>
                    <p className="text-sm">
                      Which variant actually won?
                    </p>
                    <div className="space-y-2">
                      {p.variants.map((v, i) => (
                        <button
                          key={i}
                          disabled={busy === p.id}
                          onClick={() => resolve(p.id, i)}
                          className="flex w-full items-start gap-3 rounded-md border border-zinc-300 p-3 text-left text-sm hover:bg-zinc-50 disabled:opacity-40 dark:border-zinc-700 dark:hover:bg-zinc-900"
                        >
                          <span className="text-zinc-500">{i + 1}</span>
                          <span className="flex-1">{v}</span>
                          {p.predictedWinner === i && (
                            <span className="shrink-0 rounded bg-zinc-200 px-1.5 py-0.5 text-xs dark:bg-zinc-800">
                              model&apos;s pick
                            </span>
                          )}
                          {p.userPick === i && (
                            <span className="shrink-0 rounded bg-zinc-200 px-1.5 py-0.5 text-xs dark:bg-zinc-800">
                              yours
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                    <p className="text-xs text-zinc-500">
                      Recording is one-way — an outcome cannot be changed once
                      saved, which is what stops the record being tuned after
                      the fact.
                    </p>
                  </li>
                ))}
              </ul>
            )}
          </section>

          {done.length > 0 && (
            <section className="space-y-3">
              <h2 className="text-lg font-medium">Resolved</h2>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[36rem] border-collapse text-sm">
                  <thead>
                    <tr className="border-b border-zinc-200 text-left text-xs text-zinc-500 dark:border-zinc-800">
                      <th className="py-2 pr-4 font-medium">Sealed</th>
                      <th className="py-2 pr-4 font-medium">Winner</th>
                      <th className="py-2 pr-4 font-medium">Model</th>
                      <th className="py-2 pr-4 font-medium">You</th>
                      <th className="py-2 font-medium">Seal</th>
                    </tr>
                  </thead>
                  <tbody>
                    {done.map((p) => {
                      const modelHit = p.predictedWinner === p.actualWinner;
                      const userHit =
                        p.userPick === null ? null : p.userPick === p.actualWinner;
                      return (
                        <tr
                          key={p.id}
                          className="border-b border-zinc-100 align-top dark:border-zinc-900"
                        >
                          <td className="py-3 pr-4 text-xs text-zinc-500">
                            {new Date(p.createdAt).toLocaleDateString()}
                          </td>
                          <td className="max-w-xs py-3 pr-4">
                            {p.variants[p.actualWinner!]}
                          </td>
                          <td className="py-3 pr-4">{modelHit ? "✓" : "✗"}</td>
                          <td className="py-3 pr-4">
                            {userHit === null ? "—" : userHit ? "✓" : "✗"}
                          </td>
                          <td className="py-3 text-xs">
                            {p.sealValid ? (
                              <span className="text-zinc-500">intact</span>
                            ) : (
                              <span className="font-medium text-red-600 dark:text-red-400">
                                ALTERED
                              </span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
