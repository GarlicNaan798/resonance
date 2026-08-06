"""
Paired comparison of the two encoders.

compare_encoders_subsample.py reported MiniLM 0.5758 and mpnet 0.5974 - a gain
of +0.0215 against a 0.02 keep-threshold. But it compared two independent point
estimates whose confidence intervals overlap heavily, which is the wrong test:
both models are scored on the SAME experiments, so the comparison should be
paired.

A paired test removes the between-experiment variance that dominates each
model's individual CI. Some experiments are simply easier than others, and that
shared difficulty inflates both intervals while telling us nothing about which
encoder is better.

Reported here:
  * per-experiment accuracy difference, mean and 95% CI (clustered correctly)
  * a paired bootstrap over experiments, which assumes nothing about normality
  * the proportion of experiments where each encoder wins

The keep-decision is remade on this evidence. A gain that does not survive a
paired test does not justify 5x the inference cost.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (PointwiseRanker, base_split, build_pairs,  # noqa: E402
                           carve_dev, load_rows, train, MIN_GAP)
from compare_encoders_subsample import CACHE, subsample  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
KEEP_THRESHOLD = 0.02
N_BOOT = 10_000


def per_experiment_accuracy(scores, pairs, tids):
    """Accuracy within each experiment, keyed by experiment id."""
    by_exp = defaultdict(list)
    for k, i in enumerate(pairs[:, 0]):
        by_exp[tids[i]].append(k)
    out = {}
    for exp, ks in by_exp.items():
        ks = np.array(ks)
        hi = scores[pairs[ks, 0]]
        lo = scores[pairs[ks, 1]]
        out[exp] = float((hi > lo).mean() + 0.5 * (hi == lo).mean())
    return out


def score_all(model, E, pairs):
    Et = torch.tensor(E, dtype=torch.float32)
    with torch.no_grad():
        return model.net(Et).squeeze(-1).numpy()


def main() -> None:
    rows = load_rows()
    parts, members = base_split(rows)
    inner_full, dev_full = carve_dev(parts["train"], members)
    inner, dev = subsample(inner_full, dev_full, rows)

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)

    p_in = build_pairs(y[inner], t[inner], MIN_GAP, ident[inner])
    p_dev = build_pairs(y[dev], t[dev], MIN_GAP, ident[dev])

    if not os.path.exists(CACHE):
        raise SystemExit("mpnet subsample cache missing")
    E_mp_all = np.load(CACHE)["E"]
    n_in = len(inner)
    E_mp_in, E_mp_dev = E_mp_all[:n_in], E_mp_all[n_in:]

    mini = np.load(os.path.join(PROC, "embeddings.npz"))["E"]
    E_mini_in, E_mini_dev = mini[inner], mini[dev]

    print(f"dev pairs={len(p_dev):,}")

    m_mini = train(PointwiseRanker(E_mini_in.shape[1]), E_mini_in, p_in,
                   epochs=25, lr=1e-3)
    m_mp = train(PointwiseRanker(E_mp_in.shape[1]), E_mp_in, p_in,
                 epochs=25, lr=1e-3)

    acc_mini = per_experiment_accuracy(score_all(m_mini, E_mini_dev, p_dev),
                                       p_dev, t[dev])
    acc_mp = per_experiment_accuracy(score_all(m_mp, E_mp_dev, p_dev),
                                     p_dev, t[dev])

    exps = sorted(set(acc_mini) & set(acc_mp))
    a = np.array([acc_mini[e] for e in exps])
    b = np.array([acc_mp[e] for e in exps])
    diff = b - a

    n = len(diff)
    mean_d = float(diff.mean())
    se_d = float(diff.std(ddof=1) / np.sqrt(n))
    ci = (mean_d - 1.96 * se_d, mean_d + 1.96 * se_d)

    print(f"\n=== PAIRED over {n:,} experiments ===")
    print(f"  MiniLM mean accuracy : {a.mean():.4f}")
    print(f"  mpnet  mean accuracy : {b.mean():.4f}")
    print(f"  paired difference    : {mean_d:+.4f}")
    print(f"  95% CI               : [{ci[0]:+.4f}, {ci[1]:+.4f}]")
    print(f"  paired SE            : {se_d:.4f}  (vs ~0.0103 unpaired)")

    rng = np.random.default_rng(0)
    boots = np.array([
        diff[rng.integers(0, n, n)].mean() for _ in range(N_BOOT)
    ])
    lo, hi = np.percentile(boots, [2.5, 97.5])
    p_gt_zero = float((boots > 0).mean())
    p_gt_thresh = float((boots > KEEP_THRESHOLD).mean())
    print(f"\n  bootstrap 95% CI     : [{lo:+.4f}, {hi:+.4f}]")
    print(f"  P(mpnet better)      : {p_gt_zero:.3f}")
    print(f"  P(gain > {KEEP_THRESHOLD})       : {p_gt_thresh:.3f}")

    wins = float((diff > 0).mean())
    ties = float((diff == 0).mean())
    print(f"\n  experiments where mpnet wins: {wins:.1%}  "
          f"ties: {ties:.1%}  MiniLM wins: {1-wins-ties:.1%}")

    keep = ci[0] > KEEP_THRESHOLD
    print("\n  DECISION: " + (
        "KEEP mpnet - the paired lower bound clears the threshold"
        if keep else
        "KEEP MiniLM - the gain does not reliably exceed the threshold, and "
        "mpnet costs ~5x more to serve"))

    with open(os.path.join(PROC, "phase15_paired.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"n_experiments": n, "minilm": float(a.mean()),
                   "mpnet": float(b.mean()), "paired_diff": mean_d,
                   "ci95": list(ci), "bootstrap_ci": [float(lo), float(hi)],
                   "p_better": p_gt_zero, "p_gain_over_threshold": p_gt_thresh,
                   "keep_mpnet": bool(keep)}, fh, indent=1)


if __name__ == "__main__":
    main()
