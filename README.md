# Resonance

**Ranks marketing copy, and tells you when it can't.**

Given two or more headlines, Resonance predicts which will perform better and
reports how confident that prediction is. It is trained on 32,487 randomised
A/B tests with real click outcomes, and it declines to answer when the
comparison is too close to call.

It runs entirely on your own machine. No account, no telemetry, no outbound
network calls at runtime.

---

## The number, and why it is the wrong number to look at first

| | |
|---|---|
| Chance | 50.0% |
| **Ranking model** | **61.8%** (95% CI 60.8–62.8) |
| Measured ceiling | **66.2%** |
| Share of achievable signal captured | **~72%** |
| Accuracy on its most confident 25% | **76.0%** |

61.8% looks unimpressive until you know what perfect looks like. The training
labels are *noisy measurements*: the median experiment arm had 3,118
impressions and 42 clicks, so a model with flawless knowledge of every
headline's true click rate would still only agree with the recorded winner
**66.2%** of the time. Only ~12% of the variance in those labels is signal;
the rest is sampling noise.

So the honest scale runs 50% → 66.2%, not 50% → 100%. On that scale the model
captures about **72% of the signal that exists to be captured**.

That ceiling was measured, not assumed — see `model/ceiling_robustness.py`. An
earlier estimate of 0.788 was wrong because it treated each arm's *observed*
click rate as its true rate. Correcting it moved the ceiling down and made the
model look better; it was corrected anyway.

## What it cannot do

Enumerated in code as `PROHIBITED_CLAIMS` in `resonance/lib/constructs.ts`, not
just in prose:

- **Predict conversions, revenue or ROI.** Regression against the outcome
  reaches R² ≈ 0.01 — and so does an unconstrained 512-unit network. That is a
  property of the task, not of the architecture.
- **Measure neurochemistry.** The six diagnostic modules are named for
  functional systems the literature associates with each construct. They are
  psychometric scores from published human word ratings. No dopamine, no
  cortisol, no brain scanning.
- **Rank variants that differ only by image.** It reads copy. 48% of pairs in
  the source data differed only by picture; those are excluded from training
  and evaluation.
- **Replace A/B testing.**

**It has never been measured against a human baseline.** The obvious pitch line
— "beats copywriter intuition" — is not evidenced, so it is not made.

The study to settle it is built and pre-registered but has **no participants
yet**: `model/human_baseline.py` draws 60 blind pairs from the held-out set,
balances winner position exactly 30/30, scores the model on the identical items
a participant answered, and compares them with McNemar's exact test. The power
calculation was fixed before collection — ≈560 answered items, 10 participants
— so a null result cannot later be passed off as evidence of equivalence.

Whatever it returns gets published here, including the outcome where humans win.

## Two layers, deliberately separate

1. **The ranker** predicts. It reads sentence embeddings, scores 61.8%, and
   cannot explain itself.
2. **The diagnostic profile** explains. Six constructs — salience, affect,
   valuation, encoding, approach, control — from Warriner et al. (2013)
   valence/arousal/dominance norms and Brysbaert et al. (2014) concreteness.
   It scores 53.5%, barely above chance.

**The profile does not explain the ranking.** The ranker never sees those
features. Presenting one as the reason for the other would be post-hoc
rationalisation, so the two are reported side by side even when they disagree —
and when they disagree, that is information.

## Sealed predictions

The part that answers *"does this work on MY campaigns?"*

1. Before launch, seal a comparison. Variants and the model's pick are SHA-256
   hashed with a timestamp; send the hash to a client and it proves afterwards
   the call preceded the result.
2. Record the real winner when it is known. Write-once — a record you can
   revise measures nothing.
3. Read the track record: hit rate with a Wilson interval, on your campaigns.

You can also log **your own pick, made before the model runs and locked
afterwards**, so the same page scores your judgement against the model's.

The page refuses to claim an edge below 10 resolved outcomes, whatever the
interval says. Wilson's lower bound at 4-of-4 is 0.51 — technically excluding
chance, but a fair coin does that one time in sixteen.

## Running it

```bash
cd resonance
npm install
npm run fetch-encoder     # one-time, ~87 MB — the only download that ever happens
npm run dev               # http://localhost:3000
```

As a desktop app:

```bash
npm run desktop
```

Campaign data goes to the OS user-data directory; **File → Show data folder**
opens it. Not code-signed yet, so a distributed build would trip SmartScreen
and Gatekeeper — running from source does not.

