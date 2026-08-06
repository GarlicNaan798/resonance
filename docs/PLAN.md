<!--
Snapshot of the working plan, copied here so plan history is version-controlled
alongside the code it describes.

The live copy Claude Code edits lives at ~/.claude/plans/ and is NOT in this
repo. This file can therefore drift. Re-copy it whenever the plan changes
materially, and treat the git history of this file as the record of how the
plan evolved.
-->

# Resonance — from research pipeline to shippable product

## Context

The goal is a tool that lets marketing agencies score campaign copy against a
specified demographic, using behavioural science, and compare variants before
spending media budget.

Where we actually are: **22 Python files of validated research pipeline, and zero
product code.** `resonance/` is still a bare Next.js scaffold whose
`lib/lexicons.ts` holds the hand-written word lists the model work replaced.

What the research established, on 32,487 randomised Upworthy experiments
(150,624 arms, leakage-safe grouped splits, test set sealed):

| Approach | Pairwise accuracy |
|---|---|
| 50 psycholinguistic norm features | 0.5628 |
| 78 interpretable features (v2) | 0.5611 |
| 384-dim semantic embeddings | **0.6247** |
| Shuffled-label control | 0.5176 (≈1.3 SE — noise) |

Two findings drive this plan. **Embeddings beat interpretable features by ~6
points** (~4.5 SE, real). And **theory-driven features added exactly nothing** —
curiosity gap, discrete emotion, self-reference, frequency and social proof
collectively moved accuracy by −0.0017.

Absolute outcome prediction is not achievable here: R² ≈ 0.01 even for an
unconstrained 512-unit MLP. **The product is a ranker and a diagnostic, never an
outcome oracle.**

**Phase 1 outcome (test set opened once):** embedding ranker **0.5942**
[0.5839-0.6044]; module model **0.5346** [0.5241-0.5452], over 2,665
experiments. Both fell ~3 points from validation, as predicted — validation had
been evaluated ~10 times and was optimistically biased. The test figures are the
only ones quoted externally.

**Measured oracle ceiling: 0.7880.** Labels are noisy estimates, so no model can
exceed this at the current filter. Every accuracy figure in this project is read
against that ceiling, not against 1.00.

## Decisions locked

1. **Two-layer, clearly separated.** An embedding ranker produces the
   prediction; the norm modules produce an independent diagnostic profile. The
   profile is never presented as the explanation of the prediction — that would
   be post-hoc rationalisation.
2. **One timeboxed diagnostic, then build** regardless of its outcome.
3. **v1 scope:** campaign scoring + audience picker, variant comparison, client
   data upload with recalibration, methodology/provenance panel.

## Standing rules (apply to every phase)

- Splitting unit is the **group** (transitive closure over shared test-id and
  shared headline) — never the individual arm.
- **Copy-only pairs**: exclude pairs with identical feature vectors. Upworthy
  varied headline × image, and 48% of raw pairs differ only by picture.
- Ties score **0.5**, not 0 — counting them as losses is what produced the
  spurious 0.27 result.
- Every reported gain must exceed the **shuffled-label control's deviation from
  chance** (currently 0.0176) and be expressed in SE over *groups* (≈0.0136),
  never over pairs.
- Test set stays sealed until the feature set is frozen; opened **once**.

---

## Phase 0 — Disagreement diagnostic (timeboxed)

Settle whether the 6-point gap is closable with interpretable features.

- New `model/diagnose_disagreement.py`: find val pairs where the embedding
  ranker orders correctly and v2 fails, sample them, and dump the headline text
  side by side with both scores.
- Look for a nameable property. If one appears, operationalise it, re-run
  `model/compare_features.py`, and keep it only if the gain clears the control
  deviation.
- **Exit condition:** one round. Proceed to Phase 1 either way.

## Phase 1 — Freeze and export the models

- `model/train_final.py`: fit the embedding ranker and the constrained module
  model on train+val with settings already chosen, then **open the test set
  once** via `unlock_test()` and record both numbers.
  - Report the test figure as the headline result. Val has now been evaluated
    ~8 times, so val is optimistically biased — say so in the model card.
- `model/export_weights.py`: dump the module model to JSON (weights, scaler,
  feature names, constraint values) for TypeScript inference.
- `data/processed/model_card.md`: training data, metrics with CIs, the R² ≈ 0.01
  ceiling, Upworthy domain-shift warning, and what the tool must not claim.

