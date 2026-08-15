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
HITS = 1000          # Algolia's hard cap: nbPages is 1 at this size
SLEEP = 0.25         # be polite; Algolia is generous but not free
DAYS_BACK = 3650
START_WINDOW_DAYS = 16   # bisected down until each window holds < 1000

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


def _window(begin: int, end: int) -> tuple[list[dict], int]:
    """One query. Returns (hits, nbHits), nbHits is the TRUE count in range."""
    q = urllib.parse.urlencode({
        "tags": "story",
        "hitsPerPage": HITS,
        "numericFilters": f"created_at_i>{begin},created_at_i<{end}",
    })
    data = fetch(f"{API}?{q}")
    return data.get("hits", []), int(data.get("nbHits", 0))


def harvest() -> list[dict]:
    """Walk backwards through time, bisecting any window that overflows.

    Algolia caps results at 1,000 per query no matter how you paginate. A
    single month returns nbHits=28,801 but hands back 1,000. The first version
    of this script ignored that and took 5 pages per 30-day window, which
    collected the most recent ~4 days of each month: 2.9% coverage in
    contiguous slices rather than a sample. Since reposts sit months apart,
    both halves of a pair almost never landed in range, and the resulting
    "617 usable groups" measured the sampling design instead of the data.

    Fix: nbHits tells us the true count in a window. If it exceeds the cap,
    halve the window and recurse. Every leaf is then complete, and coverage is
    total rather than a biased slice.

    Resumable: rows append as they are found, so a crash costs the current
    window, not the run.
    """
    # A completion sentinel, because the harvest writes incrementally and a
    # network blip mid-run leaves a perfectly readable PARTIAL file. Without
    # this, the next run would treat that partial as the full corpus and report
    # a yield for a date range nobody chose.
    done = RAW + ".done"
    if os.path.exists(RAW):
        with open(RAW, encoding="utf-8") as fh:
            rows = [json.loads(l) for l in fh if l.strip()]
        if os.path.exists(done):
            print(f"reusing complete harvest: {RAW} ({len(rows):,} stories)")
        else:
            span = (min(r["created_at_i"] for r in rows),
                    max(r["created_at_i"] for r in rows))
            print(f"WARNING: {RAW} is PARTIAL, {len(rows):,} stories covering "
                  f"{time.strftime('%Y-%m-%d', time.gmtime(span[0]))} to "
                  f"{time.strftime('%Y-%m-%d', time.gmtime(span[1]))}.")
            print("Analysing what is there. Delete the file to harvest again.")
        return rows

    os.makedirs(os.path.dirname(RAW), exist_ok=True)
    now = int(time.time())
    start = now - DAYS_BACK * 86400
    seen: set[str] = set()
    stories: list[dict] = []
    requests = 0
    splits = 0

    def keep(hits: list[dict]) -> None:
        for h in hits:
            oid = h.get("objectID")
            if not oid or oid in seen or not h.get("url"):
                continue
            seen.add(oid)
            stories.append({
                "id": oid,
                "title": h.get("title") or "",
                "url": h.get("url") or "",
                "points": h.get("points") or 0,
                "comments": h.get("num_comments") or 0,
                "author": h.get("author") or "",
                "created_at_i": h.get("created_at_i") or 0,
            })

    def collect(begin: int, end: int, depth: int = 0) -> None:
        nonlocal requests, splits
        hits, total = _window(begin, end)
        requests += 1
        time.sleep(SLEEP)
        if total <= HITS or end - begin <= 3600 or depth > 14:
            # Complete, or narrowed to an hour and still overflowing (a spike
            # we cannot split further, rare, and losing it beats looping).
            keep(hits)
            return
        splits += 1
        mid = (begin + end) // 2
        collect(mid, end, depth + 1)
        collect(begin, mid, depth + 1)

    end = now
    step = START_WINDOW_DAYS * 86400
    with open(RAW, "w", encoding="utf-8") as fh:
        while end > start:
            begin = max(end - step, start)
            before = len(stories)
            collect(begin, end)
            for s in stories[before:]:
                fh.write(json.dumps(s, ensure_ascii=False) + "\n")
            fh.flush()
            print(f"  {time.strftime('%Y-%m-%d', time.gmtime(begin))}  "
                  f"stories {len(stories):,}  requests {requests:,}  "
                  f"splits {splits:,}", flush=True)
            end = begin

    with open(done, "w", encoding="utf-8") as fh:
        fh.write(f"{len(stories)} stories, {requests} requests\n")
    print(f"\nharvest complete: {len(stories):,} stories in {requests:,} requests")
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
