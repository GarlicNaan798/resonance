"""
Ingest the Upworthy archive, fixing the two caveats found in the audit.

CAVEAT 1 - duplicate headlines would leak across splits
------------------------------------------------------
~50% of headlines repeat. Grouping by `clickability_test_id` alone is not
enough: a headline reused in tests A and B would put near-identical text on both
sides of a split. Fix: union-find over BOTH relations - two arms are in the same
group if they share a test OR share a normalised headline. Transitive closure
then guarantees no headline and no test spans a split.

The risk of that closure is a giant connected component swallowing the corpus,
which would make splitting impossible. This script measures component sizes and
refuses to proceed if the largest exceeds MAX_COMPONENT_FRAC.

CAVEAT 2 - domain shift (2013-15 viral media vs. general marketing)
-------------------------------------------------------------------
Predicting raw CTR would bake in Upworthy's absolute click level, its topics and
its era - none of which transfer to a B2B or retail advertiser.

Fix: the target is the WITHIN-TEST log-odds contrast, not absolute CTR. Arms in
a test share article, image and timing, so subtracting the test's pooled
log-odds removes topic, imagery, seasonality and Upworthy's baseline click rate,
leaving the effect attributable to the words. "Which copy wins, holding
everything else fixed" is domain-transferable in a way that "what CTR will this
get" is not.

Two further precautions:
  * Haldane-Anscombe (+0.5) correction so zero-click arms stay finite.
  * Inverse-variance WEIGHTS, so an arm measured on 2,000 impressions does not
    influence the fit as much as one measured on 30,000. CTR is a noisy
    estimate and pretending otherwise inflates apparent performance.
"""

from __future__ import annotations

import csv
import json
import math
import os
import re
from collections import Counter, defaultdict

csv.field_size_limit(10_000_000)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "raw", "upworthy")
OUT = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")

FILES = {
    "exploratory": "upworthy_exploratory.csv",
    "confirmatory": "upworthy_confirmatory.csv",
    "holdout": "upworthy_holdout.csv",
}

MIN_IMPRESSIONS = 500          # below this the CTR estimate is close to noise
MIN_ARMS_PER_TEST = 2          # a contrast needs something to contrast against
MAX_COMPONENT_FRAC = 0.20      # refuse if one component exceeds this share

_ws = re.compile(r"\s+")
_punct = re.compile(r"[^a-z0-9\s]")


def norm_headline(text: str) -> str:
    return _ws.sub(" ", _punct.sub(" ", text.lower())).strip()


# ----------------------------------------------------------------- union-find

class DSU:
    def __init__(self, n: int):
        self.p = list(range(n))

    def find(self, x: int) -> int:
        while self.p[x] != x:
            self.p[x] = self.p[self.p[x]]
            x = self.p[x]
        return x

    def union(self, a: int, b: int) -> None:
        ra, rb = self.find(a), self.find(b)
        if ra != rb:
            self.p[max(ra, rb)] = min(ra, rb)


# ----------------------------------------------------------------- load

def load_rows() -> list[dict]:
    rows: list[dict] = []
    for release, fn in FILES.items():
        path = os.path.join(SRC, fn)
        if not os.path.exists(path):
            print(f"MISSING {fn}")
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                head = (r.get("headline") or "").strip()
                if not head:
                    continue
                try:
                    impr = int(float(r.get("impressions") or 0))
                    clk = int(float(r.get("clicks") or 0))
                except ValueError:
                    continue
                if impr < MIN_IMPRESSIONS or clk < 0 or clk > impr:
                    continue
                rows.append({
                    "release": release,
                    "test_id": (r.get("clickability_test_id") or "").strip(),
                    "headline": head,
                    "excerpt": (r.get("excerpt") or "").strip(),
                    "lede": (r.get("lede") or "").strip(),
                    "impressions": impr,
                    "clicks": clk,
                    "test_week": (r.get("test_week") or "").strip(),
                    "created_at": (r.get("created_at") or "").strip(),
                    "winner": (r.get("winner") or "").strip().lower() == "true",
                })
    return rows


