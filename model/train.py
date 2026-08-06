"""
Training loop with overfitting defences.

Layered defences, strongest first:

  1. ARCHITECTURE   research-fixed constraints + a six-scalar bottleneck.
                    Most of the work happens here (see architecture.py).
  2. EARLY STOPPING on validation loss, restoring the best checkpoint - not the
                    last. Patience is short because the dataset is small.
  3. WEIGHT DECAY   applied to weights only, never to biases, LayerNorm, or the
                    constrained research parameters (decaying those would drag
                    documented effects toward zero, which is exactly wrong).
  4. GRAD CLIPPING  keeps a small dataset from producing violent updates.
  5. DETERMINISM    fixed seeds so a result can be reproduced and disputed.

The test set is never touched here. Model selection uses validation only.
"""

from __future__ import annotations

import copy
import random
from dataclasses import dataclass

import numpy as np
import torch
import torch.nn as nn

from architecture import ModelConfig, ResonanceNet


@dataclass
class TrainConfig:
    lr: float = 3e-3
    weight_decay: float = 1e-2
    max_epochs: int = 300
    patience: int = 25          # epochs without val improvement before stopping
    batch_size: int = 256
    grad_clip: float = 1.0
    seed: int = 20260805
    min_delta: float = 1e-4     # improvement smaller than this does not count


def set_seed(seed: int) -> None:
    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.use_deterministic_algorithms(True, warn_only=True)


def param_groups(model: nn.Module, weight_decay: float) -> list[dict]:
    """Decay weight matrices only.

    Biases, norm parameters and the constrained research parameters are exempt:
    weight decay pulls parameters toward zero, and zeroing a documented effect
    (say, arousal's contribution to encoding) would silently delete the science
    the architecture exists to encode.
    """
    decay, no_decay = [], []
    for name, p in model.named_parameters():
        if not p.requires_grad:
            continue
        if p.ndim == 1 or name.startswith("_") or "audience_gain" in name \
                or "bias" in name or "LayerNorm" in name or "norm" in name:
            no_decay.append(p)
        else:
            decay.append(p)
    return [
        {"params": decay, "weight_decay": weight_decay},
        {"params": no_decay, "weight_decay": 0.0},
    ]


def _weighted(loss_el: torch.Tensor, w: torch.Tensor | None) -> torch.Tensor:
    """Mean loss, optionally weighted by measurement precision.

    CTR measured on 2,000 impressions is far noisier than the same CTR measured
    on 30,000. Inverse-variance weights stop the fit chasing noise in the
    low-impression arms.
    """
    if w is None:
        return loss_el.mean()
    return (loss_el * w).sum() / w.sum().clamp_min(1e-8)


def train_model(X_train: torch.Tensor, y_train: torch.Tensor,
                a_train: torch.Tensor | None,
                X_val: torch.Tensor, y_val: torch.Tensor,
                a_val: torch.Tensor | None,
                w_train: torch.Tensor | None = None,
                w_val: torch.Tensor | None = None,
                model_cfg: ModelConfig | None = None,
                cfg: TrainConfig | None = None,
                verbose: bool = False) -> ResonanceNet:
    """Fit and return the best-validation checkpoint.

    Signature matches what negative_controls.run_all expects, so the very same
    function is used for the real fit and for the permutation controls. That
    matters: a control that trains differently from the real model proves
    nothing about the real model.
    """
    cfg = cfg or TrainConfig()
    model_cfg = model_cfg or ModelConfig(n_features=X_train.shape[1])
    set_seed(cfg.seed)

    model = ResonanceNet(model_cfg)
    opt = torch.optim.AdamW(param_groups(model, cfg.weight_decay), lr=cfg.lr)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(
        opt, mode="min", factor=0.5, patience=max(cfg.patience // 3, 3))
    # reduction='none' so per-arm precision weights can be applied
    loss_fn = nn.HuberLoss(delta=1.0, reduction="none")   # robust to outliers

    n = len(y_train)
    best_val = float("inf")
    best_state = copy.deepcopy(model.state_dict())
    best_epoch = 0
    stale = 0

    for epoch in range(cfg.max_epochs):
        model.train()
        perm = torch.randperm(n)
        for start in range(0, n, cfg.batch_size):
            idx = perm[start:start + cfg.batch_size]
            aud = a_train[idx] if a_train is not None else None
            wb = w_train[idx] if w_train is not None else None
            opt.zero_grad(set_to_none=True)
            out = model(X_train[idx], aud)
            loss = _weighted(loss_fn(out["score"], y_train[idx]), wb)
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), cfg.grad_clip)
            opt.step()

        model.eval()
        with torch.no_grad():
            val_loss = float(_weighted(
                loss_fn(model(X_val, a_val)["score"], y_val), w_val))
        sched.step(val_loss)

        if val_loss < best_val - cfg.min_delta:
            best_val, best_epoch, stale = val_loss, epoch, 0
            best_state = copy.deepcopy(model.state_dict())
        else:
            stale += 1
            if stale >= cfg.patience:
                if verbose:
                    print(f"early stop @ {epoch} (best {best_epoch}, "
                          f"val {best_val:.4f})")
                break

    model.load_state_dict(best_state)
    if verbose:
        print(f"restored epoch {best_epoch}, val loss {best_val:.4f}")
    return model
