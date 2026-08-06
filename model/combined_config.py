"""
Combine the regularising changes, then ensemble on top.

The sweep showed five independent axes all pointing the same way — lower
learning rate, shallower net, fewer epochs, more dropout, smaller hidden layer
— and removing dropout entirely was the single worst result. That is not five
separate findings; it is one finding seen five ways: THE ORIGINAL CONFIG WAS
OVERFITTING.

Individually each change gave ~+0.016, just under the 0.02 keep-threshold. The
question is whether they stack (different aspects of the same problem, partially
redundant) or compound (independent contributions).

Ensembling gave +0.0159 separately. Ensembling a better-regularised model should
help at least as much, since ensembles benefit from lower-variance members.

SELECTION BIAS, STATED UP FRONT: the combination is chosen from a sweep already
run on dev, so its dev score is optimistically biased. The honest number for
anything shipped from here is a single test-set read, which is deliberately NOT
taken in this script.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (base_split, build_pairs, carve_dev,  # noqa: E402
                           load_rows, MIN_GAP)
from tune_and_ensemble import acc_ci, fit, scores_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
N_SEEDS = 7
KEEP_THRESHOLD = 0.02

ORIGINAL = dict(hidden=128, lr=1e-3, epochs=25, dropout=0.2, wd=1e-4, depth=2)
# Every change is in the direction the sweep pointed.
COMBINED = dict(hidden=64, lr=3e-4, epochs=12, dropout=0.4, wd=1e-4, depth=1)
# One step further, to check we have not overshot into underfitting.
STRONGER = dict(hidden=32, lr=3e-4, epochs=10, dropout=0.5, wd=1e-3, depth=1)


def evaluate_config(name, cfg, E_in, p_in, E_dev, p_dev, t_dev, dim):
    accs, all_scores = [], []
    for s in range(N_SEEDS):
        m = fit(E_in, p_in, dim, seed=s, **cfg)
        sc = scores_of(m, E_dev)
        all_scores.append(sc)
        a, _ = acc_ci(sc, p_dev, t_dev)
        accs.append(a)
    accs = np.array(accs)
    z = np.stack([(s - s.mean()) / (s.std() + 1e-9) for s in all_scores])
    ens_acc, ens_ci = acc_ci(z.mean(axis=0), p_dev, t_dev)
    print(f"  {name:<12} single {accs.mean():.4f} (sd {accs.std(ddof=1):.4f})   "
          f"ensemble {ens_acc:.4f} [{ens_ci[0]:.4f}, {ens_ci[1]:.4f}]")
    return {"name": name, "single_mean": float(accs.mean()),
            "single_sd": float(accs.std(ddof=1)), "ensemble": ens_acc,
            "ensemble_ci": list(ens_ci)}


def main() -> None:
    rows = load_rows()
    parts, members = base_split(rows)
    inner, dev = carve_dev(parts["train"], members)

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)
    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]

    p_in = build_pairs(y[inner], t[inner], MIN_GAP, ident[inner])
    p_dev = build_pairs(y[dev], t[dev], MIN_GAP, ident[dev])
    print(f"inner pairs {len(p_in):,}  dev pairs {len(p_dev):,}\n")
    print(f"{N_SEEDS} seeds per config\n")

    out = []
    for name, cfg in (("original", ORIGINAL), ("combined", COMBINED),
                      ("stronger", STRONGER)):
        out.append(evaluate_config(name, cfg, E[inner], p_in, E[dev], p_dev,
                                   t[dev], E.shape[1]))

    base = out[0]
    best = max(out[1:], key=lambda r: r["ensemble"])
    gain = best["ensemble"] - base["single_mean"]

    print(f"\noriginal single-seed mean : {base['single_mean']:.4f}")
    print(f"original ensemble         : {base['ensemble']:.4f}")
    print(f"best ({best['name']}) ensemble  : {best['ensemble']:.4f}")
    print(f"\ntotal gain vs original single seed : {gain:+.4f}")
    print(f"  of which regularisation : "
          f"{best['single_mean'] - base['single_mean']:+.4f}")
    print(f"  of which ensembling     : "
          f"{best['ensemble'] - best['single_mean']:+.4f}")

    print(f"\nVERDICT: {'KEEP' if gain > KEEP_THRESHOLD else 'below threshold'}"
          f" (threshold {KEEP_THRESHOLD})")
    if out[2]["ensemble"] < out[1]["ensemble"]:
        print("  'stronger' underperforms 'combined' - we have found the floor,")
        print("  not merely walked toward it. Regularisation is not free.")

    print("\nNOTE: these are DEV numbers with selection bias from the earlier")
    print("sweep. Shipping this requires one pre-registered test-set read.")

    with open(os.path.join(PROC, "combined_config.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"configs": {"original": ORIGINAL, "combined": COMBINED,
                               "stronger": STRONGER},
                   "results": out, "gain": gain}, fh, indent=1)


if __name__ == "__main__":
    main()
