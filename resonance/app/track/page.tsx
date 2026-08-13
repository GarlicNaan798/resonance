"use client";

import { useCallback, useEffect, useState } from "react";
import { buildExport } from "@/lib/export";
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
          <span className="text-xs text-faint">
            ({board.correct}/{board.n})
          </span>
        </span>
      </div>
      {/* The interval is the point, so it is drawn rather than the point
          estimate. A wide bar crossing the 50% line is the honest picture at
          small n, and it should look wide. */}
      <div className="relative h-6 w-full rounded bg-sunk">
        <div
          className={`absolute inset-y-0 rounded ${
            board.beatsChance
              ? "bg-pale-green-ink/40"
              : "bg-rule-strong"
          }`}
          style={{ left: `${lo * 100}%`, width: `${Math.max(hi - lo, 0.01) * 100}%` }}
        />
        <div
          className="absolute inset-y-0 w-px bg-ink"
          style={{ left: `${board.rate * 100}%` }}
        />
        <div className="absolute inset-y-0 left-1/2 w-px border-l border-dashed border-faint" />
      </div>
      <div className="flex justify-between font-mono text-xs text-faint">
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
    <div className="max-w-3xl space-y-10">
      <div>
        <p className="eyebrow">Measure</p>
        <h1 className="display text-3xl sm:text-4xl">Track record</h1>
        <p className="mt-2 text-sm text-muted">
          The global 61.8% was measured on 2013–15 viral media. This page
          measures the model on <em>your</em> campaigns instead. Seal a
          prediction before launch, record the winner when you know it, and the
          numbers below are yours.
        </p>
      </div>

      {error && (
        <p className="rounded-md bg-pale-red p-3 text-sm text-pale-red-ink">
          {error}
        </p>
      )}

      {data && (
        <>
          <section className="space-y-5 rounded-lg border border-rule p-5">
            <p className="text-sm">{data.track.verdict}</p>

            {data.track.model.n > 0 && (
              <div className="space-y-5">
                <Bar board={data.track.model} label="Model" />
                {data.track.user ? (
                  <Bar board={data.track.user} label="Your blind picks" />
                ) : (
                  <p className="text-xs text-faint">
                    No blind picks recorded yet. On the Compare page you can
                    choose your own favourite before running the model — that is
                    the only way to find out how your own judgement scores, and
                    it has to be chosen before you see the answer to mean
                    anything.
                  </p>
                )}
              </div>
            )}

            <dl className="grid grid-cols-3 gap-4 border-t border-rule pt-4 text-sm">
              <div>
                <dt className="text-xs text-faint">Sealed</dt>
                <dd className="font-mono tabular-nums">{data.track.total}</dd>
              </div>
              <div>
                <dt className="text-xs text-faint">Awaiting outcome</dt>
                <dd className="font-mono tabular-nums">{data.track.pending}</dd>
              </div>
              <div>
                <dt className="text-xs text-faint">Resolved</dt>
                <dd className="font-mono tabular-nums">{data.track.model.n}</dd>
              </div>
            </dl>
          </section>

          <section className="space-y-3">
            <h2 className="text-lg font-medium">Awaiting an outcome</h2>
            {pending.length === 0 ? (
              <p className="text-sm text-faint">
                Nothing open. Seal a prediction from the Compare page.
              </p>
            ) : (
              <ul className="space-y-3">
                {pending.map((p) => (
                  <li
                    key={p.id}
                    className="space-y-3 card p-5"
                  >
                    <div className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-faint">
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
                          className="flex w-full items-start gap-3 rounded-md border border-rule-strong p-3 text-left text-sm hover:bg-sunk disabled:opacity-40"
                        >
                          <span className="text-faint">{i + 1}</span>
                          <span className="flex-1">{v}</span>
                          {p.predictedWinner === i && (
                            <span className="shrink-0 rounded bg-sunk px-1.5 py-0.5 text-xs">
                              model&apos;s pick
                            </span>
                          )}
                          {p.userPick === i && (
                            <span className="shrink-0 rounded bg-sunk px-1.5 py-0.5 text-xs">
                              yours
                            </span>
                          )}
                        </button>
                      ))}
                    </div>
                    <p className="text-xs text-faint">
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
                    <tr className="border-b border-rule text-left text-xs text-faint">
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
                          className="border-b border-rule align-top"
                        >
                          <td className="py-3 pr-4 text-xs text-faint">
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
                              <span className="text-faint">intact</span>
                            ) : (
                              <span className="font-medium text-pale-red-ink">
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

          {done.length > 0 && <Contribute predictions={data.predictions} />}
        </>
      )}
    </div>
  );
}

