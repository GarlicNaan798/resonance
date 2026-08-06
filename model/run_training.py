"""
Train the model and run the negative controls. Test set is NOT opened here.

Order matters: baselines first, then the real fit, then the permutation control.
If the permutation control fails, the reported numbers are meaningless and the
run should be thrown away rather than published.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from architecture import MODULES, ModelConfig, ResonanceNet  # noqa: E402
from negative_controls import (baseline_floor, constraint_audit,  # noqa: E402
                               label_permutation_test)
from train import TrainConfig, train_model  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPZ = os.path.join(ROOT, "data", "processed", "dataset.npz")
OUT = os.path.join(ROOT, "data", "processed", "model_report.json")


def r2(pred: np.ndarray, true: np.ndarray, w: np.ndarray | None = None) -> float:
    if w is None:
        w = np.ones_like(true)
    mu = np.average(true, weights=w)
    ss_res = float((w * (true - pred) ** 2).sum())
    ss_tot = float((w * (true - mu) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def main() -> None:
    d = np.load(NPZ)
    t = lambda k: torch.tensor(d[k], dtype=torch.float32)  # noqa: E731
    X_tr, y_tr, w_tr = t("X_train"), t("y_train"), t("w_train")
    X_va, y_va, w_va = t("X_val"), t("y_val"), t("w_val")

    print(f"train {tuple(X_tr.shape)}  val {tuple(X_va.shape)}")
    cfg = ModelConfig(n_features=X_tr.shape[1])
    print(ResonanceNet(cfg).capacity_report(n_train_clusters=6264))
    print()

    tcfg = TrainConfig()

    def fit(Xa, ya, aa, Xb, yb, ab, wa=None, wb=None):
        return train_model(Xa, ya, aa, Xb, yb, ab,
                           w_train=wa, w_val=wb, model_cfg=cfg, cfg=tcfg)

    print("fitting real model...")
    model = fit(X_tr, y_tr, None, X_va, y_va, None, w_tr, w_va)
    with torch.no_grad():
        pred_va = model(X_va, None)["score"].numpy()
    real_r2 = r2(pred_va, y_va.numpy(), w_va.numpy())
    print(f"  weighted val R2 = {real_r2:.4f}")

    print("\nrunning negative controls...")
    # permutation control uses the identical fit function
    perm = label_permutation_test(
        lambda Xa, ya, aa, Xb, yb, ab: fit(Xa, ya, aa, Xb, yb, ab),
        X_tr, y_tr, None, X_va, y_va, None, n_repeats=3)
    base = baseline_floor(model, X_tr, y_tr, X_va, y_va, None)
    cons = constraint_audit(model)

    print()
    for r in (perm, base, cons):
        print(r)

    with torch.no_grad():
        acts = model(X_va, None)["modules"]
    print("\nmodule activations on val (mean +/- sd):")
    for name in MODULES:
        a = acts[name].numpy()
        print(f"  {name:<10} {a.mean():+.3f} +/- {a.std():.3f}")
    print(f"\nlearned arousal optimum: {float(model.arousal_optimum()):.3f}")

    report = {
        "val_r2_weighted": real_r2,
        "controls": {r.name: {"passed": r.passed, "detail": r.detail}
                     for r in (perm, base, cons)},
        "arousal_optimum": float(model.arousal_optimum()),
        "n_parameters": model.n_parameters(),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)

    ok = all(r.passed for r in (perm, base, cons))
    print(f"\nALL CONTROLS: {'PASS' if ok else 'FAIL'}")
    if ok:
        torch.save(model.state_dict(),
                   os.path.join(ROOT, "data", "processed", "model.pt"))
        print("saved model.pt")


if __name__ == "__main__":
    main()
