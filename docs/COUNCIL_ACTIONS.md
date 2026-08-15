# Council findings — what happens about each

From the council session of 2026-08-14. Every catch is listed, including the
ones being deliberately ignored, because a plan that silently drops the
inconvenient findings is just a to-do list with better PR.

**Ordering principle: nothing here reopens the model.** All five advisors
independently concluded that code stopped being the bottleneck. The work below
is either evidence-gathering, or honesty repairs to things the app currently
says. Anything that is neither waits.

---

## Status

| # | Catch | Verdict | State |
|---|---|---|---|
| 1 | No decision rule for the study | Fix | **Done** — `docs/PREREGISTRATION.md` |
| 2 | Sampling fails the project's own standards | Fix | **Done** — §7, plus instrument now records experience |
| 3 | Abstention *reads* as failure | Fix | **Done** — and the rate was 50%, not 75% |
| 4 | Domain transfer never explained to a user | Fix | **Done** — answered on /compare and in README |
| 5 | Diagnostic layer undefended | Decide | **Done** — kept, justified on /analyse |
| 6 | Unsigned binary scares people off | Fix, later | Phase C |
| 7 | Pivot to "the notary is the product" | **Reject** | Not doing — reasoning below |
| 8 | Recruit participants | Do | Phase B |

---

## Phase A — honesty repairs (before recruiting)

These change what the app *says*, not what it does. They come first because
participants and visitors arrive at the same README, and every one of them is a
thing a stranger flagged as confusing or off-putting.

### A1. Reframe the abstention

**The catch.** *"Three times out of four it just shrugs? A 25% hit rate on
giving me any opinion is going to feel broken, not humble. I'd assume I was
doing something wrong."*

The behaviour is right and stays. The framing is wrong. Two advisors called
abstention the spine of the design; the one advisor reacting as a user read it
as the product failing.

**Do:**
- On `/compare`, when the model abstains, lead with what it *did* establish —
  "these are within noise of each other, so picking either is defensible and the
  difference is not worth a test" — rather than "insufficient confidence".
- State the abstention rate up front on the home page instead of letting a user
  discover it by hitting it. A tool that says "I answer about a quarter of
  comparisons, and I'm right 76% of the time when I do" is honest; one that
  quietly shrugs feels broken.
- Add the counterfactual: measured at **56.3%**, six points above a coin.
  Abstaining is not "the model has nothing"; it is "what it has here is too
  weak to spend on".

**Correction found while doing this.** The brief given to the council said the
app abstains on ~75% of comparisons. It is ~50%: coverage in the tier table is
cumulative, and the model answers at both the high AND moderate tiers. The
Outsider's "three times out of four it just shrugs" was answering a worse
product than the one that exists. The framing critique still stands at 50%,
which is why this was fixed rather than dismissed.

**Not doing:** lowering the abstention thresholds to answer more often. That
trades calibration for the appearance of usefulness, which is the exact swap
this project exists to refuse.

### A2. Answer "why does clickbait generalise to my SaaS landing page?"

**The catch.** *"Nobody told me why that data generalizes to my Facebook ad copy
or my SaaS landing page. That's the thing that would actually kill my trust,
more than the accuracy numbers."*

The README states the limitation. It never answers the question. The honest
answer is uncomfortable and should be given anyway: **it may not transfer, we
have not measured it, and the track record is how you find out for yourself.**

**Do:** put that answer where the user meets the doubt — on `/compare` and in
the README, not buried in the methodology page — and link it to Track record as
the remedy.

### A3. Decide the diagnostic layer's fate

**The catch.** *"53.5% — barely better than a coin — and the tool itself admits
it doesn't explain its own prediction. So why is that feature in the product at
all? That reads like something built because it was interesting to build."*

Four advisors did not engage with this. The Outsider is right that it is
currently indefensible *as presented*.

There are only two honest options, and the choice is the developer's:

- **Keep and justify.** It is a shared vocabulary for arguing about copy —
  salience, affect, concreteness — grounded in published human ratings rather
  than invented. Value as a discussion aid does not require predictive power.
  If this is the answer, the page must say so in one sentence at the top, and
  stop reporting 53.5% as though accuracy were the point.
- **Cut it.** Six constructs at chance is a large surface for a weak feature,
  and removing it would sharpen the product to one claim.

**Recommendation: keep and justify.** It is the only part of the system that
produces language a marketer can act on, and cutting it leaves a ranker that
says "this one" with no vocabulary attached. But the justification has to be
written, not implied.

---

## Phase B — the study (the actual bottleneck)

Nothing in Phase A blocks this; run them in parallel if you like, but do not let
Phase A become a reason to delay.

### B1. Recruit 10 participants

`data/processed/human_quiz.html` is built and instrumented. Recruitment is the
work, and it is not engineering.

- Channels: r/copywriting, r/marketing, marketing Slack and Discord
  communities, LinkedIn, and anyone you know who writes ad copy for money.
- Ask: ten minutes, sixty pairs, no account, runs offline in a browser.
- Compensation is allowed and must be disclosed in the write-up (§7).
- **Aim past 560 answered items.** The power calculation assumes the model and a
  human err independently. They will not — both find the same easy pairs easy —
  and correlated errors shrink the discordant pool that carries all the
  information. 560 is a floor.

### B2. Close collection, then analyse once

Fixed date or 560 items, whichever is later. `human_baseline.py score` runs
once. No peeking, no stopping early on a significant result.

### B3. Publish whatever it says

Into README, FUNDAMENTALS §3, and the methodology page, following the table in
`PREREGISTRATION.md` §5. If humans win, that goes at the top.

---

## Phase C — only after B reports

Deliberately gated. Each of these is reasonable work that would be premature
now, because the study's result changes whether it is worth doing at all.

- **C1. Code signing.** A reviewer correctly noted this was misfiled: it is
  bounded, solved work, not speculation. It is still second, because a signed
  installer for a tool with no evidence is polish on an unanswered question.
- **C2. Per-tenant recalibration (Phase 4).** Only if the study and any track
  records suggest the model transfers at all. Building it first assumes an
  answer.
- **C3. A second corpus.** Same gate.

---

## Rejected

### Pivoting to "the notary is the product"

One advisor argued the sealed-prediction machinery — SHA-256 commitment,
write-once outcomes, measured ceilings — is a general trust layer for any
forecasting domain, and the headline ranker is merely its demo.

**Rejected, and all three peer reviewers agreed independently.** The argument
diagnoses the project's problem as an unvalidated value proposition, then
proposes a different value proposition with *even less* validation. It also
elevates the exact feature the one user-perspective advisor found most
alienating: *"who asked for provable prediction timestamps? That sounds like a
feature for impressing other engineers."*

Recorded rather than deleted, because it is a genuinely interesting reframe and
may become right later. It is not right while the current claim is unmeasured.

---

## The failure mode to watch

This project has now hit the same class of bug three times:

1. `pipeline/splits.py` — a test-set lock with zero callers, guarding an
   abandoned corpus.
2. `describeSafety()` — a test asserting the *wording* of a guarantee that no
   code provided.
3. `PREREGISTRATION.md` — nearly committed promising two fields the quiz did not
   record.

Each time: machinery that looked like rigour, wired to nothing. The third was
caught before commit only because the document was written before the
recruitment rather than after.

**The check, for anything in this plan: if it claims something is enforced, run
the thing that would fail when it is not.**
