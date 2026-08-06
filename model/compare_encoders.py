"""
Phase 1.5, step 2: does a stronger encoder buy accuracy?

Step 1 ruled out the bi-encoder structure (C9). This tests the encoder itself.

  all-MiniLM-L6-v2   6 layers,  384 dim, ~23M params   (incumbent)
  all-mpnet-base-v2 12 layers,  768 dim, ~110M params

Identical head, identical pairs, identical dev-test split, identical seeds - the
only variable is the representation.

Also evaluates a concatenation of both, since the two encoders may capture
partly complementary information.

Decision rule, pre-registered: keep the larger encoder only if it beats MiniLM
by more than 0.02 on dev-test. It is ~5x the inference cost, so a marginal gain
does not justify it in production.

The sealed test set is not touched here.
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (PointwiseRanker, base_split, build_pairs,  # noqa: E402
                           carve_dev, evaluate, load_rows, train, MIN_GAP)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
KEEP_THRESHOLD = 0.02


def main() -> None:
    rows = load_rows()
    parts, members = base_split(rows)
    inner, dev = carve_dev(parts["train"], members)

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])

    # identical-copy detector: same normalised headline -> same id
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)

    p_in = build_pairs(y[inner], t[inner], MIN_GAP, ident[inner])
    p_dev = build_pairs(y[dev], t[dev], MIN_GAP, ident[dev])
    print(f"inner pairs={len(p_in):,}  dev pairs={len(p_dev):,}\n")

    mini = np.load(os.path.join(PROC, "embeddings.npz"))["E"]
    mpnet_path = os.path.join(PROC, "embeddings_mpnet.npz")
    if not os.path.exists(mpnet_path):
        raise SystemExit("embeddings_mpnet.npz missing - run embed_large.py")
    mpnet = np.load(mpnet_path)["E"]
    print(f"MiniLM {mini.shape}   mpnet {mpnet.shape}\n")

    arms = {
        "MiniLM-L6 (384d)": mini,
        "mpnet-base (768d)": mpnet,
        "both concatenated": np.hstack([mini, mpnet]),
    }

    print("=== dev-test pairwise accuracy ===")
    results = {}
    for name, E in arms.items():
        model = train(PointwiseRanker(E.shape[1]), E[inner], p_in,
                      epochs=25, lr=1e-3)
        _, (acc, ci, nexp) = evaluate(model, E[dev], p_dev, t[dev])
        results[name] = acc
        print(f"  {name:<20} {acc:.4f}  95% CI [{ci[0]:.4f}, {ci[1]:.4f}]")

    a_mini = results["MiniLM-L6 (384d)"]
    a_mp = results["mpnet-base (768d)"]
    gain = a_mp - a_mini
    print(f"\n  over {nexp:,} dev experiments")
    print(f"  mpnet gain over MiniLM: {gain:+.4f}")
    print(f"  ceiling 0.7880 | signal captured: MiniLM {(a_mini-0.5)/0.288:.1%}"
          f"  mpnet {(a_mp-0.5)/0.288:.1%}")

    verdict = ("KEEP mpnet - gain justifies ~5x inference cost"
               if gain > KEEP_THRESHOLD else
               "KEEP MiniLM - mpnet gain does not justify its cost")
    print(f"\n  VERDICT: {verdict}")

    with open(os.path.join(PROC, "phase15_step2.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"results": results, "gain": gain,
                   "threshold": KEEP_THRESHOLD}, fh, indent=1)


if __name__ == "__main__":
    main()
