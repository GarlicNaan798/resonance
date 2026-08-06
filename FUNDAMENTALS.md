# Resonance — Project Fundamentals

Last updated: 2026-08-05

The single document to read before working on, selling, or evaluating this
system. It records what the product is, what the evidence supports, what it must
never claim, and every result — including the negative ones, which are the most
useful part.

---

## 1. What this is

A decision aid for marketing teams. Given campaign copy it produces two
**independent** outputs:

1. **A ranking prediction** — of two or more variants, which is likelier to
   perform better. From a ranker over sentence embeddings.
2. **A diagnostic profile** — six behavioural-science scores, computed from
   published human word ratings, optionally conditioned on audience.

**These layers are separate and must be presented separately.** The diagnostic
profile does *not* explain the ranking prediction — the ranker does not use
those features. Presenting one as the other is post-hoc rationalisation and is
the most likely way this product would lose credibility with a technical buyer.

## 2. Headline numbers

Held-out test set, opened exactly once. Chance = 0.500.

| Metric | Value |
|---|---|
| Embedding ranker | **0.5942** (95% CI 0.5839–0.6044) |
| Module model (diagnostic) | **0.5346** (95% CI 0.5241–0.5452) |
| **Measured oracle ceiling** | **0.7880** |
| Signal captured | ~33% of achievable |
| Evaluated on | 2,665 experiments / 20,452 copy-only pairs |

**The ceiling is the number people miss.** Labels are noisy estimates — the
median arm had 3,118 impressions and 42 clicks — so a model with *perfect*
knowledge of every headline's true click rate would still only agree with the
recorded labels 78.8% of the time. Read every accuracy figure against 0.788, not
against 1.00.

Practically: given two variants where one genuinely performed better, the model
picks correctly ~59 times in 100. Out of 10 A/B choices, roughly 6 right instead
of 5.

## 3. What it must never claim

Enforced in code as `PROHIBITED_CLAIMS` in `resonance/lib/constructs.ts`.

- Predicting conversion rates, revenue or ROI from copy
- Measuring or predicting neurotransmitters, hormones or brain states
- Reading, scanning or simulating an individual person's brain
- Replacing A/B testing
- Any accuracy figure above the 0.788 measured ceiling

**Outcome prediction is not achievable on this data.** R² ≈ 0.01 — including for
an *unconstrained* 512-unit network. That is a property of the task, not a
limitation of the architecture.

**We have never measured against human baseline.** The natural pitch line
("beats copywriter intuition") is not evidenced. Earning it is cheap: show ~200
held-out pairs to experienced marketers and score them identically. Until then,
the honest answer to "better than my creative director?" is *"we haven't tested
that."*

## 4. The six modules

Named for the functional systems the literature associates with each construct.
That is an association for naming, **not a measurement of neural activity**.

| Module | Construct | Functional referent |
|---|---|---|
| Salience | attention capture | anterior insula / dorsal ACC |
| Affect | affective arousal | amygdala |
| Valuation | subjective value | vmPFC / ventral striatum |
| Encoding | memory encoding | hippocampus / MTL |
| Approach | approach–avoidance | frontal alpha asymmetry |
| Control | processing fluency | dlPFC |

**Deliberately excluded:** MacLean's triune brain (reptilian/limbic/neocortex)
and left/right hemisphere dominance. Both appear in the source papers for this
project and both are discredited as neuroscience. They must not appear in
customer-facing copy.

**Open validation gap:** the `approach` module rests on frontal alpha asymmetry
taken from the literature, never validated against measured EEG here. If NeuMa
validation fails, the module gets a purely behavioural name.

### Research constraints, enforced by construction

Five findings are hard-wired as reparameterisations, so they hold exactly at
every training step rather than being encouraged by a penalty:

| | Constraint | Source |
|---|---|---|
| C1 | arousal → outcome is **inverted-U** | Yerkes–Dodson |
| C2 | arousal **enhances** encoding (gate ≥ 0) | Cahill & McGaugh |
| C3 | attention **gates** valuation | Krajbich et al. |
| C4 | fluency → evaluation **increasing** | Reber et al. |
| C5 | cognitive load → outcome **decreasing** | load literature |