/**
 * Voluntary contribution.
 *
 * The app makes no outbound calls and this does not change that — it writes a
 * file and the user decides whether to send it. That distinction is what keeps
 * the `--network none` guarantee true, so the wording avoids implying anything
 * is transmitted.
 *
 * The payload is shown in full before it can be downloaded. Asking someone to
 * share data from a tool whose whole pitch is verifiability, without letting
 * them read exactly what they would be sharing, would be the wrong way round.
 */
function Contribute({ predictions }: { predictions: Row[] }) {
  const [payload, setPayload] = useState<string | null>(null);

  const resolved = predictions.filter((p) => p.actualWinner !== null).length;

  function preview() {
    setPayload(JSON.stringify(buildExport(predictions), null, 2));
  }

  function download() {
    if (!payload) return;
    const url = URL.createObjectURL(
      new Blob([payload], { type: "application/json" }),
    );
    const a = document.createElement("a");
    a.href = url;
    a.download = `resonance-track-record-${new Date()
      .toISOString()
      .slice(0, 10)}.json`;
    a.click();
    URL.revokeObjectURL(url);
  }

  return (
    <section className="card space-y-4 p-6">
      <div className="space-y-2">
        <span className="tag tag-blue">Optional</span>
        <h2 className="display text-xl">
          See how your hit rate compares to other teams
        </h2>
        <p className="max-w-2xl text-sm leading-relaxed text-muted">
          Your {resolved} resolved prediction{resolved === 1 ? "" : "s"} only
          describe your own campaigns. Pooled with other teams they answer a
          question none of us can answer alone: whether the model holds up
          outside the 2013–15 viral media it was trained on.
        </p>
      </div>

      <ul className="space-y-1.5 text-sm text-muted">
        {[
          "Your campaign copy is not included — not the text of any variant",
          "Campaign names and labels are not included",
          "No impressions, clicks or spend figures",
          "Nothing identifying you, your machine or your organisation",
        ].map((line) => (
          <li key={line} className="flex gap-2.5">
            <span aria-hidden="true" className="text-pale-green-ink">
              &minus;
            </span>
            <span>{line}</span>
          </li>
        ))}
      </ul>

      <p className="text-sm text-muted">
        What is included: the sealed hash, the date, how many variants, the
        confidence tier, the margin, and whether each pick was right.
      </p>

      {payload === null ? (
        <button onClick={preview} className="btn btn-secondary">
          Show me exactly what would be shared
        </button>
      ) : (
        <div className="space-y-3">
          <pre className="max-h-80 overflow-auto rounded-lg border border-rule bg-sunk p-4 font-mono text-xs leading-relaxed">
            {payload}
          </pre>
          <div className="flex flex-wrap items-center gap-3">
            <button onClick={download} className="btn btn-primary">
              Download this file
            </button>
            <button
              onClick={() => setPayload(null)}
              className="btn btn-secondary"
            >
              Close
            </button>
          </div>
          <p className="text-xs text-faint">
            Nothing has been sent. The file is written to your downloads folder
            and goes nowhere unless you send it yourself.
          </p>
        </div>
      )}
    </section>
  );
}
