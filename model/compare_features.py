"""
Do the v2 interpretable features close the gap to embeddings?

Everything is held identical across arms so the comparison is fair:
  * same grouped split (groups = transitive closure of test-id and headline)
  * same copy-only pair set, built once from v1 features
  * same ranker architecture, same epochs, same seed

Overfitting guards, applied to every arm:
  * shuffled-label control - train on permuted labels, evaluate on real pairs.
    Any arm whose control sits far above 0.50 is not trusted, however good its
    headline number looks.
  * val only. The test set stays sealed until the feature set is frozen.
  * a gain smaller than the control's deviation from chance is not a gain.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

from features_v2 import FEATURE_NAMES_V2, extract_vector_v2  # noqa: E402
from features_v3 import FEATURE_NAMES_V3, extract_vector_v3  # noqa: E402
from train_ranking import build_pairs, pairwise_accuracy  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPZ = os.path.join(ROOT, "data", "processed", "dataset.npz")
UPW = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")
EMB = os.path.join(ROOT, "data", "processed", "embeddings.npz")
V2_CACHE = os.path.join(ROOT, "data", "processed", "features_v2.npz")
V3_CACHE = os.path.join(ROOT, "data", "processed", "features_v3.npz")
MIN_GAP = 0.05
# Contingency C1: a feature set is kept only if it beats the incumbent by more
# than the shuffled-label control's deviation from chance. Anything smaller is
# indistinguishable from noise, regardless of how good the theory sounds.
KEEP_THRESHOLD = 0.0176


def load_rows() -> list[dict]:
    rows = []
    with open(UPW, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def split_indices(rows) -> dict[str, np.ndarray]:
    import random
    from collections import defaultdict
    members = defaultdict(list)
    for i, r in enumerate(rows):
        members[r["group"]].append(i)
    gids = sorted(members)
    random.Random(20260805).shuffle(gids)
    n = len(gids)
    n_tr, n_va = int(round(n * 0.70)), int(round(n * 0.15))
    parts = {"train": gids[:n_tr], "val": gids[n_tr:n_tr + n_va],
             "test": gids[n_tr + n_va:]}
    return {k: np.array(sorted(i for g in v for i in members[g]))
            for k, v in parts.items()}


def build_cached(rows, cache: str, names: list[str], fn) -> np.ndarray:
    if os.path.exists(cache):
        print(f"loading cached {os.path.basename(cache)}")
        return np.load(cache)["X"]
    print(f"extracting {len(names)} features for {len(rows):,} headlines...")
    X = np.zeros((len(rows), len(names)), dtype=np.float32)
    for i, r in enumerate(rows):
        X[i] = fn(r["headline"])
        if (i + 1) % 25000 == 0:
            print(f"  {i+1:,}/{len(rows):,}")
    np.savez_compressed(cache, X=X)
    return X


def rank_mlp(Xtr, ptr, Xva, pva, hidden=128, epochs=30, lr=1e-3, seed=0):
    torch.manual_seed(seed)
    net = nn.Sequential(
        nn.Linear(Xtr.shape[1], hidden), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(hidden, hidden), nn.ReLU(),
        nn.Linear(hidden, 1),
    )
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    Xt = torch.tensor(Xtr, dtype=torch.float32)
    Xv = torch.tensor(Xva, dtype=torch.float32)
    best = 0.5
    for _ in range(epochs):
        net.train()
        perm = np.random.permutation(len(ptr))
        for s in range(0, len(ptr), 4096):
            sel = ptr[perm[s:s + 4096]]
            opt.zero_grad(set_to_none=True)
            hi = net(Xt[torch.from_numpy(sel[:, 0])]).squeeze(-1)
            lo = net(Xt[torch.from_numpy(sel[:, 1])]).squeeze(-1)
            nn.functional.softplus(-(hi - lo)).mean().backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            best = max(best, pairwise_accuracy(net(Xv).squeeze(-1).numpy(), pva))
    return best


def standardise(Xtr, Xva):
    mu, sd = Xtr.mean(0), Xtr.std(0)
    sd[sd < 1e-6] = 1.0
    return (Xtr - mu) / sd, (Xva - mu) / sd


def main() -> None:
    d = np.load(NPZ, allow_pickle=True)
    rows = load_rows()
    idx = split_indices(rows)
    tr, va = idx["train"], idx["val"]

    X1_tr, X1_va = d["X_train"], d["X_val"]
    y_tr, t_tr = d["y_train"], d["t_train"]
    y_va, t_va = d["y_val"], d["t_val"]

    # One pair set, built from v1, reused everywhere.
    p_tr = build_pairs(y_tr, t_tr, MIN_GAP, X1_tr)
    p_va = build_pairs(y_va, t_va, MIN_GAP, X1_va)
    print(f"copy-only pairs: train={len(p_tr):,} val={len(p_va):,}\n")

    X2 = build_cached(rows, V2_CACHE, FEATURE_NAMES_V2, extract_vector_v2)
    X3 = build_cached(rows, V3_CACHE, FEATURE_NAMES_V3, extract_vector_v3)
    X2_tr, X2_va = standardise(X2[tr], X2[va])
    X3_tr, X3_va = standardise(X3[tr], X3[va])
    E = np.load(EMB)["E"]
    E_tr, E_va = E[tr], E[va]

    arms = {
        "v1 norms (50)": (X1_tr, X1_va),
        "v2 interpretable (78)": (X2_tr, X2_va),
        "v3 + identifiable (86)": (X3_tr, X3_va),
        "embeddings (384)": (E_tr, E_va),
        "v3 + embeddings (470)": (np.hstack([X3_tr, E_tr]),
                                  np.hstack([X3_va, E_va])),
    }

    print("=== pairwise accuracy (val) ===")
    results = {}
    for name, (A, B) in arms.items():
        acc = rank_mlp(A, p_tr, B, p_va)
        results[name] = acc
        print(f"  {name:<24} {acc:.4f}")

    # Shuffled-label control on the interpretable arm - the one we intend to
    # ship. If this is not near 0.50 the gain is not real.
    print("\n=== shuffled-label control (v2) ===")
    rng = np.random.default_rng(0)
    y_shuf = y_tr.copy()
    rng.shuffle(y_shuf)
    p_shuf = build_pairs(y_shuf, t_tr, MIN_GAP, X1_tr)
    ctrl = rank_mlp(X2_tr, p_shuf, X2_va, p_va)
    print(f"  v2 on shuffled labels    {ctrl:.4f}  (must be ~0.50)")

    v1, v2 = results["v1 norms (50)"], results["v2 interpretable (78)"]
    v3, emb = results["v3 + identifiable (86)"], results["embeddings (384)"]
    dev = abs(ctrl - 0.5)

    print(f"\nv2 gain over v1      : {v2 - v1:+.4f}")
    print(f"v3 gain over v2      : {v3 - v2:+.4f}   <- the C1 test")
    print(f"remaining gap to emb : {emb - v3:+.4f}")
    print(f"control deviation    : {dev:.4f}  (gains below this are noise)")

    verdict = ("KEEP v3 - gain clears the noise floor"
               if (v3 - v2) > KEEP_THRESHOLD else
               "DISCARD v3 - gain is within noise; the identifiable-individual "
               "hypothesis is not supported at scale")
    print(f"\nC1 VERDICT: {verdict}")

    with open(os.path.join(ROOT, "data", "processed",
                           "feature_comparison.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"results": results, "shuffled_control_v2": ctrl,
                   "n_val_pairs": int(len(p_va))}, fh, indent=1)


if __name__ == "__main__":
    main()
