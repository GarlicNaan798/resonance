"""
Human baseline: can experienced marketers pick the winning headline?

THE POINT. The project reports 61.8% and has no idea whether that is good.
Against chance it is clearly better; against a competent copywriter it is
unmeasured, and "beats copywriter intuition" is therefore a claim the product
is forbidden from making (FUNDAMENTALS.md section 3). Published work on this
task puts humans near chance, but that is someone else's corpus. This measures
it on ours.

METHOD, and the parts that are easy to get wrong:

  BLIND. Participants see two headlines and nothing else. No scores, no
  impression counts, no hint of which experiment they came from.

  ORDER RANDOMISED. Which arm appears first is decided by coin flip at build
  time and recorded. Without this, a participant who always picks the top one
  would inherit the winner's position rather than judge the copy — and we would
  have measured our own pair-construction order.

  SAME ITEMS. The model is scored on exactly the pairs each participant saw,
  never on its global 61.8%. Comparing a human's 60 items against a number
  computed on 20,452 different ones would be a different comparison wearing the
  same clothes.

  PAIRED TEST. Human and model answer identical items, so the comparison is
  McNemar's exact test on the discordant pairs, not two independent intervals
  eyeballed for overlap.

  KEY WITHHELD. The quiz file contains no answers. Scoring happens here,
  against a key that never leaves this machine — otherwise a curious
  participant can read the labels out of the page they are being tested with.

This reads the held-out test set, so it goes through the gate in
pipeline/test_lock.py and is recorded like any other read.

Usage:
    python model/human_baseline.py build [--n 60] [--seed 7]
    python model/human_baseline.py score responses/*.json
"""

from __future__ import annotations

import argparse
import glob
import html
import json
import math
import os
import random
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "model"))
sys.path.insert(0, os.path.join(ROOT, "pipeline"))

from accuracy_push import load_rows, MIN_GAP          # noqa: E402
from train_ranking import build_pairs                 # noqa: E402
from test_lock import split_indices, unlock_test      # noqa: E402

PROC = os.path.join(ROOT, "data", "processed")
NPZ = os.path.join(PROC, "dataset.npz")
EMB = os.path.join(PROC, "embeddings.npz")
RANKER = os.path.join(ROOT, "resonance", "lib", "inference", "ranker.json")

QUIZ_HTML = os.path.join(PROC, "human_quiz.html")
QUIZ_JSON = os.path.join(PROC, "human_quiz.json")
KEY_JSON = os.path.join(PROC, "human_key.json")

Z95 = 1.96


# ------------------------------------------------------------------ scoring

def load_ensemble():
    with open(RANKER, encoding="utf-8") as fh:
        r = json.load(fh)
    members = []
    for m in r["members"]:
        layers = [(np.asarray(l["w"], dtype=np.float64),
                   np.asarray(l["b"], dtype=np.float64),
                   l.get("act")) for l in m["layers"]]
        members.append((layers, float(m["mean"]), float(m["sd"])))
    return members, int(r["embedding_dim"])


def score_embeddings(E: np.ndarray, members) -> np.ndarray:
    """Mirror of scoreEmbedding() in resonance/lib/inference/ranker.ts.

    Each member is standardised by its own fit-set mean/sd before averaging;
    normalising across the batch instead would flatten every member to the same
    spread and quietly turn the ensemble into a majority vote.
    """
    total = np.zeros(len(E), dtype=np.float64)
    for layers, mean, sd in members:
        h = E.astype(np.float64)
        for w, b, act in layers:
            h = h @ w.T + b
            if act == "relu":
                h = np.maximum(h, 0.0)
        total += (h[:, 0] - mean) / sd
    return total / len(members)


