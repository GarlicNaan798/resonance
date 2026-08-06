"""
Phase 1: freeze both models, then open the sealed test set ONCE.

The feature set is now frozen (v1 norms for the diagnostic layer; MiniLM
embeddings for the ranker). v2 and v3 were both tested and discarded against a
pre-registered threshold, so there is nothing left to tune.

Discipline enforced here:
  * Models are refit on TRAIN + VAL. Validation has served its purpose as the
    selection set and is now training data - keeping it held out would waste
    ~15% of the corpus for no benefit once selection has stopped.
  * The test set is read exactly once, at the end, and no decision is taken
    after seeing it. If the number disappoints, contingency C4 applies: report
    it, do not retune.
  * Validation has been evaluated roughly ten times across this project, so the
    val figures are optimistically biased. The TEST number is the honest one and
    is what the model card will quote.
  * Confidence intervals are computed over EXPERIMENTS, not pairs, because pairs
    drawn from one experiment are not independent.

Run this once. Re-running after any change to features or architecture
invalidates the test number.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "pipeline"))

from architecture import MODULES, ModelConfig, ResonanceNet  # noqa: E402
from train_ranking import build_pairs, pairwise_accuracy  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NPZ = os.path.join(ROOT, "data", "processed", "dataset.npz")
EMB = os.path.join(ROOT, "data", "processed", "embeddings.npz")
UPW = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")
OUT_DIR = os.path.join(ROOT, "data", "processed")
MIN_GAP = 0.05


def load_rows():
    rows = []
    with open(UPW, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def split_indices(rows):
    import random
    members = defaultdict(list)
    for i, r in enumerate(rows):
        members[r["group"]].append(i)
    gids = sorted(members)
    random.Random(20260805).shuffle(gids)
    n = len(gids)
    n_tr, n_va = int(round(n * 0.70)), int(round(n * 0.15))
    parts = {"train": gids[:n_tr], "val": gids[n_tr:n_tr + n_va],
             "test": gids[n_tr + n_va:]}
    return {k: np.array(sorted(i for g in v for i in members[g]))
            for k, v in parts.items()}


def accuracy_ci(scores, pairs, tids):
    """Pairwise accuracy with a 95% CI clustered by experiment."""
    by_exp = defaultdict(list)
    for k, (i, j) in enumerate(pairs):
        by_exp[tids[i]].append(k)
    per_exp = []
    for ks in by_exp.values():
        hi = scores[pairs[ks, 0]]
        lo = scores[pairs[ks, 1]]
        per_exp.append(float((hi > lo).mean() + 0.5 * (hi == lo).mean()))
    a = np.array(per_exp)
    m = float(a.mean())
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return m, (m - 1.96 * se, m + 1.96 * se), len(a), len(pairs)


def fit_embedding_ranker(Xtr, ptr, hidden=128, epochs=30, lr=1e-3, seed=0):
    torch.manual_seed(seed)
    net = nn.Sequential(
        nn.Linear(Xtr.shape[1], hidden), nn.ReLU(), nn.Dropout(0.2),
        nn.Linear(hidden, hidden), nn.ReLU(),
        nn.Linear(hidden, 1),
    )
    opt = torch.optim.AdamW(net.parameters(), lr=lr, weight_decay=1e-4)
    Xt = torch.tensor(Xtr, dtype=torch.float32)
    for _ in range(epochs):
        net.train()
        perm = np.random.permutation(len(ptr))
        for s in range(0, len(ptr), 4096):
            sel = ptr[perm[s:s + 4096]]
            opt.zero_grad(set_to_none=True)
            hi = net(Xt[torch.from_numpy(sel[:, 0])]).squeeze(-1)
            lo = net(Xt[torch.from_numpy(sel[:, 1])]).squeeze(-1)
            nn.functional.softplus(-(hi - lo)).mean().backward()
            opt.step()
    net.eval()
    return net


def fit_module_model(Xtr, ptr, ytr, wtr, cfg, epochs=60, lr=3e-3, seed=0):
    """The constrained six-module model, trained on the same ranking objective."""
    torch.manual_seed(seed)
    model = ResonanceNet(cfg)
    decay, no_decay = [], []
    for name, p in model.named_parameters():
        (no_decay if p.ndim == 1 or name.startswith("_") else decay).append(p)
    opt = torch.optim.AdamW(
        [{"params": decay, "weight_decay": 1e-2},
         {"params": no_decay, "weight_decay": 0.0}], lr=lr)
    Xt = torch.tensor(Xtr, dtype=torch.float32)
    yt = torch.tensor(ytr, dtype=torch.float32)
    wt = torch.tensor(wtr, dtype=torch.float32)
    for _ in range(epochs):
        model.train()
        perm = np.random.permutation(len(ptr))
        for s in range(0, len(ptr), 4096):
            sel = ptr[perm[s:s + 4096]]
            hi_i = torch.from_numpy(sel[:, 0])
            lo_i = torch.from_numpy(sel[:, 1])
            opt.zero_grad(set_to_none=True)
            s_hi = model(Xt[hi_i], None)["score"]
            s_lo = model(Xt[lo_i], None)["score"]
            gap = (yt[hi_i] - yt[lo_i]).abs()
            prec = 2.0 / (1.0 / wt[hi_i].clamp_min(1e-6)
                          + 1.0 / wt[lo_i].clamp_min(1e-6))
            pw = gap * prec
            pw = pw / pw.mean().clamp_min(1e-8)
            (nn.functional.softplus(-(s_hi - s_lo)) * pw).mean().backward()
            nn.utils.clip_grad_norm_(model.parameters(), 1.0)
            opt.step()
    model.eval()
    return model


def main() -> None:
    d = np.load(NPZ, allow_pickle=True)
    rows = load_rows()
    idx = split_indices(rows)

    # train + val become the fitting set; test remains untouched until the end
    fit_idx = np.concatenate([idx["train"], idx["val"]])
    X_fit = np.vstack([d["X_train"], d["X_val"]])
    y_fit = np.concatenate([d["y_train"], d["y_val"]])
    w_fit = np.concatenate([d["w_train"], d["w_val"]])
    t_fit = np.concatenate([d["t_train"], d["t_val"]])

    X_te, y_te, t_te = d["X_test"], d["y_test"], d["t_test"]

    E = np.load(EMB)["E"]
    E_fit = E[fit_idx]
    E_te = E[idx["test"]]

    p_fit = build_pairs(y_fit, t_fit, MIN_GAP, X_fit)
    p_te = build_pairs(y_te, t_te, MIN_GAP, X_te)
    print(f"fit pairs={len(p_fit):,}  test pairs={len(p_te):,}")
    print(f"fit arms={len(y_fit):,}  test arms={len(y_te):,}\n")

    print("fitting embedding ranker...")
    ranker = fit_embedding_ranker(E_fit, p_fit)

    print("fitting constrained module model...")
    cfg = ModelConfig(n_features=X_fit.shape[1])
    module_model = fit_module_model(X_fit, p_fit, y_fit, w_fit, cfg)

    # ---------------- the single test-set read -------------------------
    print("\n" + "=" * 62)
    print("OPENING SEALED TEST SET - once, no decisions taken after this")
    print("=" * 62)

    with torch.no_grad():
        s_emb = ranker(torch.tensor(E_te, dtype=torch.float32)).squeeze(-1).numpy()
        out = module_model(torch.tensor(X_te, dtype=torch.float32), None)
        s_mod = out["score"].numpy()

    a_emb, ci_emb, n_exp, n_pairs = accuracy_ci(s_emb, p_te, t_te)
    a_mod, ci_mod, _, _ = accuracy_ci(s_mod, p_te, t_te)

    print(f"\nover {n_exp:,} experiments / {n_pairs:,} copy-only pairs\n")
    print(f"  embedding ranker : {a_emb:.4f}  95% CI [{ci_emb[0]:.4f}, {ci_emb[1]:.4f}]")
    print(f"  module model     : {a_mod:.4f}  95% CI [{ci_mod[0]:.4f}, {ci_mod[1]:.4f}]")
    print(f"\n  (val figures were 0.6241 and ~0.5649 - val is biased by "
          f"~10 evaluations)")

    drop = 0.6241 - a_emb
    if drop > 0.04:
        print(f"\n  C4 TRIGGERED: test is {drop:.4f} below val. Reporting test "
              f"as truth; no retuning.")

    print("\nmodule activations on test (mean +/- sd):")
    for m in MODULES:
        a = out["modules"][m].numpy()
        print(f"  {m:<10} {a.mean():+.3f} +/- {a.std():.3f}")

    torch.save(ranker.state_dict(), os.path.join(OUT_DIR, "final_ranker.pt"))
    torch.save(module_model.state_dict(),
               os.path.join(OUT_DIR, "final_module_model.pt"))

    report = {
        "test": {
            "embedding_ranker": {"accuracy": a_emb, "ci95": list(ci_emb)},
            "module_model": {"accuracy": a_mod, "ci95": list(ci_mod)},
            "n_experiments": n_exp, "n_pairs": n_pairs,
        },
        "val_for_reference": {"embedding_ranker": 0.6241, "module_model": 0.5649},
        "notes": "Val evaluated ~10 times and is optimistically biased. "
                 "Test read once. No tuning after this point.",
    }
    with open(os.path.join(OUT_DIR, "final_report.json"), "w",
              encoding="utf-8") as fh:
        json.dump(report, fh, indent=1)
    print(f"\nwrote final_report.json")


if __name__ == "__main__":
    main()
