"""
Does demographic conditioning actually change anything? (Contingency C5)

Two things need saying plainly before the audience feature ships.

1. THE MODEL'S AUDIENCE LAYER IS UNTRAINED.
   `ResonanceNet` has an audience embedding whose gains are initialised to zero
   and were never fitted, because the Upworthy archive carries NO per-arm
   demographic labels. There is no way to learn "this copy works better for
   women aged 55+" from data that never recorded who saw what. Left as-is, the
   audience selector would be a no-op dressed up as personalisation.

2. WHAT *IS* EMPIRICALLY AVAILABLE.
   Warriner et al. rated every word separately by gender (M/F), age band (Y/O)
   and education level (L/H). So we can legitimately recompute a module profile
   using the ratings *of the selected group* rather than the overall mean. That
   is a real measurement: "these words are rated more positively by women than
   by men" is a fact about the norms, not a prediction about behaviour.

This script quantifies whether that is worth surfacing at all. If M and F
ratings barely differ, the feature is noise with a demographic label on it and
should be cut.

Measured here:
  * distribution of per-word rating differences between each demographic pair
  * how often the difference exceeds a perceptible threshold
  * effect on real headlines: how much a module score moves between segments
"""

from __future__ import annotations

import json
import os
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NORMS = os.path.join(ROOT, "data", "processed", "norms.json")
UPW = os.path.join(ROOT, "data", "interim", "upworthy.jsonl")

PAIRS = [
    ("M", "F", "gender (male vs female raters)"),
    ("Y", "O", "age (younger vs older raters)"),
    ("L", "H", "education (lower vs higher)"),
]
DIMS = {0: "valence", 1: "arousal", 2: "dominance"}

# Warriner used 1-9 scales. A difference below ~0.3 is small relative to the
# ~1.3 SD of valence across the lexicon, so treat that as the perceptibility bar.
MEANINGFUL = 0.3


def main() -> None:
    with open(NORMS, encoding="utf-8") as fh:
        norms = json.load(fh)
    demo = norms["vad_demo"]
    stats = norms["stats"]
    print(f"{len(demo):,} words with demographic splits\n")

    print("PER-WORD RATING DIFFERENCES BETWEEN GROUPS")
    print(f"(scale 1-9; lexicon SD: valence {stats['valence']['sd']:.2f}, "
          f"arousal {stats['arousal']['sd']:.2f})\n")

    for a, b, label in PAIRS:
        print(f"  {label}")
        for dim, dim_name in DIMS.items():
            diffs = []
            for word, seg in demo.items():
                if a in seg and b in seg:
                    diffs.append(seg[a][dim] - seg[b][dim])
            if not diffs:
                continue
            mean = st.mean(diffs)
            sd = st.pstdev(diffs)
            big = sum(1 for d in diffs if abs(d) > MEANINGFUL) / len(diffs)
            # Cohen's d against the lexicon-wide SD for that dimension
            d_eff = abs(mean) / stats[dim_name]["sd"]
            print(f"    {dim_name:<10} mean={mean:+.3f}  sd={sd:.3f}  "
                  f"|d|>{MEANINGFUL}: {big:5.1%}  cohen_d={d_eff:.3f}")
        print()

    # ---- effect on real copy -------------------------------------------
    heads = []
    with open(UPW, encoding="utf-8") as fh:
        for i, line in enumerate(fh):
            if i >= 4000:
                break
            line = line.strip()
            if line:
                heads.append(json.loads(line)["headline"])

    import re
    word_re = re.compile(r"[a-z][a-z'-]*")

    print("EFFECT ON REAL HEADLINES (mean valence per headline, by segment)")
    print(f"sampled {len(heads):,} headlines\n")

    for a, b, label in PAIRS:
        shifts = []
        for h in heads:
            toks = word_re.findall(h.lower())
            va, vb = [], []
            for t in toks:
                seg = demo.get(t)
                if seg and a in seg and b in seg:
                    va.append(seg[a][0])
                    vb.append(seg[b][0])
            if len(va) >= 3:
                shifts.append(st.mean(va) - st.mean(vb))
        if not shifts:
            continue
        mean_abs = st.mean(abs(s) for s in shifts)
        pct_big = sum(1 for s in shifts if abs(s) > MEANINGFUL) / len(shifts)
        print(f"  {label}")
        print(f"    mean |shift| = {mean_abs:.3f} points  "
              f"max = {max(abs(s) for s in shifts):.3f}  "
              f"headlines shifting >{MEANINGFUL}: {pct_big:.1%}")

    print("\nVERDICT GUIDE")
    print("  If mean |shift| is well under 0.3, demographic conditioning moves")
    print("  scores less than the perceptibility bar, and the audience selector")
    print("  must be presented as descriptive segmentation only (C5).")


if __name__ == "__main__":
    main()
