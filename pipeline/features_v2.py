"""
Feature set v2: closing the gap to semantic embeddings with INTERPRETABLE features.

Embeddings scored 0.6251 pairwise; the 50 norm features scored 0.5636. That
+6.1 gap is signal our features miss. Rather than accept an opaque model, v2
adds constructs that (a) plausibly explain part of that gap and (b) each rest on
a published finding, so every number in the product can still be defended.

New blocks, each with its source:

  FREQUENCY / FLUENCY   Brysbaert & New (2009); wordfreq Zipf scale.
                        Frequent words are processed faster, and processing
                        fluency raises evaluation (Reber et al.). v1 had no
                        frequency information at all - a clear omission.

  DISCRETE EMOTION      Mohammad & Turney (2013), NRC Emotion Lexicon.
                        Valence-arousal is dimensional and cannot distinguish
                        fear from anger, or joy from trust, though these drive
                        very different behaviour. 8 emotions + 2 sentiments.

  CURIOSITY GAP         Loewenstein (1994), information-gap theory.
                        Curiosity arises from a felt gap between what one knows
                        and wants to know. Operationalised as unresolved
                        reference: wh-words, leading demonstratives, list
                        promises, ellipsis.

  SELF-REFERENCE        Rogers, Kuiper & Kirker (1977).
                        Self-referent encoding produces markedly better recall.
                        Operationalised as second-person address.

  NEGATIVITY BIAS       Rozin & Royzman (2001); Baumeister et al. (2001).
                        Negative information is weighted more heavily than
                        equivalent positive information. Explicit negation is
                        distinct from negative valence and v1 conflated them.

  SOCIAL PROOF          Cialdini (2001).
                        Consensus cues shift behaviour.

Interpretability is the point: if a feature cannot be explained to a marketer in
one sentence, it does not belong here - that is what embeddings are for.

OVERFITTING NOTE: v2 roughly doubles the feature count, which raises variance.
The same guards apply - grouped splits, copy-only pairs, shuffled-label control,
and the test set stays sealed. A gain that does not survive the control is not a
gain.
"""

from __future__ import annotations

import json
import os
import re
import statistics as st

from wordfreq import zipf_frequency

from features import (FEATURE_NAMES as V1_NAMES, Norms, STOPWORDS,  # noqa: F401
                      extract as v1_extract, tokenize)

# --- NRC Emotion Lexicon -------------------------------------------------
_NRC: dict[str, list[str]] | None = None
EMOTIONS = ("anger", "anticipation", "disgust", "fear", "joy",
            "sadness", "surprise", "trust", "negative", "positive")


def _nrc() -> dict[str, list[str]]:
    global _NRC
    if _NRC is None:
        import nrclex
        path = os.path.join(os.path.dirname(nrclex.__file__), "data", "nrc_en.json")
        with open(path, encoding="utf-8") as fh:
            _NRC = json.load(fh)
    return _NRC


# --- closed-class marker sets (function words, not content judgements) ----
WH_WORDS = frozenset("what why how who when where which whose whom".split())
DEMONSTRATIVES = frozenset("this that these those it".split())
SECOND_PERSON = frozenset("you your yours yourself yourselves".split())
FIRST_PERSON = frozenset("i me my mine we us our ours".split())
NEGATIONS = frozenset("""no not never none nothing nobody nowhere neither nor
cannot cant dont doesnt didnt wont wouldnt shouldnt couldnt isnt arent wasnt
werent havent hasnt hadnt without stop quit avoid""".split())
CONSENSUS = frozenset("""everyone everybody all most many people others nation
world americans women men parents kids everyone's majority millions thousands
""".split())

_num_list = re.compile(r"\b(\d{1,3})\s+(things|ways|reasons|tips|facts|signs|"
                       r"times|people|photos|steps|rules|secrets|lessons)\b", re.I)
_ellipsis = re.compile(r"\.\.\.|…")

V2_ONLY_NAMES: list[str] = [
    # frequency / fluency
    "zipf_mean", "zipf_min", "zipf_sd", "rare_word_frac", "common_word_frac",
    # discrete emotion
    *[f"emo_{e}" for e in EMOTIONS],
    "emo_diversity", "emo_intensity", "emo_neg_minus_pos",
    # curiosity gap
    "wh_frac", "leading_demonstrative", "num_list_promise", "ellipsis_count",
    "curiosity_score",
    # self-reference / person
    "second_person_frac", "first_person_frac",
    # negativity bias
    "negation_frac", "has_negation",
    # social proof
    "consensus_frac",
]

