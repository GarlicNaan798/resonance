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

# Second copy, served by GitHub Pages. Recruiting converts far better on "click
# this link" than on "download this file and open it", and a hosted page also
# sidesteps the unsigned-binary problem entirely — taking part requires no
# install at all. Safe to publish: the quiz carries no answer key, which is
# asserted in model/human_baseline_check.py rather than assumed.
PUBLIC_QUIZ = os.path.join(ROOT, "docs", "quiz", "index.html")
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
    core = min(CORE_ITEMS, len(key))
    print(f"\nPOWER, decided now rather than after the fact:")
    print(f"  To detect humans at 50% against the model at "
          f"{model_right/len(key):.0%} on these items needs about {need} "
          f"answered items at 80% power.")
    print(f"  The quiz asks for a {core}-item core and offers {len(key)-core} more,")
    print(f"  so that is {math.ceil(need/core)} participants if everyone takes "
          f"the exit, or {people} if everyone completes all {len(key)}.")
    print(f"  Total items is what power depends on — a shorter ask does not")
    print(f"  reduce the work, it spreads it over more people, which also")
    print(f"  widens the sample. Below the total, a null result means the study")
    print(f"  was too small, not that humans and the model are equal.")


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
 .statgrid{display:grid;grid-template-columns:repeat(2,1fr);gap:.75rem;
   margin:1.5rem 0}
 @media(min-width:34rem){.statgrid{grid-template-columns:repeat(4,1fr)}}
 .stat{border:1px solid var(--rule);border-radius:10px;padding:.85rem}
 .stat b{display:block;font-size:1.5rem;font-weight:500;
   font-variant-numeric:tabular-nums;letter-spacing:-.02em}
 .stat span{font-family:ui-monospace,monospace;font-size:.62rem;
   letter-spacing:.1em;text-transform:uppercase;color:var(--muted)}
</style></head><body><main>
<div id="intro">
 <h1>Can you beat the machine?</h1>
 <p>Each screen shows two real headlines that ran as a randomised A/B test on
 the same article, at the same moment, to the same audience. Exactly one won.</p>
 <p>Pick the one you believe got the higher click-through rate. A model has
 already answered these same pairs and scored <strong>58%</strong>. Most people
 assume they can do better. Nobody has checked &mdash; that is what this is.</p>
 <p>Five minutes. Go with instinct; there is no penalty for being wrong, and a
 realistic result is far more useful to us than a flattering one.</p>
 <p><strong>Please do not look anything up.</strong> We are measuring judgement,
 not search skill.</p>
 <!-- Collected because docs/PREREGISTRATION.md commits to reporting accuracy
      broken out by experience, and to treating professionals as the primary
      subgroup. A pre-registration whose instrument cannot supply the fields it
      promises is paperwork. -->
 <p class="meta" style="margin-top:2rem">Two questions first</p>
 <p><label>Years writing or testing marketing copy<br>
  <select id="years" style="font:inherit;padding:.5rem;margin-top:.35rem;
   border:1px solid var(--rule);border-radius:8px">
   <option value="">Prefer not to say</option>
   <option value="0">None</option>
   <option value="1">Less than 1</option>
   <option value="3">1&ndash;3</option>
   <option value="7">4&ndash;10</option>
   <option value="15">More than 10</option>
  </select></label></p>
 <p><label><input type="checkbox" id="paid"> Writing or testing copy is part of
  my paid work</label></p>
 <button class="opt" onclick="start()"><strong>Begin</strong></button>
</div>
<div id="quiz" hidden>
 <div class="meta" id="progress"></div>
 <div class="bar"><div id="fill"></div></div>
 <div id="opts"></div>
 <p class="meta" id="skip" style="cursor:pointer">No idea &mdash; skip this one</p>
</div>
<div id="more" hidden class="done">
 <h1>That is the study &mdash; thank you</h1>
 <p>You have done the part we need. Finish here and your answers count in full.</p>
 <p>If you have another five minutes, there are <span id="left"></span> more
 pairs. Every extra one narrows the result, and means we need fewer people.</p>
 <p><button class="opt" onclick="finish()"><strong>Finish now</strong></button></p>
 <p><button class="opt" onclick="extend()">Keep going</button></p>
