"""
Can we pick the winning headline within an experiment?

R2 against a noisy continuous target understates ranking ability, and ranking is
what the product does: a marketer holds two or three variants and asks which to
run. So the honest metric is pairwise accuracy WITHIN an experiment, where the
article, image and timing are held constant.

Chance is 50%. Anything reliably above that is commercially useful even if R2 is
near zero, because the alternative - copywriter intuition - is what A/B testing
exists to correct.

A confidence interval is reported, computed over EXPERIMENTS rather than pairs,
because pairs drawn from the same experiment are not independent.
"""

from __future__ import annotations

import os
import sys
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPZ = os.path.join(ROOT, "data", "processed", "dataset.npz")

MIN_GAP = 0.10   # ignore near-tied arms: their ordering is mostly noise


def fit_mlp(Xtr, ytr, hidden=128, epochs=40, lr=2e-3, wd=1e-4, seed=0):
    torch.manual_seed(seed)
    net = nn.Sequential(
        nn.Linear(Xtr.shape[1], hidden), nn.ReLU(),
        nn.Linear(hidden, hidden), nn.ReLU(),
        nn.Linear(hidden, 1),
    )
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
    Xt, yt = torch.tensor(Xtr), torch.tensor(ytr)
    n = len(yt)
    for _ in range(epochs):
        perm = torch.randperm(n)
        for s in range(0, n, 1024):
            idx = perm[s:s + 1024]
            opt.zero_grad(set_to_none=True)
            nn.functional.mse_loss(net(Xt[idx]).squeeze(-1), yt[idx]).backward()
            opt.step()
    net.eval()
    return net


def pairwise_by_experiment(pred, y, tids, min_gap=MIN_GAP):
    """Accuracy per experiment, so the CI respects clustering."""
    groups: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(tids):
        groups[t].append(i)

    per_exp = []
    n_pairs = 0
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        correct = total = 0
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                gap = y[i] - y[j]
                if abs(gap) < min_gap:
                    continue
                pgap = pred[i] - pred[j]
                if pgap == 0:
                    continue
                correct += int((gap > 0) == (pgap > 0))
                total += 1
        if total:
            per_exp.append(correct / total)
            n_pairs += total
    arr = np.array(per_exp)
    mean = float(arr.mean())
    se = float(arr.std(ddof=1) / np.sqrt(len(arr)))
    return mean, (mean - 1.96 * se, mean + 1.96 * se), len(arr), n_pairs


def main() -> None:
    d = np.load(NPZ, allow_pickle=True)
    Xtr, ytr = d["X_train"], d["y_train"]
    Xva, yva, tva = d["X_val"], d["y_val"], d["t_val"]

    print(f"train {Xtr.shape}  val {Xva.shape}")
    print(f"pairs use |target gap| >= {MIN_GAP} (near-ties are noise)\n")

    net = fit_mlp(Xtr, ytr)
    with torch.no_grad():
        pred = net(torch.tensor(Xva)).squeeze(-1).numpy()

    acc, ci, n_exp, n_pairs = pairwise_by_experiment(pred, yva, tva)
    print(f"MODEL   pairwise accuracy = {acc:.4f}  "
          f"95% CI [{ci[0]:.4f}, {ci[1]:.4f}]")
    print(f"        over {n_exp:,} experiments / {n_pairs:,} pairs")

    rng = np.random.default_rng(0)
    racc, rci, _, _ = pairwise_by_experiment(
        rng.normal(size=len(yva)), yva, tva)
    print(f"RANDOM  pairwise accuracy = {racc:.4f}  "
          f"95% CI [{rci[0]:.4f}, {rci[1]:.4f}]")

    # Single strongest feature, selected on TRAIN and scored on VAL.
    # Selecting the feature on val and reporting its val score would be
    # optimistically biased - the selection itself is a fit to that data.
    import json
    names = json.load(open(os.path.join(ROOT, "data", "processed",
                                        "feature_scaler.json"),
                           encoding="utf-8"))["features"]
    ttr = d["t_train"]
    best_j, best_train_acc = None, 0.0
    for j in range(Xtr.shape[1]):
        for sign in (1.0, -1.0):
            a, _, _, _ = pairwise_by_experiment(sign * Xtr[:, j], ytr, ttr)
            if a > best_train_acc:
                best_train_acc, best_j = a, (j, sign)

    j, sign = best_j
    val_acc, val_ci, _, _ = pairwise_by_experiment(sign * Xva[:, j], yva, tva)
    print(f"BEST 1-FEATURE (chosen on train): {names[j]} "
          f"sign {sign:+.0f}")
    print(f"        train acc={best_train_acc:.4f}   "
          f"val acc={val_acc:.4f}  95% CI [{val_ci[0]:.4f}, {val_ci[1]:.4f}]")

    lift = acc - 0.5
    print(f"\nlift over chance: {lift:+.4f} "
          f"({'significant' if ci[0] > 0.5 else 'NOT significant'})")


if __name__ == "__main__":
    main()
