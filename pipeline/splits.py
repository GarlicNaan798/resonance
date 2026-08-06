"""
Leakage-safe dataset splitting.

The corpus is 49% exact duplicates and 89% of ads live in near-duplicate
clusters (see audit_duplicates.py). Random splitting is therefore invalid: an
exact copy of almost any test ad would appear in training, and the test score
would measure memorisation, not generalisation.

Rules enforced here:

  1. GROUPED  - the unit of splitting is the near-duplicate cluster, never the
                individual ad. A cluster lands wholly in one split.
  2. LOCKED   - the test split is written once and fingerprinted. Any later
                change to its contents is detected and refused.
  3. BLIND    - test is loaded only through unlock_test(), which demands an
                explicit reason. Validation is what you tune against.
  4. AUDITED  - verify() proves zero cluster overlap and zero text overlap
                across splits, and is run in CI and before every training run.

Splitting is deterministic given SEED, so splits are reproducible.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import random
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM = os.path.join(ROOT, "data", "interim")
SPLIT_DIR = os.path.join(ROOT, "data", "splits")
LOCK_PATH = os.path.join(SPLIT_DIR, "test.lock.json")

SEED = 20260805
RATIOS = {"train": 0.70, "val": 0.15, "test": 0.15}


# ---------------------------------------------------------------- loading

def load_corpus() -> list[dict]:
    rows: list[dict] = []
    for path in sorted(glob.glob(os.path.join(INTERIM, "ads_*.jsonl"))):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def load_clusters(n: int) -> list[int]:
    path = os.path.join(INTERIM, "dedup_clusters.json")
    if not os.path.exists(path):
        raise SystemExit("Run pipeline/audit_duplicates.py first "
                         "(dedup_clusters.json missing).")
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    clusters = data["cluster_of"]
    if len(clusters) != n:
        raise SystemExit(
            f"Cluster file covers {len(clusters)} ads but corpus has {n}. "
            "The corpus changed - re-run audit_duplicates.py.")
    return clusters


# ---------------------------------------------------------------- splitting

def make_splits(rows: list[dict], clusters: list[int]) -> dict[str, list[int]]:
    """Assign whole clusters to splits, keeping source proportions stable.

    Clusters are bucketed by their dominant source and dealt out per source, so
    a small corpus (e.g. programmatic_text) is not swallowed by one split.
    """
    members: dict[int, list[int]] = defaultdict(list)
    for idx, cid in enumerate(clusters):
        members[cid].append(idx)

    # dominant source per cluster
    by_source: dict[str, list[int]] = defaultdict(list)
    for cid, idxs in members.items():
        counts = defaultdict(int)
        for i in idxs:
            counts[rows[i]["source_name"]] += 1
        dominant = max(counts.items(), key=lambda kv: kv[1])[0]
        by_source[dominant].append(cid)

    rng = random.Random(SEED)
    out: dict[str, list[int]] = {k: [] for k in RATIOS}

    for source, cids in sorted(by_source.items()):
        cids = sorted(cids)          # deterministic before shuffle
        rng.shuffle(cids)
        n = len(cids)
        n_train = int(round(n * RATIOS["train"]))
        n_val = int(round(n * RATIOS["val"]))
        parts = {
            "train": cids[:n_train],
            "val": cids[n_train:n_train + n_val],
            "test": cids[n_train + n_val:],
        }
        for split, chosen in parts.items():
            for cid in chosen:
                out[split].extend(members[cid])

    return {k: sorted(v) for k, v in out.items()}


# ---------------------------------------------------------------- integrity

def _fingerprint(rows: list[dict], idxs: list[int]) -> str:
    h = hashlib.sha256()
    for i in idxs:
        h.update(rows[i]["text"].encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def verify(rows: list[dict], clusters: list[int],
           splits: dict[str, list[int]]) -> None:
    """Prove the split is sound. Raises on any violation."""
    names = list(splits)

    # every ad used exactly once
    seen: set[int] = set()
    for name in names:
        dup = seen & set(splits[name])
        if dup:
            raise AssertionError(f"{name}: {len(dup)} ads appear in two splits")
        seen |= set(splits[name])
    if len(seen) != len(rows):
        raise AssertionError(f"split covers {len(seen)} of {len(rows)} ads")

    # no cluster spans two splits
    cluster_side: dict[int, str] = {}
    for name in names:
        for i in splits[name]:
            cid = clusters[i]
            prior = cluster_side.get(cid)
            if prior and prior != name:
                raise AssertionError(
                    f"cluster {cid} spans {prior} and {name} - leakage")
            cluster_side[cid] = name

    # belt and braces: no normalised text string crosses splits
    text_side: dict[str, str] = {}
    for name in names:
        for i in splits[name]:
            key = " ".join(rows[i]["text"].lower().split())
            prior = text_side.get(key)
            if prior and prior != name:
                raise AssertionError(
                    f"identical text in {prior} and {name} - leakage")
            text_side[key] = name

    print("verify: OK - no ad, cluster or text string crosses a split")


def lock_test(rows: list[dict], splits: dict[str, list[int]]) -> None:
    """Fingerprint the test split so silent drift is impossible."""
    fp = _fingerprint(rows, splits["test"])
    if os.path.exists(LOCK_PATH):
        with open(LOCK_PATH, encoding="utf-8") as fh:
            existing = json.load(fh)
        if existing["fingerprint"] != fp:
            raise SystemExit(
                "\nTEST SET CHANGED.\n"
                f"  locked: {existing['fingerprint'][:16]}…\n"
                f"  now   : {fp[:16]}…\n"
                "A locked test set must never change. If the corpus genuinely "
                "grew, delete the lock deliberately and treat every previous "
                "test number as void.\n")
        print(f"lock: test set matches existing lock ({fp[:16]}…)")
        return
    with open(LOCK_PATH, "w", encoding="utf-8") as fh:
        json.dump({"fingerprint": fp, "n": len(splits["test"]), "seed": SEED},
                  fh, indent=1)
    print(f"lock: test set sealed ({fp[:16]}…, n={len(splits['test'])})")


def unlock_test(reason: str) -> list[dict]:
    """Load the test split. Requires a stated reason - use once, at the end."""
    if not reason or len(reason) < 20:
        raise SystemExit(
            "unlock_test() needs an explicit reason (>=20 chars). "
            "Touching test during development is how models get oversold.")
    path = os.path.join(SPLIT_DIR, "test.jsonl")
    with open(path, encoding="utf-8") as fh:
        data = [json.loads(l) for l in fh if l.strip()]
    print(f"!! TEST SET OPENED: {reason} ({len(data)} ads)")
    return data


# ---------------------------------------------------------------- main

def main() -> None:
    os.makedirs(SPLIT_DIR, exist_ok=True)
    rows = load_corpus()
    clusters = load_clusters(len(rows))
    splits = make_splits(rows, clusters)
    verify(rows, clusters, splits)

    n = len(rows)
    n_clusters = len(set(clusters))
    print(f"\ncorpus {n} ads across {n_clusters} independent clusters")
    print(f"{'split':<7} {'ads':>7} {'%':>6} {'clusters':>9}")
    for name in ("train", "val", "test"):
        idxs = splits[name]
        cl = len({clusters[i] for i in idxs})
        print(f"{name:<7} {len(idxs):>7} {len(idxs)/n:>5.1%} {cl:>9}")

    for name, idxs in splits.items():
        with open(os.path.join(SPLIT_DIR, f"{name}.jsonl"), "w",
                  encoding="utf-8") as fh:
            for i in idxs:
                rec = dict(rows[i])
                rec["_cluster"] = clusters[i]
                fh.write(json.dumps(rec, ensure_ascii=False) + "\n")

    lock_test(rows, splits)
    print(f"\nsplits -> {SPLIT_DIR}")


if __name__ == "__main__":
    main()
