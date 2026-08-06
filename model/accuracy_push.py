"""
Phase 1.5, step 1: pairwise interaction on frozen embeddings.

The current ranker is a BI-ENCODER: each headline is scored alone, and the
comparison is just score(A) > score(B). That throws away every interaction
between the two texts - it cannot represent "B is better than A *because* B is
more specific than A", only "B scores high in isolation".

A cross-encoder fixes that by running a transformer over both texts jointly, but
on CPU that is hours of compute. This script tests whether the *interaction
itself* is where the gain lives, using cached embeddings and no transformer:

    input = [a, b, a-b, a*b]   ->   MLP   ->   logit P(A beats B)

The difference and product terms are exactly the interaction signals a
cross-encoder learns in its attention. If this moves the needle, a real
cross-encoder is worth the compute. If it does not, that is strong evidence the
bi-encoder was not the bottleneck and C9 applies.

Symmetry: every pair is trained in BOTH orders with flipped labels, and scored
antisymmetrically at eval, so the model cannot cheat by learning a position bias.

PROTOCOL: all iteration here is against a dev-test carved from TRAIN. The sealed
test set is untouched by this script.
"""

from __future__ import annotations

import json
import os
import random
import sys
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_ranking import build_pairs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPZ = os.path.join(ROOT, "data", "processed", "dataset.npz")
EMB = os.path.join(ROOT, "data", "processed", "embeddings.npz")
UPW = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")
MIN_GAP = 0.05
DEV_FRAC = 0.15
SEED = 20260805


def load_rows():
    rows = []
    with open(UPW, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def base_split(rows):
    members = defaultdict(list)
    for i, r in enumerate(rows):
        members[r["group"]].append(i)
    gids = sorted(members)
    random.Random(SEED).shuffle(gids)
    n = len(gids)
    n_tr, n_va = int(round(n * 0.70)), int(round(n * 0.15))
    return {"train": gids[:n_tr], "val": gids[n_tr:n_tr + n_va],
            "test": gids[n_tr + n_va:]}, members


def carve_dev(train_gids, members):
    """Split TRAIN groups into inner-train and dev-test. Test stays sealed."""
    gids = list(train_gids)
    random.Random(SEED + 1).shuffle(gids)
    k = int(round(len(gids) * DEV_FRAC))
    dev_g, inner_g = gids[:k], gids[k:]
    dev = np.array(sorted(i for g in dev_g for i in members[g]))
    inner = np.array(sorted(i for g in inner_g for i in members[g]))
    return inner, dev


def acc_ci(pred_wins: np.ndarray, tids: np.ndarray, pairs: np.ndarray):
    """Pairwise accuracy, 95% CI clustered by experiment."""
    by_exp = defaultdict(list)
    for k, i in enumerate(pairs[:, 0]):
        by_exp[tids[i]].append(k)
    per = [float(pred_wins[ks].mean()) for ks in by_exp.values()]
    a = np.array(per)
    m = float(a.mean())
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return m, (m - 1.96 * se, m + 1.96 * se), len(a)


# ---------------------------------------------------------------- models

class PointwiseRanker(nn.Module):
    """The incumbent: score each headline alone."""

    def __init__(self, d, hidden=128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(d, hidden), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1))

    def compare(self, a, b):
        return self.net(a).squeeze(-1) - self.net(b).squeeze(-1)