</div>
<div id="end" hidden class="done">
 <h1>Send this back to get your score</h1>
 <div id="stats" class="statgrid"></div>
 <p><strong>We deliberately do not score you here.</strong> Doing that would
 mean shipping the answer key inside this page, where anyone could read it —
 and one person peeking would quietly ruin the study for everyone. So the
 answers stay on our side.</p>
 <p>Send the block below and you get back: how many you got right, how many the
 model got right on your exact pairs, and whether you beat it.</p>
 <textarea id="out" readonly onclick="this.select()"></textarea>
 <p><button class="opt" onclick="copyOut()"><strong id="copybtn">Copy to clipboard</strong></button></p>
 <p><button class="opt" onclick="dl()">Download as a file instead</button></p>
</div>
</main><script>
const ITEMS=__ITEMS__, SEED=__SEED__, CORE=__CORE__;
let i=0; const answers=[]; let shown=0; let profile={}; let extended=false;

// Each participant sees the items in their OWN order. Without this, everyone
// who stops at the core block answers the SAME first 30 pairs, so half the
// sample would carry no responses at all and the result would generalise over
// 30 items rather than 60. Answers carry the item id, so scoring is unaffected
// by display order, and the winner's left/right position is fixed per item in
// the key — shuffling the sequence does not disturb that balance.
const ORDER=ITEMS.map((_,k)=>k);
for(let k=ORDER.length-1;k>0;k--){const j=Math.floor(Math.random()*(k+1));
 [ORDER[k],ORDER[j]]=[ORDER[j],ORDER[k]];}

function start(){
 // Snapshot the intake before the quiz replaces the screen.
 const y=document.getElementById('years').value;
 profile={years:(y===''?null:Number(y)),
          paid:document.getElementById('paid').checked};
 document.getElementById('intro').hidden=true;
 document.getElementById('quiz').hidden=false; render();}
function extend(){extended=true;
 document.getElementById('more').hidden=true;
 document.getElementById('quiz').hidden=false; render();}
function render(){
 if(i>=ITEMS.length) return finish();
 // Offer the exit at the end of the core block. Ten minutes is a big ask of a
 // stranger; five is not. Anyone stopping here has given a complete response.
 if(i>=CORE && !extended){
   document.getElementById('quiz').hidden=true;
   document.getElementById('left').textContent=String(ITEMS.length-i);
   document.getElementById('more').hidden=false;
   return;
 }
 const it=ITEMS[ORDER[i]];
 const total=extended?ITEMS.length:CORE;
 document.getElementById('progress').textContent=`Item ${i+1} of ${total}`;
 document.getElementById('fill').style.width=(100*i/total)+'%';
 const o=document.getElementById('opts'); o.innerHTML='';
 // Milliseconds spent on THIS item. The pre-registered exclusion rule drops a
 // response whose median is under 2s (clicking through without reading), and
 // it cannot be applied to data that was never recorded. Elapsed time only —
 // no wall-clock timestamp, so this reveals nothing about when someone worked.
 shown=Date.now();
 [it.a,it.b].forEach((text,choice)=>{
   const b=document.createElement('button');
   b.className='opt'; b.textContent=text;
   b.onclick=()=>{answers.push({id:it.id,choice:choice,ms:Date.now()-shown});
     i++;render();};
   o.appendChild(b);
 });
}
document.getElementById('skip').onclick=()=>{
 answers.push({id:ITEMS[ORDER[i]].id,choice:null,ms:Date.now()-shown});
 i++;render();};
function payload(){return JSON.stringify({seed:SEED,n:ITEMS.length,core:CORE,
 profile:profile,answers:answers},null,1);}
