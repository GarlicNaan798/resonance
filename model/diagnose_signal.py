"""
How much signal is actually in these features?

The constrained model underfits and loses to ridge. Two very different causes:

  (a) the task is intrinsically near-noise - within-test CTR contrasts on
      ~3,000 impressions are dominated by sampling error, or
  (b) our architecture is broken / too small.

Tuning before distinguishing these is how people waste weeks. This script
establishes the CEILING with deliberately unconstrained models. If a large
free-form MLP also lands near zero, the honest conclusion is (a) and the
product claim has to change. If it lands well above, the fault is ours.

Also reports the noise floor: with n impressions and CTR p, the standard error
of the log-odds is sqrt(1/c + 1/(n-c)). Comparing that to the spread of the
target tells us what fraction of the variance is even explainable in principle.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPZ = os.path.join(ROOT, "data", "processed", "dataset.npz")


def r2(pred, true, w=None):
    if w is None:
        w = np.ones_like(true)
    mu = np.average(true, weights=w)
    ss_res = float((w * (true - pred) ** 2).sum())
    ss_tot = float((w * (true - mu) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def ridge(Xtr, ytr, Xva, lam):
    A = Xtr.T @ Xtr + lam * np.eye(Xtr.shape[1])
    w = np.linalg.solve(A, Xtr.T @ ytr)
    return Xva @ w


def mlp(Xtr, ytr, Xva, yva, hidden, epochs=60, lr=2e-3, wd=1e-4, seed=0):
    """Deliberately unconstrained - this is a ceiling probe, not a product model."""
    torch.manual_seed(seed)
    net = nn.Sequential(
        nn.Linear(Xtr.shape[1], hidden), nn.ReLU(),
        nn.Linear(hidden, hidden), nn.ReLU(),
        nn.Linear(hidden, 1),
    )
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=wd)
    Xt = torch.tensor(Xtr); yt = torch.tensor(ytr)
    Xv = torch.tensor(Xva)
    n = len(yt)
    best, best_pred = -9e9, None
    for ep in range(epochs):
        net.train()
        perm = torch.randperm(n)
        for s in range(0, n, 1024):
            idx = perm[s:s + 1024]
            opt.zero_grad(set_to_none=True)
            loss = nn.functional.mse_loss(net(Xt[idx]).squeeze(-1), yt[idx])
            loss.backward()
            opt.step()
        net.eval()
        with torch.no_grad():
            p = net(Xv).squeeze(-1).numpy()
        s = r2(p, yva)
        if s > best:
            best, best_pred = s, p
    return best


def main() -> None:
    d = np.load(NPZ)
    Xtr, ytr, wtr = d["X_train"], d["y_train"], d["w_train"]
    Xva, yva, wva = d["X_val"], d["y_val"], d["w_val"]
    print(f"train {Xtr.shape}  val {Xva.shape}")

    # ---- noise floor -------------------------------------------------
    # w = 1/var(log-odds), normalised to mean 1 on train. Recover raw variance.
    raw_var = 1.0 / (wtr * (1.0 / (1.0 / wtr).mean()))
    mean_noise_var = float(np.mean(1.0 / wtr)) * float(np.mean(wtr))
    target_var = float(ytr.var())
    print(f"\ntarget variance      : {target_var:.4f}")
    print(f"relative noise scale : {mean_noise_var:.4f}")
    print("(if measurement noise is comparable to target variance, most of the "
          "spread is sampling error and R2 is capped very low)")

    # ---- correlations -------------------------------------------------
    cors = []
    for j in range(Xtr.shape[1]):
        c = np.corrcoef(Xtr[:, j], ytr)[0, 1]
        cors.append((abs(c), c, j))
    cors.sort(reverse=True)
    print("\ntop 8 |correlation| with target:")
    names = None
    import json
    sc = os.path.join(ROOT, "data", "processed", "feature_scaler.json")
    if os.path.exists(sc):
        names = json.load(open(sc, encoding="utf-8"))["features"]
    for a, c, j in cors[:8]:
        nm = names[j] if names else f"f{j}"
        print(f"  {nm:<24} r={c:+.4f}")
    print(f"max |r| = {cors[0][0]:.4f}  "
          f"=> a single feature explains at most {cors[0][0]**2:.2%} of variance")

    # ---- baselines ----------------------------------------------------
    print("\nunweighted val R2 by model:")
    for lam in (1.0, 10.0, 100.0, 1000.0):
        p = ridge(Xtr, ytr, Xva, lam)
        print(f"  ridge(lam={lam:<6.0f})     {r2(p, yva):+.4f}")

    for h in (32, 128, 512):
        s = mlp(Xtr, ytr, Xva, yva, hidden=h)
        print(f"  MLP(hidden={h:<4d})     {s:+.4f}   <- unconstrained ceiling probe")

    print("\nIf every number above is ~0.01 or below, the features carry very "
          "little information about within-test CTR and no architecture will "
          "fix that.")


if __name__ == "__main__":
    main()
