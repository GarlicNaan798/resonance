"""
Extract ad copy from the AdImageNet parquet shards.

The shards are ~682 MB because they embed creative images. Parquet is columnar,
so we read only `text` and `dimensions` and never materialise the image bytes.

Input : *.parquet shards (project root or data/raw/)
Output: data/interim/ads_adimagenet.jsonl
"""

from __future__ import annotations

import glob
import json
import os

import pyarrow.parquet as pq

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "interim", "ads_adimagenet.jsonl")
COLUMNS = ["text", "dimensions"]


def find_shards() -> list[str]:
    """AdImageNet shards, wherever they were dropped."""
    seen: list[str] = []
    for pattern in ("train-*-of-*.parquet",
                    os.path.join("data", "raw", "train-*-of-*.parquet")):
        seen.extend(glob.glob(os.path.join(ROOT, pattern)))
    return sorted(set(seen))


def main() -> None:
    shards = find_shards()
    if not shards:
        raise SystemExit("No AdImageNet shards found (train-*-of-*.parquet).")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    written = 0
    skipped = 0

    with open(OUT, "w", encoding="utf-8") as fh:
        for shard in shards:
            pf = pq.ParquetFile(shard)
            print(f"{os.path.basename(shard)}: {pf.metadata.num_rows} rows")
            # batch-wise so peak memory stays flat regardless of shard size
            for batch in pf.iter_batches(batch_size=512, columns=COLUMNS):
                texts = batch.column("text").to_pylist()
                dims = batch.column("dimensions").to_pylist()
                for text, dim in zip(texts, dims):
                    if not text or not text.strip():
                        skipped += 1
                        continue
                    fh.write(json.dumps({
                        "source": "hf:PeterBrendan/AdImageNet",
                        "source_name": "adimagenet",
                        "text": text.strip(),
                        "meta": {"dimensions": dim},
                        "labels": {},        # no outcome signal in this corpus
                        "license": "mit",
                    }, ensure_ascii=False) + "\n")
                    written += 1

    print(f"\nwrote {written} ads ({skipped} empty skipped) -> {OUT}")


if __name__ == "__main__":
    main()
