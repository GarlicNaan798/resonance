"""
Re-embed with a stronger encoder.

Step 1 of the accuracy push showed pairwise interaction adds nothing (C9), so
the bi-encoder structure is not the limit. But the ceiling test showed semantics
carry ~6 points over psycholinguistic features, which points at the ENCODER as
the place where more signal might live.

Current: all-MiniLM-L6-v2  - 6 layers, 384 dim, ~23M params.
This run: all-mpnet-base-v2 - 12 layers, 768 dim, ~110M params, consistently
stronger on sentence-similarity benchmarks.

Cached to its own file so the MiniLM embeddings stay intact for comparison.
"""

from __future__ import annotations

import json
import os

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
UPW = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")
OUT = os.path.join(ROOT, "data", "processed", "embeddings_mpnet.npz")
MODEL = "sentence-transformers/all-mpnet-base-v2"


def main() -> None:
    if os.path.exists(OUT):
        print(f"already present: {OUT}")
        return

    heads = []
    with open(UPW, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                heads.append(json.loads(line)["headline"])
    print(f"{len(heads):,} headlines")

    from sentence_transformers import SentenceTransformer
    m = SentenceTransformer(MODEL)
    E = m.encode(heads, batch_size=128, show_progress_bar=True,
                 convert_to_numpy=True, normalize_embeddings=True)
    np.savez_compressed(OUT, E=E.astype(np.float32))
    print(f"wrote {OUT}  shape={E.shape}")


if __name__ == "__main__":
    main()
