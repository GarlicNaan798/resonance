"""
Feature set v3: the identifiable-individual hypothesis.

Phase 0's disagreement diagnostic showed no interpretable feature separating the
pairs by more than 0.11 SD, and a topic probe suggesting the signal is concrete
subject matter rather than style. Reading the pairs directly surfaced one
nameable property that v2 genuinely lacks:

    winners centre an IDENTIFIABLE INDIVIDUAL;
    losers make COLLECTIVE or ABSTRACT claims.

    WINNER  "A Fan Called Her Ugly And Fat. Her Response Is Top Notch."
    LOSER   "These Stars Love Their Fans ... Until They Get Too Comfortable"

Grounding: the identifiable victim effect (Small, Loewenstein & Slovic, 2007) -
people respond far more strongly to a single identified person than to
statistically equivalent abstractions. Related: narrative transportation
(Green & Brock, 2000).

v2 already had first- and second-person markers but NO third-person singular,
which is precisely the individual-agent marker. That is the gap this tests.

This is a single pre-registered test, per contingency C1 of the plan:
    keep ONLY if the gain exceeds the shuffled-label control deviation (0.0176).
Anything smaller is noise and gets discarded, however good the story sounds.
"""

from __future__ import annotations

import re

from features_v2 import (FEATURE_NAMES_V2, extract_v2)  # noqa: F401
from features import tokenize

# Third-person singular: the identifiable-individual marker.
THIRD_SINGULAR = frozenset("he she her him his hers herself himself".split())

# Collective / abstract reference.
COLLECTIVE = frozenset("""they them their theirs themselves people everyone
everybody all most many others society americans women men parents kids
students workers citizens humans humanity nations countries groups
""".split())

# Narrative past tense - a story that happened to someone, versus a standing
# claim. Irregulars are listed because a suffix rule alone misses the common
# ones that carry most narrative weight.
PAST_IRREGULAR = frozenset("""said told went came saw got made took gave found
knew thought became left felt brought began kept held wrote stood heard let
meant set met ran paid sat spoke lay led read grew lost fell sent built
understood drew broke spent cut rose drove bought wore chose
""".split())
_ed = re.compile(r"^[a-z]+ed$")

# A capitalised token that is not sentence-initial is usually a name or place -
# a cheap proxy for a specific referent without any named-entity model.
_cap_mid = re.compile(r"(?<!^)(?<![.!?]\s)\b([A-Z][a-z]{2,})\b")

V3_ONLY_NAMES: list[str] = [
    "third_singular_frac",
    "collective_frac",
    "individual_minus_collective",
    "has_individual_agent",
    "past_tense_frac",
    "narrative_score",
    "midcap_count",
    "specific_referent_score",
]

FEATURE_NAMES_V3: list[str] = list(FEATURE_NAMES_V2) + V3_ONLY_NAMES
N_FEATURES_V3 = len(FEATURE_NAMES_V3)


def extract_v3(text: str) -> dict[str, float]:
    f = dict(extract_v2(text))

    toks = tokenize(text)
    n = max(len(toks), 1)

    third = sum(1 for t in toks if t in THIRD_SINGULAR)
    coll = sum(1 for t in toks if t in COLLECTIVE)
    past = sum(1 for t in toks if t in PAST_IRREGULAR or _ed.match(t))
    midcaps = len(_cap_mid.findall(text))

    f["third_singular_frac"] = third / n
    f["collective_frac"] = coll / n
    f["individual_minus_collective"] = (third - coll) / n
    f["has_individual_agent"] = 1.0 if third else 0.0
    f["past_tense_frac"] = past / n

    # A narrative is a specific person doing something that already happened.
    f["narrative_score"] = (
        0.5 * min(third, 2) / 2.0
        + 0.3 * min(past, 2) / 2.0
        + 0.2 * (1.0 if midcaps else 0.0)
    )

    f["midcap_count"] = float(midcaps)
    # Specificity = concrete individual reference, penalised by abstraction.
    f["specific_referent_score"] = (
        f["has_individual_agent"] + min(midcaps, 2) / 2.0
        - min(coll, 2) / 2.0
    )
    return f


def extract_vector_v3(text: str) -> list[float]:
    f = extract_v3(text)
    return [f[k] for k in FEATURE_NAMES_V3]


if __name__ == "__main__":
    print(f"v2={len(FEATURE_NAMES_V2)}  v3={N_FEATURES_V3} "
          f"(+{len(V3_ONLY_NAMES)})\n")
    pairs = [
        ("A Fan Called Her Ugly And Fat. Her Response Is Top Notch.",
         "These Stars Love Their Fans ... Until They Get Too Comfortable"),
        ("A Woman Set Herself On Fire To Escape Abuse. Her Sister's Still Here",
         "When Muslim Women And Western Women Stand Together, There Will Be No Stopping Them"),
    ]
    for win, lose in pairs:
        for label, s in (("WINNER", win), ("LOSER ", lose)):
            f = extract_v3(s)
            print(f"{label}: {s[:62]}")
            print(f"   3rd_sing={f['third_singular_frac']:.3f} "
                  f"collective={f['collective_frac']:.3f} "
                  f"narrative={f['narrative_score']:.2f} "
                  f"specific={f['specific_referent_score']:+.2f}")
        print()