Verified adversarially: forcing every raw parameter to −50 leaves all signs
intact. The data cannot argue the model into claiming that more cognitive load
helps.

## 5. Data

**Training:** Upworthy Research Archive — 32,487 randomised A/B tests, 150,624
arms after filtering to ≥500 impressions.

Randomisation is why this dataset was chosen over ad-library data: arms within
one test share article, image and publication moment, so the within-test
contrast isolates the effect of the *words*. Observational ad data cannot
support that inference.

**Target:** within-test log-odds contrast, Haldane–Anscombe corrected, weighted
by inverse variance.

**Norms:** Warriner et al. (2013) VAD for 13,905 words including demographic
splits; Brysbaert et al. (2014) concreteness for 39,954 words.

**Also collected but not used for training:** 18,100 ad creatives (no outcome
labels); Google Ads Transparency bundle (spend/impressions/longevity/targeting
but **no ad text** — creatives are archived as images).

## 6. Leakage controls

The corpus was **49% exact duplicates**, and 89% of ads sat in near-duplicate
clusters. A random split would have put an exact copy of nearly every test item
into training.

- Split unit is the **group**: transitive closure over shared test-id *and*
  shared headline. Test-id alone leaks, because ~50% of headlines recur.
- Verified: no index, group or headline string crosses a split.
- Test set SHA-256 fingerprinted and locked.
- Feature standardisation fitted on **training data only**.
- **Copy-only pairs**: Upworthy varied headline × image, so 48% of raw pairs
  differ only by picture. Those are unpredictable from text by construction and
  are excluded. Including them once produced a spurious *below-chance* result.
- Ties score 0.5, not 0.
- Shuffled-label control throughout; its deviation from chance (~0.018–0.023)
  is the noise floor every claimed gain must exceed.

## 7. Negative results

The most valuable section. Four hypotheses tested honestly and rejected.

**Feature engineering round 1 (v2, +28 features).** Discrete emotion, curiosity
gap, self-reference, word frequency, social proof — all cited, all
theory-motivated. Result: **−0.0009**.

**Feature engineering round 2 (v3, +8 features).** Identifiable-victim effect
and narrative markers, derived from reading actual disagreement pairs. Result:
**+0.0057** against a 0.0232 noise floor. Discarded under a pre-registered
threshold.

**Pairwise interaction.** Feeding `[a, b, a−b, a·b]` instead of scoring headlines
independently. Result: **−0.0038**. The bi-encoder was not the bottleneck — and
since those terms approximate cross-encoder attention, that is cheap evidence a
full cross-encoder would not repay its compute.

**Larger encoder (mpnet-base, 768d vs MiniLM 384d).** Unpaired comparison
suggested +0.0215, apparently clearing the 0.02 bar. A **paired** test — correct,
because both models score the same experiments — gave **+0.0128, CI [−0.0119,
+0.0375]**, P(gain > 0.02) = 0.28. Kept MiniLM and avoided a 5× inference cost
for noise.

**What these add up to:** interpretable psycholinguistic features plateau around
0.56; semantic embeddings reach 0.62. A disagreement analysis found no
interpretable feature separating the two by more than 0.11 SD, and indicated the
residual signal is concrete subject matter rather than style. **The gap is
semantic content that psycholinguistic norms cannot represent.**

**Encoder fine-tuning (the last untried lever).** Unfroze the final transformer
layer plus the ranking head — 8.1% of parameters — warm-started from a
frozen-embedding head trained on the same split. Baseline 0.5958 [0.5766,
0.6150]; fine-tuned 0.6011 [0.5820, 0.6201]. **Gain +0.0053**, below the 0.02
threshold. Kept frozen embeddings.

Stated precisely, because the distinction matters: this was *partial*
fine-tuning, 6,000 pairs, 2 epochs, CPU-timeboxed. A full fine-tune over all
93,000 pairs on a GPU might do better. The honest claim is **"not demonstrated
with the compute available"**, not "fine-tuning does not work".

### Three invalid experiments, recorded so they are not repeated

The fine-tuning measurement took four attempts. Each of the first three produced
a plausible-looking number from a broken setup:

| Run | Baseline | Reported gain | What was actually wrong |
|---|---|---|---|
| 1 | 0.5052 (chance) | −0.0016 | Random head init; loss frozen at ln(2) — never trained |
| 2 | 0.4926 (chance) | +0.0103 | Subset-local pair indices used against the global headline array |
| 3 | **0.8315** | −0.1393 | Warm start from a model fit on train+val, evaluated on data carved from train |
| 4 | 0.5958 | +0.0053 | valid |

Runs 1 and 3 would both have entered the record as findings.

**What caught every one of them was checking the baseline, not the delta.** Two
tells, now enforced as hard aborts in `finetune_encoder.py`:

- **Baseline near chance** → the model or the plumbing is broken; any delta is
  noise on noise.
- **Baseline above the 0.788 oracle ceiling** → arithmetically impossible on
  held-out data, so the evaluation set has leaked into training.

That second check is worth dwelling on. The ceiling was computed to keep
accuracy claims honest in reporting; it turned out to be a **leak detector**, and
it caught a train/test contamination that no unit test would have found. Any
project with a measurable performance ceiling should assert against it in code.

The generalisable rule: **a negative result is only informative when the
machinery demonstrably worked.** Flat loss, chance baseline, or an
above-ceiling baseline all mean the experiment failed — not the hypothesis.

### Simulated tenant validation (Phase 4 de-risking) — inconclusive

Two attempts to demonstrate that per-tenant recalibration beats the global
model, using splits inside Upworthy as a stand-in for client data:

**Temporal split** — no gain at any tenant size. Uninformative: the filtered
corpus spans 2014-06 to 2014-11, five months of one publisher, so there was
essentially no drift to adapt to.

**Topic split** — k-means over embeddings, most distinctive cluster held out as
the tenant. All five deltas positive (+0.0013 to +0.0102), which is mildly
suggestive, but the average is +0.007 against a 0.02 noise floor and there is
**no dose-response**: 2,001 tenant arms performed worse than 200.

**Conclusion: Phase 4 is not de-risked.** Recalibration may well help a client
whose copy is unlike viral media, but that cannot be demonstrated with one
publisher's data, and building a database plus auth layer on an undemonstrated
premise is the wrong order of work.

## 8. Audience and demographics

The founding premise was demographic-specific insight. Here is exactly how far
the evidence goes.

**No dataset here links copy to outcome by demographic.** Upworthy recorded what
ran and how it did, never who saw it. So the model's audience gains were never
fitted and sat at zero initialisation.

**Per-word demographic norms are noise.** Warriner splits every word by
gender/age/education, which invites per-word audience lookups. Measured:

| | |
|---|---|
| per-word gender difference in valence | mean +0.127, **SD 0.874** |
| SD predicted by rating noise alone | 0.57–0.90 |

The spread is fully explained by small subgroup rater counts. Men and women are
not disagreeing about individual words. **Only the lexicon-wide mean shift
survives** (SE ≈ 0.007 across 13,905 words): gender arousal +0.285 (d = 0.32),
age +0.182, education −0.139.

**Segment priors (`resonance/lib/segments.ts`)** therefore encode published
findings, bounded to ±15%, labelled as priors:

- **Involvement** (Petty & Cacioppo, ELM) — *the best-supported prior*. Note ELM
  is moderated by involvement and need for cognition, **not by demographics**;
  "education → central route" is unsupported (NFC–education r ≈ 0.2–0.3). So
  involvement is a first-class marketer input.
- **Positivity effect** (Carstensen & Mikels; meta-analysis d ≈ 0.25) — older
  audiences favour positive framing.
- **Arousal rating differences** — flagged **low confidence**, because a rating
  difference is not a demonstrated behavioural difference.

### Measured impact (C12) — read this honestly

Ranking flips on dev data, against a ~2% noise floor:

| Segment | Flip rate |
|---|---|
| involvement (high/low) | 2.12% / 2.21% |
| age | 0.81% – 1.31% |
| gender | 0.68% / 0.79% |
| education | 0.47% / 0.49% |
| all four combined | 2.93% – 3.71% |

**The demographic axes individually fall below the noise floor.** The prior that
actually moves the model is **involvement — which is not demographic**. Stated
plainly: today's demographic conditioning is close to explanatory framing, and
the honest fix is client data, not better theory.

