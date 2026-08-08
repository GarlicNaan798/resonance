"""
Export the listwise ensemble for TypeScript inference.

Test result: 0.6176 [0.6075, 0.6277] vs 0.5942 incumbent. Shipped under the
pre-registered rule in test_read_listwise.py.

Five listwise models, averaged. The eval z-scored each model's outputs across
the whole dev set before averaging, so each member contributed on a comparable
scale. At inference we only have 2-8 variants, and z-scoring within a request
that small would flatten every model to +/-0.707 and turn the ensemble into a
majority vote.

So each model's mean and sd are computed here over the fit set and exported as
constants. Inference normalises with those, preserving the eval semantics.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import load_rows  # noqa: E402
from listwise import build_lists, train_listwise  # noqa: E402
from train_final import split_indices  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
OUT = os.path.join(ROOT, "resonance", "lib", "inference", "ranker.json")
N_SEEDS = 5


def tolist(t):
    return t.detach().cpu().numpy().astype(float).tolist()


def main() -> None:
    rows = load_rows()
    idx = split_indices(rows)
    fit_idx = np.concatenate([idx["train"], idx["val"]])

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)
    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]
    dim = E.shape[1]

    lists = build_lists(fit_idx, rows, y, ident)
    pos = {int(g): k for k, g in enumerate(fit_idx)}
    lists_local = [np.array([pos[int(i)] for i in l]) for l in lists]

    members = []
    for s in range(N_SEEDS):
        print(f"training member {s}...")
        m = train_listwise(E[fit_idx], lists_local, y[fit_idx], dim, seed=s)
        with torch.no_grad():
            out = m(torch.tensor(E[fit_idx], dtype=torch.float32)).numpy()
        net = m.net
        members.append({
            "mean": float(out.mean()),
            "sd": float(out.std()),
            "layers": [
                {"w": tolist(net[0].weight), "b": tolist(net[0].bias), "act": "relu"},
                {"w": tolist(net[3].weight), "b": tolist(net[3].bias), "act": "relu"},
                {"w": tolist(net[5].weight), "b": tolist(net[5].bias), "act": "none"},
            ],
        })

    payload = {
        "format_version": 2,
        "embedding_dim": dim,
        "embedding_model": "Xenova/all-MiniLM-L6-v2",
        "normalize_embeddings": True,
        "members": members,
        "provenance": {
            "test_accuracy": 0.6176,
            "test_ci95": [0.6075, 0.6277],
            "chance": 0.5,
            "oracle_ceiling": 0.662,
            "trained_on": "Upworthy Research Archive, 32,487 randomised tests",
            "note": "Ranking only. Scores are comparable within one request and "
                    "carry no absolute meaning.",
            "ceiling_note": "0.662 from model/ceiling_robustness.py. Corrected "
                            "from 0.788, which treated observed click rates as "
                            "true rates.",
        },
    }

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    print(f"\nwrote {OUT} ({os.path.getsize(OUT)/1024:.0f} KB, "
          f"{N_SEEDS} members)")

    # Parity fixtures against the ensemble, not a single member.
    test_E = E[idx["test"]][:6]
    scores = []
    for mem in members:
        h = test_E
        for layer in mem["layers"]:
            w = np.array(layer["w"])
            h = h @ w.T + np.array(layer["b"])
            if layer["act"] == "relu":
                h = np.maximum(h, 0)
        scores.append((h[:, 0] - mem["mean"]) / mem["sd"])
    ens = np.mean(scores, axis=0)

    with open(os.path.join(ROOT, "resonance", "lib", "inference",
                           "ranker_fixtures.json"), "w", encoding="utf-8") as fh:
        json.dump({"tolerance": 1e-4,
                   "cases": [{"embedding": test_E[i].astype(float).tolist(),
                              "expected_score": float(ens[i])}
                             for i in range(len(test_E))]}, fh)
    print(f"score range: {ens.min():+.4f} .. {ens.max():+.4f}")


if __name__ == "__main__":
    main()