**Embedding inference is the one architectural risk.** The earlier "train in
Python, run in TS" decision does not cover a transformer. Resolution:
`@xenova/transformers` (ONNX MiniLM) runs in Node, keeping single-deploy. See
contingency C3.

## Phase 1.5 — Accuracy push (NEW)

Phase 1 delivered 0.5942 on held-out test. The measured oracle ceiling is
**0.7880** — a model with perfect knowledge of every headline's true click rate
could not beat that, because the labels themselves are noisy (median arm: 3,118
impressions, 42 clicks). So the real scoreboard is:

    chance 0.500  ->  us 0.5942  ->  ceiling 0.7880
    we currently capture 33% of the achievable signal.

Goal: capture 50-70% of achievable signal, i.e. **0.64-0.70 test accuracy**.
90% is not reachable at this label quality and will not be claimed.

### Protocol guard — the test set has already been read once

Re-reading the sealed test after every experiment would destroy it through
multiple testing. Therefore:

- Carve a **grouped dev-test** out of TRAIN (same transitive-closure grouping,
  ~15% of train groups). All Phase 1.5 iteration happens against dev-test.
- The real test set is read **exactly once more**, at the end, on the single
  pre-registered winner. Total reads: 2. That is declared here in advance.
- If an experiment looks good on dev-test but the final test read disagrees,
  the test number wins and no further tuning occurs.

### Experiments, in order of expected value

1. **Cross-encoder** — feed both headlines to one transformer together rather
   than embedding each independently. Bi-encoders lose pairwise information by
   construction; this is the largest honest gain available.
2. **Fine-tune end-to-end** — unfreeze the encoder instead of MLP-on-frozen-
   MiniLM.
3. **Larger encoder** — MiniLM is 6-layer / 384-dim, the small end.
4. **Ensemble** the above.

### Calibrated abstention

Accuracy on *every* pair is the wrong product target. Add a confidence estimate
from the model's score margin, calibrated on dev-test, so the product can say
"confident on this comparison, unsure on that one".

Report as a **coverage/accuracy curve**: accuracy at 100%, 50%, 25% coverage.
A defensible "80%+" claim is available at reduced coverage and must always be
stated with its coverage. Confidence must derive from the model's own margin,
never from the true gap, which is unavailable at prediction time.

### Contingencies

**C9 — cross-encoder gains less than the noise floor (~0.02).** Keep the
bi-encoder; it is cheaper to serve. Record the negative result and move on.

**C10 — cross-encoder is too slow to serve.** A cross-encoder scores every pair
rather than caching per-headline vectors, so cost grows with the square of the
variant count. If latency is unacceptable, use it as a re-ranker over the
bi-encoder's top candidates, or keep the bi-encoder and rely on abstention.

**C11 — final test read comes in below dev-test.** Expected to some degree.
Report the test number, keep the model that was pre-registered, do not re-tune.

## Phase 3.5 — Demographic conditioning (NEW)

Returns to the founding premise: telling a company how a campaign lands with
**their** target demographic. Today the audience layer is descriptive only,
because no dataset here links copy to outcome by demographic (Upworthy recorded
what ran and how it did, never who saw it), and the model's audience gains sit
at their zero initialisation.

The mechanism is already correct — an audience embedding feeding multiplicative
module gains. It needs a signal, and there are three, in increasing order of
evidential strength.

### 1. Theory-derived segment priors (build now)

Module gains derived from published findings, labelled in the UI as priors, not
measurements.

**Elaboration Likelihood Model** (Petty & Cacioppo, 1986). Central route weights
argument quality (valuation, control); peripheral route weights cues (salience,
affect).

> **Scientific correction that shapes the design:** ELM's moderators are
> *involvement* and *need for cognition* — NOT demographics. Mapping
> "education -> central route" is a stretch; NFC correlates with education only
> at r ~ 0.2-0.3. So **involvement becomes a first-class user input** (the
> marketer knows whether they sell cars or chewing gum), and education is used
> only as a weak, explicitly-flagged NFC proxy.

**Positivity effect** (Carstensen & Mikels, 2005; meta-analysis Reed, Chan &
Mikels, 2014, d ~ 0.25). Older adults preferentially process positive over
negative information. Modest, and attenuated under cognitive load.

**Arousal rating differences** (measured here from Warriner): men +0.285
(d = 0.32), younger +0.182 (d = 0.20).

> **Second correction:** these are differences in how raters *rate words*, not
> demonstrated differences in *behavioural response to advertising*. Treating a
> rating difference as a response difference is exactly the inferential leap
> this project exists to avoid. Flagged as low confidence.

