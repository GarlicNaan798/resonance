"""
What is the maximum pairwise accuracy ANY model could reach on this data?

The labels are not ground truth - they are noisy estimates. Each arm saw ~3,000
impressions at ~1.25% CTR, so roughly 39 clicks. The click count is binomial, so
the measured CTR carries real sampling error, and sometimes the arm we record as
the "winner" only won by luck.

A model that predicted each arm's TRUE click probability perfectly would still
be marked wrong whenever noise flipped the recorded order. That defines a hard
ceiling, and it is a property of the data, not of any architecture.

Method - split-half simulation:
  For each arm, treat the observed CTR as the true rate. Draw TWO independent
  binomial samples at the arm's real impression count. Sample A plays the role
  of "an oracle's knowledge"; sample B plays the role of "the recorded label".
  How often A and B agree on the ordering of a pair is the reliability ceiling.

Anything a model scores must be read against this number, not against 100%.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPW = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")
MIN_GAP = 0.05
N_SIM = 5


def load():
    rows = []
    with open(UPW, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                rows.append(json.loads(line))
    return rows


def log_odds(c, n):
    p = (c + 0.5) / (n + 1.0)
    return np.log(p / (1.0 - p))


def ceiling(rows, rng, gap_filter):
    """One simulated replication; returns oracle-vs-label agreement."""
    by_test = defaultdict(list)
    for i, r in enumerate(rows):
        by_test[r["test_id"]].append(i)

    impressions = np.array([r["impressions"] for r in rows])
    p_true = np.array([r["clicks"] / r["impressions"] for r in rows])

    # two independent replications of the same experiment
    cA = rng.binomial(impressions, p_true)
    cB = rng.binomial(impressions, p_true)
    loA = log_odds(cA, impressions)
    loB = log_odds(cB, impressions)

    agree = total = 0
    for idxs in by_test.values():
        if len(idxs) < 2:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                # pair selection uses replication B, mirroring how the real
                # dataset was filtered on its single observed measurement
                gapB = loB[i] - loB[j]
                if abs(gapB) < gap_filter:
                    continue
                gapA = loA[i] - loA[j]
                if gapA == 0:
                    continue
                agree += int((gapA > 0) == (gapB > 0))
                total += 1
    return agree / max(total, 1), total


def main() -> None:
    rows = load()
    print(f"{len(rows):,} arms")
    med_impr = np.median([r["impressions"] for r in rows])
    med_clicks = np.median([r["clicks"] for r in rows])
    print(f"median impressions={med_impr:,.0f}  median clicks={med_clicks:,.0f}\n")

    rng = np.random.default_rng(0)

    print("ORACLE CEILING - agreement between two independent replications")
    print("(a perfect model cannot beat this; it is pure measurement noise)\n")
    print(f"{'|gap| filter':>14} {'ceiling':>9} {'pairs':>10}")
    for gf in (0.05, 0.10, 0.20, 0.30, 0.50, 0.80):
        vals, tots = [], 0
        for s in range(N_SIM):
            rng_s = np.random.default_rng(s)
            c, t = ceiling(rows, rng_s, gf)
            vals.append(c)
            tots = t
        print(f"{gf:>14.2f} {np.mean(vals):>9.4f} {tots:>10,}")

    print("\nOur model on held-out test (|gap| >= 0.05): 0.5942")
    print("\nRead every model number against the matching ceiling row, not "
          "against 1.00.")


if __name__ == "__main__":
    main()
