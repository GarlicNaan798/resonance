"""
Why is pairwise accuracy below chance?

A shuffled-label model scoring 0.27 instead of 0.50 cannot be a modelling
result - random predictions cannot be reliably WRONG. That pattern points at
ties: `scores[i] > scores[j]` is False when the two scores are equal, so a model
whose output has collapsed to a near-constant scores far BELOW chance rather
than at it.

This script checks the score distribution, the tie rate, and each module's
spread to find where the collapse happens.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from architecture import MODULES, ModelConfig, ResonanceNet  # noqa: E402
from train_ranking import build_pairs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
d = np.load(os.path.join(ROOT, "data", "processed", "dataset.npz"),
            allow_pickle=True)

Xv = torch.tensor(d["X_val"], dtype=torch.float32)
yv, tv = d["y_val"], d["t_val"]

cfg = ModelConfig(n_features=Xv.shape[1])
model = ResonanceNet(cfg)
state = os.path.join(ROOT, "data", "processed", "ranker.pt")
if os.path.exists(state):
    model.load_state_dict(torch.load(state))
    print("loaded trained ranker.pt")
model.eval()

with torch.no_grad():
    out = model(Xv, None)
s = out["score"].numpy()

print(f"\nscore: mean={s.mean():+.6f}  sd={s.std():.6f}")
print(f"       min={s.min():+.6f}  max={s.max():+.6f}  range={np.ptp(s):.6f}")
print(f"unique score values: {len(np.unique(s)):,} of {len(s):,}")

print("\nmodule activations (sd is the thing to watch):")
for m in MODULES:
    a = out["modules"][m].numpy()
    print(f"  {m:<10} mean={a.mean():+.4f} sd={a.std():.6f} "
          f"min={a.min():+.4f} max={a.max():+.4f}")

pairs = build_pairs(yv, tv, 0.05)
hi, lo = s[pairs[:, 0]], s[pairs[:, 1]]
wins = (hi > lo).mean()
ties = (hi == lo).mean()
losses = (hi < lo).mean()
print(f"\npairs={len(pairs):,}")
print(f"  strict wins : {wins:.4f}")
print(f"  exact ties  : {ties:.4f}   <-- counted as failures by `>`")
print(f"  losses      : {losses:.4f}")
print(f"  tie-corrected accuracy = {wins + 0.5 * ties:.4f}")

# Localise the inversion: if TRAIN accuracy is also below chance, the loss is
# not doing what the eval measures, and the fault is in the objective - not in
# generalisation.
Xt_ = torch.tensor(d["X_train"], dtype=torch.float32)
with torch.no_grad():
    st_ = model(Xt_, None)["score"].numpy()
tr_pairs = build_pairs(d["y_train"], d["t_train"], 0.05)
thi, tlo = st_[tr_pairs[:, 0]], st_[tr_pairs[:, 1]]
print(f"\nTRAIN pairs={len(tr_pairs):,}  strict wins={(thi > tlo).mean():.4f}")
print("  (if this is also << 0.5, the objective is inverted, not overfitting)")

# Does the raw target correlate with score in the expected direction?
print(f"\ncorr(score, target) on val = {np.corrcoef(s, yv)[0,1]:+.4f}")
print("  (should be POSITIVE if higher score means better-performing copy)")

print("\nfeature sanity (post-standardisation):")
X = d["X_train"]
bad = []
for j in range(X.shape[1]):
    col = X[:, j]
    if not np.isfinite(col).all():
        bad.append((j, "non-finite"))
    elif col.std() < 1e-6:
        bad.append((j, "zero variance"))
    elif np.abs(col).max() > 50:
        bad.append((j, f"extreme max {np.abs(col).max():.0f}"))
print(f"  problem columns: {bad if bad else 'none'}")
print(f"  overall |X| max = {np.abs(X).max():.1f}")
