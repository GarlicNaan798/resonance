"""
Feature extraction: text -> the numeric inputs the six modules consume.

This replaces lib/lexicons.ts. Nothing here is a hand-picked word list. Every
lexical number is a lookup into published human ratings (Warriner VAD,
Brysbaert concreteness); everything else is a structural property of the text
that can be counted without judgement.

Two design rules, both driven by the domain-shift problem:

  1. NO VOCABULARY FEATURES. No n-grams, no topic words, no "power word"
     lists. Those would let the model memorise Upworthy's 2013-15 subject
     matter and would not transfer to a client's product copy. Every feature is
     either a psycholinguistic norm statistic or a structural count.

  2. COVERAGE IS A FEATURE, NOT A SILENT FAILURE. Norm dictionaries miss words.
     The share of tokens actually found is reported so the model can learn to
     trust sparse-coverage text less, and so the UI can warn on it.

Features are grouped by the module they primarily inform. The grouping is
documentation, not a hard constraint - each module head sees the whole vector
and learns its own weighting.
"""

from __future__ import annotations

import json
import math
import os
import re
import statistics as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
NORMS_PATH = os.path.join(ROOT, "data", "processed", "norms.json")

_word_re = re.compile(r"[a-z][a-z'-]*")
_sent_re = re.compile(r"[.!?]+")

# Function words are excluded from norm averages: they are rated near-neutral
# and would dilute any real affective signal in the content words.
STOPWORDS = frozenset("""
a an the and or but if then than that this these those of to in on at for with
from by as is are was were be been being am do does did doing have has had
having i you he she it we they me him her us them my your his its our their
not no nor so too very can will just don should now
""".split())


