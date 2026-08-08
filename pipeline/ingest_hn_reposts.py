"""
Harvest Hacker News reposts: same URL, different titles, different scores.

Why this shape of data. Upworthy is valuable because arms within a test share
the article and differ only in headline, which isolates the copy effect. A
repost reproduces that structure naturally: the same link submitted twice with
different titles holds content constant and varies only the wording.

It is NOT randomised, and the confounds are real - time of day, day of week,
submitter reputation, and front-page luck all move scores independently of the
title. So this is quasi-experimental evidence, weaker than Upworthy, and any
model trained on it needs those controls.

FEASIBILITY FIRST. This script's job is to measure YIELD before anyone invests
in modelling: how many URLs have two or more submissions with genuinely
different titles, and how large are the score differences. If the answer is a
few hundred groups, the idea dies here and that is a cheap result.

Data source: the HN Algolia search API. Public, no account, no key. Paged by
time window because Algolia caps pagination at 1,000 hits per query.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "interim", "hn_reposts.jsonl")
RAW = os.path.join(ROOT, "data", "interim", "hn_stories.jsonl")

API = "https://hn.algolia.com/api/v1/search_by_date"
UA = "resonance-research/0.1 (headline repost feasibility study)"
HITS = 1000          # Algolia max per page
PAGE_LIMIT = 5       # pages per window before we slide the window
SLEEP = 0.4          # be polite; Algolia is generous but not free

# Walk backwards from this many days ago, in windows.
DAYS_BACK = 3650
WINDOW_DAYS = 30

_utm = re.compile(r"[?&](utm_[a-z]+|ref|source|fbclid|gclid)=[^&]*", re.I)


def normalise_url(u: str) -> str:
    """Strip the differences that do not change the destination."""
    if not u:
        return ""
    u = u.strip().lower()
    u = re.sub(r"^https?://", "", u)
    u = re.sub(r"^www\.", "", u)
    u = _utm.sub("", u)
    u = u.split("#")[0]
    return u.rstrip("/?&")


def normalise_title(t: str) -> str:
    return " ".join((t or "").lower().split())


def fetch(url: str, tries: int = 4) -> dict:
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=45) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001
            last = exc
            time.sleep(1.5 * (i + 1))
    raise RuntimeError(f"failed: {url}\n{last}")


def harvest() -> list[dict]:
    """Page backwards through time, collecting stories that have a URL."""
    if os.path.exists(RAW):
        print(f"reusing {RAW}")
        with open(RAW, encoding="utf-8") as fh:
            return [json.loads(l) for l in fh if l.strip()]

    now = int(time.time())
    stories: list[dict] = []
    seen_ids: set[int] = set()
    window = WINDOW_DAYS * 86400

    end = now
    start = now - DAYS_BACK * 86400
    while end > start:
        begin = end - window
        for page in range(PAGE_LIMIT):
            q = urllib.parse.urlencode({
                "tags": "story",
                "hitsPerPage": HITS,
                "page": page,
                "numericFilters": f"created_at_i>{begin},created_at_i<{end}",
            })
            data = fetch(f"{API}?{q}")
            hits = data.get("hits", [])
            for h in hits:
                oid = h.get("objectID")
                if not oid or oid in seen_ids or not h.get("url"):
                    continue
                seen_ids.add(oid)
                stories.append({
                    "id": oid,
                    "title": h.get("title") or "",
                    "url": h.get("url") or "",
                    "points": h.get("points") or 0,
                    "comments": h.get("num_comments") or 0,
                    "author": h.get("author") or "",
                    "created_at_i": h.get("created_at_i") or 0,
                })
            if len(hits) < HITS:
                break
            time.sleep(SLEEP)
        print(f"  {time.strftime('%Y-%m', time.gmtime(begin))}  "
              f"total {len(stories):,}", flush=True)
        end = begin
        time.sleep(SLEEP)

    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    with open(RAW, "w", encoding="utf-8") as fh:
        for s in stories:
            fh.write(json.dumps(s, ensure_ascii=False) + "\n")
    return stories


def main() -> None:
    stories = harvest()
    print(f"\n{len(stories):,} stories with URLs")

    by_url: dict[str, list[dict]] = defaultdict(list)
    for s in stories:
        key = normalise_url(s["url"])
        if key:
            by_url[key].append(s)

    groups = []
    for url, posts in by_url.items():
        if len(posts) < 2:
            continue
        titles = {normalise_title(p["title"]) for p in posts}
        if len(titles) < 2:
            continue          # same URL AND same title: not a copy comparison
        groups.append({"url": url, "posts": posts, "n_titles": len(titles)})

    multi = [g for g in groups if len(g["posts"]) >= 2]
    scored = [g for g in multi
              if max(p["points"] for p in g["posts"]) >= 10]

    print(f"distinct URLs            : {len(by_url):,}")
    print(f"URLs posted 2+ times     : "
          f"{sum(1 for v in by_url.values() if len(v) > 1):,}")
    print(f"  ...with DIFFERENT titles: {len(multi):,}")
    print(f"  ...and 10+ points on one: {len(scored):,}")

    if scored:
        import statistics as st
        spreads = []
        for g in scored:
            pts = sorted((p["points"] for p in g["posts"]), reverse=True)
            spreads.append(pts[0] - pts[1])
        print(f"\nscore gap between top two, among usable groups:")
        print(f"  median {st.median(spreads):,.0f}   "
              f"mean {st.mean(spreads):,.0f}   max {max(spreads):,}")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        for g in scored:
            fh.write(json.dumps(g, ensure_ascii=False) + "\n")
    print(f"\nwrote {len(scored):,} usable groups -> {OUT}")

    print("\nYIELD VERDICT:")
    if len(scored) < 2000:
        print("  Too few to train on. Upworthy has 32,487 experiments; this")
        print("  would be a rounding error, and noisier. Stop here.")
    else:
        print("  Enough to be worth modelling, WITH controls for submission")
        print("  time, weekday and author - none of which Upworthy needed,")
        print("  because Upworthy randomised and this does not.")


if __name__ == "__main__":
    main()
