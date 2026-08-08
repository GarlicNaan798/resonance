"""
Are we leaving usable copy on the table in the Upworthy archive?

We train on `headline` only, but each arm also carries `excerpt`, `lede` and
`share_text`. If those vary within a test they would be extra copy signal — and
they would rescue pairs currently discarded as "identical copy", which is 10.8%
of all within-test pairs (32,119 of them).

The test has to control for two things, and getting either wrong reverses the
answer:

  IMAGE.       Upworthy varied headline AND eyecatcher. Pairs where "nothing
               differs" in text still differ by picture, so they are not a
               null condition unless eyecatcher_id is held equal.
  SAMPLE SIZE. Raw |log-odds gap| is dominated by sampling noise, which scales
               as 1/sqrt(n). Comparing raw gaps across groups compares their
               impression counts, not their copy.

So the statistic is |gap| divided by that pair's own standard error, computed
only within pairs sharing an eyecatcher. Pure binomial noise gives mean |z| of
about 0.80 (half-normal).

Result: body-only pairs are indistinguishable from no-change pairs, while
headline-differing pairs are far above both. The extra fields carry no click
signal — presumably because the excerpt is not visible at the moment of the
click decision. Adding those 32,119 pairs would add noise, not data.
"""

from __future__ import annotations

import csv
import math
import os
import statistics as st
from collections import defaultdict

csv.field_size_limit(10_000_000)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "raw", "upworthy")
FILES = ["upworthy_confirmatory.csv", "upworthy_exploratory.csv",
         "upworthy_holdout.csv"]
MIN_IMPRESSIONS = 500


def norm(s: str | None) -> str:
    return " ".join((s or "").lower().split())


def log_odds(c: float, n: float) -> float:
    p = (c + 0.5) / (n + 1.0)
    return math.log(p / (1.0 - p))


def se(c: float, n: float) -> float:
    return math.sqrt(1.0 / (c + 0.5) + 1.0 / (n - c + 0.5))


def load():
    by_test = defaultdict(list)
    for fn in FILES:
        path = os.path.join(SRC, fn)
        if not os.path.exists(path):
            continue
        with open(path, encoding="utf-8", newline="") as fh:
            for r in csv.DictReader(fh):
                try:
                    n = int(float(r["impressions"] or 0))
                    c = int(float(r["clicks"] or 0))
                except ValueError:
                    continue
                if n < MIN_IMPRESSIONS or c < 0 or c > n:
                    continue
                r["_lo"] = log_odds(c, n)
                r["_se"] = se(c, n)
                by_test[r["clickability_test_id"]].append(r)
    return by_test


def main() -> None:
    by_test = load()
    cells = defaultdict(list)

    for arms in by_test.values():
        if len(arms) < 2:
            continue
        for i in range(len(arms)):
            for j in range(i + 1, len(arms)):
                a, b = arms[i], arms[j]
                # Hold the image constant, or the comparison is meaningless.
                if (a.get("eyecatcher_id") or "") != (b.get("eyecatcher_id") or ""):
                    continue
                z = abs(a["_lo"] - b["_lo"]) / math.sqrt(a["_se"] ** 2 + b["_se"] ** 2)
                if norm(a["headline"]) != norm(b["headline"]):
                    cells["headline differs"].append(z)
                elif (norm(a.get("excerpt")) != norm(b.get("excerpt"))
                      or norm(a.get("lede")) != norm(b.get("lede"))):
                    cells["ONLY body differs"].append(z)
                else:
                    cells["nothing differs"].append(z)

    print("Same image; |log-odds gap| normalised by the pair's standard error.")
    print("Pure binomial noise gives mean |z| ~ 0.80.\n")
    print(f"{'pair type':<22}{'pairs':>9}{'mean |z|':>10}")
    for k in ("headline differs", "ONLY body differs", "nothing differs"):
        v = cells[k]
        if v:
            print(f"{k:<22}{len(v):>9,}{st.mean(v):>10.4f}")

    body = st.mean(cells["ONLY body differs"])
    null = st.mean(cells["nothing differs"])
    head = st.mean(cells["headline differs"])
    print(f"\nbody-only / nothing : {body / null:.3f}x")
    print(f"headline / nothing  : {head / null:.3f}x")

    if body / null < 1.1:
        print("\nVERDICT: body copy carries no detectable click signal. The")
        print("pairs it would unlock are noise, not data. Keep training on")
        print("headline alone.")
    else:
        print("\nVERDICT: body copy moves clicks. Worth feeding to the model.")

    # Overdispersion note: even 'nothing differs' sits above the 0.80 that pure
    # binomial sampling predicts, so some variation is driven by factors we
    # never observe — time within the test, position, audience mix. That is
    # consistent with the low signal fraction measured in ceiling_robustness.py.
    print(f"\nNote: 'nothing differs' at {null:.3f} exceeds the 0.80 expected")
    print("from binomial noise alone, so unobserved factors (timing, position,")
    print("audience mix) move clicks even when the creative is identical.")


if __name__ == "__main__":
    main()
