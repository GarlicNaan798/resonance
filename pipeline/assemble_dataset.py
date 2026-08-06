"""
Assemble the trainable dataset: Upworthy arms -> features, targets, weights,
and leakage-safe grouped splits.

Splitting rules (same discipline as pipeline/splits.py, applied to the grouping
produced by ingest_upworthy.py):

  * The split unit is the GROUP - the transitive closure over shared test-id and
    shared headline. A group lands wholly in one split.
  * Feature standardisation is fitted on TRAIN ONLY, then applied to val/test.
    Fitting the scaler on all the data is a classic silent leak: test statistics
    bleed into training.
  * The test split is fingerprinted and locked.

Output: data/processed/dataset.npz + feature_scaler.json + split_manifest.json
"""

from __future__ import annotations

import hashlib
import json
import os
import random
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import FEATURE_NAMES, extract_vector  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")
OUT_DIR = os.path.join(ROOT, "data", "processed")
NPZ = os.path.join(OUT_DIR, "dataset.npz")
SCALER = os.path.join(OUT_DIR, "feature_scaler.json")
MANIFEST = os.path.join(OUT_DIR, "split_manifest.json")

SEED = 20260805
RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}


def load() -> list[dict]:
    rows = []
    with open(SRC, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def split_by_group(rows: list[dict]) -> dict[str, list[int]]:
    members: dict[int, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        members[r["group"]].append(i)

    gids = sorted(members)
    rng = random.Random(SEED)
    rng.shuffle(gids)

    n = len(gids)
    n_tr = int(round(n * RATIOS["train"]))
    n_va = int(round(n * RATIOS["val"]))
    parts = {"train": gids[:n_tr],
             "val": gids[n_tr:n_tr + n_va],
             "test": gids[n_tr + n_va:]}
    return {k: sorted(i for g in v for i in members[g]) for k, v in parts.items()}


def verify(rows: list[dict], splits: dict[str, list[int]]) -> None:
    seen: set[int] = set()
    for name, idxs in splits.items():
        if seen & set(idxs):
            raise AssertionError(f"{name}: overlapping indices")
        seen |= set(idxs)
    if len(seen) != len(rows):
        raise AssertionError("split does not cover the corpus")

    side: dict[int, str] = {}
    for name, idxs in splits.items():
        for i in idxs:
            g = rows[i]["group"]
            if g in side and side[g] != name:
                raise AssertionError(f"group {g} spans {side[g]} and {name}")
            side[g] = name

    # no identical headline across splits
    hside: dict[str, str] = {}
    for name, idxs in splits.items():
        for i in idxs:
            key = " ".join(rows[i]["headline"].lower().split())
            if key in hside and hside[key] != name:
                raise AssertionError(f"headline crosses {hside[key]}/{name}")
            hside[key] = name
    print("verify: OK - no index, group or headline crosses a split")


def main() -> None:
    rows = load()
    print(f"loaded {len(rows):,} labelled arms")

    print("extracting features...")
    X = np.zeros((len(rows), len(FEATURE_NAMES)), dtype=np.float32)
    for i, r in enumerate(rows):
        X[i] = extract_vector(r["headline"])
        if (i + 1) % 25000 == 0:
            print(f"  {i+1:,}/{len(rows):,}")

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    w = np.array([r["weight"] for r in rows], dtype=np.float32)

    splits = split_by_group(rows)
    verify(rows, splits)

    tr = np.array(splits["train"])
    # Scaler fitted on TRAIN ONLY - fitting on everything leaks test statistics.
    mu = X[tr].mean(axis=0)
    sd = X[tr].std(axis=0)
    sd[sd < 1e-6] = 1.0
    Xs = (X - mu) / sd

    # Weights normalised to mean 1 within train so the loss scale is stable.
    w = w / w[tr].mean()

    print(f"\n{'split':<7}{'arms':>9}{'groups':>9}{'target sd':>11}")
    for name in ("train", "val", "test"):
        idx = np.array(splits[name])
        g = len({rows[i]['group'] for i in splits[name]})
        print(f"{name:<7}{len(idx):>9,}{g:>9,}{y[idx].std():>11.4f}")

    # Test ids are kept per split so evaluation can work WITHIN experiments -
    # pairwise "which arm won" is the question the product actually answers,
    # and it needs the experiment grouping at eval time.
    test_ids = np.array([r["test_id"] for r in rows])
    va, te = np.array(splits["val"]), np.array(splits["test"])

    os.makedirs(OUT_DIR, exist_ok=True)
    np.savez_compressed(
        NPZ,
        X_train=Xs[tr], y_train=y[tr], w_train=w[tr], t_train=test_ids[tr],
        X_val=Xs[va], y_val=y[va], w_val=w[va], t_val=test_ids[va],
        X_test=Xs[te], y_test=y[te], w_test=w[te], t_test=test_ids[te],
    )
    with open(SCALER, "w", encoding="utf-8") as fh:
        json.dump({"features": FEATURE_NAMES,
                   "mean": mu.tolist(), "sd": sd.tolist()}, fh, indent=1)

    fp = hashlib.sha256()
    for i in splits["test"]:
        fp.update(rows[i]["headline"].encode("utf-8")); fp.update(b"\x00")
    manifest = {
        "seed": SEED,
        "n_features": len(FEATURE_NAMES),
        "counts": {k: len(v) for k, v in splits.items()},
        "test_fingerprint": fp.hexdigest(),
    }
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=1)

    print(f"\ntest fingerprint: {manifest['test_fingerprint'][:16]}...")
    print(f"wrote {NPZ}")


if __name__ == "__main__":
    main()
