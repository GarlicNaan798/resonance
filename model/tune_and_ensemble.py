"""
Two standard techniques never applied here: systematic tuning, and ensembling.

Every experiment so far used ONE hyperparameter configuration, hidden 128,
lr 1e-3, 25 epochs, dropout 0.2, chosen early and never revisited. And every
result came from a SINGLE random seed. Both are ordinary sources of a point or
two, and both are cheap on cached embeddings.

Worth being clear about why these are the remaining candidates. Most published
CTR work reaches high AUC using USER features, behavioural logs, session
history, user ids. Those systems answer "will this user click this ad". We
answer "which copy is better", from text alone, with no user information. The
techniques that carry that literature do not transfer; generic model-selection
hygiene does.

Three things measured:
  1. Seed variance      - how much does the reported number move on seed alone?
                          If it moves more than our 0.02 threshold, every past
                          single-seed result needs reading more sceptically.
  2. Hyperparameter sweep - is the original config leaving anything on the table?
  3. Ensemble           - averaging scores across seeds, the most reliable
                          small win in the book.

Same dev split, same copy-only pairs, clustered CIs. Pre-registered rule: keep
only if the gain exceeds 0.02.
"""

from __future__ import annotations

import json
import os
import sys
import time
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (base_split, build_pairs, carve_dev,  # noqa: E402
                           load_rows, MIN_GAP)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
KEEP_THRESHOLD = 0.02
N_SEEDS = 7


class Ranker(nn.Module):
    def __init__(self, dim, hidden, dropout, depth=2):
        super().__init__()
        layers: list[nn.Module] = [nn.Linear(dim, hidden), nn.ReLU(),
                                   nn.Dropout(dropout)]
        for _ in range(depth - 1):
            layers += [nn.Linear(hidden, hidden), nn.ReLU()]
        layers += [nn.Linear(hidden, 1)]
        self.net = nn.Sequential(*layers)

    def forward(self, x):
        return self.net(x).squeeze(-1)


def fit(E, pairs, dim, hidden, lr, epochs, dropout, wd, depth, seed, batch=4096):
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = Ranker(dim, hidden, dropout, depth)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    Et = torch.tensor(E, dtype=torch.float32)
    n = len(pairs)
    for _ in range(epochs):
        model.train()
        perm = np.random.permutation(n)
        for s in range(0, n, batch):
            sel = pairs[perm[s:s + batch]]
            opt.zero_grad(set_to_none=True)
            hi = model(Et[torch.from_numpy(sel[:, 0])])
            lo = model(Et[torch.from_numpy(sel[:, 1])])
            nn.functional.softplus(-(hi - lo)).mean().backward()
            opt.step()
    model.eval()
    return model


def scores_of(model, E):
    with torch.no_grad():
        return model(torch.tensor(E, dtype=torch.float32)).numpy()


