import Link from "next/link";
import { PERFORMANCE, PROHIBITED_CLAIMS } from "@/lib/constructs";
import { TIERS } from "@/lib/inference/ranker";

/**
 * The pitch.
 *
 * Ordering is the whole design. The honest numbers are the differentiator
 * against neuromarketing vendors, but leading with "61.8%" reads as "coin flip
 * plus a bit" to anyone not yet told the ceiling is 66.2%. So: what it does ->
 * what it is worth -> the numbers framed against the ceiling -> what it refuses
 * to claim -> an ask that costs the reader nothing.
 *
 * The ask is deliberately NOT "upload your campaign data". That is the
 * highest-trust action in the product, and asking for it before demonstrating
 * anything is why it gets refused.
 */

const highTier = TIERS.find((t) => t.tier === "high")!;

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

const CAPTURED = Math.round(
  ((PERFORMANCE.rankerAccuracy - PERFORMANCE.chance) /
    (PERFORMANCE.oracleCeiling - PERFORMANCE.chance)) *
    100,
);

const CAPABILITIES = [
  {
    tag: "Rank",
    tagClass: "tag-blue",
    title: "Know which variant wins before you spend",
    body:
      "Give it two or more versions of a headline and it picks the likely " +
      "winner — or tells you the two are too close to call, which is the more " +
      "useful answer when it is true.",
    href: "/compare",
    cta: "Compare copy",
    span: "sm:col-span-6",
  },
  {
    tag: "Diagnose",
    tagClass: "tag-green",
    title: "Six constructs, scored against your audience",
    body:
      "Salience, affect, valuation, encoding, approach and control — computed " +
      "from published human word ratings, with the demographic ratings applied " +
      "for the segment you specify.",
    href: "/analyse",
    cta: "Analyse copy",
    span: "sm:col-span-2",
  },
  {
    tag: "Allocate",
    tagClass: "tag-yellow",
    title: "Stop paying to learn what you already knew",
    body:
      "Seed a bandit with the model's prediction instead of splitting evenly. " +
      "Simulated on held-out experiments: 31.8% fewer impressions wasted on " +
      "losing variants than an even A/B test.",
    href: "/allocate",
    cta: "Split budget",
    span: "sm:col-span-2",
  },
  {
    tag: "Measure",
    tagClass: "tag-red",
    title: "Find out if any of this works on your campaigns",
    body:
      "Seal a prediction before launch, record the winner afterwards. The " +
      "track record is yours, not ours — including your own blind picks, so " +
      "you learn how your judgement scores too.",
    href: "/track",
    cta: "Track record",
    span: "sm:col-span-2",
  },
];