All gains are bounded to the published effect sizes. No claim is made that these
correspond to demographic differences in neural activity — evidence for that is
substantially weaker than for the behavioural findings.

### 2. Client segment recalibration (Phase 4, highest value)

Meta and Google already report campaign performance **broken down by age bracket
and gender**. A client's export therefore supplies `(copy, segment, impressions,
clicks)` — enough to *fit* segment gains instead of assuming them. Priors are
replaced by measurement per tenant, and the upload schema is designed for this
from the start.

### 3. NeuMa validation (post-v1)

42 participants with age, gender, education, Big Five and shopping motivation,
viewing products with EEG and eye-tracking. Small N, product stimuli rather than
copy — usable to test whether segment differences appear at all, not to fit
gains.

### Contingencies

**C12 — priors are indistinguishable from no conditioning.** If bounded gains
move rankings less than the noise floor, present the segment panel as
explanatory framing only and say so, rather than shipping a control that does
nothing.

**C13 — client segment data contradicts a prior.** The data wins, per tenant,
and the contradiction is surfaced rather than hidden. A prior that client data
repeatedly overturns is removed from the global defaults.

## Phase 5 — Beyond the ceiling (NEW)

### The constraint, stated first

The 0.788 ceiling was measured by simulating two independent replications of the
same experiment and asking how often they agree on the winner. They agree 78.8%
of the time. **A perfect oracle scores 0.788 against these labels.** No model —
brain-inspired or otherwise — can exceed it, because the target is itself a
noisy measurement.

So "beyond the ceiling" means changing the LABELS, not the model. That is
achievable, and abstention already demonstrates it: 0.806 at 5% coverage, above
the global ceiling, by selecting comparisons whose labels are less noisy.

### What the research review found

- **aDDM** (Krajbich; Fisher multiattribute) — best neurally-validated model of
  consumer choice. Requires visual fixation input. We have text only.
- **Brain encoding models** (Algonauts 2025, RABBiT) — LLM representations
  predict fMRI/ECoG well, but the direction is text -> neural activity. We need
  text -> behaviour.
- **Industrial CTR systems** — high AUC via user features and session history.
  Not transferable: we score copy with no user information.
- **Convergent finding:** every strong model in this space is bottlenecked by
  what was MEASURED, not by architecture. So is ours.

### Candidate solutions, ranked by expected value

1. **Listwise objective** (cheap, untried). Train on all arms of an experiment
   jointly rather than on extracted pairs. Uses the full ranking signal instead
   of decomposing it. Standard in learning-to-rank; we never tried it.
2. **Brain-tuned encoder** (cheap if weights are public). Swap the encoder for
   one fine-tuned on neural data. Directly tests whether brain-alignment buys
   downstream generalisation.
3. **Multi-signal supervision** (moderate). Train against impressions, clicks
   and test-level structure jointly rather than a single contrast.
4. **Predicted attention -> aDDM** (speculative). Predict fixation from text,
   feed the validated choice model. Principled but two error-prone steps.
5. **Additional labelled corpora** (PENS/MSN). More data, different domain.
6. **Better labels** — client campaigns at higher impression volume. The only
   route that raises the ceiling itself.

### Working rules for this phase

- **Backup first.** Git repository initialised; baseline committed before any
  Phase 5 change.
- **Simple code only.** If an approach cannot be explained in the file's
  docstring, it does not go in. Complexity we cannot audit is how the
  fine-tuning bugs survived three runs.
- **Review as we build.** Every change is checked for whether it is a durable
  improvement or a number that happens to look good on dev.
- **Selection bias is assumed, not hoped away.** Anything chosen by sweeping on
  dev needs a pre-registered test read before it ships.

### Contingencies

**C14 — nothing clears the noise floor.** Likely, given seven prior experiments.
Then the honest conclusion is that model accuracy is saturated for this data,
and the product's claim moves to spend reduction (measured: 31.8% less wasted
budget) plus abstention. That is a stronger commercial position than a leaderboard
number on a task with a 0.788 ceiling.

**C15 — a gain appears but only on dev.** Treat as selection bias until a test
read confirms it. The hyperparameter "gain" of +0.0168 evaporated under 7-seed
replication; assume the next one will too.

## Phase 2 — Data safety foundation (must precede upload)

Per the earlier decision: GDPR-grade plus a self-host path.

- `resonance/lib/safety/pii.ts` — detect and **reject at ingest**: emails,
  phones, names, addresses, card numbers. Uploads are aggregate campaign data;
  PII is never needed and never stored.
- `resonance/lib/safety/tenant.ts` — tenant id on every row, enforced at the
  data-access layer, not in route handlers.
- `resonance/lib/safety/audit.ts` — append-only log of access and export.
- Encryption at rest and in transit; data-residency config; per-tenant model
  isolation so one client's uploads never influence another's model.
- `docs/SELF_HOSTING.md` + Docker compose for in-VPC deployment.

## Phase 3 — Application

Replace the scaffold. Delete `resonance/lib/lexicons.ts`.

- `resonance/lib/constructs.ts` — rewrite the 11 ad-hoc constructs as the **6
  literature-grounded modules** (salience, affect, valuation, encoding,
  approach, control), each carrying its citation and stated limitation.
  Explicitly excludes triune-brain and hemisphere-dominance theory.
- `resonance/lib/inference/` — TS forward pass for the module model (port of
  `model/architecture.py` constraints), plus the embedding ranker call.
- `resonance/lib/audience.ts` — map UI demographics onto Warriner's M/F, Y/O,
  L/H columns, which is the only empirically grounded part of the audience
  layer. Anything beyond those three axes is presented as *segmentation*, not
  measurement.
- Routes: `/analyse` (single campaign + audience), `/compare` (variant ranking
  with confidence), `/methodology` (provenance panel), `/upload` (client data).
- Every displayed number carries provenance and a confidence interval.

## Phase 4 — Client recalibration

- Upload schema: copy text + impressions + clicks/conversions + optional segment.
- Freeze the module layer; refit **only the outcome head** per tenant.
- **Minimum 200 campaigns** before a tenant-specific number is shown; below
  that, shrink toward the global model and label it as such.
- Reuse `pipeline/splits.py` grouping logic so client data gets the same
  leakage discipline.

---

## Contingencies

**C1 — Diagnostic finds a nameable property.** Operationalise it, re-run the
comparison, keep only if the gain clears 0.0176. If it does, the interpretable
layer may carry the prediction too, and the two-layer split collapses into one.

**C2 — Diagnostic finds nothing nameable (likely).** Conclude the gap is
semantic content that norms cannot represent. Ship two-layer as planned and put
that finding in the model card. No further feature hunting.

**C3 — `@xenova/transformers` fails or is too slow in Node.** Fall back to a
small Python FastAPI service for embeddings only, with the module model still
running in TS. Costs a second deployable; does not change the product. Decide by
benchmarking on 100 headlines before committing to Phase 3 routes.

**C4 — Test score comes in well below val (say < 0.58).** That is val-overfitting
from repeated evaluation. Report the test number as the truth, do not retune to
recover it, and state the discrepancy plainly in the model card.

**C5 — The audience layer shows no measurable benefit.** Warriner's demographic
splits may not shift rankings materially. Test before shipping: if segment
conditioning does not change predictions beyond noise, present the audience
feature as **descriptive segmentation** with that limitation stated, rather than
implying predictive personalisation.

**C6 — A client's uploaded data is too small or too noisy.** Enforce the 200
campaign floor, shrink to the global model, and show the widened interval rather
than a falsely precise number.

**C7 — Domain shift bites in production.** Upworthy is 2013-15 viral media; a
B2B SaaS advertiser is not. Mitigations: per-tenant recalibration (Phase 4), an
explicit warning in the UI when copy is far from training distribution, and the
model card limitation. If a client's recalibrated model beats the global one,
that validates the moat.

**C8 — NeuMa construct validation fails.** If frontal alpha asymmetry does not
track preference in the open EEG data, **rename the APPROACH module** to a purely
behavioural label and drop the neural framing for it. Deferred to post-v1; it
affects naming and marketing claims, not function.

## Verification

- `pipeline/splits.py` and `pipeline/assemble_dataset.py` `verify()` must pass —
  no index, group, or headline crosses a split.
- `model/negative_controls.py`: shuffled-label control near chance; model beats
  ridge; constraint audit passes (C1–C5 signs hold under adversarial forcing).
- `model/smoke_test.py` passes after any architecture edit.
- TS inference parity: same input through `model/architecture.py` and the TS
  port must agree to 1e-4 — a dedicated test, since silent divergence here would
  be invisible in the UI.
- PII rejection: unit tests with synthetic emails, phones, and card numbers.
- Tenant isolation: a test asserting tenant A cannot read or train on tenant B.
- End-to-end: `npm run dev`, paste two variants, confirm ranking, confidence
  interval, module profile, and provenance all render.
