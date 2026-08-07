"""
Which target construction gives the least noisy training signal?

Four options, all attacking sampling noise rather than the model:

  baseline   current: per-arm within-test log-odds contrast, >=500 impressions
  pooled     average the contrast across every test a headline appeared in
             (~50% of headlines recur, so this is free extra precision)
  shrunk     empirical-Bayes: pull each arm toward its test mean by the share
             of its spread attributable to sampling noise
  floor2000  raise the impression floor, trading data volume for cleaner labels

DECISION RULE (fixed before running):

  1. ONE fixed evaluation set, using ORIGINAL labels, restricted to pairs that
     survive the strictest condition (floor2000). Each option changes the
     labels, so scoring each on its own labels would compare nothing.
  2. Same 5 seeds per option; compare the PER-SEED difference, not point
     estimates. An unpaired comparison once said mpnet was +0.0215 when the
     paired test said +0.0128 with a CI spanning zero.
  3. Winner must beat baseline by more than the 0.02 noise floor AND have a
     paired CI excluding zero.

Scoring against noisy labels understates the benefit of cleaner training
labels. That is deliberate: a client's next test will be noisy too, so
predicting noisy observations is the real task.
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
from tune_and_ensemble import acc_ci, fit, scores_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
N_SEEDS = 5
KEEP_THRESHOLD = 0.02
FLOOR_STRICT = 2000
CFG = dict(hidden=128, lr=1e-3, epochs=25, dropout=0.2, wd=1e-4, depth=2)


def pooled_target(rows, y):
    """Average each headline's contrast over every test it appeared in."""
    by_head = defaultdict(list)
    for i, r in enumerate(rows):
        by_head[" ".join(r["headline"].lower().split())].append(i)
    out = y.copy()
    for idxs in by_head.values():
        if len(idxs) > 1:
            # Precision-weighted mean; arms with more impressions count more.
            w = np.array([rows[i]["impressions"] for i in idxs], dtype=float)
            out[idxs] = float(np.average(y[idxs], weights=w))
    return out


def shrunk_target(rows, y):
    """Empirical Bayes: shrink toward the test mean by the noise share."""
    by_test = defaultdict(list)
    for i, r in enumerate(rows):
        by_test[r["test_id"]].append(i)
    out = y.copy()
    for idxs in by_test.values():
        if len(idxs) < 2:
            continue
        idxs = np.array(idxs)
        obs_var = float(np.var(y[idxs]))
        if obs_var <= 0:
            continue
        # Per-arm log-odds noise variance.
        noise = np.mean([
            1.0 / (rows[i]["clicks"] + 0.5)
            + 1.0 / (rows[i]["impressions"] - rows[i]["clicks"] + 0.5)
            for i in idxs
        ])
        w = max(0.0, (obs_var - noise)) / obs_var
        m = float(y[idxs].mean())
        out[idxs] = m + w * (y[idxs] - m)
    return out


def main() -> None:
    rows = load_rows()
    parts, members = base_split(rows)
    inner, dev = carve_dev(parts["train"], members)

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)
    impr = np.array([r["impressions"] for r in rows])
    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]
    dim = E.shape[1]

    # --- fixed evaluation set: original labels, strictest floor -----------
    strict = np.array([i for i in dev if impr[i] >= FLOOR_STRICT])
    p_dev = build_pairs(y[strict], t[strict], MIN_GAP, ident[strict])
    p_dev_global = strict[p_dev]
    print(f"fixed eval: {len(strict):,} arms >= {FLOOR_STRICT} impressions, "
          f"{len(p_dev):,} pairs\n")

    targets = {
        "baseline": (inner, y),
        "pooled": (inner, pooled_target(rows, y)),
        "shrunk": (inner, shrunk_target(rows, y)),
        "floor2000": (np.array([i for i in inner if impr[i] >= FLOOR_STRICT]), y),
    }

    print(f"{'option':<12}{'train arms':>11}{'pairs':>9}{'mean acc':>10}"
          f"{'sd':>8}")
    per_seed = {}
    for name, (idx, tgt) in targets.items():
        p_in = build_pairs(tgt[idx], t[idx], MIN_GAP, ident[idx])
        accs = []
        for s in range(N_SEEDS):
            m = fit(E[idx], p_in, dim, seed=s, **CFG)
            sc = scores_of(m, E)                       # score all rows
            a, _ = acc_ci(sc, p_dev_global, t)
            accs.append(a)
        per_seed[name] = np.array(accs)
        print(f"{name:<12}{len(idx):>11,}{len(p_in):>9,}"
              f"{per_seed[name].mean():>10.4f}{per_seed[name].std(ddof=1):>8.4f}")

    base = per_seed["baseline"]
    print(f"\n{'option':<12}{'paired diff':>13}{'95% CI':>22}{'verdict':>10}")
    results = {}
    for name, accs in per_seed.items():
        if name == "baseline":
            continue
        d = accs - base
        m = float(d.mean())
        se = float(d.std(ddof=1) / np.sqrt(len(d)))
        lo, hi = m - 1.96 * se, m + 1.96 * se
        keep = lo > KEEP_THRESHOLD
        results[name] = {"diff": m, "ci": [lo, hi], "keep": bool(keep)}
        print(f"{name:<12}{m:>+13.4f}{f'[{lo:+.4f}, {hi:+.4f}]':>22}"
              f"{'KEEP' if keep else 'no':>10}")

    winners = [k for k, v in results.items() if v["keep"]]
    print(f"\nrule: paired CI lower bound must exceed {KEEP_THRESHOLD}")
    print("winner:", winners[0] if winners else "none - keep baseline")

    with open(os.path.join(PROC, "noise_reduction.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"per_seed": {k: v.tolist() for k, v in per_seed.items()},
                   "paired": results}, fh, indent=1)


if __name__ == "__main__":
    main()
