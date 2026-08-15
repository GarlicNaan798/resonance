"""
Ingest open advertising-creative datasets from the HuggingFace datasets-server.

These corpora supply real ad language. Most carry NO outcome labels, so they are
used for domain pretraining of the feature encoder, not for the outcome head.
Anything with a usable signal is tagged in `labels`.

Output: data/interim/ads_<name>.jsonl  (one JSON object per ad)
Resumable: re-running skips datasets whose output already exists.
"""

from __future__ import annotations

import json
import os
import time
import urllib.parse
import urllib.request

import env as env_loader

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(ROOT, "data", "interim")
ROWS_URL = "https://datasets-server.huggingface.co/rows"
PAGE = 100
UA = "resonance-research/0.1 (academic feature-extraction; contact via repo)"

# name -> (hf id, config, split, text field candidates)
DATASETS = {
    "programmatic_text": (
        "PeterBrendan/Ads_Creative_Text_Programmatic", "default", "train", ["text"]),
    "programmatic_copy": (
        "PeterBrendan/Ads_Creative_Ad_Copy_Programmatic", "default", "train", ["text"]),
    "ad_copy_generation": (
        "smangrul/ad-copy-generation", "default", "train", ["content"]),
    "ad_imagenet": (
        "PeterBrendan/AdImageNet", "default", "train",
        ["Ad Creative Text", "text", "creative_text"]),
}


HF_TOKEN = env_loader.get("HF_TOKEN")


def _headers() -> dict[str, str]:
    """Authenticate when a token exists, gated datasets 401 without it."""
    h = {"User-Agent": UA}
    if HF_TOKEN:
        h["Authorization"] = f"Bearer {HF_TOKEN}"
    return h


def fetch(url: str, tries: int = 5) -> dict:
    """GET JSON with linear backoff. The datasets-server rate-limits anonymous callers."""
    last = None
    for attempt in range(tries):
        try:
            req = urllib.request.Request(url, headers=_headers())
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read().decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - surface after retries
            last = exc
            time.sleep(2 + attempt * 3)
    raise RuntimeError(f"failed after {tries} tries: {url}\n{last}")


def info(dataset: str) -> dict:
    q = urllib.parse.quote(dataset, safe="")
    return fetch(f"https://datasets-server.huggingface.co/info?dataset={q}")


def n_rows(dataset: str, config: str, split: str) -> int:
    meta = info(dataset)
    splits = meta["dataset_info"][config]["splits"]
    return int(splits[split]["num_examples"])


def pick_text(row: dict, candidates: list[str]) -> str | None:
    for c in candidates:
        v = row.get(c)
        if isinstance(v, str) and v.strip():
            return v.strip()
    # fall back to the longest string field present
    strings = [v.strip() for v in row.values() if isinstance(v, str) and v.strip()]
    return max(strings, key=len) if strings else None


def ingest(name: str, dataset: str, config: str, split: str, fields: list[str]) -> int:
    out_path = os.path.join(OUT_DIR, f"ads_{name}.jsonl")
    if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
        print(f"SKIP {name} (already present)")
        return sum(1 for _ in open(out_path, encoding="utf-8"))

    total = n_rows(dataset, config, split)
    print(f"{name}: {total} rows from {dataset}")

    q = urllib.parse.quote(dataset, safe="")
    tmp = out_path + ".part"

    # Resume: a partial file records how far we got. Offsets are page-aligned,
    # so we restart at the last whole page rather than re-fetching everything.
    done_pages = 0
    written = 0
    if os.path.exists(tmp):
        with open(tmp, encoding="utf-8") as fh:
            written = sum(1 for _ in fh)
        done_pages = written // PAGE
        print(f"  resuming at row {done_pages * PAGE} ({written} already written)")

    with open(tmp, "a", encoding="utf-8") as fh:
        for offset in range(done_pages * PAGE, total, PAGE):
            url = (f"{ROWS_URL}?dataset={q}&config={config}"
                   f"&split={split}&offset={offset}&length={PAGE}")
            payload = fetch(url)
            for item in payload.get("rows", []):
                row = item.get("row", {})
                text = pick_text(row, fields)
                if not text:
                    continue
                # keep any non-image scalar as potential metadata / weak label
                meta = {k: v for k, v in row.items()
                        if isinstance(v, (str, int, float)) and k not in fields}
                fh.write(json.dumps({
                    "source": f"hf:{dataset}",
                    "source_name": name,
                    "text": text,
                    "meta": meta,
                    "labels": {},          # no outcome signal in these corpora
                    "license": "see dataset card",
                }, ensure_ascii=False) + "\n")
                written += 1
            print(f"  {min(offset + PAGE, total)}/{total}", end="\r", flush=True)
            time.sleep(0.25)
    os.replace(tmp, out_path)
    print(f"\n  wrote {written} -> {out_path}")
    return written


def main() -> None:
    os.makedirs(OUT_DIR, exist_ok=True)
    print(f"HF_TOKEN: {env_loader.redact(HF_TOKEN or '')}")
    if not HF_TOKEN:
        print("  (no token, gated datasets such as AdImageNet will be skipped)")
    grand = 0
    for name, (ds, cfg, split, fields) in DATASETS.items():
        try:
            grand += ingest(name, ds, cfg, split, fields)
        except Exception as exc:  # noqa: BLE001 - one bad source must not kill the run
            print(f"ERROR {name}: {exc}")
    print(f"\nTOTAL ads ingested: {grand}")


if __name__ == "__main__":
    main()
