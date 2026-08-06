"""
Export the embedding ranker to JSON for TypeScript inference.

This is the strong model: 0.5942 on held-out test, against 0.5346 for the
diagnostic module model and a measured 0.662 ceiling. It is what /compare must
use — putting the weaker model there would undercut the whole two-layer design.

Architecture is a plain MLP over frozen MiniLM embeddings:
    Linear(384 -> 128) -> ReLU -> Dropout -> Linear(128 -> 128) -> ReLU
        -> Linear(128 -> 1)

Dropout is identity at inference and is not exported.

Also emits parity fixtures: real embedding vectors with their PyTorch scores, so
the TypeScript port can be verified to 1e-4 the same way the module model was.
Only the RELATIVE order of scores matters for ranking, but an absolute check is
strictly stronger and catches sign or scale errors a rank check would miss.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(ROOT, "resonance", "lib", "inference", "ranker.json")
FIXTURES = os.path.join(ROOT, "resonance", "lib", "inference", "ranker_fixtures.json")
N_FIXTURES = 6
HIDDEN = 128


def build(dim: int) -> nn.Sequential:
    return nn.Sequential(
        nn.Linear(dim, HIDDEN), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(HIDDEN, HIDDEN), nn.ReLU(),
        nn.Linear(HIDDEN, 1),
    )


def tolist(t: torch.Tensor):
    return t.detach().cpu().numpy().astype(float).tolist()


def main() -> None:
    state = torch.load(os.path.join(PROC, "final_ranker.pt"))
    dim = state["0.weight"].shape[1]
    net = build(dim)
    net.load_state_dict(state)
    net.eval()

    payload = {
        "format_version": 1,
        "embedding_dim": dim,
        "embedding_model": "Xenova/all-MiniLM-L6-v2",
        "normalize_embeddings": True,
        "layers": [
            {"w": tolist(net[0].weight), "b": tolist(net[0].bias), "act": "relu"},
            {"w": tolist(net[3].weight), "b": tolist(net[3].bias), "act": "relu"},
            {"w": tolist(net[5].weight), "b": tolist(net[5].bias), "act": "none"},
        ],
        "provenance": {
            "test_accuracy": 0.5942,
            "test_ci95": [0.5839, 0.6044],
            "chance": 0.5,
            # Corrected from 0.788: the original split-half simulation treated
            # observed click rates as true rates, inflating the estimate. See
            # model/ceiling_robustness.py.
            "oracle_ceiling": 0.662,
            "trained_on": "Upworthy Research Archive, 32,487 randomised tests",
            "note": "Ranking only. Scores are comparable within one request and "
                    "carry no absolute meaning.",
        },
    }

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    print(f"wrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB, dim={dim})")

    emb = np.load(os.path.join(PROC, "embeddings.npz"))["E"][:N_FIXTURES]
    with torch.no_grad():
        scores = net(torch.tensor(emb, dtype=torch.float32)).squeeze(-1).numpy()

    with open(FIXTURES, "w", encoding="utf-8") as fh:
        json.dump({
            "tolerance": 1e-4,
            "cases": [{"embedding": emb[i].astype(float).tolist(),
                       "expected_score": float(scores[i])}
                      for i in range(len(emb))],
        }, fh)
    print(f"wrote {FIXTURES} ({N_FIXTURES} cases)")
    print(f"score range in fixtures: {scores.min():+.4f} .. {scores.max():+.4f}")


if __name__ == "__main__":
    main()
