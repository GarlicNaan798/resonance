"""
Measure duplication in the ad corpus BEFORE designing the split.

Why this matters: programmatic advertising ships many near-identical creative
variants (same campaign, swapped CTA, different size). A random train/test split
scatters those variants across both sides, the model memorises rather than
generalises, and the test score is inflated. You cannot fix that after the fact
- you have to know the duplication structure first.

Three levels are measured:
  exact      - byte-identical after whitespace normalisation
  normalised - identical after lowercasing + punctuation/digit stripping
  near       - MinHash/Jaccard >= THRESHOLD on character 5-grams

No third-party dependencies: MinHash is implemented directly.
"""

from __future__ import annotations

import glob
import hashlib
import json
import os
import random
import re
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
INTERIM = os.path.join(ROOT, "data", "interim")

SHINGLE = 5          # character n-gram size
NUM_HASHES = 64      # MinHash signature length
THRESHOLD = 0.80     # Jaccard at/above which two ads are "near-duplicate"
BANDS = 16           # LSH bands; rows = NUM_HASHES // BANDS

_punct = re.compile(r"[^a-z0-9\s]")
_digits = re.compile(r"\d+")
_ws = re.compile(r"\s+")


def load_corpus() -> list[dict]:
    rows = []
    for path in sorted(glob.glob(os.path.join(INTERIM, "ads_*.jsonl"))):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    rows.append(json.loads(line))
    return rows


def norm_exact(text: str) -> str:
    return _ws.sub(" ", text).strip()


def norm_loose(text: str) -> str:
    t = _ws.sub(" ", _digits.sub("#", _punct.sub(" ", text.lower()))).strip()
    return t


def shingles(text: str) -> set[str]:
    t = norm_loose(text)
    if len(t) < SHINGLE:
        return {t} if t else set()
    return {t[i:i + SHINGLE] for i in range(len(t) - SHINGLE + 1)}


def make_hashers(n: int, seed: int = 17) -> list[tuple[int, int]]:
    rng = random.Random(seed)
    P = (1 << 61) - 1
    return [(rng.randrange(1, P), rng.randrange(0, P)) for _ in range(n)]


HASHERS = make_hashers(NUM_HASHES)
P = (1 << 61) - 1


def minhash(sh: set[str]) -> tuple[int, ...]:
    if not sh:
        return tuple([0] * NUM_HASHES)
    base = [int.from_bytes(hashlib.blake2b(s.encode(), digest_size=8).digest(), "big")
            for s in sh]
    return tuple(min((a * h + b) % P for h in base) for a, b in HASHERS)


def jaccard(a: set[str], b: set[str]) -> float:
    if not a or not b:
        return 0.0
    inter = len(a & b)
    return inter / (len(a) + len(b) - inter)


def main() -> None:
    rows = load_corpus()
    n = len(rows)
    print(f"corpus: {n} ads\n")

    # ---- level 1 & 2: hash-based exact / normalised duplicates ----------
    exact = Counter(norm_exact(r["text"]) for r in rows)
    loose = Counter(norm_loose(r["text"]) for r in rows)
    exact_dupes = sum(c - 1 for c in exact.values() if c > 1)
    loose_dupes = sum(c - 1 for c in loose.values() if c > 1)

    print(f"exact duplicates      : {exact_dupes:>6}  ({exact_dupes / n:6.1%})  "
          f"unique={len(exact)}")
    print(f"normalised duplicates : {loose_dupes:>6}  ({loose_dupes / n:6.1%})  "
          f"unique={len(loose)}")

    # ---- level 3: LSH-banded near-duplicate clustering ------------------
    sigs = []
    shs = []
    for r in rows:
        s = shingles(r["text"])
        shs.append(s)
        sigs.append(minhash(s))

    rows_per_band = NUM_HASHES // BANDS
    buckets: dict[tuple, list[int]] = defaultdict(list)
    for idx, sig in enumerate(sigs):
        for b in range(BANDS):
            key = (b,) + sig[b * rows_per_band:(b + 1) * rows_per_band]
            buckets[key].append(idx)

    # union-find over candidate pairs confirmed by true Jaccard
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[max(ra, rb)] = min(ra, rb)

    checked = set()
    confirmed = 0
    for members in buckets.values():
        if len(members) < 2 or len(members) > 400:   # skip degenerate buckets
            continue
        for i in range(len(members)):
            for j in range(i + 1, len(members)):
                a, b = members[i], members[j]
                pair = (a, b) if a < b else (b, a)
                if pair in checked:
                    continue
                checked.add(pair)
                if jaccard(shs[a], shs[b]) >= THRESHOLD:
                    union(a, b)
                    confirmed += 1

    clusters: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        clusters[find(i)].append(i)
    sizes = sorted((len(v) for v in clusters.values()), reverse=True)
    multi = [s for s in sizes if s > 1]

    print(f"near-dup pairs (J>={THRESHOLD}) : {confirmed}")
    print(f"clusters              : {len(clusters)} "
          f"(singletons={sizes.count(1)}, multi-ad={len(multi)})")
    print(f"ads in multi-ad clusters: {sum(multi)} ({sum(multi) / n:.1%})")
    print(f"largest clusters      : {sizes[:10]}")

    # ---- per-source breakdown ------------------------------------------
    print("\nper-source duplication:")
    by_src: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_src[r["source_name"]].append(i)
    for src, idxs in sorted(by_src.items()):
        cl = {find(i) for i in idxs}
        print(f"  {src:<22} n={len(idxs):>6}  distinct_clusters={len(cl):>6}  "
              f"collapse={1 - len(cl) / len(idxs):5.1%}")

    # persist cluster assignment - this becomes the grouping key for splitting
    out = os.path.join(INTERIM, "dedup_clusters.json")
    with open(out, "w", encoding="utf-8") as fh:
        json.dump({"threshold": THRESHOLD,
                   "cluster_of": [find(i) for i in range(n)]}, fh)
    print(f"\ncluster assignment -> {out}")


if __name__ == "__main__":
    main()