class Norms:
    """Lazy-loaded norm tables with z-scoring against corpus statistics."""

    _cache: "Norms | None" = None

    def __init__(self) -> None:
        with open(NORMS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        self.vad: dict[str, list[float]] = data["vad"]
        self.vad_demo: dict[str, dict[str, list[float]]] = data["vad_demo"]
        self.conc: dict[str, float] = data["concreteness"]
        self.stats: dict[str, dict[str, float]] = data["stats"]

    @classmethod
    def get(cls) -> "Norms":
        if cls._cache is None:
            cls._cache = Norms()
        return cls._cache

    def z(self, dim: str, value: float) -> float:
        s = self.stats[dim]
        return (value - s["mean"]) / (s["sd"] or 1.0)


def tokenize(text: str) -> list[str]:
    return _word_re.findall(text.lower())


def _agg(values: list[float]) -> tuple[float, float, float, float]:
    """mean, sd, min, max - with safe fallbacks for short inputs."""
    if not values:
        return 0.0, 0.0, 0.0, 0.0
    if len(values) == 1:
        return values[0], 0.0, values[0], values[0]
    return st.mean(values), st.pstdev(values), min(values), max(values)


FEATURE_NAMES: list[str] = [
    # --- AFFECT (arousal) ---
    "arousal_mean_z", "arousal_sd", "arousal_max_z", "arousal_min_z",
    "arousal_range", "arousal_top3_z",
    # --- VALUATION / APPROACH (valence, dominance) ---
    "valence_mean_z", "valence_sd", "valence_max_z", "valence_min_z",
    "valence_range", "valence_skew", "valence_pos_frac", "valence_neg_frac",
    "dominance_mean_z", "dominance_sd",
    # --- ENCODING (concreteness) ---
    "concrete_mean_z", "concrete_sd", "concrete_max_z", "concrete_min_z",
    "concrete_frac_high", "concrete_frac_low",
    # --- SALIENCE (attention-grabbing surface form) ---
    "extremity_mean", "extremity_max", "exclaim_count", "question_count",
    "caps_ratio", "digit_ratio", "has_number", "quote_count",
    "first_word_arousal_z", "last_word_valence_z",
    # --- CONTROL (fluency / cognitive load) ---
    "n_words", "n_chars", "avg_word_len", "long_word_frac",
    "n_sentences", "avg_sentence_len", "type_token_ratio", "repeat_ratio",
    "vad_coverage", "conc_coverage", "stopword_frac", "punct_density",
    # --- DEMOGRAPHIC DIFFERENTIALS (Warriner segment columns) ---
    "valence_gender_gap", "arousal_gender_gap",
    "valence_age_gap", "arousal_age_gap",
    "valence_edu_gap", "arousal_edu_gap",
]

N_FEATURES = len(FEATURE_NAMES)


def extract(text: str) -> dict[str, float]:
    """Compute the full named feature dict for one piece of copy."""
    n = Norms.get()
    raw_tokens = tokenize(text)
    content = [t for t in raw_tokens if t not in STOPWORDS]
    lookup = content or raw_tokens          # never divide by zero on stopword-only text

    val, aro, dom, con = [], [], [], []
    demo_acc: dict[str, list[list[float]]] = {k: [] for k in ("M", "F", "Y", "O", "L", "H")}

    for tok in lookup:
        v = n.vad.get(tok)
        if v:
            val.append(v[0]); aro.append(v[1]); dom.append(v[2])
            seg = n.vad_demo.get(tok)
            if seg:
                for k, arr in seg.items():
                    demo_acc[k].append(arr)
        c = n.conc.get(tok)
        if c is not None:
            con.append(c)

    v_mean, v_sd, v_min, v_max = _agg(val)
    a_mean, a_sd, a_min, a_max = _agg(aro)
    d_mean, d_sd, _, _ = _agg(dom)
    c_mean, c_sd, c_min, c_max = _agg(con)

    # Extremity = distance from the neutral midpoint of the 1-9 scale. High
    # extremity means strongly polarised wording regardless of direction.
    extremity = [abs(x - 5.0) for x in val]
    e_mean, _, _, e_max = _agg(extremity)

    n_words = len(raw_tokens)
    n_chars = len(text)
    sentences = [s for s in _sent_re.split(text) if s.strip()]
    n_sent = max(len(sentences), 1)
    caps = sum(1 for ch in text if ch.isupper())
    digits = sum(1 for ch in text if ch.isdigit())
    punct = sum(1 for ch in text if ch in ",.;:!?-, '\"()")
    uniq = len(set(raw_tokens))

    top3 = sorted(aro, reverse=True)[:3]

    def demo_gap(a: str, b: str, dim: int) -> float:
        xs, ys = demo_acc[a], demo_acc[b]
        if not xs or not ys:
            return 0.0
        return st.mean(x[dim] for x in xs) - st.mean(y[dim] for y in ys)

    f = {
        "arousal_mean_z": n.z("arousal", a_mean) if aro else 0.0,
        "arousal_sd": a_sd,
        "arousal_max_z": n.z("arousal", a_max) if aro else 0.0,
        "arousal_min_z": n.z("arousal", a_min) if aro else 0.0,
        "arousal_range": a_max - a_min,
        "arousal_top3_z": n.z("arousal", st.mean(top3)) if top3 else 0.0,

        "valence_mean_z": n.z("valence", v_mean) if val else 0.0,
        "valence_sd": v_sd,
        "valence_max_z": n.z("valence", v_max) if val else 0.0,
        "valence_min_z": n.z("valence", v_min) if val else 0.0,
        "valence_range": v_max - v_min,
        "valence_skew": (v_mean - (v_min + v_max) / 2.0) if val else 0.0,
        "valence_pos_frac": sum(1 for x in val if x > 6.0) / len(val) if val else 0.0,
        "valence_neg_frac": sum(1 for x in val if x < 4.0) / len(val) if val else 0.0,
        "dominance_mean_z": n.z("dominance", d_mean) if dom else 0.0,
        "dominance_sd": d_sd,

        "concrete_mean_z": n.z("concreteness", c_mean) if con else 0.0,
        "concrete_sd": c_sd,
        "concrete_max_z": n.z("concreteness", c_max) if con else 0.0,
        "concrete_min_z": n.z("concreteness", c_min) if con else 0.0,
        "concrete_frac_high": sum(1 for x in con if x > 4.0) / len(con) if con else 0.0,
        "concrete_frac_low": sum(1 for x in con if x < 2.0) / len(con) if con else 0.0,

        "extremity_mean": e_mean,
        "extremity_max": e_max,
        "exclaim_count": float(text.count("!")),
        "question_count": float(text.count("?")),
        "caps_ratio": caps / max(n_chars, 1),
        "digit_ratio": digits / max(n_chars, 1),
        "has_number": 1.0 if digits else 0.0,
        "quote_count": float(text.count('"') + text.count("'")),
        "first_word_arousal_z": (n.z("arousal", n.vad[lookup[0]][1])
                                 if lookup and lookup[0] in n.vad else 0.0),
        "last_word_valence_z": (n.z("valence", n.vad[lookup[-1]][0])
                                if lookup and lookup[-1] in n.vad else 0.0),

        "n_words": float(n_words),
        "n_chars": float(n_chars),
        "avg_word_len": (sum(len(t) for t in raw_tokens) / n_words) if n_words else 0.0,
        "long_word_frac": (sum(1 for t in raw_tokens if len(t) >= 8) / n_words)
                          if n_words else 0.0,
        "n_sentences": float(n_sent),
        "avg_sentence_len": n_words / n_sent,
        "type_token_ratio": uniq / max(n_words, 1),
        "repeat_ratio": 1.0 - uniq / max(n_words, 1),
        "vad_coverage": len(val) / max(len(lookup), 1),
        "conc_coverage": len(con) / max(len(lookup), 1),
        "stopword_frac": (n_words - len(content)) / max(n_words, 1),
        "punct_density": punct / max(n_chars, 1),

        "valence_gender_gap": demo_gap("M", "F", 0),
        "arousal_gender_gap": demo_gap("M", "F", 1),
        "valence_age_gap": demo_gap("Y", "O", 0),
        "arousal_age_gap": demo_gap("Y", "O", 1),
        "valence_edu_gap": demo_gap("L", "H", 0),
        "arousal_edu_gap": demo_gap("L", "H", 1),
    }
    return f


def extract_vector(text: str) -> list[float]:
    f = extract(text)
    return [f[name] for name in FEATURE_NAMES]


if __name__ == "__main__":
    samples = [
        "Let's See ... Hire Cops, Pay Teachers, Buy Books For Schools. Or Kill People.",
        "Save 20% today. Limited time only!",
        "The quarterly report is now available for download.",
    ]
    print(f"{N_FEATURES} features\n")
    for s in samples:
        f = extract(s)
        print(f"> {s}")
        print(f"   arousal_mean_z={f['arousal_mean_z']:+.2f}  "
              f"valence_mean_z={f['valence_mean_z']:+.2f}  "
              f"concrete_mean_z={f['concrete_mean_z']:+.2f}")
        print(f"   extremity_max={f['extremity_max']:.2f}  "
              f"vad_coverage={f['vad_coverage']:.0%}  "
              f"avg_sentence_len={f['avg_sentence_len']:.1f}")
        print(f"   gender_gap(v)={f['valence_gender_gap']:+.3f}  "
              f"age_gap(a)={f['arousal_age_gap']:+.3f}\n")
