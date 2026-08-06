"""
Pairwise ranking trainer.

Why this replaces regression
----------------------------
Regression on the within-test contrast scored 0.5187 pairwise - worse than a
single feature (exclaim_count, 0.5698). The cause is an objective mismatch:
roughly a third of the target's variance is sampling noise, and squared error
spends most of its effort fitting that noise. The product never needs the
absolute contrast; it needs the ORDER of two variants.

So we optimise order directly. For every pair of arms (i, j) inside the same
experiment, RankNet loss:

    L = -log sigmoid( (s_i - s_j) * sign(y_i - y_j) )

Pairs are drawn WITHIN `clickability_test_id` only, so article, image and
timing are held constant and the comparison isolates copy - the same logic that
justified the within-test target.

Two weightings, both principled:
  * gap weight       |y_i - y_j|, so confidently-ordered pairs matter more than
                     near-ties whose order is mostly noise.
  * precision weight harmonic mean of the two arms' inverse-variance weights, so
                     a pair measured on few impressions counts for less.
"""

from __future__ import annotations

import copy
import os
import sys
from collections import defaultdict
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn
import torch.nn.functional as F

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from architecture import ModelConfig, ResonanceNet  # noqa: E402
from train import set_seed  # noqa: E402


@dataclass
class RankConfig:
    lr: float = 3e-3
    weight_decay: float = 1e-2
    max_epochs: int = 200
    patience: int = 20
    pairs_per_batch: int = 4096
    grad_clip: float = 1.0
    min_gap: float = 0.05     # ignore pairs closer than this - noise
    seed: int = 20260805


def build_pairs(y: np.ndarray, tids: np.ndarray, min_gap: float,
                X: np.ndarray | None = None) -> np.ndarray:
    """Within-experiment pairs with a meaningful gap, as (i, j) with y_i > y_j.

    CRITICAL: Upworthy varied headline AND image (`eyecatcher_id`), so many arms
    inside one experiment share identical copy and differ only in the picture.
    Those pairs are unpredictable from text by construction - 48% of all pairs -
    and including them silently caps accuracy near chance. When X is supplied,
    pairs with identical feature vectors are excluded so the metric measures the
    copy effect and nothing else.
    """
    groups: dict[str, list[int]] = defaultdict(list)
    for i, t in enumerate(tids):
        groups[t].append(i)

    pairs = []
    for idxs in groups.values():
        if len(idxs) < 2:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                if abs(y[i] - y[j]) < min_gap:
                    continue
                if X is not None and np.array_equal(X[i], X[j]):
                    continue          # same copy, different image
                pairs.append((i, j) if y[i] > y[j] else (j, i))
    return np.array(pairs, dtype=np.int64)


def pairwise_accuracy(scores: np.ndarray, pairs: np.ndarray) -> float:
    """Fraction of pairs ordered correctly; exact ties score 0.5, not 0.

    Counting a tie as a loss pushes a tied model BELOW chance, which is what
    made an untrained control report 0.27 instead of 0.50.
    """
    if len(pairs) == 0:
        return 0.5
    hi, lo = scores[pairs[:, 0]], scores[pairs[:, 1]]
    return float((hi > lo).mean() + 0.5 * (hi == lo).mean())


def train_ranker(X_tr, y_tr, w_tr, t_tr, X_va, y_va, w_va, t_va,
                 model_cfg: ModelConfig | None = None,
                 cfg: RankConfig | None = None,
                 verbose: bool = True) -> tuple[ResonanceNet, dict]:
    cfg = cfg or RankConfig()
    model_cfg = model_cfg or ModelConfig(n_features=X_tr.shape[1])
    set_seed(cfg.seed)

    tr_pairs = build_pairs(y_tr, t_tr, cfg.min_gap, X_tr)
    va_pairs = build_pairs(y_va, t_va, cfg.min_gap, X_va)
    if verbose:
        print(f"pairs: train={len(tr_pairs):,}  val={len(va_pairs):,}")

    Xt = torch.tensor(X_tr, dtype=torch.float32)
    Xv = torch.tensor(X_va, dtype=torch.float32)
    yt = torch.tensor(y_tr, dtype=torch.float32)
    wt = torch.tensor(w_tr, dtype=torch.float32)

    model = ResonanceNet(model_cfg)
    decay, no_decay = [], []
    for name, p in model.named_parameters():
        (no_decay if p.ndim == 1 or name.startswith("_") else decay).append(p)
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": cfg.weight_decay},
         {"params": no_decay, "weight_decay": 0.0}], lr=cfg.lr)

    best_acc, best_state, stale = 0.0, copy.deepcopy(model.state_dict()), 0
    n_pairs = len(tr_pairs)

    for epoch in range(cfg.max_epochs):
        model.train()
        perm = np.random.permutation(n_pairs)
        for s in range(0, n_pairs, cfg.pairs_per_batch):
            sel = tr_pairs[perm[s:s + cfg.pairs_per_batch]]
            hi = torch.from_numpy(sel[:, 0])
            lo = torch.from_numpy(sel[:, 1])

            opt.zero_grad(set_to_none=True)
            s_hi = model(Xt[hi], None)["score"]
            s_lo = model(Xt[lo], None)["score"]

            gap = (yt[hi] - yt[lo]).abs()
            prec = 2.0 / (1.0 / wt[hi].clamp_min(1e-6)
                          + 1.0 / wt[lo].clamp_min(1e-6))   # harmonic mean
            pw = gap * prec
            pw = pw / pw.mean().clamp_min(1e-8)

            loss = (F.softplus(-(s_hi - s_lo)) * pw).mean()
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
            opt.step()

        model.eval()
        with torch.no_grad():
            sv = model(Xv, None)["score"].numpy()
        acc = pairwise_accuracy(sv, va_pairs)

        if acc > best_acc + 1e-4:
            best_acc, best_state, stale = acc, copy.deepcopy(model.state_dict()), 0
        else:
            stale += 1
            if stale >= cfg.patience:
                break
        if verbose and epoch % 10 == 0:
            print(f"  epoch {epoch:3d}  val pairwise acc = {acc:.4f}")

    model.load_state_dict(best_state)
    return model, {"val_pairwise_acc": best_acc,
                   "n_train_pairs": int(len(tr_pairs)),
                   "n_val_pairs": int(len(va_pairs))}


def main() -> None:
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = np.load(os.path.join(root, "data", "processed", "dataset.npz"),
                allow_pickle=True)

    model, info = train_ranker(
        d["X_train"], d["y_train"], d["w_train"], d["t_train"],
        d["X_val"], d["y_val"], d["w_val"], d["t_val"])

    print(f"\nbest val pairwise accuracy: {info['val_pairwise_acc']:.4f}")
    print(f"  (regression baseline was 0.5187; "
          f"best single feature 0.5698)")

    # negative control: shuffled labels must collapse to chance
    rng = np.random.default_rng(0)
    y_shuf = d["y_train"].copy()
    rng.shuffle(y_shuf)
    _, sinfo = train_ranker(
        d["X_train"], y_shuf, d["w_train"], d["t_train"],
        d["X_val"], d["y_val"], d["w_val"], d["t_val"], verbose=False)
    print(f"shuffled-label control    : {sinfo['val_pairwise_acc']:.4f} "
          f"(must be ~0.50)")

    torch.save(model.state_dict(),
               os.path.join(root, "data", "processed", "ranker.pt"))
    print("saved ranker.pt")


if __name__ == "__main__":
    main()
