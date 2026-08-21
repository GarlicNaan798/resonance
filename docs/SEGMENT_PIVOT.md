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

### Step 0. Check the variant assumption. SUPERSEDED, see the revised version in section 6.

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

---

## 6. Step 0 desk research, and a competitor nobody had named

Done 2026-08-21, before the conversations, to sharpen them.

**Source quality is poor and the findings are treated as hypotheses, not
facts.** Everything available is marketing-agency SEO content carrying
fake-precise vendor numbers ("2.5x CTR", "67% conversion improvement", "43%
lower CPA") with no methodology attached. None of it is quotable and none of it
is in this repository's evidence base.

One signal is worth acting on anyway, because it is about advice being given to
exactly this segment right now:

> The prevailing 2026 recommendation to small businesses is **"do not pick one.
> Launch 5 to 10 variations and let the platform allocate delivery toward the
> winners."**

### Why that matters

It names an incumbent competitor the whole project has ignored: **the ad
platform's own auto-optimisation.** Meta and Google will already run every
variant and shift budget toward what performs. If the platform picks for you,
using real outcome data from your actual audience, a tool that picks in advance
from a 2013-15 prior has to justify itself against that.

It also, unexpectedly, solves the section 2 risk. If owner-operators are being
told to generate 5 to 10 variants, and LLMs make producing them free, then
**variant supply is no longer the bottleneck.** They will hold multiple
candidates. The question shifts from "do they have two?" to "does anyone need to
choose, or does the platform choose for them?"

### Where Resonance still wins, and it is a narrower place than assumed

Platform auto-optimisation needs impressions to learn, and learning costs money.
That is the same noise problem this project already measured: distinguishing two
variants requires volume, and below that volume the platform is guessing too.

So the fit is strongest exactly where auto-optimisation is absent or too
expensive to run:

- **Email subject lines to a small list.** No auto-optimiser on most small
  senders, and a 400-person list will never reach significance.
- **A website headline, a Google Business post, a flyer, a shopfront sign.**
  One slot, no test possible, the choice is made once.
- **Small paid budgets.** Under a few hundred pounds the platform burns much of
  the budget learning what a prior could have told you for free. This is the
  allocator's original argument, and it is stronger for a small budget than a
  large one.

Weakest where the segment has real budget on Meta or Google and the platform
can learn properly. There, the honest answer is to let the platform do it.

### Consequence for the plan

The step 0 questions change. One question was never enough, and the second one
now matters more than the first.

### Step 0, revised. Five conversations, six questions, no code.

Ask in this order. Do not explain the product first; that biases every answer
after it. Say only "I am working on something for small businesses and I want to
understand how you write your ads."

1. **"Last time you wrote an ad, an email subject line, or a headline for your
   site, walk me through what you actually did."**
   Open, unled. Let them describe it. Everything below is a follow-up you only
   ask if they did not already answer it.

2. **"Did you end up with more than one version, or just the one?"**
   The section 2 assumption. If they use ChatGPT they almost certainly had
   several, whether or not they thought of it as having options.

3. **"How did you choose between them?"**
   The real question. Listen for "I just picked one", "I asked my partner",
   "I let Facebook decide". Each implies a different product.

4. **"When you run ads, do you let the platform test versions and pick a winner
   itself, or do you choose one and run that?"**
   The competitor question from section 6. If the platform already does this
   for them and they are happy with it, Resonance is competing with something
   free and better-informed on paid social.

5. **"Roughly what do you spend on a campaign?"**
   Decides whether platform auto-optimisation can actually learn. Small budgets
   are where a prior beats waiting for data.

6. **"Where does the copy go that you cannot test at all?"**
   Website headline, shopfront, flyer, Google Business post, a one-off email.
   These are the uncontested slots, and possibly the real product.

### How to read the answers

- **Multiple versions, chose by gut, small budget, untestable slots.** Best
  case. Proceed to step 1 as written.
- **Multiple versions, but the platform picks and they are happy.** The pivot
  survives but narrows to email, web and offline copy. The allocator and the
  paid-ads framing get cut rather than reconsidered.
- **One version, ship it, no testing anywhere.** Stop. The product needs to
  generate variants before it can rank them, and that is a different project.

Record the answers in `responses/interviews.md`, which is gitignored along with
everything else in that folder. Five short paragraphs is enough. The point is
to be able to re-read them when the answers stop feeling surprising.

---

## 7. Fourth council on the pivot, 2026-08-21

The most useful session of the four, and three of its findings are aimed at
errors in sections 1 to 6 above rather than at the product.

### The finding that matters most

One advisor was briefed to answer **as the target customer**: a plumber, a
baker, a two-person studio, doing their own ads badly in the evenings. Asked
whether they would use this, they said:

> "Probably not, honestly. I do maybe two Facebook ads a month and one
> newsletter subject line a week. That's not enough volume for me to build a new
> habit around a tool."

And on the honesty this project is built on:

> "It flat out tells me it's never seen anything like what I write. That's a red
> flag for trust, not a neutral disclaimer."

**The candour that makes this project credible to a technical reviewer reads as
a warning label to the actual buyer.** That is not a reason to stop being
candid. It is a reason to stop assuming candour sells.

They named exactly one slot where they would open it: **email subject lines,
because Mailchimp does not auto-test those for them.** Four of five advisors
converged on that same slot independently.

And what they actually wanted was not this product:

> "Something that just writes me three headline options in my own voice, not a
> scorer."

**The stated want is variant generation. Resonance does variant ranking.** That
is the opposite end of the same workflow.

### Three errors in my own analysis

**1. The volume argument was made wrongly.** Section 6 says auto-optimisation
needs impressions to learn, "which is the same noise problem this project
already measured", and leans on the 66.2% ceiling. That conflates two different
things. The ceiling measures noise in the *training labels* at Upworthy's
sample sizes. Whether a shopkeeper's own campaign can resolve a difference is a
separate question about *their* n.

The conclusion survives, the justification does not. And the correct tool was
already built: `requiredImpressions()` and `assessDecidability()` in
`lib/power.ts` answer exactly "can this test ever settle, at your volume".
The argument should be made with those, not by borrowing an unrelated number.

**2. The narrowing arrived backwards.** Sections 2 and 6 were written from
SEO blogs before a single owner-operator was spoken to. As one advisor put it:
found a competitor, got worried, pre-wrote the positioning. **The five
conversations were supposed to produce the narrowing, not ratify it.**

**3. The stated reason for the pivot is not the real one.** "Competes with an
untrained guess rather than a professional" is a story about what the effect
size should be, with no data behind it. The defensible reasons are different and
better:

- **Recruitment.** Agencies are gatekept and busy. Owner-operators are
  reachable. This segment is where the study actually gets participants.
- **Legibility.** In a world where you can A/B test properly, any prior loses to
  ground truth. The tool's real claim is only legible where no test is possible.

### What survives, and is stronger than what it replaced

**Restraint as the product, not the caveat.** The best idea in four councils:

> "A tool that says 'no signal' half the time, in a market of tools that always
> say something, is the actual differentiator. Nobody has pitched restraint as
> the feature."

Related, and a genuinely different product from the one currently built: the
first question for this user is not "which of these two" but **"does this
choice matter at all?"** Given a model that declines half the time, the honest
answer is often "ship either, the difference will not show up at your volume".
That is a *do not sweat this* tool, and `power.ts` already computes it.

**A wider door than small business.** The structural niche is any low-frequency,
high-stakes-per-instance text choice with no feedback loop: a nonprofit
fundraising appeal, a grant application subject line, one-shot crisis comms.
Same shape, more people who care.

### The gate, now dated and named

The previous gate was criticised precisely: *"a gate only holds if it is dated
and named. Right now it isn't."* So:

- **Message 15 people, not 5.** Some will not answer.
- **All 15 sent before doing anything else.** Not spread over a week.
- **Answers logged in `responses/interviews.md`** as they arrive.
- **The gate closes when 5 have answered, or on a date chosen now**, whichever
  comes first.

No code, no docs, no palette, no fifth council until that is done.

### The stop condition, stated in advance

If the conversations come back as *"we already just run 5 variants on Meta and
do not think about it"*, that is decisive. **The correct response is to stop,
not to narrow a second time.** One more reframe after this one would be the
pattern rather than a pivot.

If they come back as *"email subject lines, and I have no idea which to send"*,
that is the product, and it is a much smaller and more specific one than
anything built so far.