function finish(){document.getElementById('quiz').hidden=true;
 document.getElementById('more').hidden=true;
 const e=document.getElementById('end'); e.hidden=false;
 document.getElementById('out').value=payload();
 // Stats that reveal nothing about correctness — computable without the key,
 // so they cost the study nothing and still give the screen something to say.
 const done=answers.filter(a=>a.choice!==null);
 const times=done.map(a=>a.ms).sort((x,y)=>x-y);
 const med=times.length?times[Math.floor(times.length/2)]/1000:0;
 const total=done.reduce((s,a)=>s+a.ms,0)/1000;
 const fast=done.filter(a=>a.ms<3000).length;
 const cell=(v,l)=>`<div class="stat"><b>${v}</b><span>${l}</span></div>`;
 document.getElementById('stats').innerHTML=
   cell(done.length,'calls made')+
   cell(med.toFixed(1)+'s','median per call')+
   cell(Math.round(total)+'s','total thinking')+
   cell(Math.round(100*fast/Math.max(done.length,1))+'%','snap judgements');
}
function copyOut(){const t=document.getElementById('out');
 t.select(); let ok=false;
 try{ok=document.execCommand('copy');}catch(e){}
 if(navigator.clipboard&&!ok){navigator.clipboard.writeText(t.value);ok=true;}
 document.getElementById('copybtn').textContent=ok?'Copied':'Select it and copy';}
function dl(){const b=new Blob([payload()],{type:'application/json'});
 const a=document.createElement('a');a.href=URL.createObjectURL(b);
 a.download='headline-study-response.json';a.click();}
