"""
THIRD AND FINAL TEST-SET READ. Pre-registered before running.

Candidate: listwise objective + 5-seed ensemble.
Incumbent: single pairwise model, 0.5942 test.

Dev said +0.0209, the only result in nine experiments to clear the 0.02 noise
floor. Dev has been evaluated well over a dozen times, so some of that is
selection bias - this read is what separates the real part from the inflated
part.

DECISION, fixed before seeing the number:
  ship the candidate iff its test accuracy exceeds 0.5942 by more than 0.01.
  Below that, the extra complexity of an ensemble is not worth carrying.
  No tuning happens after this runs, whatever it says.

Fit on train+val (selection is over, so holding val out wastes 15% of the data),
evaluated on the sealed test split with CIs clustered by experiment.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import build_pairs, load_rows, MIN_GAP  # noqa: E402
from listwise import build_lists, train_listwise, train_pairwise  # noqa: E402
from tune_and_ensemble import acc_ci, scores_of  # noqa: E402
from train_final import split_indices  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
INCUMBENT = 0.5942
MARGIN = 0.01
N_SEEDS = 5


def main() -> None:
    rows = load_rows()
    idx = split_indices(rows)
    fit_idx = np.concatenate([idx["train"], idx["val"]])

    sys.path.insert(0, os.path.join(ROOT, "pipeline"))
    from test_lock import unlock_test  # noqa: E402
    test_idx = unlock_test(
        rows,
        "test_read_listwise.py: pre-registered read of the listwise ensemble "
        f"against incumbent {INCUMBENT} with a {MARGIN} ship margin",
    )

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)
    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]
    dim = E.shape[1]

    p_fit = build_pairs(y[fit_idx], t[fit_idx], MIN_GAP, ident[fit_idx])
    p_test_local = build_pairs(y[test_idx], t[test_idx], MIN_GAP, ident[test_idx])
    p_test = test_idx[p_test_local]

    lists = build_lists(fit_idx, rows, y, ident)
    pos = {int(g): k for k, g in enumerate(fit_idx)}
    lists_local = [np.array([pos[int(i)] for i in l]) for l in lists]

    print(f"fit: {len(fit_idx):,} arms, {len(p_fit):,} pairs, "
          f"{len(lists):,} lists")
    print(f"test: {len(test_idx):,} arms, {len(p_test):,} pairs\n")

    print("training candidate (listwise x 5 seeds)...")
    scores = []
    for s in range(N_SEEDS):
        m = train_listwise(E[fit_idx], lists_local, y[fit_idx], dim, seed=s)
        sc = scores_of(m, E)
        scores.append((sc - sc.mean()) / (sc.std() + 1e-9))
    ens = np.mean(scores, axis=0)

    print("training reference (single pairwise, same setup)...")
    ref = scores_of(train_pairwise(E[fit_idx], p_fit, dim, seed=0), E)

    print("\n" + "=" * 60)
    print("OPENING SEALED TEST SET - third and final read")
    print("=" * 60)

    a_cand, ci_cand = acc_ci(ens, p_test, t)
    a_ref, ci_ref = acc_ci(ref, p_test, t)
    n_exp = len({t[i] for i in p_test[:, 0]})

    print(f"\nover {n_exp:,} experiments / {len(p_test):,} pairs\n")
    print(f"  listwise ensemble : {a_cand:.4f}  "
          f"95% CI [{ci_cand[0]:.4f}, {ci_cand[1]:.4f}]")
    print(f"  pairwise single   : {a_ref:.4f}  "
          f"95% CI [{ci_ref[0]:.4f}, {ci_ref[1]:.4f}]")
    print(f"  incumbent (shipped): {INCUMBENT:.4f}")

    gain = a_cand - INCUMBENT
    print(f"\n  gain vs incumbent : {gain:+.4f}  (dev said +0.0209)")
    ship = gain > MARGIN
    print(f"\n  DECISION: {'SHIP the ensemble' if ship else 'KEEP the incumbent'}"
          f"  (rule: gain > {MARGIN})")
    if not ship and gain > 0:
        print("  Positive but under the bar. Dev overstated it, as expected.")

    with open(os.path.join(PROC, "test_read_listwise.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"candidate": a_cand, "candidate_ci": list(ci_cand),
                   "reference_pairwise": a_ref, "incumbent": INCUMBENT,
                   "gain": gain, "ship": bool(ship),
                   "dev_gain": 0.0209, "n_experiments": n_exp}, fh, indent=1)


if __name__ == "__main__":
    main()