def acc_ci(scores, pairs, tids):
    by_exp = defaultdict(list)
    for k, i in enumerate(pairs[:, 0]):
        by_exp[tids[i]].append(k)
    hi, lo = scores[pairs[:, 0]], scores[pairs[:, 1]]
    correct = (hi > lo).astype(float) + 0.5 * (hi == lo)
    per = [float(correct[np.array(ks)].mean()) for ks in by_exp.values()]
    a = np.array(per)
    m = float(a.mean())
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return m, (m - 1.96 * se, m + 1.96 * se)


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
    dim = E.shape[1]

    p_in = build_pairs(y[inner], t[inner], MIN_GAP, ident[inner])
    p_dev = build_pairs(y[dev], t[dev], MIN_GAP, ident[dev])
    E_in, E_dev, t_dev = E[inner], E[dev], t[dev]
    print(f"inner pairs {len(p_in):,}  dev pairs {len(p_dev):,}\n")

    BASE = dict(hidden=128, lr=1e-3, epochs=25, dropout=0.2, wd=1e-4, depth=2)

    # ---- 1. seed variance ------------------------------------------------
    print("=== seed variance on the ORIGINAL config ===")
    seed_scores, seed_accs = [], []
    for s in range(N_SEEDS):
        m = fit(E_in, p_in, dim, seed=s, **BASE)
        sc = scores_of(m, E_dev)
        seed_scores.append(sc)
        a, _ = acc_ci(sc, p_dev, t_dev)
        seed_accs.append(a)
        print(f"  seed {s}: {a:.4f}")
    sa = np.array(seed_accs)
    print(f"  mean {sa.mean():.4f}  sd {sa.std(ddof=1):.4f}  "
          f"range {sa.max()-sa.min():.4f}")
    if sa.max() - sa.min() > KEEP_THRESHOLD:
        print("  NOTE: seed range exceeds the 0.02 keep-threshold. Single-seed")
        print("  results in this project should be read with that in mind.")

    # ---- 2. ensemble ------------------------------------------------------
    print("\n=== ensemble (mean of z-scored seed outputs) ===")
    z = np.stack([(s - s.mean()) / (s.std() + 1e-9) for s in seed_scores])
    ens_acc, ens_ci = acc_ci(z.mean(axis=0), p_dev, t_dev)
    print(f"  {N_SEEDS}-seed ensemble: {ens_acc:.4f} "
          f"95% CI [{ens_ci[0]:.4f}, {ens_ci[1]:.4f}]")
    print(f"  vs mean single seed   : {ens_acc - sa.mean():+.4f}")
    print(f"  vs best single seed   : {ens_acc - sa.max():+.4f}")

    # ---- 3. hyperparameter sweep -----------------------------------------
    print("\n=== hyperparameter sweep (seed 0) ===")
    grid = [
        dict(BASE),
        {**BASE, "hidden": 64},
        {**BASE, "hidden": 256},
        {**BASE, "lr": 3e-4},
        {**BASE, "lr": 3e-3},
        {**BASE, "epochs": 50},
        {**BASE, "epochs": 12},
        {**BASE, "dropout": 0.0},
        {**BASE, "dropout": 0.4},
        {**BASE, "wd": 1e-2},
        {**BASE, "depth": 1},
        {**BASE, "depth": 3},
    ]
    start = time.time()
    results = []
    for cfg in grid:
        m = fit(E_in, p_in, dim, seed=0, **cfg)
        a, ci = acc_ci(scores_of(m, E_dev), p_dev, t_dev)
        diff = {k: v for k, v in cfg.items() if BASE[k] != v} or {"(baseline)": ""}
        label = ", ".join(f"{k}={v}" for k, v in diff.items())
        results.append({"config": cfg, "label": label, "accuracy": a})
        print(f"  {label:<24} {a:.4f}  [{ci[0]:.4f}, {ci[1]:.4f}]")
    print(f"  ({time.time()-start:.0f}s)")

    base_acc = results[0]["accuracy"]
    best = max(results, key=lambda r: r["accuracy"])
    print(f"\nbaseline config : {base_acc:.4f}")
    print(f"best config     : {best['accuracy']:.4f}  ({best['label']})")
    print(f"tuning gain     : {best['accuracy'] - base_acc:+.4f}")
    print(f"ensemble gain   : {ens_acc - sa.mean():+.4f}")

    print("\nVERDICT:")
    for name, gain in (("tuning", best["accuracy"] - base_acc),
                       ("ensembling", ens_acc - sa.mean())):
        verdict = "KEEP" if gain > KEEP_THRESHOLD else "not above noise floor"
        print(f"  {name:<12} {gain:+.4f}  {verdict}")
    print(f"\n  Caveat: the sweep selects on dev, so the best config's dev score")
    print(f"  is optimistically biased by roughly the seed sd ({sa.std(ddof=1):.4f}).")

    with open(os.path.join(PROC, "tune_ensemble.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"seed_accs": seed_accs, "seed_sd": float(sa.std(ddof=1)),
                   "ensemble": ens_acc, "baseline": base_acc,
                   "best": {"label": best["label"], "accuracy": best["accuracy"]},
                   "sweep": [{"label": r["label"], "accuracy": r["accuracy"]}
                             for r in results]}, fh, indent=1)


if __name__ == "__main__":
    main()
