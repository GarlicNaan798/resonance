import Link from "next/link";
import { PERFORMANCE, PROHIBITED_CLAIMS } from "@/lib/constructs";
import { TIERS } from "@/lib/inference/ranker";

/**
 * The pitch.
 *
 * Ordering is the whole design here. The honest numbers are the differentiator
 * against neuromarketing vendors, but leading with "61.8%" reads as "coin flip
 * plus a bit" to anyone who has not yet been told the ceiling is 66.2%. So:
 * what it does -> what it is worth -> the numbers, framed against the ceiling
 * -> what it refuses to claim -> an ask that costs the reader nothing.
 *
 * The ask deliberately is NOT "upload your campaign data". That is the
 * highest-trust action in the product and asking for it before demonstrating
 * anything is why it gets refused.
 */

const highTier = TIERS.find((t) => t.tier === "high")!;

const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

const CAPTURED = Math.round(
  ((PERFORMANCE.rankerAccuracy - PERFORMANCE.chance) /
    (PERFORMANCE.oracleCeiling - PERFORMANCE.chance)) *
    100,
);

const DOES = [
  {
    title: "Rank variants before you spend",
    body:
      "Give it two or more versions of a headline and it picks the likely " +
      "winner — and tells you when the two are too close to call rather than " +
      "guessing.",
    href: "/compare",
    cta: "Compare copy",
  },
  {
    title: "Diagnose copy against an audience",
    body:
      "Six behavioural constructs scored from published human word ratings, " +
      "with the demographic ratings applied for the segment you specify.",
    href: "/analyse",
    cta: "Analyse copy",
  },
  {
    title: "Split budget across variants",
    body:
      "Seed a bandit with the model's prediction instead of splitting evenly. " +
      "In simulation on held-out experiments this wasted 31.8% fewer " +
      "impressions than a full even A/B test.",
    href: "/allocate",
    cta: "Split budget",
  },
];

export default function Home() {
  return (
    <div className="space-y-16">
      <section className="space-y-5">
        <h1 className="max-w-2xl text-3xl font-semibold leading-tight tracking-tight">
          Which headline wins, and how confident we actually are.
        </h1>
        <p className="max-w-2xl text-zinc-600 dark:text-zinc-400">
          Resonance ranks marketing copy and profiles it against published
          behavioural science. It was built on the{" "}
          {PERFORMANCE.trainingData} — real randomised experiments with real
          click outcomes, not opinion.
        </p>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/compare"
            className="rounded-md bg-zinc-900 px-4 py-2 text-sm font-medium text-white dark:bg-zinc-100 dark:text-zinc-900"
          >
            Try it on copy you already have
          </Link>
          <Link
            href="/methodology"
            className="rounded-md border border-zinc-300 px-4 py-2 text-sm font-medium dark:border-zinc-700"
          >
            Read how it was measured
          </Link>
        </div>
        <p className="text-xs text-zinc-500">
          No account, no upload, nothing stored. Paste two headlines and see
          what it says.
        </p>
      </section>

      <section className="grid gap-4 sm:grid-cols-3">
        {DOES.map((d) => (
          <div
            key={d.href}
            className="flex flex-col rounded-lg border border-zinc-200 p-4 dark:border-zinc-800"
          >
            <h2 className="font-medium">{d.title}</h2>
            <p className="mt-2 flex-1 text-sm text-zinc-600 dark:text-zinc-400">
              {d.body}
            </p>
            <Link
              href={d.href}
              className="mt-3 text-sm font-medium underline underline-offset-4"
            >
              {d.cta}
            </Link>
          </div>
        ))}
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">The numbers, in context</h2>
        <div className="space-y-3 rounded-lg bg-zinc-100 p-5 text-sm dark:bg-zinc-900">
          <p>
            The model picks the winning variant{" "}
            <strong>{pct(PERFORMANCE.rankerAccuracy)}</strong> of the time
            against a {pct(PERFORMANCE.chance)} coin flip. That sounds modest
            until you know the ceiling.
          </p>
          <p>
            Click outcomes are noisy measurements. On this corpus only ~
            {Math.round(PERFORMANCE.signalFraction * 100)}% of the variance in
            the results is real signal — the rest is sampling noise — so{" "}
            <strong>
              a model with perfect knowledge would still only score{" "}
              {pct(PERFORMANCE.oracleCeiling)}
            </strong>
            . We measured that ceiling rather than assuming it. Against it, the
            model captures <strong>{CAPTURED}%</strong> of the signal that is
            there to capture.
          </p>
          <p>
            And it knows when it does not know. On the{" "}
            {Math.round(highTier.coverage * 100)}% of comparisons where it is
            most confident, accuracy is{" "}
            <strong>{pct(highTier.accuracy)}</strong>. On the rest it says the
            comparison is too close to call, which is a more useful answer than
            a confident guess.
          </p>
        </div>
      </section>

      <section className="grid gap-6 sm:grid-cols-2">
        <div className="space-y-3">
          <h2 className="text-lg font-medium">What it will not claim</h2>
          <ul className="list-disc space-y-1 pl-5 text-sm text-zinc-600 dark:text-zinc-400">
            {PROHIBITED_CLAIMS.map((c) => (
              <li key={c}>{c}</li>
            ))}
          </ul>
          <p className="text-sm text-zinc-500">
            These are enforced in the codebase, not just written down. Four
            hypotheses that failed are documented on the{" "}
            <Link href="/methodology" className="underline">
              methodology page
            </Link>{" "}
            alongside the ones that worked.
          </p>
        </div>

        <div className="space-y-3">
          <h2 className="text-lg font-medium">Your data does not move</h2>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Resonance makes <strong>no outbound network calls at runtime</strong>.
            Models run in-process, and the encoder is fetched once at build time
            and then locked to local files — there is no setting that re-enables
            a remote fetch. You can verify the claim rather than trust it: run it
            with networking disabled and it still works.
          </p>
          <pre className="overflow-x-auto rounded-md bg-zinc-100 p-3 font-mono text-xs dark:bg-zinc-900">
            docker compose run --rm --network none app npm run selftest
          </pre>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Or skip the server entirely — <code className="font-mono text-xs">npm run desktop</code>{" "}
            builds a local app whose campaign data never leaves the machine it
            runs on.
          </p>
          <p className="text-sm text-zinc-600 dark:text-zinc-400">
            Uploads containing emails, phone numbers, addresses, IPs or card
            numbers are rejected at ingest — not stored and redacted. The tool
            needs aggregate copy performance and nothing about individuals.
          </p>
        </div>
      </section>

      <section className="space-y-3 rounded-lg border border-zinc-200 p-5 dark:border-zinc-800">
        <h2 className="text-lg font-medium">
          The training data is 2013–15 viral media. You are probably not that.
        </h2>
        <p className="max-w-3xl text-sm text-zinc-600 dark:text-zinc-400">
          Stated up front because it is the honest limitation: the constructs
          transfer across domains more readily than the calibration does. A
          model refitted on your own campaign results should be expected to beat
          the global one. That is the intended path, not a workaround — but the
          tool is useful before you get there, which is why nothing above
          requires you to hand over anything.
        </p>
        <Link
          href="/upload"
          className="inline-block text-sm font-medium underline underline-offset-4"
        >
          What a recalibration export would need
        </Link>
      </section>
    </div>
  );
}
