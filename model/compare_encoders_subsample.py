"""
Encoder comparison on a stratified subsample.

Embedding all 150,624 headlines with mpnet-base exceeded 70 minutes on CPU and
was cut. The question it was meant to answer - does a larger encoder beat
MiniLM by more than 0.02? - does not need the full corpus. It needs enough
experiments for the confidence interval to be narrower than the threshold being
tested.

Subsampling is done by GROUP, not by row, so the leakage discipline is
unchanged: a near-duplicate cluster is either wholly in or wholly out, and
inner-train and dev-test never share a group.

MiniLM embeddings already exist for every row, so only the subsample is
re-embedded with mpnet. Both encoders are then evaluated on identical arms,
identical pairs and identical seeds.
"""

from __future__ import annotations

import json
import os
import random
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (PointwiseRanker, base_split, build_pairs,  # noqa: E402
                           carve_dev, evaluate, load_rows, train, MIN_GAP)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
CACHE = os.path.join(PROC, "embeddings_mpnet_subsample.npz")
TARGET_ARMS = 30_000
KEEP_THRESHOLD = 0.02
MODEL = "sentence-transformers/all-mpnet-base-v2"


def subsample(inner: np.ndarray, dev: np.ndarray, rows: list[dict]):
    """Take whole groups from each side until the arm budget is met."""
    def pick(idxs: np.ndarray, budget: int) -> np.ndarray:
        by_group: dict[int, list[int]] = defaultdict(list)
        for i in idxs:
            by_group[rows[i]["group"]].append(int(i))
        gids = sorted(by_group)
        random.Random(4242).shuffle(gids)
        taken: list[int] = []
        for g in gids:
            if len(taken) >= budget:
                break
            taken.extend(by_group[g])
        return np.array(sorted(taken))

    # 80/20 between fitting and evaluation, mirroring the full-corpus ratio
    return pick(inner, int(TARGET_ARMS * 0.8)), pick(dev, int(TARGET_ARMS * 0.2))


def embed_subset(headlines: list[str]) -> np.ndarray:
    if os.path.exists(CACHE):
        print("loading cached mpnet subsample")
        return np.load(CACHE)["E"]
    from sentence_transformers import SentenceTransformer
    print(f"embedding {len(headlines):,} headlines with mpnet...")
    m = SentenceTransformer(MODEL)
    E = m.encode(headlines, batch_size=128, show_progress_bar=True,
                 convert_to_numpy=True, normalize_embeddings=True)
    E = E.astype(np.float32)
    np.savez_compressed(CACHE, E=E)
    return E


def main() -> None:
    rows = load_rows()
    parts, members = base_split(rows)
    inner_full, dev_full = carve_dev(parts["train"], members)
    inner, dev = subsample(inner_full, dev_full, rows)
    print(f"subsample: inner={len(inner):,} arms  dev={len(dev):,} arms")

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)

    p_in = build_pairs(y[inner], t[inner], MIN_GAP, ident[inner])
    p_dev = build_pairs(y[dev], t[dev], MIN_GAP, ident[dev])
    print(f"pairs: inner={len(p_in):,}  dev={len(p_dev):,}\n")

    if len(p_dev) < 2000:
        raise SystemExit("dev pairs too few to resolve a 0.02 difference")

    order = np.concatenate([inner, dev])
    texts = [rows[i]["headline"] for i in order]
    E_mp_all = embed_subset(texts)
    n_in = len(inner)
    E_mp_in, E_mp_dev = E_mp_all[:n_in], E_mp_all[n_in:]

    mini = np.load(os.path.join(PROC, "embeddings.npz"))["E"]
    E_mini_in, E_mini_dev = mini[inner], mini[dev]

    print("\n=== dev pairwise accuracy (identical arms and pairs) ===")
    results = {}
    for name, (Ein, Edev) in {
        "MiniLM-L6 (384d)": (E_mini_in, E_mini_dev),
        "mpnet-base (768d)": (E_mp_in, E_mp_dev),
        "both concatenated": (np.hstack([E_mini_in, E_mp_in]),
                              np.hstack([E_mini_dev, E_mp_dev])),
    }.items():
        model = train(PointwiseRanker(Ein.shape[1]), Ein, p_in,
                      epochs=25, lr=1e-3)
        _, (acc, ci, nexp) = evaluate(model, Edev, p_dev, t[dev])
        results[name] = acc
        print(f"  {name:<20} {acc:.4f}  95% CI [{ci[0]:.4f}, {ci[1]:.4f}]")

    gain = results["mpnet-base (768d)"] - results["MiniLM-L6 (384d)"]
    print(f"\n  over {nexp:,} dev experiments")
    print(f"  mpnet gain: {gain:+.4f}  (threshold {KEEP_THRESHOLD})")
    print("\n  VERDICT: " + ("KEEP mpnet - gain justifies ~5x inference cost"
                             if gain > KEEP_THRESHOLD else
                             "KEEP MiniLM - mpnet does not justify its cost"))

    with open(os.path.join(PROC, "phase15_step2.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"results": results, "gain": gain,
                   "threshold": KEEP_THRESHOLD,
                   "subsample_arms": int(len(inner) + len(dev)),
                   "dev_experiments": int(nexp)}, fh, indent=1)


if __name__ == "__main__":
    main()
