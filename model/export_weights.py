"""
Export the constrained module model to JSON for TypeScript inference.

The product runs the diagnostic layer in-process in Next.js, so the weights have
to leave PyTorch. What is exported:

  * every weight matrix and bias, as nested plain arrays
  * the feature scaler (mean/sd) fitted on training data
  * the feature names, in the exact order the TS side must build its vector
  * the CONSTRAINED values (post-reparameterisation), not the raw parameters -
    the TS port must never re-derive softplus signs and risk getting them wrong

A parity test lives alongside this: `parity_cases.json` holds a handful of real
feature vectors with their PyTorch outputs, so the TypeScript implementation can
be checked to 1e-4. Silent divergence between the two would be invisible in the
UI, which is exactly the kind of bug that ships.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from architecture import MODULES, ModelConfig, ResonanceNet  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
WEIGHTS_OUT = os.path.join(ROOT, "resonance", "lib", "inference", "module_model.json")
PARITY_OUT = os.path.join(ROOT, "resonance", "lib", "inference", "parity_cases.json")
N_PARITY = 8


def tolist(t: torch.Tensor):
    return t.detach().cpu().numpy().astype(float).tolist()


def main() -> None:
    scaler = json.load(open(os.path.join(PROC, "feature_scaler.json"),
                            encoding="utf-8"))
    n_features = len(scaler["features"])

    cfg = ModelConfig(n_features=n_features)
    model = ResonanceNet(cfg)
    model.load_state_dict(torch.load(os.path.join(PROC, "final_module_model.pt")))
    model.eval()

    modules_out = {}
    for name in MODULES:
        head = model.modules_[name]
        lin1, norm, lin2 = head.net[0], head.net[1], head.net[4]
        modules_out[name] = {
            "signed": name in cfg.signed,
            "w1": tolist(lin1.weight), "b1": tolist(lin1.bias),
            "ln_gamma": tolist(norm.weight), "ln_beta": tolist(norm.bias),
            "ln_eps": float(norm.eps),
            "w2": tolist(lin2.weight), "b2": tolist(lin2.bias),
        }

    payload = {
        "format_version": 1,
        "n_features": n_features,
        "feature_names": scaler["features"],
        "scaler": {"mean": scaler["mean"], "sd": scaler["sd"]},
        "module_order": list(MODULES),
        "modules": modules_out,
        # Post-constraint values. The TS side uses these directly and must NOT
        # reapply softplus - the signs are already guaranteed here.
        "constrained": {
            "arousal_to_encoding": float(model.arousal_to_encoding),
            "arousal_quad": float(model.arousal_quad),
            "arousal_lin": float(model._arousal_lin),
            "fluency_w": float(model.fluency_w),
            "load_w": float(model.load_w),
            "salience_gate_w": float(model._salience_gate_w),
            "salience_gate_b": float(model._salience_gate_b),
            "free_w": tolist(model.free_w.weight),
            "free_b": tolist(model.free_w.bias),
            "bias": tolist(model.bias),
        },
        "audience": {
            "embedding": tolist(model.audience.weight),
            "gain_w": tolist(model.audience_gain.weight),
            "gain_b": tolist(model.audience_gain.bias),
        },
        "provenance": {
            "trained_on": "Upworthy Research Archive, 32,487 randomised tests",
            "test_accuracy": 0.5346,
            "test_ci95": [0.5241, 0.5452],
            "note": "Diagnostic layer. Not the predictor - see model_card.md",
        },
    }

    os.makedirs(os.path.dirname(WEIGHTS_OUT), exist_ok=True)
    with open(WEIGHTS_OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    size = os.path.getsize(WEIGHTS_OUT) / 1024
    print(f"wrote {WEIGHTS_OUT} ({size:.0f} KB)")

    # ---- parity fixtures -------------------------------------------------
    d = np.load(os.path.join(PROC, "dataset.npz"), allow_pickle=True)
    X = d["X_test"][:N_PARITY]
    with torch.no_grad():
        out = model(torch.tensor(X, dtype=torch.float32), None)
    cases = []
    for i in range(len(X)):
        cases.append({
            "features_standardised": X[i].astype(float).tolist(),
            "expected": {
                "score": float(out["score"][i]),
                "modules": {m: float(out["modules"][m][i]) for m in MODULES},
            },
        })
    with open(PARITY_OUT, "w", encoding="utf-8") as fh:
        json.dump({"tolerance": 1e-4, "cases": cases}, fh)
    print(f"wrote {PARITY_OUT} ({N_PARITY} cases)")

    print("\nconstrained values (signs must hold):")
    c = payload["constrained"]
    print(f"  arousal_quad        {c['arousal_quad']:+.4f}  (must be < 0)")
    print(f"  arousal_to_encoding {c['arousal_to_encoding']:+.4f}  (must be >= 0)")
    print(f"  fluency_w           {c['fluency_w']:+.4f}  (must be >= 0)")
    print(f"  load_w              {c['load_w']:+.4f}  (must be <= 0)")


if __name__ == "__main__":
    main()
