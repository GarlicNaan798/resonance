"""
Phase 0: what do the embeddings know that our interpretable features do not?

Embeddings rank at 0.6247; 78 interpretable features rank at 0.5611. Theory-led
feature engineering closed none of that gap, so guessing again is a poor bet.
This script does the evidence-led thing instead: find the pairs where the
embedding ranker gets the order RIGHT and the interpretable model gets it
WRONG, and read them.

Output is deliberately human-readable. The question being answered is "is there
a nameable property here?", and only a person reading headlines can answer it.

Three views are produced:
  1. Worst disagreements - largest margin by which embeddings beat v2.
  2. Aggregate contrasts - how the winning and losing headlines differ on every
     interpretable feature, as a standardised mean difference. If a feature
     shows a large gap here but is not being used, that is a modelling failure
     rather than a feature gap.
  3. Topic probe - the most distinctive words in true winners vs losers, which
     reveals whether the signal is SUBJECT MATTER (which norms structurally
     cannot represent) rather than style.

No training data is touched and the test set is not opened.
"""

from __future__ import annotations

import json
import os
import re
import sys
from collections import Counter

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

from features_v2 import FEATURE_NAMES_V2  # noqa: E402
from train_ranking import build_pairs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPZ = os.path.join(ROOT, "data", "processed", "dataset.npz")
UPW = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")
EMB = os.path.join(ROOT, "data", "processed", "embeddings.npz")
V2 = os.path.join(ROOT, "data", "processed", "features_v2.npz")
OUT = os.path.join(ROOT, "data", "processed", "disagreements.txt")
MIN_GAP = 0.05
N_SHOW = 25


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


def rank_mlp(Xtr, ptr, Xva, hidden=128, epochs=30, lr=1e-3, seed=0):
    """Train a ranker and return its val scores."""
    torch.manual_seed(seed)
    net = nn.Sequential(
        nn.Linear(Xtr.shape[1], hidden), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(hidden, hidden), nn.ReLU(),
        nn.Linear(hidden, 1),
    )
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    Xt = torch.tensor(Xtr, dtype=torch.float32)
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
        return net(torch.tensor(Xva, dtype=torch.float32)).squeeze(-1).numpy()


def standardise(a, b):
    mu, sd = a.mean(0), a.std(0)
    sd[sd < 1e-6] = 1.0
    return (a - mu) / sd, (b - mu) / sd


_word = re.compile(r"[a-z][a-z'-]+")


def distinctive_words(win: list[str], lose: list[str], k: int = 18):
    """Words most over-represented in winners vs losers (add-1 smoothed ratio)."""
    cw = Counter(w for h in win for w in set(_word.findall(h.lower())))
    cl = Counter(w for h in lose for w in set(_word.findall(h.lower())))
    vocab = {w for w in cw if cw[w] >= 8} | {w for w in cl if cl[w] >= 8}
    nw, nl = max(len(win), 1), max(len(lose), 1)
    scored = []
    for w in vocab:
        pw = (cw[w] + 1) / (nw + 2)
        pl = (cl[w] + 1) / (nl + 2)
        scored.append((np.log(pw / pl), w, cw[w], cl[w]))
    scored.sort(reverse=True)
    return scored[:k], scored[-k:]


def main() -> None:
    d = np.load(NPZ, allow_pickle=True)
    rows = load_rows()
    idx = split_indices(rows)
    tr, va = idx["train"], idx["val"]

    X1_tr, X1_va = d["X_train"], d["X_val"]
    y_va, t_va = d["y_val"], d["t_val"]
    y_tr, t_tr = d["y_train"], d["t_train"]

    p_tr = build_pairs(y_tr, t_tr, MIN_GAP, X1_tr)
    p_va = build_pairs(y_va, t_va, MIN_GAP, X1_va)

    X2 = np.load(V2)["X"]
    X2_tr, X2_va = standardise(X2[tr], X2[va])
    E = np.load(EMB)["E"]
    E_tr, E_va = E[tr], E[va]

    print(f"val pairs: {len(p_va):,}\ntraining both rankers...")
    s_v2 = rank_mlp(X2_tr, p_tr, X2_va)
    s_emb = rank_mlp(E_tr, p_tr, E_va)

    heads = [rows[i]["headline"] for i in va]

    hi, lo = p_va[:, 0], p_va[:, 1]
    emb_right = s_emb[hi] > s_emb[lo]
    v2_right = s_v2[hi] > s_v2[lo]
    disagree = emb_right & ~v2_right
    both_right = emb_right & v2_right

    print(f"  embeddings right, v2 wrong : {disagree.sum():,} "
          f"({disagree.mean():.1%})")
    print(f"  both right                 : {both_right.sum():,}")
    print(f"  v2 right, embeddings wrong : {(v2_right & ~emb_right).sum():,}")

    # margin by which embeddings separated the pair that v2 got backwards
    margin = (s_emb[hi] - s_emb[lo]) - (s_v2[hi] - s_v2[lo])
    order = np.argsort(-margin)
    order = [i for i in order if disagree[i]][:N_SHOW]

    lines = []
    lines.append("PAIRS THE EMBEDDINGS ORDER CORRECTLY AND v2 GETS BACKWARDS")
    lines.append("(WINNER is the arm that actually performed better)\n")
    for rank, i in enumerate(order, 1):
        a, b = hi[i], lo[i]
        lines.append(f"--- {rank}. margin={margin[i]:+.3f}  "
                     f"true gap={y_va[a]-y_va[b]:+.3f}")
        lines.append(f"  WINNER : {heads[a]}")
        lines.append(f"  LOSER  : {heads[b]}")
        lines.append("")

    # aggregate feature contrast on the disagreement set
    lines.append("\nSTANDARDISED MEAN DIFFERENCE (winner - loser) ON DISAGREEMENTS")
    lines.append("large |d| = a real difference our features CAN see but the "
                 "model is not exploiting\n")
    dh, dl = hi[disagree], lo[disagree]
    diffs = []
    for j, name in enumerate(FEATURE_NAMES_V2):
        delta = X2_va[dh, j] - X2_va[dl, j]
        sd = delta.std()
        diffs.append((abs(delta.mean() / sd) if sd > 1e-9 else 0.0,
                      delta.mean(), name))
    diffs.sort(reverse=True)
    for dmag, dmean, name in diffs[:15]:
        lines.append(f"  {name:<24} d={dmean:+.4f}  |d/sd|={dmag:.3f}")

    # topic probe over ALL val pairs, not just disagreements
    win_h = [heads[a] for a in hi]
    lose_h = [heads[b] for b in lo]
    top, bottom = distinctive_words(win_h, lose_h)
    lines.append("\nWORDS OVER-REPRESENTED IN WINNERS (all val pairs)")
    for s, w, cw, cl in top:
        lines.append(f"  {w:<18} log-ratio={s:+.3f}  win={cw} lose={cl}")
    lines.append("\nWORDS OVER-REPRESENTED IN LOSERS")
    for s, w, cw, cl in reversed(bottom):
        lines.append(f"  {w:<18} log-ratio={s:+.3f}  win={cw} lose={cl}")

    text = "\n".join(lines)
    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(f"\nwrote {OUT}")
    print("\n" + text[:3000])


if __name__ == "__main__":
    main()
