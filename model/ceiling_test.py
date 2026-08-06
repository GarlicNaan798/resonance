"""
Feature ceiling test: are 50 psycholinguistic norms enough?

The constrained model reached 0.5649 pairwise on copy-only pairs. The open
question is whether that is the limit of the TASK or the limit of our FEATURES.

Method: replace the 50 hand-designed features with sentence embeddings - a
384-dimensional semantic representation that carries meaning, topic, syntax and
tone. Embeddings are uninterpretable and would be a poor product surface, but
they are an excellent probe of how much signal the text contains at all.

Read the outcome like this:

  embeddings >> norms   the features are the bottleneck. Meaning matters more
                        than affective norms, and the product needs a semantic
                        layer (with interpretability recovered some other way).

  embeddings ~= norms   our interpretable features already capture what is
                        learnable. Keep them - they are strictly better for a
                        product that must explain itself.

  both near chance      the task is intrinsically hard; no feature set fixes it,
                        and the product claim must be measurement, not
                        prediction.

Everything is evaluated on the SAME grouped splits and the SAME copy-only pairs
as the main model, so the numbers are directly comparable.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from train_ranking import build_pairs, pairwise_accuracy  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPZ = os.path.join(ROOT, "data", "processed", "dataset.npz")
UPW = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")
EMB_CACHE = os.path.join(ROOT, "data", "processed", "embeddings.npz")
MIN_GAP = 0.05
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"


def load_headlines() -> list[str]:
    """Headlines in the same row order used to build dataset.npz."""
    heads = []
    with open(UPW, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                heads.append(json.loads(line)["headline"])
    return heads


def split_indices(n_rows: int) -> dict[str, np.ndarray]:
    """Rebuild the exact same grouped split assemble_dataset.py used."""
    import random
    from collections import defaultdict

    rows = []
    with open(UPW, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))

    members: dict[int, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        members[r["group"]].append(i)
    gids = sorted(members)
    random.Random(20260805).shuffle(gids)
    n = len(gids)
    n_tr = int(round(n * 0.70))
    n_va = int(round(n * 0.15))
    parts = {"train": gids[:n_tr], "val": gids[n_tr:n_tr + n_va],
             "test": gids[n_tr + n_va:]}
    return {k: np.array(sorted(i for g in v for i in members[g]))
            for k, v in parts.items()}


def embed(headlines: list[str]) -> np.ndarray:
    if os.path.exists(EMB_CACHE):
        print("loading cached embeddings")
        return np.load(EMB_CACHE)["E"]
    from sentence_transformers import SentenceTransformer
    print(f"embedding {len(headlines):,} headlines with {MODEL_NAME}")
    m = SentenceTransformer(MODEL_NAME)
    E = m.encode(headlines, batch_size=256, show_progress_bar=True,
                 convert_to_numpy=True, normalize_embeddings=True)
    np.savez_compressed(EMB_CACHE, E=E.astype(np.float32))
    return E.astype(np.float32)


def rank_mlp(Xtr, ptr, Xva, pva, hidden=128, epochs=30, lr=1e-3, seed=0):
    """Plain unconstrained ranker - a ceiling probe, not a product model."""
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
    for ep in range(epochs):
        net.train()
        perm = np.random.permutation(len(ptr))
        for s in range(0, len(ptr), 4096):
            sel = ptr[perm[s:s + 4096]]
            opt.zero_grad(set_to_none=True)
            s_hi = net(Xt[torch.from_numpy(sel[:, 0])]).squeeze(-1)
            s_lo = net(Xt[torch.from_numpy(sel[:, 1])]).squeeze(-1)
            nn.functional.softplus(-(s_hi - s_lo)).mean().backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            sv = net(Xv).squeeze(-1).numpy()
        best = max(best, pairwise_accuracy(sv, pva))
    return best


def main() -> None:
    d = np.load(NPZ, allow_pickle=True)
    heads = load_headlines()
    idx = split_indices(len(heads))
    print(f"{len(heads):,} headlines; train={len(idx['train']):,} "
          f"val={len(idx['val']):,}")

    E = embed(heads)
    print(f"embeddings: {E.shape}")

    y_tr, t_tr = d["y_train"], d["t_train"]
    y_va, t_va = d["y_val"], d["t_val"]
    X_tr, X_va = d["X_train"], d["X_val"]
    E_tr, E_va = E[idx["train"]], E[idx["val"]]

    # Pairs are built on the NORM features so both arms of the comparison use
    # an identical pair set - otherwise the two numbers are not comparable.
    p_tr = build_pairs(y_tr, t_tr, MIN_GAP, X_tr)
    p_va = build_pairs(y_va, t_va, MIN_GAP, X_va)
    print(f"copy-only pairs: train={len(p_tr):,} val={len(p_va):,}\n")

    print("=== pairwise accuracy on identical splits and pairs ===")
    a_norm = rank_mlp(X_tr, p_tr, X_va, p_va)
    print(f"  50 norm features      : {a_norm:.4f}")

    a_emb = rank_mlp(E_tr, p_tr, E_va, p_va)
    print(f"  384-dim embeddings    : {a_emb:.4f}")

    a_both = rank_mlp(np.hstack([X_tr, E_tr]), p_tr,
                      np.hstack([X_va, E_va]), p_va)
    print(f"  norms + embeddings    : {a_both:.4f}")

    print(f"\n  constrained model     : 0.5649  (from train_ranking.py)")
    print(f"  best single feature   : 0.5698")

    delta = a_emb - a_norm
    print(f"\nembedding advantage: {delta:+.4f}")
    if delta > 0.03:
        print("=> FEATURES are the bottleneck; semantics carry real extra signal.")
    elif delta > 0.01:
        print("=> modest semantic gain; worth a hybrid, not a rewrite.")
    else:
        print("=> norms already capture what is learnable. Keep the "
              "interpretable features.")

    with open(os.path.join(ROOT, "data", "processed", "ceiling_report.json"),
              "w", encoding="utf-8") as fh:
        json.dump({"norms": a_norm, "embeddings": a_emb, "both": a_both,
                   "constrained_model": 0.5649, "best_single_feature": 0.5698,
                   "n_val_pairs": int(len(p_va))}, fh, indent=1)


if __name__ == "__main__":
    main()
