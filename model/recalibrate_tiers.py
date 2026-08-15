"""
Recalibrate the abstention thresholds for the ensemble.

The tiers in ranker.ts (margin >= 2.16 -> "high", >= 1.203 -> "moderate") were
measured on a single pairwise model's RAW score differences. The ensemble emits
an average of per-member z-scores, which is a completely different scale, so
those thresholds are meaningless now, and would silently mislabel confidence
rather than fail visibly.

Same method as calibrate_abstention.py: sweep a margin threshold over dev pairs
and record accuracy at each coverage level. Dev, not test. The test set is
closed after the third read, and thresholds are a presentation choice rather
than a model claim.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (base_split, build_pairs, carve_dev,  # noqa: E402
                           load_rows, MIN_GAP)
from listwise import build_lists, train_listwise  # noqa: E402
from tune_and_ensemble import scores_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
N_SEEDS = 5
COVERAGES = [1.0, 0.75, 0.5, 0.25, 0.10]


def accuracy_at(scores, pairs, tids, coverage):
    margins = np.abs(scores[pairs[:, 0]] - scores[pairs[:, 1]])
    thr = 0.0 if coverage >= 1.0 else float(np.quantile(margins, 1 - coverage))
    sel = pairs[margins >= thr]
    if len(sel) == 0:
        return None
    by_exp = defaultdict(list)
    for k, i in enumerate(sel[:, 0]):
        by_exp[tids[i]].append(k)
    hi, lo = scores[sel[:, 0]], scores[sel[:, 1]]
    correct = (hi > lo).astype(float) + 0.5 * (hi == lo)
    per = np.array([correct[np.array(ks)].mean() for ks in by_exp.values()])
    return {"coverage": len(sel) / len(pairs), "threshold": thr,
            "accuracy": float(per.mean()), "n_pairs": int(len(sel))}


def main() -> None:
    rows = load_rows()
    parts, members_map = base_split(rows)
    inner, dev = carve_dev(parts["train"], members_map)

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)
    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]

    lists = build_lists(inner, rows, y, ident)
    pos = {int(g): k for k, g in enumerate(inner)}
    lists_local = [np.array([pos[int(i)] for i in l]) for l in lists]

    parts_scores = []
    for s in range(N_SEEDS):
        m = train_listwise(E[inner], lists_local, y[inner], E.shape[1], seed=s)
        sc = scores_of(m, E)
        # Member normalisation uses the FIT set, matching export_ensemble.py.
        parts_scores.append((sc - sc[inner].mean()) / (sc[inner].std() + 1e-9))
    ens = np.mean(parts_scores, axis=0)

    p_dev = dev[build_pairs(y[dev], t[dev], MIN_GAP, ident[dev])]
    print(f"dev pairs: {len(p_dev):,}\n")
    print(f"{'coverage':>9}{'accuracy':>10}{'margin':>10}{'pairs':>9}")

    curve = []
    for cov in COVERAGES:
        r = accuracy_at(ens, p_dev, t, cov)
        if r:
            curve.append(r)
            print(f"{r['coverage']:>8.0%}{r['accuracy']:>10.4f}"
                  f"{r['threshold']:>10.3f}{r['n_pairs']:>9,}")

    high = next(r for r in curve if abs(r["coverage"] - 0.25) < 0.05)
    mod = next(r for r in curve if abs(r["coverage"] - 0.5) < 0.05)
    print(f"\nnew tiers for ranker.ts:")
    print(f"  high     minMargin {high['threshold']:.3f}  "
          f"accuracy {high['accuracy']:.4f}  coverage 0.25")
    print(f"  moderate minMargin {mod['threshold']:.3f}  "
          f"accuracy {mod['accuracy']:.4f}  coverage 0.50")

    with open(os.path.join(PROC, "tiers_ensemble.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"curve": curve,
                   "high": {"minMargin": high["threshold"],
                            "accuracy": high["accuracy"], "coverage": 0.25},
                   "moderate": {"minMargin": mod["threshold"],
                                "accuracy": mod["accuracy"], "coverage": 0.5}},
                  fh, indent=1)


if __name__ == "__main__":
    main()