## Verifying the no-egress claim

Don't take it on trust; that is the point.

```bash
docker compose run --rm --network none app npm run selftest
```

The encoder is fetched once at build time and the runtime is then locked to
local files, with no setting that re-enables a remote fetch. A missing encoder
fails loudly rather than reaching for the network.

This was not always true. Until 2026-08-12 the offline lock was gated behind
`RESONANCE_MODE=self-hosted`, so the default configuration silently downloaded
the encoder from HuggingFace on first inference. The claim on the tin was true
only of a deployment that had already run once with network access. The gate is
gone rather than fixed — a guarantee you have to remember to switch on is not a
guarantee.

## What did not work

Kept because a project that reports only its wins has not earned trust.

| Hypothesis | Result | Decision |
|---|---|---|
| +28 interpretable features (discrete emotion, curiosity gap, self-reference, social proof) | −0.0009 | Discarded |
| Identifiable-individual features | +0.0057, below the 0.0232 noise floor | Discarded under a pre-registered rule |
| Pairwise interaction ranker | −0.0038 | The bi-encoder was not the bottleneck |
| Larger encoder (mpnet-base, 768d) | +0.0128, CI [−0.0119, +0.0375] | Not significant once paired correctly. Avoided 5× inference cost |

Two rounds of theory-driven feature engineering produced nothing, and no
interpretable feature separated the two models' disagreements by more than 0.11
SD. The remaining ~6-point gap appears to be semantic content that
psycholinguistic norms cannot represent.

**The data hunt also closed negative.** Yahoo R6, Criteo, Avazu and Outbrain
publish clicks without creative text; MIND has no randomisation; PENS has no
per-variant clicks; Reddit and Meta require accounts or government ID. A
Hacker News repost corpus was harvested (2.1M stories, 55,324 repost groups)
and rejected: HN scoring is a front-page cascade, and only 4.9% of pairs had
both arms live. The structural finding is that platforms release *behaviour*
and strip *creative*. Upworthy exists only because a researcher published it
specifically to study headlines.

## Leakage controls

- The corpus was **49% exact duplicates**, with 89% of items in near-duplicate
  clusters. Splitting is therefore on the transitive closure of shared test-id
  *and* shared headline — never on rows.
- Verified that no row, cluster or headline string crosses a split boundary.
- Feature standardisation is fitted on training data only.
- A shuffled-label control runs throughout; its deviation from chance
  (0.018–0.023) is the noise floor any claimed gain must exceed.
- Splits come from **one** deterministic seeded partition
  (`pipeline/test_lock.py`, seed 20260805). It was previously defined three
  times in three files; all three were verified byte-identical before being
  collapsed into one, so no number changed.
- The test partition is **fingerprinted** (`081f57f3…`, n=22,648). A change to
  the corpus or the seed is refused rather than silently revaluing every result
  ever reported.
- Reading test requires a **written reason** and appends to
  `data/processed/test_reads.jsonl`. `pipeline/test_lock_check.py` verifies the
  gate rejects short reasons, that refused reads are not logged, and that
  editing a test row trips the fingerprint while editing a train row does not.

> **How this came about**, since the fix is more interesting than the feature.
>
> `pipeline/splits.py` advertised exactly this protocol and had **zero callers**
> — it guarded `data/splits/test.jsonl`, 2,806 LLM instruction prompts from an
> abandoned corpus no model ever touched. Every real read used an ungated
> in-process split instead.
>
> Nothing leaked: the split was grouped, deterministic and consistent, so
> train/test separation held and every reported number stands. But because no
> read was gated or recorded, **the project could not say how many times the
> test set had been opened** — three documents gave three different answers. A
> static audit finds two evaluations plus one non-evaluative fixture read; the
> historical count cannot be certified from code alone, which is precisely the
> argument for the log. The known reads are backfilled and flagged as such.

## Layout

```
pipeline/    ingestion, deduplication, feature extraction, splits
model/       architecture, training, negative controls, ceiling estimation
resonance/   Next.js app + Electron desktop shell (245 tests)
docs/        plan, self-hosting guide, source papers
FUNDAMENTALS.md   the single document to read before evaluating this system
```

## Honest summary

A ranker at 72% of a measured ceiling, an interpretable layer that is a weak
predictor and says so, a diagnostic that never pretends to explain the
prediction, and a track-record feature built to find out whether any of it
transfers to your campaigns. The training data is 2013–15 viral media and you
are probably not that; the constructs travel better than the calibration does.
