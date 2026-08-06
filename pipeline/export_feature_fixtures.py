"""
Generate feature-parity fixtures for the TypeScript extractor.

The TS port must reproduce pipeline/features.py exactly. If it drifts, every
score in the product is quietly wrong — the model would be receiving inputs that
differ from what it was trained on, with no error anywhere.

Cases deliberately include the awkward inputs, not just clean sentences:
empty-ish text, stopwords only, unusual punctuation, all-caps, numerals, and
words absent from the norm dictionaries.

Output: resonance/lib/inference/feature_fixtures.json
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from features import FEATURE_NAMES, extract  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "resonance", "lib", "inference", "feature_fixtures.json")

CASES = [
    # ordinary marketing copy
    "Save 20% today. Limited time only!",
    "The quarterly report is now available for download.",
    "Join over one million happy customers worldwide",
    # Upworthy-style
    "This Is What Happens When You Ignore 7 Warning Signs",
    "A Fan Called Her Ugly And Fat. Her Response Is Top Notch.",
    # edge cases
    "",
    "the and of to a",                       # stopwords only
    "AAAAA!!!",                              # no dictionary words
    "SHOUTING IN ALL CAPS RIGHT NOW",
    "42",                                    # digits only
    "Won't you? Can't we! Shouldn't they...",
    "hello",                                 # single word
    "supercalifragilisticexpialidocious",    # out-of-vocabulary
    "Multi. Sentence. Copy. Here.",
    "  leading and trailing whitespace  ",
    "Café naïve résumé",                     # non-ASCII
]


def main() -> None:
    fixtures = []
    for text in CASES:
        f = extract(text)
        fixtures.append({
            "text": text,
            "features": {name: round(float(f[name]), 6) for name in FEATURE_NAMES},
        })

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump({"tolerance": 1e-4,
                   "feature_names": list(FEATURE_NAMES),
                   "cases": fixtures}, fh, ensure_ascii=False, indent=1)
    print(f"wrote {len(fixtures)} fixtures ({len(FEATURE_NAMES)} features) -> {OUT}")


if __name__ == "__main__":
    main()