def wilson(successes: int, n: int) -> tuple[float, float]:
    if n == 0:
        return 0.0, 1.0
    p = successes / n
    z2 = Z95 * Z95
    denom = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denom
    half = (Z95 * math.sqrt(p * (1 - p) / n + z2 / (4 * n * n))) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def items_needed(p_human: float, p_model: float, power: float = 0.80) -> int:
    """Answered items needed to detect a human/model gap with McNemar.

    Stated before collecting anything, because "we ran it and it was not
    significant" means nothing without knowing whether the study could ever have
    detected the effect.

    Only DISCORDANT items carry information. Treating the two judges as roughly
    independent, the discordant rate is

        d = p_h(1 - p_m) + p_m(1 - p_h)

    and among those, the share favouring the model is

        q = p_m(1 - p_h) / d

    Detecting q against 0.5 is a one-proportion test, so

        n_disc = (z_a/2 * 0.5 + z_b * sqrt(q(1-q)))^2 / (q - 0.5)^2
        n_total = n_disc / d

    ponytail: the independence assumption is optimistic — a human and a model
    that both find the same items easy are positively correlated, which shrinks
    d and RAISES the requirement. Treat the number as a floor.
    """
    d = p_human * (1 - p_model) + p_model * (1 - p_human)
    if d <= 0:
        return 0
    q = p_model * (1 - p_human) / d
    if abs(q - 0.5) < 1e-9:
        return 0
    z_b = 0.84 if power <= 0.80 else 1.28
    n_disc = (Z95 * 0.5 + z_b * math.sqrt(q * (1 - q))) ** 2 / (q - 0.5) ** 2
    return math.ceil(n_disc / d)


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact p for paired accuracies.

    b = human right, model wrong. c = human wrong, model right. Items both got
    right or both got wrong carry no information about which is better, so they
    are excluded — that is the whole reason to run a paired test rather than
    compare two intervals.
    """
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


# -------------------------------------------------------------------- build

def build(n_items: int, seed: int) -> None:
    rows = load_rows()
    d = np.load(NPZ, allow_pickle=True)

    # The seed goes in the reason so the log is self-interpreting: rebuilding
    # with the same seed re-reads the SAME items, and a reader should be able to
    # tell one sample accessed repeatedly from several distinct studies. The
    # repeat entries are left in the log rather than tidied away — quietly
    # collapsing them is the habit this record exists to prevent.
    test_idx = unlock_test(
        rows,
        f"human_baseline.py: sampling {n_items} held-out pairs (seed {seed}) to "
        "measure experienced marketers against the model on identical items",
    )

    X_te, y_te, t_te = d["X_test"], d["y_test"], d["t_test"]
    if len(X_te) != len(test_idx):
        raise SystemExit(
            f"dataset.npz test block has {len(X_te)} rows but the split has "
            f"{len(test_idx)}. They must be the same partition.")

    # Assert the ORDER matches, not merely the length. A length check would pass
    # on a permuted array and every label in this study would be attached to the
    # wrong headline — silently, and in the direction of nonsense results.
    target = np.array([rows[int(i)]["target"] for i in test_idx], dtype=np.float64)
    if not np.allclose(target, y_te.astype(np.float64), atol=1e-6):
        raise SystemExit(
            "dataset.npz test targets do not match the split order. "
            "Re-run pipeline/assemble_dataset.py before trusting this.")

    pairs = build_pairs(y_te, t_te, MIN_GAP, X_te)
    print(f"{len(pairs):,} copy-only test pairs available")

    rng = random.Random(seed)
    chosen = rng.sample(range(len(pairs)), min(n_items, len(pairs)))

    E = np.load(EMB)["E"]
    members, dim = load_ensemble()
    if E.shape[1] != dim:
        raise SystemExit(f"embeddings are {E.shape[1]}-dim, ranker wants {dim}")
    scores = score_embeddings(E[test_idx], members)

    # Balance positions EXACTLY rather than flipping a coin per item. Independent
    # flips at n=60 gave a 60/40 split, which is unremarkable for a coin and
    # still a real confound: any participant with a first-position preference
    # would inherit an edge from our RNG. Half the items show the winner first,
    # half second, and the assignment is shuffled so the pattern is not learnable.
    positions = [0] * (len(chosen) // 2) + [1] * (len(chosen) - len(chosen) // 2)
    rng.shuffle(positions)

    quiz, key = [], []
    for qi, pi in enumerate(chosen):
        # build_pairs returns (winner, loser) by construction.
        win_local, lose_local = int(pairs[pi][0]), int(pairs[pi][1])

        winner_position = positions[qi]
        first, second = (
            (win_local, lose_local) if winner_position == 0
            else (lose_local, win_local)
        )

        quiz.append({
            "id": qi,
            "a": rows[int(test_idx[first])]["headline"],
            "b": rows[int(test_idx[second])]["headline"],
        })
        key.append({
            "id": qi,
            "winner_position": winner_position,
            "model_pick": 0 if scores[first] > scores[second] else 1,
            "model_margin": abs(float(scores[first] - scores[second])),
            "true_gap": abs(float(y_te[win_local] - y_te[lose_local])),
        })

    os.makedirs(PROC, exist_ok=True)
    with open(QUIZ_JSON, "w", encoding="utf-8") as fh:
        json.dump({"seed": seed, "items": quiz}, fh, indent=1)
    with open(KEY_JSON, "w", encoding="utf-8") as fh:
        json.dump({"seed": seed, "n": len(key), "items": key}, fh, indent=1)
    write_quiz_html(quiz, seed)

    model_right = sum(1 for k in key if k["model_pick"] == k["winner_position"])
    lo, hi = wilson(model_right, len(key))
    print(f"\nwrote {len(quiz)} items")
    print(f"  quiz (no answers) : {QUIZ_HTML}")
    print(f"  key  (keep local) : {KEY_JSON}")
    print(f"\nModel on this subset: {model_right}/{len(key)} = "
          f"{model_right/len(key):.1%}  95% CI {lo:.1%}-{hi:.1%}")
    print("Participants are scored against this, not against the global 61.8%.")

    shown_second = sum(k["winner_position"] for k in key)
    print(f"Winner shown second in {shown_second}/{len(key)} items "
          f"({shown_second/len(key):.0%}) - balanced by construction.")

    # Recruitment target, stated before any data is collected.
    need = items_needed(0.50, model_right / len(key))
    people = math.ceil(need / len(key))
    print(f"\nPOWER, decided now rather than after the fact:")
    print(f"  To detect humans at 50% against the model at "
          f"{model_right/len(key):.0%} on these items needs about {need} "
          f"answered items at 80% power")
    print(f"  = {people} participants x {len(key)} items.")
    print(f"  Below that, a null result means the study was too small, not "
          f"that humans and the model are equal.")


def write_quiz_html(quiz: list[dict], seed: int) -> None:
    items = json.dumps(quiz, ensure_ascii=False)
    doc = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Headline judgement study</title>
<style>
 :root{--ink:#111;--muted:#787774;--rule:#eaeaea;--canvas:#fbfbfa;--surface:#fff}
 *{box-sizing:border-box}
 body{margin:0;background:var(--canvas);color:var(--ink);line-height:1.6;
   font-family:"SF Pro Display","Helvetica Neue",system-ui,sans-serif}
 main{max-width:44rem;margin:0 auto;padding:3rem 1.5rem 6rem}
 h1{font-family:Georgia,serif;font-weight:400;letter-spacing:-.02em;
   line-height:1.1;font-size:2rem;margin:0 0 1rem}
 p{color:var(--muted)}
 .bar{height:2px;background:var(--rule);margin:2rem 0}
 .bar>div{height:2px;background:var(--ink);width:0;transition:width .3s}
 button.opt{display:block;width:100%;text-align:left;background:var(--surface);
   border:1px solid var(--rule);border-radius:12px;padding:1.25rem 1.5rem;
   font:inherit;margin-bottom:.75rem;cursor:pointer;transition:border-color .15s}
 button.opt:hover{border-color:var(--ink)}
 .meta{font-family:ui-monospace,monospace;font-size:.75rem;color:var(--muted);
   letter-spacing:.08em;text-transform:uppercase}
 textarea{width:100%;height:11rem;font-family:ui-monospace,monospace;
   font-size:.75rem;border:1px solid var(--rule);border-radius:8px;padding:1rem}
 .done{background:var(--surface);border:1px solid var(--rule);
   border-radius:12px;padding:2rem}
</style></head><body><main>
<div id="intro">
 <h1>Which headline got more clicks?</h1>
 <p>Each screen shows two real headlines that ran as a randomised A/B test on
 the same article, at the same moment, to the same audience. Exactly one won.</p>
 <p>Pick the one you believe got the higher click-through rate. Go with your
 professional instinct — there is no penalty for being wrong, and a realistic
 result is far more useful to us than a flattering one. Roughly ten minutes.</p>
 <p><strong>Please do not look anything up.</strong> We are measuring judgement,
 not search skill.</p>
 <button class="opt" onclick="start()"><strong>Begin</strong></button>
</div>
<div id="quiz" hidden>
 <div class="meta" id="progress"></div>
 <div class="bar"><div id="fill"></div></div>
 <div id="opts"></div>
 <p class="meta" id="skip" style="cursor:pointer">No idea &mdash; skip this one</p>
</div>
<div id="end" hidden class="done">
 <h1>Done &mdash; thank you</h1>
 <p>Copy everything in the box and send it back. It contains your answers and
 nothing else: no name, no email, nothing about your device.</p>
 <textarea id="out" readonly onclick="this.select()"></textarea>
 <p><button class="opt" onclick="dl()"><strong>Download instead</strong></button></p>
</div>
</main><script>
const ITEMS=__ITEMS__, SEED=__SEED__;
let i=0; const answers=[];
function start(){document.getElementById('intro').hidden=true;
 document.getElementById('quiz').hidden=false; render();}
function render(){
 if(i>=ITEMS.length) return finish();
 const it=ITEMS[i];
 document.getElementById('progress').textContent=`Item ${i+1} of ${ITEMS.length}`;
 document.getElementById('fill').style.width=(100*i/ITEMS.length)+'%';
 const o=document.getElementById('opts'); o.innerHTML='';
 [it.a,it.b].forEach((text,choice)=>{
   const b=document.createElement('button');
   b.className='opt'; b.textContent=text;
   b.onclick=()=>{answers.push({id:it.id,choice:choice});i++;render();};
   o.appendChild(b);
 });
}
document.getElementById('skip').onclick=()=>{
 answers.push({id:ITEMS[i].id,choice:null});i++;render();};
function payload(){return JSON.stringify({seed:SEED,n:ITEMS.length,
 answers:answers},null,1);}
function finish(){document.getElementById('quiz').hidden=true;
 const e=document.getElementById('end'); e.hidden=false;
 document.getElementById('out').value=payload();}
function dl(){const b=new Blob([payload()],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(b);
 a.download='headline-study-response.json';a.click();}
</script></body></html>
"""
    doc = doc.replace("__ITEMS__", items).replace("__SEED__", str(seed))
    with open(QUIZ_HTML, "w", encoding="utf-8") as fh:
        fh.write(doc)