FEATURE_NAMES_V2: list[str] = list(V1_NAMES) + V2_ONLY_NAMES
N_FEATURES_V2 = len(FEATURE_NAMES_V2)


def extract_v2(text: str) -> dict[str, float]:
    f = dict(v1_extract(text))

    toks = tokenize(text)
    n = max(len(toks), 1)
    content = [t for t in toks if t not in STOPWORDS] or toks

    # --- frequency / fluency --------------------------------------------
    zipfs = [zipf_frequency(t, "en") for t in content]
    zipfs = [z for z in zipfs if z > 0]
    if zipfs:
        f["zipf_mean"] = st.mean(zipfs)
        f["zipf_min"] = min(zipfs)
        f["zipf_sd"] = st.pstdev(zipfs) if len(zipfs) > 1 else 0.0
        f["rare_word_frac"] = sum(1 for z in zipfs if z < 3.0) / len(zipfs)
        f["common_word_frac"] = sum(1 for z in zipfs if z > 5.0) / len(zipfs)
    else:
        f.update({k: 0.0 for k in ("zipf_mean", "zipf_min", "zipf_sd",
                                   "rare_word_frac", "common_word_frac")})

    # --- discrete emotion ------------------------------------------------
    lex = _nrc()
    counts = {e: 0 for e in EMOTIONS}
    hits = 0
    for t in content:
        tags = lex.get(t)
        if tags:
            hits += 1
            for tag in tags:
                if tag in counts:
                    counts[tag] += 1
    denom = max(len(content), 1)
    for e in EMOTIONS:
        f[f"emo_{e}"] = counts[e] / denom
    present = [counts[e] for e in EMOTIONS[:8]]          # the 8 true emotions
    f["emo_diversity"] = sum(1 for c in present if c > 0) / 8.0
    f["emo_intensity"] = (max(present) / denom) if present else 0.0
    f["emo_neg_minus_pos"] = (counts["negative"] - counts["positive"]) / denom

    # --- curiosity gap (Loewenstein) -------------------------------------
    wh = sum(1 for t in toks if t in WH_WORDS)
    f["wh_frac"] = wh / n
    f["leading_demonstrative"] = 1.0 if toks and toks[0] in DEMONSTRATIVES else 0.0
    f["num_list_promise"] = 1.0 if _num_list.search(text) else 0.0
    f["ellipsis_count"] = float(len(_ellipsis.findall(text)))
    # composite: an information gap needs a question AND an unresolved referent
    f["curiosity_score"] = (
        0.4 * min(wh, 2) / 2.0
        + 0.3 * f["leading_demonstrative"]
        + 0.2 * f["num_list_promise"]
        + 0.1 * min(f["ellipsis_count"], 1.0)
    )

    # --- self-reference (Rogers et al.) ----------------------------------
    f["second_person_frac"] = sum(1 for t in toks if t in SECOND_PERSON) / n
    f["first_person_frac"] = sum(1 for t in toks if t in FIRST_PERSON) / n

    # --- negativity bias --------------------------------------------------
    neg = sum(1 for t in toks if t in NEGATIONS)
    f["negation_frac"] = neg / n
    f["has_negation"] = 1.0 if neg else 0.0

    # --- social proof -----------------------------------------------------
    f["consensus_frac"] = sum(1 for t in toks if t in CONSENSUS) / n

    return f


def extract_vector_v2(text: str) -> list[float]:
    f = extract_v2(text)
    return [f[k] for k in FEATURE_NAMES_V2]


if __name__ == "__main__":
    print(f"v1={len(V1_NAMES)}  v2={N_FEATURES_V2} "
          f"(+{len(V2_ONLY_NAMES)} new)\n")
    for s in ["This Is What Happens When You Ignore 7 Warning Signs",
              "Save 20% today. Limited time only!",
              "The quarterly report is now available for download."]:
        f = extract_v2(s)
        print(f"> {s}")
        print(f"   curiosity={f['curiosity_score']:.2f} "
              f"2nd_person={f['second_person_frac']:.2f} "
              f"zipf_mean={f['zipf_mean']:.2f} rare={f['rare_word_frac']:.2f}")
        top = sorted(((f[f'emo_{e}'], e) for e in EMOTIONS[:8]), reverse=True)[:3]
        print(f"   emotions: " + ", ".join(f"{e}={v:.2f}" for v, e in top))
        print(f"   negation={f['negation_frac']:.2f} "
              f"consensus={f['consensus_frac']:.2f}\n")
