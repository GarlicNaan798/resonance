# Pre-registration — human baseline study

**Status: fixed before any participant data exists. Committed 2026-08-14.**

Everything below is decided in advance. The point of writing it down is that a
result cannot later be reinterpreted into whichever conclusion flatters the
project. If this file and the eventual result disagree, this file wins and the
disagreement gets published.

The analysis code was written before this document and is already committed:
`model/human_baseline.py score`. No new analysis will be written after seeing
the data.

---

## 1. The question

On identical held-out comparisons, does the Resonance ranker pick the winning
headline more often than an experienced marketer does?

This has never been measured. `FUNDAMENTALS.md` §3 forbids the claim "beats
copywriter intuition" precisely because of that, and will keep forbidding it
unless this study earns it.

## 2. Design

- **Items.** 60 pairs per participant, drawn by seed from the 20,452 copy-only
  pairs in the locked test partition (fingerprint `081f57f3…`). Each pair is two
  real headlines from the same randomised Upworthy experiment — same article,
  same moment, same audience — so exactly one genuinely won.
- **Blind.** Two headlines and nothing else. No scores, no impressions, no
  indication of which experiment they came from.
- **Position balanced by construction.** The winner appears first in exactly 30
  of 60 items, shuffled. A participant who always picks the first option scores
  50% by definition rather than inheriting an edge from our sampling.
- **The model answers the same items**, and is scored only on the items a given
  participant actually answered — never on its global 61.8%.
- **Key withheld.** The quiz file contains no answers. Scoring happens locally
  against a key participants never receive.

## 3. Primary test

**McNemar's exact test, two-sided, α = 0.05**, on discordant items — those where
exactly one of {participant, model} was correct. Concordant items carry no
information about which judge is better.

Paired, because both judges answer the identical question. Comparing two
independent confidence intervals and checking for overlap would be the wrong
test and would have less power.

## 4. Sample size and stopping rule

**Target: 560 answered items** (≈10 participants × 60, allowing for skips).

That figure comes from `items_needed()` in `model/human_baseline.py`, computed
before collection. Detecting humans at 50% against the model at **35/60 =
58.33%** — its measured accuracy on this exact item sample — needs **560**
answered items for 80% power. (Rounding that rate to 58.3% gives 565; the
figure is sensitive at the third digit, so the exact fraction is used.)

The calculation assumes the two judges err independently, which is optimistic:
a human and a model both find the same easy items easy, and that correlation
shrinks the discordant pool and raises the true requirement. **560 is a floor,
not a target to stop at.**

**Minimum detectable effect at n=560 is 8.4 percentage points** at 80% power.
That number is what makes the "no difference" verdict in §5 meaningful rather
than empty.

**Stopping rule: collection closes at a fixed date or at 560 answered items,
whichever is later. The analysis is run once, after collection closes.** No
interim peeking, and specifically no stopping the moment a result turns
significant — that inflates the false-positive rate well past 5% and is the most
common way an honest-looking study becomes worthless.

## 5. What each outcome licenses — decided now

| Result | What may be claimed | What may not |
|---|---|---|
| **Model ahead, p < 0.05** | "On held-out randomised tests, the model picked the winner more often than experienced marketers did (n items, CI)." Always with the sampling caveat from §7. | Any claim about *your* campaigns. The items are still Upworthy. |
| **No significant difference** | "No difference of 8.4 points or more was detected between the model and experienced marketers on identical items." Combined with instant, free and always-available, that is still a real product claim. | **"As good as a professional."** Non-significance is not equivalence. Differences smaller than 8.4 points remain entirely possible and this study cannot resolve them. |
| **Humans ahead, p < 0.05** | Publish it, prominently, in README and FUNDAMENTALS. The accuracy claim is withdrawn; the product's remaining case is speed, consistency, calibrated abstention and the track record — not being right more often. | Any framing that buries it, or a follow-up study run until a better number appears. |

All three outcomes are publishable. That is the entire reason for fixing them in
advance.

## 6. Pre-specified secondary analyses

Named now so they cannot be dredged later. Each is descriptive; none carries a
significance claim, and no multiplicity correction is applied because none of
them will be reported as a finding.