# -------------------------------------------------------------------- score

def score(paths: list[str]) -> None:
    with open(KEY_JSON, encoding="utf-8") as fh:
        key_file = json.load(fh)
    key = {k["id"]: k for k in key_file["items"]}

    files = [p for pat in paths for p in sorted(glob.glob(pat))]
    if not files:
        raise SystemExit(f"no response files matched: {paths}")

    all_human, all_model, per_person = [], [], []
    b_total = c_total = 0

    for path in files:
        with open(path, encoding="utf-8") as fh:
            resp = json.load(fh)
        if resp.get("seed") != key_file["seed"]:
            raise SystemExit(
                f"{os.path.basename(path)} was generated from seed "
                f"{resp.get('seed')}, key is seed {key_file['seed']}. "
                "Answers and items would not line up.")

        h_right = m_right = answered = b = c = 0
        for a in resp["answers"]:
            if a["choice"] is None:            # skipped
                continue
            k = key[a["id"]]
            answered += 1
            hit_h = a["choice"] == k["winner_position"]
            hit_m = k["model_pick"] == k["winner_position"]
            h_right += hit_h
            m_right += hit_m
            if hit_h and not hit_m:
                b += 1
            elif hit_m and not hit_h:
                c += 1
            all_human.append(hit_h)
            all_model.append(hit_m)

        b_total += b
        c_total += c
        per_person.append((os.path.basename(path), h_right, m_right, answered))

    print(f"{'participant':<34}{'human':>10}{'model':>10}{'n':>6}")
    for name, h, m, n in per_person:
        print(f"{name:<34}{h/n:>9.1%}{m/n:>10.1%}{n:>6}")

    n = len(all_human)
    h_right = sum(all_human)
    m_right = sum(all_model)
    h_lo, h_hi = wilson(h_right, n)
    m_lo, m_hi = wilson(m_right, n)
    p = mcnemar_exact(b_total, c_total)

    print(f"\nPOOLED over {len(files)} participant(s), {n} answered items")
    print(f"  humans {h_right}/{n} = {h_right/n:.1%}  95% CI {h_lo:.1%}-{h_hi:.1%}")
    print(f"  model  {m_right}/{n} = {m_right/n:.1%}  95% CI {m_lo:.1%}-{m_hi:.1%}")
    print(f"\n  discordant: human-only right {b_total}, model-only right {c_total}")
    print(f"  McNemar exact two-sided p = {p:.4f}")

    print("\nREADING THIS")
    if h_lo <= 0.5 <= h_hi:
        print("  Human accuracy is not distinguishable from chance.")
    elif h_lo > 0.5:
        print("  Humans are better than chance.")
    else:
        print("  Humans are WORSE than chance — check for an inverted key "
              "before believing it.")

    if p < 0.05:
        better = "model" if c_total > b_total else "humans"
        print(f"  The {better} are better on the same items (p = {p:.4f}).")
    else:
        print(f"  No significant difference between human and model on these "
              f"items (p = {p:.4f}).")
        if n < 100:
            print(f"  With n={n} that is weak evidence of similarity, not "
                  "evidence of no difference. Collect more before concluding.")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="sample pairs and write the quiz")
    b.add_argument("--n", type=int, default=60)
    b.add_argument("--seed", type=int, default=7)
    s = sub.add_parser("score", help="score response files against the key")
    s.add_argument("responses", nargs="+")
    args = ap.parse_args()

    if args.cmd == "build":
        build(args.n, args.seed)
    else:
        score(args.responses)


if __name__ == "__main__":
    main()