export default function Home() {
  return (
    <div className="space-y-28 sm:space-y-36">
      {/* ------------------------------------------------------------ hero */}
      <section className="space-y-8" data-reveal>
        <p className="eyebrow">Behavioural analysis for campaign copy</p>
        <h1 className="display max-w-3xl text-[2.75rem] sm:text-[4rem]">
          Which headline wins, and how confident we actually are.
        </h1>
        <p className="max-w-xl text-[1.0625rem] leading-relaxed text-muted">
          Resonance ranks marketing copy and profiles it against published
          behavioural science. Built on the {PERFORMANCE.trainingData} — real
          randomised experiments with real click outcomes, not opinion.
        </p>
        <div className="flex flex-wrap items-center gap-3">
          <Link href="/compare" className="btn btn-primary">
            Try it on copy you already have
          </Link>
          <Link href="/methodology" className="btn btn-secondary">
            Read how it was measured
          </Link>
        </div>
        <p className="text-sm text-faint">
          No account, no upload, nothing stored. Paste two headlines and see
          what it says.
        </p>
      </section>

      {/* -------------------------------------------------- product preview */}
      <section data-reveal>
        <FauxWindow />
      </section>

      {/* --------------------------------------------------------- bento */}
      <section className="space-y-10">
        <div className="max-w-2xl space-y-3" data-reveal>
          <p className="eyebrow">What it does</p>
          <h2 className="display text-3xl sm:text-4xl">
            Four decisions, each with its own evidence.
          </h2>
        </div>
        <div className="grid gap-4 sm:grid-cols-6">
          {CAPABILITIES.map((c, i) => (
            <div
              key={c.href}
              className={`card card-hover flex flex-col p-7 sm:p-8 ${c.span}`}
              data-reveal
              style={{ ["--index" as string]: i }}
            >
              <span className={`tag ${c.tagClass} self-start`}>{c.tag}</span>
              <h3 className="mt-5 text-lg font-medium tracking-[-0.01em]">
                {c.title}
              </h3>
              <p className="mt-3 flex-1 text-sm leading-relaxed text-muted">
                {c.body}
              </p>
              <Link
                href={c.href}
                className="mt-6 inline-flex items-center gap-1.5 text-sm font-medium text-ink underline decoration-rule-strong underline-offset-4 transition-colors hover:decoration-ink"
              >
                {c.cta}
                <Arrow />
              </Link>
            </div>
          ))}
        </div>
      </section>

      {/* -------------------------------------------------------- numbers */}
      <section className="space-y-10">
        <div className="max-w-2xl space-y-3" data-reveal>
          <p className="eyebrow">Measured, not claimed</p>
          <h2 className="display text-3xl sm:text-4xl">
            {pct(PERFORMANCE.rankerAccuracy)} sounds modest until you know the
            ceiling.
          </h2>
        </div>

        <div className="grid gap-4 sm:grid-cols-4" data-reveal>
          <Metric label="Chance" value={pct(PERFORMANCE.chance)} note="a coin" />
          <Metric
            label="This model"
            value={pct(PERFORMANCE.rankerAccuracy)}
            note={`CI ${pct(PERFORMANCE.rankerCi95[0])}–${pct(PERFORMANCE.rankerCi95[1])}`}
            emphasis
          />
          <Metric
            label="Measured ceiling"
            value={pct(PERFORMANCE.oracleCeiling)}
            note="no model can exceed"
          />
          <Metric
            label="Signal captured"
            value={`${CAPTURED}%`}
            note="of what is achievable"
          />
        </div>

        <div className="grid gap-8 sm:grid-cols-2" data-reveal>
          <div className="space-y-4 text-sm leading-relaxed text-muted">
            <p>
              Click outcomes are noisy measurements. On this corpus only about{" "}
              <span className="numeric text-ink">
                {Math.round(PERFORMANCE.signalFraction * 100)}%
              </span>{" "}
              of the variance in the results is real signal — the rest is
              sampling noise. So{" "}
              <span className="text-ink">
                a model with perfect knowledge would still only score{" "}
                {pct(PERFORMANCE.oracleCeiling)}
              </span>
              . We measured that ceiling rather than assuming it.
            </p>
            <p>
              Evaluated on{" "}
              <span className="numeric text-ink">
                {PERFORMANCE.nExperiments.toLocaleString()}
              </span>{" "}
              held-out experiments and{" "}
              <span className="numeric text-ink">
                {PERFORMANCE.nPairs.toLocaleString()}
              </span>{" "}
              copy pairs, with intervals clustered by experiment because pairs
              from one experiment are not independent.
            </p>
          </div>

          <div className="card p-7 sm:p-8">
            <span className="tag tag-green self-start">Knows when it knows</span>
            <p className="mt-5 text-sm leading-relaxed text-muted">
              On the{" "}
              <span className="numeric text-ink">
                {Math.round(highTier.coverage * 100)}%
              </span>{" "}
              of comparisons where the margin is widest, accuracy rises to{" "}
              <span className="numeric text-ink">{pct(highTier.accuracy)}</span>.
              On the rest it declines to call it. A tool that abstains on the
              hard cases is worth more than one that guesses confidently on all
              of them.
            </p>
          </div>
        </div>
      </section>

      {/* --------------------------------------------------------- trust */}
      <section className="grid gap-12 sm:grid-cols-2">
        <div className="space-y-5" data-reveal>
          <p className="eyebrow">Refusals</p>
          <h2 className="display text-2xl sm:text-3xl">
            What this will never claim.
          </h2>
          <ul className="space-y-3 text-sm text-muted">
            {PROHIBITED_CLAIMS.map((c) => (
              <li key={c} className="flex gap-3">
                <Barred />
                <span>{c}</span>
              </li>
            ))}
          </ul>
          <p className="text-sm text-faint">
            Enforced in the codebase, not just written down. Four hypotheses
            that failed are documented on the{" "}
            <Link
              href="/methodology"
              className="text-ink underline decoration-rule-strong underline-offset-4"
            >
              methodology page
            </Link>{" "}
            alongside the ones that worked.
          </p>
        </div>

        <div className="space-y-5" data-reveal>
          <p className="eyebrow">Data protection</p>
          <h2 className="display text-2xl sm:text-3xl">Your data does not move.</h2>
          <p className="text-sm leading-relaxed text-muted">
            Resonance makes no outbound network calls at runtime. Models run
            in-process, and the encoder is fetched once at build time then
            locked to local files — there is no setting that re-enables a remote
            fetch. Verify it rather than trust it:
          </p>
          <pre className="overflow-x-auto rounded-lg border border-rule bg-sunk p-4 font-mono text-xs text-muted">
            docker compose run --rm --network none app npm run selftest
          </pre>
          <p className="text-sm leading-relaxed text-muted">
            Or skip the server entirely — <code>npm run desktop</code> builds a
            local app whose campaign data never leaves the machine it runs on.
            Uploads containing emails, phone numbers, addresses, IPs or card
            numbers are rejected at ingest rather than stored and redacted.
          </p>
        </div>
      </section>

      {/* ------------------------------------------------------ limitation */}
      <section className="card p-8 sm:p-12" data-reveal>
        <span className="tag tag-yellow">Stated up front</span>
        <h2 className="display mt-5 max-w-3xl text-2xl sm:text-3xl">
          The training data is 2013–15 viral media. You are probably not that.
        </h2>
        <p className="mt-5 max-w-3xl text-sm leading-relaxed text-muted">
          It is the honest limitation, so it goes here rather than in a
          footnote: the constructs transfer across domains more readily than the
          calibration does. A model refitted on your own campaign results should
          be expected to beat the global one. That is the intended path, not a
          workaround — but the tool is useful before you get there, which is why
          nothing above requires you to hand over anything.
        </p>
        <div className="mt-7 flex flex-wrap gap-3">
          <Link href="/track" className="btn btn-primary">
            Measure it on your own campaigns
          </Link>
          <Link href="/upload" className="btn btn-secondary">
            Check whether your exports are usable
          </Link>
        </div>
      </section>
    </div>
  );
}

