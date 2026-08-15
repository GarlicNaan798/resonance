"""
Listwise objective: train on whole experiments instead of extracted pairs.

Solution 1 from the Phase 5 list, and the cheapest untried idea.

Every model so far learns from PAIRS: an experiment with 5 arms is decomposed
into 10 independent comparisons, and the model never sees that they came from
one experiment. That throws away structure. The arms compete for one fixed
pool of impressions, and their relative order is a single joint fact, not ten
separate ones.

The listwise alternative (ListNet, Cao et al. 2007) treats each experiment as
one training example: softmax over the arms' scores, cross-entropy against the
softmax of their true values. The model is asked "which arm won this
experiment", which is exactly the question the product asks.

Why this might beat pairwise here specifically: with ~4.6 arms per experiment,
pairwise decomposition over-weights experiments with many arms (they generate
quadratically more pairs) and lets the model see the same arm many times with
inconsistent partners. Listwise weights every experiment equally.

Kept deliberately simple. One loss function, same architecture, same splits.
Evaluated on the same copy-only pairs so the number is comparable to everything
else in the project.
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
from accuracy_push import (base_split, build_pairs, carve_dev,  # noqa: E402
                           load_rows, MIN_GAP)
from tune_and_ensemble import Ranker, acc_ci, scores_of  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
N_SEEDS = 5
KEEP_THRESHOLD = 0.02
# Temperature on the target distribution. Lower = sharper = more weight on the
# single winner; higher = softer, closer to "rank them all".
TAU = 0.5


def build_lists(idxs, rows, y, ident, min_arms=2):
    """Group rows into experiments, keeping one row per distinct copy."""
    by_test = defaultdict(list)
    for i in idxs:
        by_test[rows[int(i)]["test_id"]].append(int(i))

    lists = []
    for members in by_test.values():
        seen, keep = set(), []
        for i in members:
            k = float(ident[i][0])
            if k not in seen:
                seen.add(k)
                keep.append(i)
        if len(keep) >= min_arms:
            lists.append(np.array(keep))
    return lists


def listwise_loss(scores, targets, tau=TAU):
    """ListNet cross-entropy between score-softmax and target-softmax."""
    p_target = torch.softmax(targets / tau, dim=0)
    log_p_model = torch.log_softmax(scores, dim=0)
    return -(p_target * log_p_model).sum()


def train_listwise(E, lists, y, dim, seed, hidden=128, lr=1e-3, epochs=25,
                   dropout=0.2, wd=1e-4, depth=2, batch_lists=64):
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = Ranker(dim, hidden, dropout, depth)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    Et = torch.tensor(E, dtype=torch.float32)
    yt = torch.tensor(y, dtype=torch.float32)

    for _ in range(epochs):
        model.train()
        order = np.random.permutation(len(lists))
        for s in range(0, len(order), batch_lists):
            opt.zero_grad(set_to_none=True)
            total = 0.0
            chunk = order[s:s + batch_lists]
            for li in chunk:
                idx = lists[li]
                sc = model(Et[torch.from_numpy(idx)])
                total = total + listwise_loss(sc, yt[torch.from_numpy(idx)])
            (total / max(len(chunk), 1)).backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
    model.eval()
    return model


def train_pairwise(E, pairs, dim, seed, hidden=128, lr=1e-3, epochs=25,
                   dropout=0.2, wd=1e-4, depth=2, batch=4096):
    """The incumbent, retrained here so both arms share this script's setup."""
    torch.manual_seed(seed)
    np.random.seed(seed)
    model = Ranker(dim, hidden, dropout, depth)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    Et = torch.tensor(E, dtype=torch.float32)
    for _ in range(epochs):
        model.train()
        perm = np.random.permutation(len(pairs))
        for s in range(0, len(pairs), batch):
            sel = pairs[perm[s:s + batch]]
            opt.zero_grad(set_to_none=True)
            hi = model(Et[torch.from_numpy(sel[:, 0])])
            lo = model(Et[torch.from_numpy(sel[:, 1])])
            nn.functional.softplus(-(hi - lo)).mean().backward()
            opt.step()
    model.eval()
    return model


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
    lists_in = build_lists(inner, rows, y, ident)

    arms = [len(l) for l in lists_in]
    print(f"pairwise training pairs : {len(p_in):,}")
    print(f"listwise training lists : {len(lists_in):,} "
          f"(mean {np.mean(arms):.1f} arms, max {max(arms)})")
    print(f"dev pairs               : {len(p_dev):,}\n")

    E_in_local = E[inner]
    # Lists hold GLOBAL indices; remap to positions within E_in_local.
    pos = {int(g): k for k, g in enumerate(inner)}
    lists_local = [np.array([pos[int(i)] for i in l]) for l in lists_in]
    y_local = y[inner]

    print(f"{N_SEEDS} seeds per method\n")
    results = {}
    for name in ("pairwise", "listwise"):
        accs, scores = [], []
        for s in range(N_SEEDS):
            if name == "pairwise":
                m = train_pairwise(E_in_local, p_in, dim, seed=s)
            else:
                m = train_listwise(E_in_local, lists_local, y_local, dim, seed=s)
            sc = scores_of(m, E[dev])
            scores.append(sc)
            a, _ = acc_ci(sc, p_dev, t[dev])
            accs.append(a)
        accs = np.array(accs)
        z = np.stack([(s - s.mean()) / (s.std() + 1e-9) for s in scores])
        ens, ens_ci = acc_ci(z.mean(axis=0), p_dev, t[dev])
        results[name] = {"single_mean": float(accs.mean()),
                         "single_sd": float(accs.std(ddof=1)),
                         "ensemble": ens, "ensemble_ci": list(ens_ci)}
        print(f"  {name:<10} single {accs.mean():.4f} (sd {accs.std(ddof=1):.4f})"
              f"   ensemble {ens:.4f} [{ens_ci[0]:.4f}, {ens_ci[1]:.4f}]")

    gain_single = results["listwise"]["single_mean"] - results["pairwise"]["single_mean"]
    gain_ens = results["listwise"]["ensemble"] - results["pairwise"]["ensemble"]
    print(f"\nlistwise vs pairwise, single seed : {gain_single:+.4f}")
    print(f"listwise vs pairwise, ensemble    : {gain_ens:+.4f}")
    print(f"\nVERDICT: {'KEEP listwise' if max(gain_single, gain_ens) > KEEP_THRESHOLD else 'below threshold - keep pairwise'}"
          f"  (threshold {KEEP_THRESHOLD})")
    print("\nCeiling reminder: 0.7880. Dev numbers; a test read is required "
          "before anything here ships.")

    with open(os.path.join(PROC, "listwise.json"), "w", encoding="utf-8") as fh:
        json.dump({"results": results, "gain_single": gain_single,
                   "gain_ensemble": gain_ens, "tau": TAU}, fh, indent=1)


if __name__ == "__main__":
    main()