- Participant accuracy against chance (Wilson interval).
- Model accuracy on this item sample against its global 61.8%.
- Position bias: how often participants chose the first option.
- Between-participant spread in accuracy.
- Accuracy split by the model's confidence tier — do humans also find the
  low-margin pairs hard? If they do, that is evidence the abstention is tracking
  genuine difficulty rather than model weakness.

Anything not on this list, if it appears in the write-up, is labelled
exploratory.

## 7. Sampling — the honest limitation

Participants will be a **convenience sample**: self-selected, recruited through
social media and personal networks, possibly compensated. This is exactly the
kind of sample this project's own machinery — Wilson intervals, the
10-outcome floor, the measured noise ceiling — was built to distrust. Pretending
otherwise would be inconsistent with everything else here.

What that does and does not invalidate, stated precisely:

- **External validity is genuinely limited.** The measured human rate cannot be
  read as "the accuracy of marketers in general". It is the accuracy of *these*
  participants.
- **Internal validity of the paired comparison is not affected the same way.**
  The design is within-item: each participant and the model answer the identical
  questions, and McNemar compares them on that basis. Selection bias changes who
  is in the sample; it does not make the paired comparison for those people
  wrong.

Mitigations, all fixed now:

- Record each participant's **years of experience** and **whether copywriting is
  part of their paid work**. Report accuracy broken out by that, without
  claiming significance on the subgroups.
- Report n, recruitment channel and compensation in the write-up, in the same
  place as the headline number and not in a footnote.
- Label the finding **provisional pending replication**.
- If ≥3 participants report no professional copywriting experience, report the
  professional subgroup separately as the primary figure.

## 8. Exclusion criteria — fixed before seeing any data

A response is excluded only if:

1. Fewer than 48 of 60 items were answered (80% completion), **or**
2. Median time per item is under 2 seconds, which indicates clicking through
   without reading, **or**
3. The participant reports having seen the answer key or the source dataset.

No participant will be excluded for scoring badly, scoring well, or
disagreeing with the model. Exclusions will be reported with counts and reasons.

## 9. Commitments

- The analysis script is already written and committed. No new analysis after
  data arrives.
- Every response file received is included in the reported n, minus §8
  exclusions.
- Reading the test set for this study goes through `unlock_test()` and is
  recorded in `data/processed/test_reads.jsonl` like every other read.
- The result is published whatever it says.

---

*Amendments to this document after collection begins must be recorded as dated
additions below, never by editing the text above. An amended pre-registration
that hides its own amendments is worse than none.*

---

## Amendment 1 — 2026-08-15, before any data collection

Recorded as a dated addition rather than by editing the text above, per the
note at the end of this document. **No participant data exists at the time of
writing**, so this is a design decision, not a mid-study change. Nothing here
alters the hypothesis, the test, the decision rule or the total power
requirement.

**The ask is now a 30-item core, with the remaining 30 offered as optional.**
Sixty items is roughly ten minutes, which is a large request of a stranger with
no relationship to the project. Thirty is about five.

This costs nothing statistically. **Power is set by total answered items, not by
items per person**: 560 remains the floor. It changes only how those items are
distributed — 19 participants if everyone takes the exit, 10 if everyone
completes all 60, and in practice a mix. More participants slightly *improves*
the pooled estimate, because responses cluster within people and more clusters
is better, and it widens the sample, which is the one weakness §7 concedes.

Two consequences, both handled:

- **Item order is now shuffled per participant.** Without this every early
  finisher would answer the same first 30 pairs, leaving half the item sample
  with no responses and narrowing what the result generalises over. Answers
  carry the item id, so scoring is unaffected by display order, and the
  winner's left/right position is fixed per item in the key — shuffling the
  sequence does not disturb the 30/30 position balance.
- **The completion floor in §8 becomes absolute: 24 answered items** (80% of the
  core block), replacing "80% of 60". Under the old rule every participant who
  took the offered exit would have been excluded by design — the rule would have
  discarded the majority of the sample. The floor still catches genuine
  abandonment; `model/human_baseline_check.py` asserts both directions.

Everything else stands unchanged.