/* -------------------------------------------------------------- fragments */

function Metric({
  label,
  value,
  note,
  emphasis,
}: {
  label: string;
  value: string;
  note: string;
  emphasis?: boolean;
}) {
  return (
    <div
      className={`card p-6 ${emphasis ? "bg-sunk" : ""}`}
    >
      <div className="eyebrow">{label}</div>
      <div className="numeric mt-3 text-3xl text-ink">{value}</div>
      <div className="mt-1.5 text-xs text-faint">{note}</div>
    </div>
  );
}

/**
 * A framed preview of the real output, rather than a description of it.
 *
 * The example deliberately shows an ABSTENTION. The instinct is to demo the
 * confident case, but "too close to call" is the behaviour that distinguishes
 * this from every tool that always has an answer, so it is what the front page
 * shows.
 */
function FauxWindow() {
  return (
    <div className="card overflow-hidden">
      <div className="flex items-center gap-2 border-b border-rule bg-sunk px-4 py-3">
        <span className="h-2.5 w-2.5 rounded-full bg-rule-strong" />
        <span className="h-2.5 w-2.5 rounded-full bg-rule-strong" />
        <span className="h-2.5 w-2.5 rounded-full bg-rule-strong" />
        <span className="ml-3 font-mono text-[0.6875rem] text-faint">
          resonance — compare
        </span>
      </div>

      <div className="space-y-5 p-6 sm:p-10">
        <div className="rounded-lg border border-rule bg-pale-yellow/60 p-4 text-sm text-pale-yellow-ink">
          These variants score too closely to separate. At margins this small
          the model is near chance, so the honest answer is that we cannot tell
          them apart — pick on other grounds, or run a live test.
        </div>

        <ol className="space-y-3">
          {[
            { rank: 1, score: "-1.809", text: "The heating fix most homes miss" },
            {
              rank: 2,
              score: "-2.126",
              text: "Cut your heating bill with one simple change",
            },
          ].map((r) => (
            <li
              key={r.rank}
              className="flex items-baseline justify-between gap-6 rounded-lg border border-rule p-4"
            >
              <div className="flex items-baseline gap-4">
                <span className="numeric text-xs text-faint">
                  {String(r.rank).padStart(2, "0")}
                </span>
                <span className="text-sm">{r.text}</span>
              </div>
              <span className="numeric shrink-0 text-xs text-faint">
                {r.score}
              </span>
            </li>
          ))}
        </ol>

        <div className="flex flex-wrap items-center gap-3 border-t border-rule pt-5">
          <span className="tag tag-red">Confidence: insufficient</span>
          <span className="text-xs text-faint">
            Press <kbd>&#8984;</kbd> <kbd>&#8629;</kbd> to rank
          </span>
        </div>
      </div>
    </div>
  );
}

function Arrow() {
  return (
    <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden="true">
      <path
        d="M2.5 6h7M6.5 3l3 3-3 3"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Barred() {
  return (
    <svg
      width="14"
      height="14"
      viewBox="0 0 14 14"
      fill="none"
      aria-hidden="true"
      className="mt-1 shrink-0 text-faint"
    >
      <circle cx="7" cy="7" r="5.25" stroke="currentColor" strokeWidth="1.5" />
      <path d="M3.5 10.5 10.5 3.5" stroke="currentColor" strokeWidth="1.5" />
    </svg>
  );
}