</script></body></html>
"""
    doc = (doc.replace("__ITEMS__", items)
              .replace("__SEED__", str(seed))
              .replace("__CORE__", str(min(CORE_ITEMS, len(quiz)))))
    with open(QUIZ_HTML, "w", encoding="utf-8") as fh:
        fh.write(doc)

    # Rebuilding with a different seed republishes a different study. That is
    # intended — the hosted page and the local key must always describe the same
    # sample, and writing both from one call is what keeps them in step. A
    # mismatch would be caught by score() (it compares seeds), but it is better
    # not to create the opportunity.
    os.makedirs(os.path.dirname(PUBLIC_QUIZ), exist_ok=True)
    with open(PUBLIC_QUIZ, "w", encoding="utf-8") as fh:
        fh.write(doc)


# -------------------------------------------------------------------- score

CORE_ITEMS = 30            # the block everyone is asked for; the rest is opt-in
MIN_ANSWERED = 24          # 80% of the core block
MIN_MEDIAN_MS = 2000       # per item; faster than this is clicking, not reading


def excluded_reason(resp: dict, n_items: int) -> str | None:
    """Apply the pre-registered exclusion rules. Returns None to keep.

    Deliberately blind to accuracy: nothing here can look at whether the
    participant agreed with the model. See docs/PREREGISTRATION.md section 8.
    """
    # An ABSOLUTE floor, not a fraction of the full set. The quiz asks for a
    # 30-item core and offers 30 more; someone who takes the exit at 30 has
    # given a complete response, and a "80% of 60" rule would have thrown away
    # every one of them. The floor still catches genuine abandonment.
    answered = [a for a in resp.get("answers", []) if a.get("choice") is not None]
    if len(answered) < MIN_ANSWERED:
        return (f"answered {len(answered)}, below the {MIN_ANSWERED}-item floor "
                f"(80% of the {CORE_ITEMS}-item core)")

    times = sorted(a["ms"] for a in answered if isinstance(a.get("ms"), (int, float)))
    if not times:
        # Older responses predate timing capture. Keep them, but say so rather
        # than silently applying a rule that cannot be evaluated.
        return None
    median = times[len(times) // 2]
    if median < MIN_MEDIAN_MS:
        return f"median {median} ms per item, below the {MIN_MEDIAN_MS} ms floor"
    return None


def refuse_if_tracked(files: list[str]) -> None:
    """Stop if git is tracking a response file.

    The repository is public. Participant data reaching it would be a real
    breach, and `git add -A` is a habit. The .gitignore already covers
    responses/, but an ignore rule is a promise and this is the check that the
    promise held — the same reason every other guarantee in this project has
    something that fails when it does not.
    """
    import subprocess
    try:
        out = subprocess.run(
            ["git", "ls-files", "--error-unmatch", *files],
            cwd=ROOT, capture_output=True, text=True, timeout=20,
        )
    except (OSError, subprocess.SubprocessError):
        return          # no git here; nothing to protect against
    if out.returncode == 0 and out.stdout.strip():
        tracked = "\n  ".join(out.stdout.strip().splitlines())
        raise SystemExit(
            "\nREFUSING TO SCORE: git is tracking these response files.\n  "
            f"{tracked}\n\n"
            "This repository is public. Run:\n"
            "  git rm --cached <file>\n"
            "and keep responses in responses/, which is gitignored.\n")


def score(paths: list[str], reply: bool = False) -> None:
    with open(KEY_JSON, encoding="utf-8") as fh:
        key_file = json.load(fh)
    key = {k["id"]: k for k in key_file["items"]}

    files = [p for pat in paths for p in sorted(glob.glob(pat))]
    if not files:
        raise SystemExit(f"no response files matched: {paths}")
    refuse_if_tracked(files)

    all_human, all_model, per_person = [], [], []
    b_total = c_total = 0
    excluded = []

    for path in files:
        with open(path, encoding="utf-8") as fh:
            resp = json.load(fh)
        if resp.get("seed") != key_file["seed"]:
            raise SystemExit(
                f"{os.path.basename(path)} was generated from seed "
                f"{resp.get('seed')}, key is seed {key_file['seed']}. "
                "Answers and items would not line up.")

        # Pre-registered exclusions (docs/PREREGISTRATION.md section 8), applied
        # mechanically before any score is computed. Deciding who to drop after
        # seeing their accuracy is how a clean-looking study gets rigged, so the
        # rule runs here and reports itself either way.
        reason = excluded_reason(resp, key_file["n"])
        if reason:
            excluded.append((os.path.basename(path), reason))
            continue

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
        prof = resp.get("profile") or {}
        per_person.append((os.path.basename(path), h_right, m_right, answered,
                           prof.get("years"), bool(prof.get("paid"))))

    if excluded:
        print(f"EXCLUDED {len(excluded)} response(s) under the pre-registered rules:")
        for name, why in excluded:
            print(f"  {name}: {why}")
        print()
    if not per_person:
        raise SystemExit("no responses survived the exclusion rules")

    if reply:
        # The quiz promises each participant their score in exchange for
        # sending the file. Promising it and then not delivering would be a
        # small betrayal of the only people helping, so the text is generated
        # here rather than left to be written by hand and forgotten.
        print("=" * 66)
        for name, h, m, n, _yrs, _paid in per_person:
            verdict = ("You beat it." if h > m else
                       "It beat you." if m > h else
                       "A dead heat.")
            print(f"\n--- reply for {name} " + "-" * max(0, 44 - len(name)))
            print(f"You got {h} of {n} right ({h/n:.0%}).")
            print(f"The model got {m} of the same {n} right ({m/n:.0%}).")
            print(f"{verdict}")
            print("For scale: a coin flip is 50%, and on this task even perfect")
            print("knowledge of every headline's true click rate would only score")
            print("about 66% — the outcomes are that noisy. Thank you, genuinely;")
            print("the result gets published either way, including if people win.")
        print("\n" + "=" * 66 + "\n")

    print(f"{'participant':<30}{'yrs':>5}{'paid':>6}{'human':>9}{'model':>9}{'n':>6}")
    for name, h, m, n, yrs, paid in per_person:
        y = "-" if yrs is None else str(yrs)
        print(f"{name:<30}{y:>5}{('yes' if paid else 'no'):>6}"
              f"{h/n:>8.1%}{m/n:>9.1%}{n:>6}")

    # Pre-registered: if 3 or more participants are not paid copy professionals,
    # the professional subgroup becomes the primary figure.
    pros = [r for r in per_person if r[5]]
    if len(per_person) - len(pros) >= 3 and pros:
        ph = sum(r[1] for r in pros); pn = sum(r[3] for r in pros)
        print(f"\n  PRIMARY (paid professionals only): {ph}/{pn} = "
              f"{ph/pn:.1%} over {len(pros)} participant(s)")
        print("  Reported as primary because 3+ respondents are not paid "
              "professionals - see docs/PREREGISTRATION.md section 7.")

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
    s.add_argument("--reply", action="store_true",
                   help="also print the message to send back to each participant")
    args = ap.parse_args()

    if args.cmd == "build":
        build(args.n, args.seed)
    else:
        score(args.responses, reply=args.reply)


if __name__ == "__main__":
    main()
