"""
Quality audit of the Upworthy Research Archive before we rely on it.

Why this dataset matters: every row is one arm of a randomised A/B test, with
the headline text AND the outcome (impressions, clicks). That is the
(text -> outcome) pairing the rest of the corpus lacks.

Why it is better than observational ad data: arms within one
`clickability_test_id` share the same article, image and publication moment and
differ only in the headline. Comparing arms WITHIN a test therefore isolates the
copy effect and controls for topic, timing and imagery - confounds that make raw
cross-campaign CTR nearly uninterpretable.

This script checks the things that would invalidate that reasoning.
"""

from __future__ import annotations

import csv
import os
import statistics as st
import sys
from collections import Counter, defaultdict

csv.field_size_limit(10_000_000)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "raw", "upworthy")
FILES = {
    "exploratory": "upworthy_exploratory.csv",
    "confirmatory": "upworthy_confirmatory.csv",
    "holdout": "upworthy_holdout.csv",
}


def audit(name: str, path: str) -> dict:
    rows = 0
    usable = 0
    no_headline = 0
    zero_impr = 0
    impressions: list[int] = []
    ctrs: list[float] = []
    tests: Counter = Counter()
    headlines: Counter = Counter()

    with open(path, encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            rows += 1
            head = (r.get("headline") or "").strip()
            try:
                impr = int(float(r.get("impressions") or 0))
                clk = int(float(r.get("clicks") or 0))
            except ValueError:
                continue
            if not head:
                no_headline += 1
                continue
            if impr <= 0:
                zero_impr += 1
                continue
            usable += 1
            impressions.append(impr)
            ctrs.append(clk / impr)
            tests[r.get("clickability_test_id", "")] += 1
            headlines[" ".join(head.lower().split())] += 1

    arms_per_test = list(tests.values())
    dup_headlines = sum(c - 1 for c in headlines.values() if c > 1)

    print(f"\n=== {name} ===")
    print(f"rows                : {rows}")
    print(f"usable (text+impr>0): {usable}  ({usable/max(rows,1):.1%})")
    print(f"  dropped no headline: {no_headline}   zero impressions: {zero_impr}")
    print(f"distinct tests      : {len(tests)}")
    print(f"arms per test       : mean={st.mean(arms_per_test):.1f} "
          f"median={st.median(arms_per_test)} max={max(arms_per_test)}")
    print(f"impressions         : median={st.median(impressions):,.0f} "
          f"p10={sorted(impressions)[len(impressions)//10]:,} "
          f"max={max(impressions):,}")
    print(f"CTR                 : median={st.median(ctrs):.4f} "
          f"mean={st.mean(ctrs):.4f} max={max(ctrs):.4f}")
    print(f"duplicate headlines : {dup_headlines} ({dup_headlines/max(usable,1):.1%})")
    return {"usable": usable, "tests": len(tests), "dupes": dup_headlines}


def main() -> None:
    if not os.path.isdir(SRC):
        sys.exit(f"missing {SRC}")
    totals = {"usable": 0, "tests": 0, "dupes": 0}
    for name, fn in FILES.items():
        path = os.path.join(SRC, fn)
        if not os.path.exists(path):
            print(f"MISSING {fn}")
            continue
        r = audit(name, path)
        for k in totals:
            totals[k] += r[k]
    print("\n=== TOTAL ===")
    print(f"usable arms : {totals['usable']:,}")
    print(f"distinct tests (grouping units): {totals['tests']:,}")
    print(f"duplicate headlines: {totals['dupes']:,}")


if __name__ == "__main__":
    main()