# ----------------------------------------------------------------- grouping

def build_groups(rows: list[dict]) -> tuple[list[int], dict]:
    """Union arms that share a test OR a normalised headline."""
    n = len(rows)
    dsu = DSU(n)

    by_test: dict[str, list[int]] = defaultdict(list)
    by_head: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_test[r["test_id"]].append(i)
        by_head[norm_headline(r["headline"])].append(i)

    for members in by_test.values():
        for j in members[1:]:
            dsu.union(members[0], j)
    for members in by_head.values():
        for j in members[1:]:
            dsu.union(members[0], j)

    groups = [dsu.find(i) for i in range(n)]
    sizes = Counter(groups)
    largest = max(sizes.values())
    stats = {
        "n_groups": len(sizes),
        "largest": largest,
        "largest_frac": largest / n,
        "top10": [c for _, c in sizes.most_common(10)],
    }
    return groups, stats


# ----------------------------------------------------------------- target

def add_targets(rows: list[dict]) -> list[dict]:
    """Within-test log-odds contrast + inverse-variance weight."""
    by_test: dict[str, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        by_test[r["test_id"]].append(i)

    kept: list[dict] = []
    for test_id, idxs in by_test.items():
        if len(idxs) < MIN_ARMS_PER_TEST:
            continue
        tot_i = sum(rows[i]["impressions"] for i in idxs)
        tot_c = sum(rows[i]["clicks"] for i in idxs)
        if tot_i <= 0 or tot_c <= 0:
            continue
        # pooled log-odds for the test (the confound-absorbing baseline)
        p_pool = (tot_c + 0.5) / (tot_i + 1.0)
        lo_pool = math.log(p_pool / (1.0 - p_pool))

        for i in idxs:
            r = rows[i]
            c, m = r["clicks"], r["impressions"]
            p = (c + 0.5) / (m + 1.0)                    # Haldane-Anscombe
            lo = math.log(p / (1.0 - p))
            # variance of a log-odds estimate ~ 1/(c+.5) + 1/(m-c+.5)
            var = 1.0 / (c + 0.5) + 1.0 / (m - c + 0.5)
            rec = dict(r)
            rec["ctr"] = c / m
            rec["log_odds"] = lo
            rec["target"] = lo - lo_pool                 # within-test contrast
            rec["weight"] = 1.0 / var                    # inverse variance
            rec["test_arms"] = len(idxs)
            kept.append(rec)
    return kept


# ----------------------------------------------------------------- main

def main() -> None:
    rows = load_rows()
    print(f"loaded {len(rows):,} arms (impressions >= {MIN_IMPRESSIONS})")

    rows = add_targets(rows)
    print(f"after within-test targeting: {len(rows):,} arms")

    groups, stats = build_groups(rows)
    print(f"\ngroups (test OR headline, transitive): {stats['n_groups']:,}")
    print(f"largest component: {stats['largest']:,} "
          f"({stats['largest_frac']:.2%} of corpus)")
    print(f"top-10 sizes     : {stats['top10']}")

    if stats["largest_frac"] > MAX_COMPONENT_FRAC:
        raise SystemExit(
            f"\nABORT: largest component is {stats['largest_frac']:.1%} of the "
            f"corpus (limit {MAX_COMPONENT_FRAC:.0%}). Transitive closure has "
            "merged too much to split safely. Fall back to exact-duplicate "
            "linking only, or drop the bridging headlines.")

    targets = [r["target"] for r in rows]
    weights = [r["weight"] for r in rows]
    print(f"\ntarget (within-test log-odds contrast):")
    print(f"  mean={sum(targets)/len(targets):+.4f}  "
          f"min={min(targets):+.3f}  max={max(targets):+.3f}")
    print(f"weight: min={min(weights):.1f} max={max(weights):.1f}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for r, g in zip(rows, groups):
            r["group"] = int(g)
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(rows):,} labelled arms -> {OUT}")


if __name__ == "__main__":
    main()
