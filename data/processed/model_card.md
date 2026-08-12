# Resonance — Model Card

Last updated: 2026-08-05

## What this system does

Given marketing copy, Resonance produces two **independent** outputs:

1. **A ranking prediction** — given two or more variants, which is likelier to
   perform better. Produced by a ranker over sentence embeddings.
2. **A diagnostic profile** — six behavioural-science scores (salience, affect,
   valuation, encoding, approach, control) computed from published human word
   ratings.

**These two layers are separate and must be presented as separate.** The
diagnostic profile does **not** explain the ranking prediction. Presenting it as
the explanation would be post-hoc rationalisation: the ranker does not use those
features, and its accuracy does not derive from them.

## Headline results (held-out test set, read once)

Evaluated on 2,665 experiments / 20,452 copy-only pairs from the Upworthy
Research Archive. Chance is 0.500. Confidence intervals are clustered by
experiment, because pairs within an experiment are not independent.

| Model | Test accuracy | 95% CI | Validation (biased) |
|---|---|---|---|
| Embedding ranker (listwise ensemble) | **0.6176** | 0.6075 – 0.6277 | 0.6291 |
| Module model (interpretable) | **0.5346** | 0.5241 – 0.5452 | 0.5649 |

Both intervals exclude chance, so both are genuinely better than guessing.

**Measured oracle ceiling: 0.662.** The labels are noisy estimates, so a model
with perfect knowledge of every headline's true click rate would still only
agree with the recorded winner 66.2% of the time. Only ~12% of the target's
variance is signal; the rest is sampling noise. Read every figure here against
0.662, not against 1.00 — at 0.6176 the ranker captures roughly 72% of the
achievable signal.

(This was reported as 0.788 until 2026-08-06. That estimate used each arm's
observed click rate as its true rate, which inflates it. See
model/ceiling_robustness.py and the correction section of FUNDAMENTALS.md.)

**Both models lost ~3 points from validation to test.** Validation was evaluated
roughly ten times during development, so those figures were optimistically
biased. **The test column is the honest number and the only one that should be
quoted externally.** No tuning was performed after the test set was opened.

## What the system cannot do

- **It cannot predict campaign outcomes.** Regression against the within-test
  effect reaches R² ≈ 0.01 — and an *unconstrained* 512-unit network reaches the
  same. This is a property of the task, not a limitation of the architecture.
  Any claim of the form "this campaign will lift conversions by X%" is
  unsupported.
- **It cannot measure neurochemistry.** No dopamine, oxytocin or cortisol
  prediction. Module names refer to functional systems the literature associates
  with each construct; they are psychometric scores from human ratings, not
  neural measurements.
- **It cannot rank variants that differ only in imagery.** The model reads copy.
  In the training data, 48% of within-experiment pairs differed only by image,
  and those are excluded from both training and evaluation.

## Training data

**Upworthy Research Archive** (Matias et al.) — 32,487 randomised A/B tests,
150,624 arms after filtering to ≥500 impressions.

Why randomised experiments matter: arms within one test share article, image and
publication moment, so the within-test contrast isolates the effect of the words
and controls for topic, timing and imagery. Observational ad data cannot support
that inference.

**Target:** within-test log-odds contrast with Haldane-Anscombe correction,
weighted by inverse variance so noisily-measured arms carry less influence.

**Norms:** Warriner et al. (2013) valence/arousal/dominance for 13,905 words,
including separate ratings by gender, age band and education level; Brysbaert et
al. (2014) concreteness for 39,954 words.

## Known limitations

**Domain shift — the most important one.** Training data is 2013–15 viral
media. A B2B SaaS or luxury retail advertiser is a different domain. The
constructs plausibly transfer; the calibration does not. Per-tenant
recalibration on client data is the intended mitigation, and a client's
recalibrated model beating the global one should be expected.

**Interpretable features have a ceiling.** Two rounds of theory-driven feature
engineering produced nothing:

- v2 (+28 features: discrete emotion, curiosity gap, self-reference, word
  frequency, social proof): **−0.0009** vs the 50-feature baseline.
- v3 (+8 features: identifiable-individual effect, narrative markers):
  **+0.0057**, against a measured noise floor of 0.0232 — discarded under a
  pre-registered threshold.

A disagreement analysis found no interpretable feature separating
embedding-correct/interpretable-wrong pairs by more than 0.11 SD, and indicated
the residual signal is concrete subject matter rather than style. The honest
conclusion is that the ~6-point gap is semantic content that psycholinguistic
norms cannot represent.

**The interpretable layer is a weak predictor.** At 0.5346 it is only ~3.5
points above chance. It earns its place as an explainable diagnostic, not as a
predictor, which is precisely why the two layers are kept separate.

## Leakage controls

- Split unit is the **group**: the transitive closure over shared test-id and
  shared headline. Splitting on test-id alone would leak, because ~50% of
  headlines recur across experiments.
- Verified: no index, group or headline string crosses a split boundary.
- Test set SHA-256 fingerprinted and locked; any change is detected and refused.
- Feature standardisation fitted on training data only.
- Shuffled-label control run throughout; its deviation from chance (~0.018–0.023)
  defines the noise floor that any claimed gain must exceed.

## Intended use

Comparing copy variants before media spend, and diagnosing copy against a
specified audience. It is a decision aid whose competing alternative is
copywriter intuition.

## Out of scope

Predicting revenue or conversion rates; claiming neural or biochemical
measurement; evaluating imagery; medical, political-manipulation, or any
application targeting individuals rather than audience segments.
