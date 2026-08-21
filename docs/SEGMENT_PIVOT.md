# Segment change: agencies to owner-operators

Decided 2026-08-21. Target moves from marketing agencies and in-house teams to
**business owners who have no marketing team, or a very small one, and have to
ship campaigns with less manpower.**

This is not a repositioning exercise. It changes what the product competes
against, what the evidence has to show, who the study must recruit, and which
three existing features stop earning their place.

---

## 1. What improves, and it is the important part

**The thing Resonance is measured against gets much weaker, so the same 61.8%
is worth far more.**

For an agency, the tool competes with an experienced copywriter's judgment.
That is a hard bar, and it is exactly why the human-baseline study was framed as
a threat to the product.

For an owner-operator with no marketing team, the tool competes with **their own
untrained guess**. Published work puts even trained people near chance on this
task. Someone who has never thought about copy is not going to be better.

Same model, same number, completely different value:

| | Agency | Owner-operator |
|---|---|---|
| Alternative to the tool | A professional's instinct | A coin flip |
| 61.8% is | A marginal edge over an expert | A large edge over guessing |
| Abstention on 50% | Fine, they have judgment to fall back on | **A problem, see section 3** |

**The study gets easier and more correct at the same time.** Professional
copywriters are hard to recruit and were never the right comparison group for
this positioning. Owner-operators are far more numerous, easier to reach, and
are the actual counterfactual.

**Domain transfer becomes more plausible.** Upworthy clickbait to a local
service ad or an Instagram caption is a shorter jump than clickbait to B2B SaaS.
Still unmeasured. Still not a claim. But the plausibility improved rather than
degraded.

**The diagnostic layer gets stronger.** It was the weakest feature for agencies,
who already have vocabulary for arguing about copy. An owner-operator has none.
"Your headline is abstract and low-urgency" is genuinely new information to
someone who has never had the concept.

---

## 2. The risk that could sink the whole pivot

**Resonance ranks variants. It does not write them.**

An agency produces three headlines as a matter of course. An owner-operator may
well write **one** headline and ship it. If they never hold two candidates at
once, the product has no input and the question it answers is not a question
they ask.

This is the single assumption the pivot rests on, it has not been checked, and
it is cheap to check. **Do this before anything else in section 4.**

If the answer is "they only ever have one", the product needs variant
generation to have any input at all, which is a different and much larger build.
Better to learn that from five conversations than from a quarter of work.

---

## 3. What the pivot breaks

### 3.1 The abstention leaves the new user with nothing

When the model declines, which is about half of all comparisons, it currently
says:

> "Pick on brand, clarity or gut, and put the test budget somewhere it will
> settle something."

That advice assumes brand guidelines, a trained gut, and a test budget with
somewhere else to spend it. **The new target has none of the three.** For an
agency this was a graceful hand-back. For an owner-operator it is the tool
shrugging at someone with nothing to fall back on.

This is the one genuine product hole the pivot creates, and it is small to fix.

### 3.2 The pre-registration reports the wrong group as primary

`docs/PREREGISTRATION.md` section 7 currently says:

> If 3 or more participants report no professional copywriting experience,
> report the **professional** subgroup separately as the primary figure.

Written when professionals were the target. Under the new segment that rule
reports the wrong headline number: the non-professional group is now the
population of interest.

The instrument already captures what is needed, the `paid` flag and years of
experience, so this is a wording change, not an engineering one. No participant
data exists, so amending is legitimate and gets recorded as a dated amendment.

### 3.3 Three features lose their reason to exist

Not deleted today. Named so they are not defended out of habit.

- **Verifiable no-egress.** An agency under NDA cares enormously about client
  copy never leaving the building. A plumber does not. Still true, still worth
  a line, no longer the wedge.
- **Sealed predictions.** This was "prove to your client you called it in
  advance". An owner-operator has no client to prove anything to. The track
  record still works as "prove it to yourself", which is a much smaller claim.
- **The budget allocator.** It requires impressions and clicks per variant,
  which presupposes a running structured A/B test. Many in the new segment do
  not have one.

---

## 4. The plan

Ordered. Each step is gated on the one before it, because the failure mode this
project keeps hitting is building the next thing before checking the last
assumption.

### Step 0. Check the variant assumption. Five conversations, no code.

Ask five owner-operators one question:

> "When you write an ad or an email subject line, do you ever have two versions
> and have to pick? Or do you write one and send it?"

That is the whole research instrument. It decides whether the product as built
has an input at all.

- **They routinely hold two or more.** The pivot works. Continue to step 1.
- **They write one and ship it.** Stop. The product needs variant generation
  before anything else matters, and that is a different project to scope.

### Step 1. Fix the abstention fallback. Small, and it is a real hole.

When the model declines, stop handing the decision back to expertise the user
does not have. Give them what the system actually knows:

- Show the diagnostic difference in plain language, "B is more concrete and more
  urgent; A is more abstract". That is information a non-marketer does not have
  and it comes from a layer already built.
- Say plainly that either is a defensible choice and that this is not a failure
  of their writing.
- Drop "put the test budget somewhere else" for this audience. Many have no
  budget to move.

This is the only build in the plan that runs before evidence, and it is here
because the pivot created the hole, not because it was on a wish list.

### Step 2. Amend the pre-registration. Wording, ten minutes.

Flip section 7 so the **non-professional** group is the primary figure, and
record it as a dated amendment before any data exists.

### Step 3. Run the study with the right population.

Same instrument, same 30-item core, same decision rule. Different room:

- r/smallbusiness, r/Entrepreneur, IndieHackers, local business Facebook groups,
  Shopify and Etsy seller communities.
- The ask changes to match the audience: not "help validate a model" but
  **"can you beat a machine at picking headlines? Five minutes."** Owner-operators
  have no professional stake in the answer, which makes them easier to ask and
  makes the result cleaner.
- Still 14 to 19 people. Still one message to one person as the first action.

### Step 4. Only after step 3 reports.

- Rewrite the landing page for the new reader. Right now it is written for
  someone who already knows what a randomised A/B test is.
- Reconsider the allocator, hide it, or rebuild it for people without
  impression counts.
- Demote the no-egress and sealed-prediction material from wedge to footnote.

---

## 5. What does not change

The pivot does not touch the model, the ceiling, the abstention behaviour, or
any measured number. It changes who those numbers are being offered to and what
they are worth to that person.

And it does not remove the need for evidence. It makes the evidence easier to
get and more relevant when it arrives. Three councils have said the binding
constraint is participants rather than features. A better-fitting target
customer does not change that, it just means the fourteen people are easier to
find and are finally the right fourteen.
