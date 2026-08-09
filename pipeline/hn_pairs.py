"""
Turn HN repost groups into usable pairs, and measure the confounding first.

A repost pair holds the LINK constant and varies the TITLE, which is the same
structure that makes Upworthy valuable. What it does not hold constant is
everything else: hour of day, weekday, how long after the original, and who
posted it. Upworthy randomised, so it needed none of those controls. This does.

So before modelling anything, quantify the damage:

  - how far apart in time are the two posts
  - how often do they share an hour-of-day bucket / weekday
  - how much of the score difference is explained by timing alone

If timing explains most of the variance, the copy signal is buried and this
corpus is not worth the compute. That is a cheap thing to find out.

Output: data/interim/hn_pairs.jsonl — one row per pair, with the controls
attached so any model can condition on them.
"""

from __future__ import annotations

import json
import math
import os
import statistics as st
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "interim", "hn_reposts.jsonl")
OUT = os.path.join(ROOT, "data", "interim", "hn_pairs.jsonl")

# HN scores start at 1 (self-upvote). Log-transform, since score distributions
# are heavily skewed and a 10->20 jump is not the same as 500->510.
def log_score(points: int) -> float:
    return math.log(max(points, 1))


def hour_of_day(ts: int) -> int:
    return (ts // 3600) % 24


def weekday(ts: int) -> int:
    return ((ts // 86400) + 4) % 7      # 1970-01-01 was a Thursday


def main() -> None:
    groups = []
    with open(SRC, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                groups.append(json.loads(line))
    print(f"{len(groups):,} repost groups")

    pairs = []
    for g in groups:
        posts = g["posts"]
        # One post per distinct title: two identical titles is not a comparison.
        seen: dict[str, dict] = {}
        for p in posts:
            key = " ".join((p["title"] or "").lower().split())
            # Keep the better-performing instance of an identical title.
            if key not in seen or p["points"] > seen[key]["points"]:
                seen[key] = p
        arms = list(seen.values())
        if len(arms) < 2:
            continue
        for i in range(len(arms)):
            for j in range(i + 1, len(arms)):
                a, b = arms[i], arms[j]
                pairs.append({
                    "url": g["url"],
                    "title_a": a["title"], "title_b": b["title"],
                    "score_a": a["points"], "score_b": b["points"],
                    "delta": log_score(a["points"]) - log_score(b["points"]),
                    "gap_days": abs(a["created_at_i"] - b["created_at_i"]) / 86400,
                    "same_hour_bucket":
                        abs(hour_of_day(a["created_at_i"])
                            - hour_of_day(b["created_at_i"])) <= 2,
                    "same_weekday":
                        weekday(a["created_at_i"]) == weekday(b["created_at_i"]),
                    "same_author": a["author"] == b["author"],
                })

    print(f"{len(pairs):,} title pairs\n")

    gaps = [p["gap_days"] for p in pairs]
    print("CONFOUNDING")
    print(f"  days between posts    median {st.median(gaps):,.0f}  "
          f"mean {st.mean(gaps):,.0f}")
    for k in ("same_hour_bucket", "same_weekday", "same_author"):
        share = sum(1 for p in pairs if p[k]) / len(pairs)
        print(f"  {k:<21} {share:.1%}")

    # How much of |delta| does timing alone explain? Compare pairs matched on
    # hour+weekday against the rest. If matched pairs show much smaller spread,
    # timing was driving the difference rather than the words.
    matched = [abs(p["delta"]) for p in pairs
               if p["same_hour_bucket"] and p["same_weekday"]]
    other = [abs(p["delta"]) for p in pairs
             if not (p["same_hour_bucket"] and p["same_weekday"])]
    print(f"\n  |delta| matched on hour+weekday : {st.mean(matched):.4f} "
          f"(n={len(matched):,})")
    print(f"  |delta| everything else         : {st.mean(other):.4f} "
          f"(n={len(other):,})")
    reduction = 1 - st.mean(matched) / st.mean(other)
    print(f"  timing explains ~{reduction:.1%} of the spread")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for p in pairs:
            fh.write(json.dumps(p, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(pairs):,} pairs -> {OUT}")

    # Timing turned out to be the wrong thing to worry about. The real problem
    # is that HN scoring is a preferential-attachment cascade: a post that gets
    # a few early upvotes reaches the front page and snowballs, and one that
    # does not dies in /new. The score measures who happened to be browsing in
    # the first ten minutes far more than it measures the headline.
    all_scores = sorted([p["score_a"] for p in pairs] + [p["score_b"] for p in pairs])
    dead = sum(1 for s in all_scores if s <= 3) / len(all_scores)
    lottery = sum(1 for p in pairs
                  if min(p["score_a"], p["score_b"]) <= 3
                  and max(p["score_a"], p["score_b"]) >= 50) / len(pairs)
    both_dead = sum(1 for p in pairs
                    if max(p["score_a"], p["score_b"]) <= 3) / len(pairs)
    live = [p for p in pairs if min(p["score_a"], p["score_b"]) >= 20]

    print("\nFRONT-PAGE LOTTERY")
    print(f"  arms scoring <=3 (never left /new)   {dead:.1%}")
    print(f"  pairs: one flopped, one hit >=50     {lottery:.1%}")
    print(f"  pairs: both flopped                  {both_dead:.1%}")
    print(f"  pairs: both got traction (>=20 each) "
          f"{len(live)/len(pairs):.1%}  (n={len(live):,})")
    if live:
        print(f"  |delta| among both-live pairs        "
              f"{st.mean([abs(p['delta']) for p in live]):.4f}  "
              f"vs {st.mean([abs(p['delta']) for p in pairs]):.4f} overall")

    print("\nREAD THIS BEFORE MODELLING")
    print(f"  Timing explains only {reduction:.0%} of the spread, so hour and")
    print("  weekday were the wrong worry. The cascade is the problem: only")
    print(f"  {len(live):,} pairs have both arms above 20 points, against")
    print("  149,090 usable copy-only pairs already available from Upworthy.")
    print("  That is ~4.5% as much data, from a different domain, measuring")
    print("  upvotes rather than clicks, and still confounded by who saw the")
    print("  post first. It does not earn its place.")


if __name__ == "__main__":
    main()
