"""
Does per-tenant recalibration actually work? (validates Phase 4 before building it)

We cannot get client campaign data, so Phase 4 would otherwise be built blind:
a database, an auth layer and a fitting pipeline, with no way to know whether
refitting on a client's own data beats the global model.

This simulates a tenant using temporal drift inside Upworthy itself. The archive
spans 2013-2015 and the platform's style changed materially over that period, so
an early-period model applied to late-period data is a genuine (if mild)
domain-shift analogue.

Protocol:
  1. Sort by publication date. Early 60% trains the GLOBAL model.
  2. The late 40% is the "tenant". Its groups are split into tenant-train and
     tenant-test, so no near-duplicate cluster spans the two.
  3. Recalibrate: warm-start from the global weights and continue training on
     tenant-train at a low learning rate — standard transfer, and what the
     product would actually do.
  4. Compare global vs recalibrated on tenant-test.

It also sweeps the amount of tenant data, which tests the 200-campaign floor in
lib/upload.ts empirically rather than by assertion.

If recalibration does not beat global here, it will not beat it on real clients
either, and Phase 4 should not be built as designed.
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

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
EARLY_FRAC = 0.60
TENANT_TEST_FRAC = 0.35
SEED = 20260805
# Arm counts to sweep. Upworthy arms are roughly one "campaign" each.
TENANT_SIZES = [200, 500, 1000, 2000, 4000, 8000]


def temporal_split(rows):
    """Order by publication date; early trains global, late is the tenant."""
    order = sorted(range(len(rows)), key=lambda i: rows[i].get("created_at") or "")
    cut = int(len(order) * EARLY_FRAC)
    return np.array(sorted(order[:cut])), np.array(sorted(order[cut:]))


def group_split(idxs, rows, frac, seed):
    """Split by GROUP so no near-duplicate cluster spans the two sides."""
    by_group = defaultdict(list)
    for i in idxs:
        by_group[rows[int(i)]["group"]].append(int(i))
    gids = sorted(by_group)
    random.Random(seed).shuffle(gids)
    k = int(round(len(gids) * frac))
    a = np.array(sorted(i for g in gids[k:] for i in by_group[g]))
    b = np.array(sorted(i for g in gids[:k] for i in by_group[g]))
    return a, b


def recalibrate(global_model, E, pairs, epochs=15, lr=2e-4, seed=0):
    """Warm-start from global weights, continue at a low learning rate.

    Low LR and few epochs on purpose: with limited tenant data, aggressive
    fitting would overwrite everything the global model learned and end up worse
    than either. This is the transfer setup the product would use.
    """
    torch.manual_seed(seed)
    model = PointwiseRanker(E.shape[1])
    model.load_state_dict(copy.deepcopy(global_model.state_dict()))
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=1e-4)
    Et = torch.tensor(E, dtype=torch.float32)
    for _ in range(epochs):
        model.train()
        perm = np.random.permutation(len(pairs))
        for s in range(0, len(pairs), 1024):
            sel = pairs[perm[s:s + 1024]]
            opt.zero_grad(set_to_none=True)
            hi = model.net(Et[torch.from_numpy(sel[:, 0])]).squeeze(-1)
            lo = model.net(Et[torch.from_numpy(sel[:, 1])]).squeeze(-1)
            nn.functional.softplus(-(hi - lo)).mean().backward()
            opt.step()
    model.eval()
    return model


def main() -> None:
    rows = load_rows()
    early, late = temporal_split(rows)
    print(f"early (global training): {len(early):,} arms")
    print(f"late  (simulated tenant): {len(late):,} arms")
    print(f"date range: {rows[int(early[0])].get('created_at','?')[:10]} .. "
          f"{rows[int(late[-1])].get('created_at','?')[:10]}\n")

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)
    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]

    tenant_train_all, tenant_test = group_split(late, rows, TENANT_TEST_FRAC, SEED)
    p_global = build_pairs(y[early], t[early], MIN_GAP, ident[early])
    p_ttest = build_pairs(y[tenant_test], t[tenant_test], MIN_GAP, ident[tenant_test])
    print(f"global train pairs : {len(p_global):,}")
    print(f"tenant train pool  : {len(tenant_train_all):,} arms")
    print(f"tenant test pairs  : {len(p_ttest):,}\n")

    print("training global model on early period...")
    global_model = train(PointwiseRanker(E.shape[1]), E[early], p_global,
                         epochs=25, lr=1e-3)
    _, (g_acc, g_ci, n_exp) = evaluate(global_model, E[tenant_test], p_ttest,
                                       t[tenant_test])
    print(f"GLOBAL on tenant test: {g_acc:.4f}  95% CI [{g_ci[0]:.4f}, {g_ci[1]:.4f}]")
    print(f"  over {n_exp:,} tenant experiments\n")

    print(f"{'tenant arms':>12} {'pairs':>8} {'recalibrated':>13} "
          f"{'vs global':>11} {'verdict':>10}")

    results = []
    for size in TENANT_SIZES:
        if size > len(tenant_train_all):
            continue
        # Take whole groups until the arm budget is met.
        by_group = defaultdict(list)
        for i in tenant_train_all:
            by_group[rows[int(i)]["group"]].append(int(i))
        gids = sorted(by_group)
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
                        "accuracy": acc, "delta": delta, "ci95": list(ci)})
        print(f"{len(sub):>12,} {len(p_sub):>8,} {acc:>13.4f} "
              f"{delta:>+11.4f} {verdict:>10}")

    print(f"\nglobal baseline: {g_acc:.4f}")
    gains = [r for r in results if r["delta"] > 0.01]
    if gains:
        smallest = min(gains, key=lambda r: r["arms"])
        print(f"recalibration first helps at ~{smallest['arms']:,} arms "
              f"({smallest['delta']:+.4f})")
        print("=> Phase 4 is worth building; the mechanism works under drift.")
    else:
        print("=> Recalibration did NOT beat global at any size tested.")
        print("   Either the simulated drift is too mild to matter, or the")
        print("   mechanism needs rethinking before Phase 4 is built.")

    with open(os.path.join(PROC, "simulated_tenant.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"global_accuracy": g_acc, "global_ci95": list(g_ci),
                   "tenant_experiments": n_exp, "sweep": results}, fh, indent=1)


if __name__ == "__main__":
    main()
