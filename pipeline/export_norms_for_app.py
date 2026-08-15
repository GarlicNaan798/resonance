"""
Emit a compact norms file for the TypeScript app.

The research norms file is 3.4 MB because it carries per-word demographic splits
(M/F, Y/O, L/H). The app does not need them: pipeline/audience_analysis.py showed
those per-word differences are dominated by rating noise (observed SD 0.874
against a noise-predicted 0.57-0.90), so only the lexicon-wide mean shift is
real, and that lives in resonance/lib/audience.ts as a constant.

Dropping them roughly halves the payload the server has to load.

Values are rounded to 2 decimals. Warriner ratings have SDs around 1.0-1.5 and
were collected from a handful of raters per word, so the third decimal is
precision the data never had.

Output: resonance/lib/inference/norms.json
  { "vad": {word: [v, a, d]}, "conc": {word: c}, "stats": {...} }
"""

from __future__ import annotations

import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "processed", "norms.json")
OUT = os.path.join(ROOT, "resonance", "lib", "inference", "norms.json")


def main() -> None:
    with open(SRC, encoding="utf-8") as fh:
        data = json.load(fh)

    # NO ROUNDING. An earlier version rounded to 2 decimals on the reasoning
    # that "the third decimal is precision the data never had", true of the
    # ratings, but it broke exact parity with the Python extractor. A 0.005
    # per-word rounding error becomes ~0.005 in z units, fifty times the 1e-4
    # parity tolerance, and parity is what guarantees the app feeds the model
    # the same inputs it was trained on. Fidelity beats file size here.
    vad = {w: [v[0], v[1], v[2]] for w, v in data["vad"].items()}
    conc = dict(data["concreteness"])
    stats = data["stats"]

    # The demographic columns ARE included, despite audience_analysis.py showing
    # the per-word differences are mostly rating noise.
    #
    # Reason: the model was TRAINED with the six demographic-gap features
    # carrying those values. Omitting them and sending zeros would feed the
    # model out-of-distribution input at inference. A silent mismatch between
    # training and serving, which is worse than shipping a slightly larger file.
    # They are excluded from the AUDIENCE layer (see lib/segments.ts), which is
    # a separate decision.
    #
    # Only the two dimensions the features actually use are kept: valence and
    # arousal. Dominance gaps are never read.
    demo = {}
    for word, segs in data["vad_demo"].items():
        keep = {seg: [arr[0], arr[1]] for seg, arr in segs.items()}
        if keep:
            demo[word] = keep

    payload = {"vad": vad, "conc": conc, "stats": stats, "demo": demo}
    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, separators=(",", ":"))

    src_mb = os.path.getsize(SRC) / 1e6
    out_mb = os.path.getsize(OUT) / 1e6
    print(f"vad words        : {len(vad):,}")
    print(f"concreteness     : {len(conc):,}")
    print(f"demographic      : {len(demo):,}")
    print(f"{src_mb:.1f} MB -> {out_mb:.1f} MB  ({out_mb/src_mb:.0%} of original)")
    print(f"wrote {OUT}")


if __name__ == "__main__":
    main()
