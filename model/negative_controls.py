"""
Negative controls - the tests that catch a model fooling itself.

Reporting a good validation score proves nothing on its own. These four checks
are what make a number believable, and every one of them is designed to FAIL
loudly when something is wrong.

  1. LABEL PERMUTATION
     Shuffle the labels (within split, so distributions are untouched) and
     retrain. A sound pipeline scores at chance. If the shuffled model still
     predicts well, the features encode the label some other way - leakage,
     duplicate contamination, or a bug. This is the single most valuable test
     in the file.

  2. BASELINE FLOOR
     The model must beat: predicting the training mean, and a linear model on
     the same features. A deep model that cannot beat linear regression is not
     earning its complexity, and should be replaced by the linear model.

  3. LEARNING CURVE
     Train on 10..100% of the data. If validation error is still falling at
     100%, more data helps. If train and validation have diverged badly, the
     model is memorising and capacity should come down.

  4. CONSTRAINT AUDIT
     Assert after training that the research constraints (C1-C5) actually hold.
     Reparameterisation should make this impossible to violate - so this is a
     regression test against someone later "simplifying" the constraint code.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn

from architecture import ResonanceNet, MODULES


@dataclass
class ControlResult:
    name: str
    passed: bool
    detail: str

    def __str__(self) -> str:
        return f"[{'PASS' if self.passed else 'FAIL'}] {self.name}: {self.detail}"


# ------------------------------------------------------------------ helpers

def _r2(pred: np.ndarray, true: np.ndarray) -> float:
    ss_res = float(((true - pred) ** 2).sum())
    ss_tot = float(((true - true.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot if ss_tot > 0 else 0.0


def _evaluate(model: nn.Module, X: torch.Tensor, y: torch.Tensor,
              aud: torch.Tensor | None) -> float:
    model.eval()
    with torch.no_grad():
        pred = model(X, aud)["score"].cpu().numpy()
    return _r2(pred, y.cpu().numpy())


# ------------------------------------------------------------------ 1. permutation

def label_permutation_test(train_fn, X_tr, y_tr, a_tr, X_va, y_va, a_va,
                           n_repeats: int = 5, seed: int = 0,
                           tolerance: float = 0.05) -> ControlResult:
    """Retrain on shuffled labels. Real R^2 must clear the shuffled ceiling."""
    rng = np.random.default_rng(seed)

    real_model = train_fn(X_tr, y_tr, a_tr, X_va, y_va, a_va)
    real_r2 = _evaluate(real_model, X_va, y_va, a_va)

    shuffled: list[float] = []
    for _ in range(n_repeats):
        perm = rng.permutation(len(y_tr))
        y_shuf = y_tr[torch.as_tensor(perm)]
        m = train_fn(X_tr, y_shuf, a_tr, X_va, y_va, a_va)
        shuffled.append(_evaluate(m, X_va, y_va, a_va))

    ceiling = float(np.max(shuffled))
    mean_shuf = float(np.mean(shuffled))
    passed = real_r2 > ceiling + tolerance and mean_shuf < tolerance

    return ControlResult(
        "label_permutation", passed,
        f"real R2={real_r2:.3f}  shuffled mean={mean_shuf:.3f} "
        f"max={ceiling:.3f}  "
        + ("real clears shuffled ceiling"
           if passed else
           "SHUFFLED LABELS PREDICT TOO WELL - suspect leakage or a bug"))


# ------------------------------------------------------------------ 2. baselines

def baseline_floor(model: nn.Module, X_tr, y_tr, X_va, y_va,
                   a_va=None) -> ControlResult:
    """Model must beat the training mean and ridge regression."""
    y_tr_np = y_tr.cpu().numpy()
    y_va_np = y_va.cpu().numpy()

    mean_r2 = _r2(np.full_like(y_va_np, y_tr_np.mean()), y_va_np)

    # closed-form ridge on the same features
    Xtr = X_tr.cpu().numpy()
    Xva = X_va.cpu().numpy()
    Xtr1 = np.hstack([Xtr, np.ones((len(Xtr), 1))])
    Xva1 = np.hstack([Xva, np.ones((len(Xva), 1))])
    lam = 1.0
    A = Xtr1.T @ Xtr1 + lam * np.eye(Xtr1.shape[1])
    w = np.linalg.solve(A, Xtr1.T @ y_tr_np)
    ridge_r2 = _r2(Xva1 @ w, y_va_np)

    model_r2 = _evaluate(model, X_va, y_va, a_va)
    passed = model_r2 > ridge_r2 and model_r2 > mean_r2

    return ControlResult(
        "baseline_floor", passed,
        f"model={model_r2:.3f}  ridge={ridge_r2:.3f}  mean={mean_r2:.3f}  "
        + ("model earns its complexity"
           if passed else
           "model does NOT beat a linear baseline - prefer the simpler model"))


# ------------------------------------------------------------------ 3. learning curve

def learning_curve(train_fn, X_tr, y_tr, a_tr, X_va, y_va, a_va,
                   fractions=(0.1, 0.25, 0.5, 0.75, 1.0),
                   gap_limit: float = 0.25, seed: int = 0) -> ControlResult:
    """Train/val gap at full data reveals memorisation."""
    rng = np.random.default_rng(seed)
    n = len(y_tr)
    rows = []
    train_r2 = val_r2 = 0.0

    for frac in fractions:
        k = max(int(n * frac), 32)
        idx = torch.as_tensor(rng.choice(n, size=k, replace=False))
        a_sub = a_tr[idx] if a_tr is not None else None
        m = train_fn(X_tr[idx], y_tr[idx], a_sub, X_va, y_va, a_va)
        train_r2 = _evaluate(m, X_tr[idx], y_tr[idx], a_sub)
        val_r2 = _evaluate(m, X_va, y_va, a_va)
        rows.append(f"{frac:.0%}:tr={train_r2:.2f}/va={val_r2:.2f}")

    gap = train_r2 - val_r2
    passed = gap < gap_limit
    return ControlResult(
        "learning_curve", passed,
        "  ".join(rows) + f"  | final gap={gap:.3f} "
        + ("(healthy)" if passed else "(MEMORISING - reduce capacity)"))


# ------------------------------------------------------------------ 4. constraints

def constraint_audit(model: ResonanceNet) -> ControlResult:
    """Verify C1-C5 hold on the trained model."""
    problems: list[str] = []

    if float(model.arousal_quad) >= 0:
        problems.append("C1 arousal quadratic is not negative (inverted-U broken)")
    if float(model.arousal_to_encoding) < 0:
        problems.append("C2 arousal->encoding gate is negative")
    if float(model.fluency_w) < 0:
        problems.append("C4 fluency weight is negative")
    if float(model.load_w) > 0:
        problems.append("C5 cognitive-load weight is positive")

    opt = float(model.arousal_optimum())
    if not 0.0 <= opt <= 1.0:
        problems.append(f"C1 arousal optimum {opt:.2f} outside [0,1]")

    detail = (f"arousal optimum={opt:.2f}, "
              f"quad={float(model.arousal_quad):.3f}, "
              f"arousal->encoding={float(model.arousal_to_encoding):.3f}, "
              f"fluency={float(model.fluency_w):.3f}, "
              f"load={float(model.load_w):.3f}")
    return ControlResult("constraint_audit", not problems,
                         detail if not problems else "; ".join(problems))


# ------------------------------------------------------------------ runner

def run_all(train_fn, model, data) -> list[ControlResult]:
    """data: dict with X_train/y_train/a_train and X_val/y_val/a_val tensors."""
    X_tr, y_tr, a_tr = data["X_train"], data["y_train"], data.get("a_train")
    X_va, y_va, a_va = data["X_val"], data["y_val"], data.get("a_val")

    results = [
        label_permutation_test(train_fn, X_tr, y_tr, a_tr, X_va, y_va, a_va),
        baseline_floor(model, X_tr, y_tr, X_va, y_va, a_va),
        learning_curve(train_fn, X_tr, y_tr, a_tr, X_va, y_va, a_va),
        constraint_audit(model),
    ]
    print("\n=== NEGATIVE CONTROLS ===")
    for r in results:
        print(r)
    if not all(r.passed for r in results):
        print("\nOne or more controls FAILED. Do not report metrics from this "
              "run, and do not open the test set.")
    return results
