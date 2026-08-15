"""
Contingency C12: do the segment priors actually change rankings?

A bounded prior that never flips a decision is a control that does nothing while
implying it does something, worse than omitting it. This measures the real
effect on real headlines using the trained module model.

Method: take dev-set headlines, compute the six module activations, apply each
segment's gain vector, recompute the score, and count how often the ORDER of a
pair changes. Ranking flips are what a user actually experiences.

Reference points:
  * noise floor from the shuffled-label control: ~0.02
  * a flip rate far below that means the panel is explanatory framing only
  * a flip rate far above 0.30 would mean the priors are doing more work than
    the underlying model, which the evidence does not justify either

Read this as a two-sided check: the priors should be visible but not dominant.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from architecture import MODULES, ModelConfig, ResonanceNet  # noqa: E402
from train_ranking import build_pairs  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
MIN_GAP = 0.05
MAX_GAIN_DELTA = 0.15

# Mirrors resonance/lib/segments.ts. Kept in sync deliberately: if these drift,
# the measured impact stops describing what the product does.
INVOLVEMENT = {
    "high": {"valuation": 1.12, "control": 1.10, "salience": 0.94, "affect": 0.94},
    "low": {"salience": 1.12, "affect": 1.10, "valuation": 0.94, "control": 0.96},
}
AGE = {
    "older": {"approach": 1.10, "valuation": 1.06, "affect": 0.95},
    "younger": {"affect": 1.06, "salience": 1.04},
}
GENDER = {"male": {"affect": 1.05}, "female": {"affect": 0.95}}
EDUCATION = {
    "higher": {"control": 1.04, "valuation": 1.03},
    "lower": {"salience": 1.04, "affect": 1.03},
}


def resolve(involvement=None, age=None, gender=None, education=None):
    gains = {m: 1.0 for m in MODULES}
    for table, key in ((INVOLVEMENT, involvement), (AGE, age),
                       (GENDER, gender), (EDUCATION, education)):
        if key and key in table:
            for mod, g in table[key].items():
                gains[mod] *= g
    lo, hi = 1 - MAX_GAIN_DELTA, 1 + MAX_GAIN_DELTA
    return {m: min(hi, max(lo, v)) for m, v in gains.items()}


def score_from_activations(model: ResonanceNet, acts: dict) -> np.ndarray:
    """Replicate the constrained score head on already-gained activations."""
    c = model
    salience, affect = acts["salience"], acts["affect"]
    valuation, encoding = acts["valuation"], acts["encoding"]
    control = acts["control"]

    gate = torch.sigmoid(c._salience_gate_w * salience + c._salience_gate_b)
    valuation = valuation * gate
    encoding = encoding * (1.0 + c.arousal_to_encoding * affect)

    arousal_term = c.arousal_quad * affect.pow(2) + c._arousal_lin * affect
    control_term = c.fluency_w * control + c.load_w * (1.0 - control)
    free = c.free_w(torch.stack([salience, valuation, encoding], dim=-1)).squeeze(-1)
    return (arousal_term + control_term + free + c.bias).detach().numpy()


def main() -> None:
    d = np.load(os.path.join(PROC, "dataset.npz"), allow_pickle=True)
    X = torch.tensor(d["X_val"], dtype=torch.float32)
    y, t = d["y_val"], d["t_val"]

    cfg = ModelConfig(n_features=X.shape[1])
    model = ResonanceNet(cfg)
    model.load_state_dict(torch.load(os.path.join(PROC, "final_module_model.pt")))
    model.eval()

    with torch.no_grad():
        out = model(X, None)
    base_acts = {m: out["modules_raw"][m].detach() for m in MODULES}
    base_score = score_from_activations(model, base_acts)

    pairs = build_pairs(y, t, MIN_GAP, d["X_val"])
    print(f"dev pairs: {len(pairs):,}\n")

    segments = [
        ("high involvement", dict(involvement="high")),
        ("low involvement", dict(involvement="low")),
        ("older", dict(age="older")),
        ("younger", dict(age="younger")),
        ("male", dict(gender="male")),
        ("female", dict(gender="female")),
        ("higher education", dict(education="higher")),
        ("lower education", dict(education="lower")),
        ("low invol + younger + male + lower ed",
         dict(involvement="low", age="younger", gender="male", education="lower")),
        ("high invol + older + female + higher ed",
         dict(involvement="high", age="older", gender="female", education="higher")),
    ]

    print(f"{'segment':<40}{'flip %':>9}{'mean |dscore|':>15}{'max gain':>10}")
    results = {}
    for label, kw in segments:
        gains = resolve(**kw)
        acts = {m: base_acts[m] * gains[m] for m in MODULES}
        seg_score = score_from_activations(model, acts)

        base_order = base_score[pairs[:, 0]] > base_score[pairs[:, 1]]
        seg_order = seg_score[pairs[:, 0]] > seg_score[pairs[:, 1]]
        flip = float((base_order != seg_order).mean())
        dscore = float(np.abs(seg_score - base_score).mean())
        max_gain = max(abs(g - 1) for g in gains.values())
        results[label] = {"flip_rate": flip, "mean_abs_dscore": dscore}
        print(f"{label:<40}{flip:>8.2%}{dscore:>15.4f}{max_gain:>10.3f}")

    flips = [v["flip_rate"] for v in results.values()]
    print(f"\nflip rate: min={min(flips):.2%} max={max(flips):.2%} "
          f"mean={np.mean(flips):.2%}")
    print("noise floor (shuffled-label control): ~2%")

    print("\nC12 VERDICT:")
    if max(flips) < 0.02:
        print("  Priors move rankings less than the noise floor. Present the")
        print("  segment panel as explanatory framing only, and say so.")
    elif max(flips) > 0.30:
        print("  Priors dominate the model. Reduce MAX_GAIN_DELTA - the")
        print("  literature does not support adjustments this large.")
    else:
        print("  Priors are visible but not dominant. Ship as segment-conditioned")
        print("  scoring, labelled as priors pending client recalibration.")

    with open(os.path.join(PROC, "segment_impact.json"), "w",
              encoding="utf-8") as fh:
        json.dump(results, fh, indent=1)


if __name__ == "__main__":
    main()