class InteractionRanker(nn.Module):
    """Sees both headlines and their interaction terms."""

    def __init__(self, d, hidden=256):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(4 * d, hidden), nn.ReLU(), nn.Dropout(0.3),
            nn.Linear(hidden, hidden // 2), nn.ReLU(), nn.Dropout(0.1),
            nn.Linear(hidden // 2, 1))

    def _f(self, a, b):
        return self.net(torch.cat([a, b, a - b, a * b], dim=-1)).squeeze(-1)

    def compare(self, a, b):
        # antisymmetric by construction: no position bias is representable
        return self._f(a, b) - self._f(b, a)


def train(model, E, pairs, epochs, lr, batch=2048, seed=0):
    torch.manual_seed(seed)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    Et = torch.tensor(E, dtype=torch.float32)
    n = len(pairs)
    for _ in range(epochs):
        model.train()
        perm = np.random.permutation(n)
        for s in range(0, n, batch):
            sel = pairs[perm[s:s + batch]]
            a = Et[torch.from_numpy(sel[:, 0])]
            b = Et[torch.from_numpy(sel[:, 1])]
            opt.zero_grad(set_to_none=True)
            # both orders, flipped targets
            d1 = model.compare(a, b)
            d2 = model.compare(b, a)
            loss = (nn.functional.softplus(-d1).mean()
                    + nn.functional.softplus(d2).mean()) / 2
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
    model.eval()
    return model


def evaluate(model, E, pairs, tids):
    Et = torch.tensor(E, dtype=torch.float32)
    outs = []
    with torch.no_grad():
        for s in range(0, len(pairs), 4096):
            sel = pairs[s:s + 4096]
            outs.append(model.compare(Et[torch.from_numpy(sel[:, 0])],
                                      Et[torch.from_numpy(sel[:, 1])]).numpy())
    d = np.concatenate(outs)
    wins = (d > 0).astype(float) + 0.5 * (d == 0)
    return d, acc_ci(wins, tids, pairs)


def main() -> None:
    d = np.load(NPZ, allow_pickle=True)
    rows = load_rows()
    parts, members = base_split(rows)
    inner, dev = carve_dev(parts["train"], members)

    E = np.load(EMB)["E"]
    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])

    # v1 features only used to identify identical-copy pairs for exclusion
    Xall = np.zeros((len(rows), 1), dtype=np.float32)
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    Xall[:, 0] = inv                      # identical text -> identical value

    p_in = build_pairs(y[inner], t[inner], MIN_GAP, Xall[inner])
    p_dev = build_pairs(y[dev], t[dev], MIN_GAP, Xall[dev])
    print(f"inner-train groups: {len(parts['train']) - int(round(len(parts['train'])*DEV_FRAC)):,}")
    print(f"inner arms={len(inner):,} pairs={len(p_in):,}")
    print(f"dev   arms={len(dev):,} pairs={len(p_dev):,}")
    print("(sealed test set untouched by this script)\n")

    E_in, E_dev = E[inner], E[dev]
    t_dev = t[dev]

    print("=== dev-test pairwise accuracy ===")
    results = {}

    pw = train(PointwiseRanker(E.shape[1]), E_in, p_in, epochs=25, lr=1e-3)
    _, (a1, ci1, nexp) = evaluate(pw, E_dev, p_dev, t_dev)
    results["pointwise (incumbent)"] = a1
    print(f"  pointwise (incumbent)  {a1:.4f}  95% CI [{ci1[0]:.4f}, {ci1[1]:.4f}]")

    ix = train(InteractionRanker(E.shape[1]), E_in, p_in, epochs=25, lr=1e-3)
    _, (a2, ci2, _) = evaluate(ix, E_dev, p_dev, t_dev)
    results["interaction"] = a2
    print(f"  interaction            {a2:.4f}  95% CI [{ci2[0]:.4f}, {ci2[1]:.4f}]")

    gain = a2 - a1
    print(f"\n  over {nexp:,} dev experiments")
    print(f"  interaction gain: {gain:+.4f}")
    print(f"  ceiling 0.7880 | signal captured: "
          f"pointwise {(a1-0.5)/0.288:.1%}  interaction {(a2-0.5)/0.288:.1%}")

    if gain > 0.02:
        print("\n  => interaction helps. A real cross-encoder is worth the compute.")
    else:
        print("\n  => C9: interaction gain is within noise. The bi-encoder was "
              "not the bottleneck.")

    with open(os.path.join(ROOT, "data", "processed", "phase15_step1.json"),
              "w", encoding="utf-8") as fh:
        json.dump({"results": results, "gain": gain,
                   "n_dev_pairs": int(len(p_dev))}, fh, indent=1)


if __name__ == "__main__":
    main()