**The real path:** Meta and Google already report performance broken down by age
bracket and gender. A client's export supplies `(copy, segment, impressions,
clicks)` — enough to *fit* segment gains rather than assume them. That converts
priors into measurement per tenant, and is the product's actual moat.

## 8a. Calibrated abstention — the largest product gain

The headline 59.4% is an average that hides real structure: the model is far
more reliable when variants are far apart in score. Measured on dev pairs
(`model/calibrate_abstention.py`):

| Coverage | Accuracy | 95% CI |
|---|---|---|
| 100% (answer everything) | 0.6001 | 0.588–0.612 |
| 50% | 0.6601 | 0.644–0.677 |
| 25% | 0.7084 | 0.688–0.729 |
| 10% | 0.7672 | 0.739–0.795 |
| 5% | 0.8059 | 0.771–0.841 |

**+20.6 points from abstaining alone** — no new data, no new compute, no model
change. The product now answers the confident quarter at ~71% and says "we
cannot tell" on the rest, rather than answering everything at 60%.

**Any figure from this table must be quoted with its coverage.** "80% accurate
on the 5% of comparisons we answer" is honest; "80% accurate" is not.

Why an accuracy above the 78.8% ceiling is not a contradiction: the ceiling was
measured across ALL pairs. Confident pairs correlate with larger true
differences, which carry a higher ceiling of their own (92.6% at |gap| ≥ 0.5).
Abstention implicitly selects less-noisy comparisons, not just ones the model
likes.

**Side effect worth noting:** the calibrated threshold (margin ≥ 1.203) is far
stricter than the arbitrary 0.15 used before. The "URGENT!!! SLASH YOUR
BILLS!!!" case that previously produced a confident recommendation now correctly
abstains at margin 0.74 — the model was never confident about it; the old
threshold was simply too permissive.

## 9. Data protection

- **PII rejected at ingest**, never stored and redacted — redaction still lets
  raw values transit logs, backups and stack traces.
- **No heuristic name detection**: any detector catching "Sarah Chen" also flags
  "Ray-Ban" and "Oscar Health". Names are excluded by upload schema instead.
- Findings carry kind and position, **never the value** — tested.
- **Tenant isolation is structural**: a query cannot be built without a tenant
  context; `tenantId` is stamped on insert, not accepted from the caller.
- **Audit log is append-only and hash-chained**; tampering is detectable, and
  campaign content never enters it.
- Config **fails startup** on an unsafe combination. Transit encryption cannot
  be disabled; EU regions reject cross-region replication; retention capped at
  730 days.
- Self-hosting makes **no outbound calls**; encoder weights are baked in at
  build time so the claim is verifiable with `--network none`.

## 10. Engineering invariants

- **Test set opened twice total**, both times pre-registered. Validation was
  evaluated ~10 times and is optimistically biased — both models fell ~3 points
  from val to test, exactly as predicted.
- **TS/PyTorch parity to 1e-4**, 8 fixtures, covering score and all six module
  activations. Two things that would have silently broken it: PyTorch's default
  GELU is the exact erf form, and LayerNorm uses biased variance.
- Constrained values are exported **post-constraint**; the TS port never
  reapplies softplus, because re-deriving a sign is how a port inverts a
  documented effect.
- Capacity ratio 0.45 params per independent training item.
- 102 tests passing.

## 11. Environment notes

- **PyTorch imports only under PowerShell**, not Git Bash — Git Bash mangles the
  DLL search path. All model commands must run in PowerShell.
- Windows console is cp1252; non-ASCII in `print()` crashes scripts.
- `data/` sits inside OneDrive and syncs. It is gitignored, and the corpora are
  redistributable only under each source's own licence.

## 12. Honest summary

A defensible decision aid that ranks copy variants ~59% of the time against a
50% baseline and a 78.8% ceiling, with a fully-cited diagnostic layer and
genuine data-protection engineering.

It is **not** an outcome predictor, it does **not** measure brains, and its
demographic conditioning is currently weaker than the premise implied. Every one
of those limits is measured, documented, and has a concrete path forward — which
is a better position than a product whose limits are unknown.
