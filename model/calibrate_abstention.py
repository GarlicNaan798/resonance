"""
Calibrated abstention: turn 59% on everything into high accuracy on a subset.

The ranker is right 59.4% of the time across all comparisons. That average hides
the useful structure: it is far more reliable when the two variants are far
apart in score than when they are close. A product that answers every question
at 59% is less useful than one that says "confident here, unsure there".

Method:
  * Score dev pairs with the trained ranker.
  * Use |score difference| as the confidence signal.
  * Sweep a threshold and record the coverage/accuracy trade-off: at each
    threshold, what fraction of comparisons do we answer, and how often are we
    right on those?

Reported as a coverage/accuracy curve. Any headline accuracy figure taken from
this MUST be quoted with its coverage, "80% accurate on the 25% of comparisons
we answer" is honest; "80% accurate" alone is not.

Nothing here is fitted to the test set. The threshold is chosen on dev and would
be confirmed once on test only if it were ever shipped as a claim.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (PointwiseRanker, base_split, build_pairs,  # noqa: E402
                           carve_dev, load_rows, train, MIN_GAP)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")

# Coverage levels to report. 1.0 is the current always-answer behaviour.
COVERAGES = [1.0, 0.75, 0.5, 0.35, 0.25, 0.15, 0.10, 0.05]


def clustered_ci(per_exp: list[float]) -> tuple[float, float, float]:
    a = np.array(per_exp)
    m = float(a.mean())
    se = float(a.std(ddof=1) / np.sqrt(len(a))) if len(a) > 1 else 0.0
    return m, m - 1.96 * se, m + 1.96 * se


def accuracy_at_coverage(scores, pairs, tids, coverage):
    """Answer only the most confident `coverage` fraction of pairs."""
    margins = np.abs(scores[pairs[:, 0]] - scores[pairs[:, 1]])
    if coverage >= 1.0:
        keep = np.ones(len(pairs), dtype=bool)
        threshold = 0.0
    else:
        threshold = float(np.quantile(margins, 1.0 - coverage))
        keep = margins >= threshold

    sel = pairs[keep]
    if len(sel) == 0:
        return None

    # Cluster by experiment so the CI respects non-independence.
    by_exp = defaultdict(list)
    for k, i in enumerate(sel[:, 0]):
        by_exp[tids[i]].append(k)

    hi = scores[sel[:, 0]]
    lo = scores[sel[:, 1]]
    correct = (hi > lo).astype(float) + 0.5 * (hi == lo)

    per_exp = [float(correct[np.array(ks)].mean()) for ks in by_exp.values()]
    mean, lo_ci, hi_ci = clustered_ci(per_exp)
    return {
        "coverage": len(sel) / len(pairs),
        "threshold": threshold,
        "accuracy": mean,
        "ci95": [lo_ci, hi_ci],
        "n_pairs": int(len(sel)),
        "n_experiments": len(per_exp),
    }


def main() -> None:
    rows = load_rows()
    parts, members = base_split(rows)
    inner, dev = carve_dev(parts["train"], members)

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)

    p_in = build_pairs(y[inner], t[inner], MIN_GAP, ident[inner])
    p_dev = build_pairs(y[dev], t[dev], MIN_GAP, ident[dev])

    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]
    model = train(PointwiseRanker(E.shape[1]), E[inner], p_in, epochs=25, lr=1e-3)

    with torch.no_grad():
        scores = model.net(
            torch.tensor(E[dev], dtype=torch.float32)
        ).squeeze(-1).numpy()

    print(f"dev pairs: {len(p_dev):,}\n")
    print(f"{'coverage':>9} {'accuracy':>9} {'95% CI':>18} {'threshold':>10} "
          f"{'pairs':>8}")

    results = []
    for cov in COVERAGES:
        r = accuracy_at_coverage(scores, p_dev, t[dev], cov)
        if r is None:
            continue
        results.append(r)
        print(f"{r['coverage']:>8.0%} {r['accuracy']:>9.4f} "
              f"[{r['ci95'][0]:.4f}, {r['ci95'][1]:.4f}] "
              f"{r['threshold']:>10.3f} {r['n_pairs']:>8,}")

    base = results[0]["accuracy"]
    best = max(results, key=lambda r: r["accuracy"])
    print(f"\nalways-answer accuracy : {base:.4f}")
    print(f"best subset            : {best['accuracy']:.4f} at "
          f"{best['coverage']:.0%} coverage")
    print(f"lift from abstaining   : {best['accuracy'] - base:+.4f}")
    print("\nCeiling for reference: 0.7880. Any figure quoted from this table "
          "must carry its coverage.")

    with open(os.path.join(PROC, "abstention_curve.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"curve": results, "always_answer": base}, fh, indent=1)


if __name__ == "__main__":
    main()
