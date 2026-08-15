"""
Per-tenant recalibration under TOPIC shift (second attempt).

The temporal version (simulated_tenant.py) returned no gain at any tenant size,
but its premise was weak: the filtered corpus spans 2014-06 to 2014-11, five
months of a single publisher. There is almost no drift there to adapt to, so
"recalibration doesn't help" was never going to be informative.

Topic is the better proxy for what actually happens with clients. A B2B software
advertiser differs from viral media in SUBJECT MATTER far more than in date, and
subject matter is exactly what the earlier disagreement analysis found the
embeddings keying on.

Method: k-means over headline embeddings, then hold out the most distinctive
cluster as the "tenant". The global model trains on everything else, so the
tenant's content genuinely differs from what the global model saw, which is the
situation Phase 4 exists to fix.

Leakage discipline is unchanged: splits are by group, and tenant-train and
tenant-test never share a near-duplicate cluster.
"""

from __future__ import annotations

import copy
import json
import os
import random
import sys
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (PointwiseRanker, build_pairs, evaluate,  # noqa: E402
                           load_rows, train, MIN_GAP)
from simulated_tenant import group_split, recalibrate  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
SEED = 20260805
N_CLUSTERS = 8
TENANT_TEST_FRAC = 0.35
TENANT_SIZES = [200, 500, 1000, 2000, 4000]


def kmeans(X, k, iters=25, seed=SEED):
    """Minimal k-means on unit-norm embeddings (cosine == euclidean here)."""
    rng = np.random.default_rng(seed)
    centres = X[rng.choice(len(X), size=k, replace=False)].copy()
    labels = np.zeros(len(X), dtype=int)
    for _ in range(iters):
        # assign: nearest centre by dot product, since vectors are normalised
        sims = X @ centres.T
        new = sims.argmax(axis=1)
        if np.array_equal(new, labels):
            break
        labels = new
        for c in range(k):
            members = X[labels == c]
            if len(members):
                v = members.mean(axis=0)
                centres[c] = v / (np.linalg.norm(v) + 1e-9)
    return labels, centres


def main() -> None:
    rows = load_rows()
    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]
    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)

    print(f"clustering {len(E):,} headlines into {N_CLUSTERS} topics...")
    labels, centres = kmeans(E, N_CLUSTERS)

    sizes = np.bincount(labels, minlength=N_CLUSTERS)
    # Most distinctive = furthest from the mean of all other centres.
    distinctiveness = []
    for c in range(N_CLUSTERS):
        others = np.delete(centres, c, axis=0).mean(axis=0)
        others /= np.linalg.norm(others) + 1e-9
        distinctiveness.append(1.0 - float(centres[c] @ others))

    print(f"\n{'cluster':>8}{'arms':>9}{'distinctiveness':>17}  sample headline")
    for c in range(N_CLUSTERS):
        idx = int(np.where(labels == c)[0][0])
        print(f"{c:>8}{sizes[c]:>9,}{distinctiveness[c]:>17.4f}  "
              f"{rows[idx]['headline'][:52]}")

    # Pick the most distinctive cluster that is still big enough to split.
    candidates = [c for c in range(N_CLUSTERS) if sizes[c] >= 6000]
    tenant_cluster = max(candidates, key=lambda c: distinctiveness[c])
    print(f"\ntenant = cluster {tenant_cluster} "
          f"({sizes[tenant_cluster]:,} arms, "
          f"distinctiveness {distinctiveness[tenant_cluster]:.4f})")

    tenant_all = np.where(labels == tenant_cluster)[0]
    global_idx = np.where(labels != tenant_cluster)[0]

    tenant_train_all, tenant_test = group_split(
        tenant_all, rows, TENANT_TEST_FRAC, SEED)

    p_global = build_pairs(y[global_idx], t[global_idx], MIN_GAP, ident[global_idx])
    p_ttest = build_pairs(y[tenant_test], t[tenant_test], MIN_GAP, ident[tenant_test])
    print(f"global train pairs: {len(p_global):,}")
    print(f"tenant test pairs : {len(p_ttest):,}\n")

    print("training global model on all other topics...")
    global_model = train(PointwiseRanker(E.shape[1]), E[global_idx], p_global,
                         epochs=25, lr=1e-3)
    _, (g_acc, g_ci, n_exp) = evaluate(global_model, E[tenant_test], p_ttest,
                                       t[tenant_test])
    print(f"GLOBAL on tenant topic: {g_acc:.4f} "
          f"95% CI [{g_ci[0]:.4f}, {g_ci[1]:.4f}]  ({n_exp:,} experiments)\n")

    print(f"{'tenant arms':>12} {'pairs':>8} {'recalibrated':>13} "
          f"{'vs global':>11} {'verdict':>10}")

    by_group = defaultdict(list)
    for i in tenant_train_all:
        by_group[rows[int(i)]["group"]].append(int(i))
    gids = sorted(by_group)

    results = []
    for size in TENANT_SIZES:
        if size > len(tenant_train_all):
            continue
        random.Random(SEED + size).shuffle(gids)
        taken: list[int] = []
        for g in gids:
            if len(taken) >= size:
                break
            taken.extend(by_group[g])
        sub = np.array(sorted(taken))

        p_sub = build_pairs(y[sub], t[sub], MIN_GAP, ident[sub])
        if len(p_sub) < 50:
            continue

        model = recalibrate(global_model, E[sub], p_sub)
        _, (acc, ci, _) = evaluate(model, E[tenant_test], p_ttest, t[tenant_test])
        delta = acc - g_acc
        verdict = "better" if delta > 0.01 else ("worse" if delta < -0.01 else "same")
        results.append({"arms": len(sub), "pairs": int(len(p_sub)),
                        "accuracy": acc, "delta": delta})
        print(f"{len(sub):>12,} {len(p_sub):>8,} {acc:>13.4f} "
              f"{delta:>+11.4f} {verdict:>10}")

    print(f"\nglobal baseline on tenant topic: {g_acc:.4f}")
    gains = [r for r in results if r["delta"] > 0.01]
    if gains:
        smallest = min(gains, key=lambda r: r["arms"])
        print(f"recalibration first helps at ~{smallest['arms']:,} arms "
              f"({smallest['delta']:+.4f})")
        print("=> Phase 4 is worth building.")
    else:
        print("=> No gain under topic shift either.")
        print("   Within one publisher even topic clusters share tone and")
        print("   format, so this may still understate real client drift -")
        print("   but two negative results is a reason to reprioritise.")

    with open(os.path.join(PROC, "simulated_tenant_topic.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"tenant_cluster": int(tenant_cluster),
                   "global_accuracy": g_acc, "sweep": results}, fh, indent=1)


if __name__ == "__main__":
    main()
