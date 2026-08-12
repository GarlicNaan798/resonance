import { MODULES, PERFORMANCE, PROHIBITED_CLAIMS } from "@/lib/constructs";
import { AUDIENCE_LIMITATION } from "@/lib/audience";
import { SEGMENT_LIMITATION } from "@/lib/segments";

/**
 * The methodology page.
 *
 * Written for the person whose job is to find the hole in this — a client's
 * data scientist, or a CMO who has been sold neuromarketing before. Every
 * number is stated with its uncertainty, every limitation is here rather than
 * in a footnote, and the negative results are included because a tool that
 * only reports its wins has not earned trust.
 */

export const metadata = {
  title: "Methodology — Resonance",
  description:
    "How Resonance was built and measured, including what it cannot do.",
};

function Stat({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="card p-5">
      <div className="text-xs text-faint">{label}</div>
      <div className="mt-1 font-mono text-xl tabular-nums">{value}</div>
      {sub && <div className="mt-1 text-xs text-faint">{sub}</div>}
    </div>
  );
}

const NEGATIVE_RESULTS = [
  {
    what: "28 extra interpretable features",
    detail:
      "Discrete emotion (NRC), curiosity gap (Loewenstein), self-reference " +
      "(Rogers et al.), word frequency, social proof (Cialdini).",
    result: "−0.0009",
    verdict: "No effect. Discarded.",
  },
  {
    what: "Identifiable-individual features",
    detail:
      "Derived by reading the pairs the semantic model got right and the " +
      "interpretable model got wrong (Small, Loewenstein & Slovic).",
    result: "+0.0057",
    verdict: "Below the 0.0232 noise floor. Discarded under a pre-registered rule.",
  },
  {
    what: "Pairwise interaction ranker",
    detail: "Feeding both variants together instead of scoring each alone.",
    result: "−0.0038",
    verdict: "The bi-encoder was not the bottleneck. Discarded.",
  },
  {
    what: "Larger encoder (mpnet-base, 768d)",
    detail:
      "An unpaired comparison suggested +0.0215, apparently clearing the bar. " +
      "A paired test — correct, since both models score the same experiments — " +
      "gave +0.0128, CI [−0.0119, +0.0375].",
    result: "not significant",
    verdict: "Kept MiniLM. Avoided a 5× inference cost for noise.",
  },
];

export default function MethodologyPage() {
  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

  return (
    <div className="space-y-12">
      <section className="space-y-3">
        <p className="eyebrow">Evidence</p>
        <h1 className="display text-3xl sm:text-4xl">Methodology</h1>
        <p className="max-w-2xl text-sm text-muted">
          What this system does, how it was measured, and what it cannot do.
          Written to be checked rather than believed.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Measured performance</h2>
        <div className="grid gap-3 sm:grid-cols-4">
          <Stat label="Chance baseline" value={pct(PERFORMANCE.chance)} />
          <Stat
            label="Ranking model"
            value={pct(PERFORMANCE.rankerAccuracy)}
            sub={`95% CI ${pct(PERFORMANCE.rankerCi95[0])}–${pct(PERFORMANCE.rankerCi95[1])}`}
          />
          <Stat
            label="Diagnostic model"
            value={pct(PERFORMANCE.moduleModelAccuracy)}
            sub={`95% CI ${pct(PERFORMANCE.moduleModelCi95[0])}–${pct(PERFORMANCE.moduleModelCi95[1])}`}
          />
          <Stat
            label="Measured ceiling"
            value={pct(PERFORMANCE.oracleCeiling)}
            sub="no model can exceed this"
          />
        </div>

        <div className="space-y-3 rounded-lg bg-sunk p-4 text-sm">
          <p>
            <strong>Read accuracy against the ceiling, not against 100%.</strong>{" "}
            The training labels are noisy measurements — the median experiment
            arm had 3,118 impressions and 42 clicks — so a model with perfect
            knowledge of every headline&apos;s true click rate would still only
            agree with the recorded winner {pct(PERFORMANCE.oracleCeiling)} of
            the time. Only about{" "}
            {Math.round(PERFORMANCE.signalFraction * 100)}% of the variance in
            those labels is signal rather than sampling noise.
          </p>
          <p>
            Against that ceiling the ranking model captures{" "}
            <strong>
              {Math.round(
                ((PERFORMANCE.rankerAccuracy - PERFORMANCE.chance) /
                  (PERFORMANCE.oracleCeiling - PERFORMANCE.chance)) *
                  100,
              )}
              %
            </strong>{" "}
            of the achievable signal — computed from the figures above rather
            than quoted, so it cannot drift out of date.
          </p>
          <p>
            Evaluated on {PERFORMANCE.nExperiments.toLocaleString()} experiments
            and {PERFORMANCE.nPairs.toLocaleString()} pairs. Confidence intervals
            are clustered by experiment, because pairs drawn from the same
            experiment are not independent.
          </p>
          <p>
            Validation had been evaluated roughly ten times and was
            optimistically biased: both models fell about three points from
            validation to test, which is why only test figures appear here.
          </p>
          <p>
            <strong>On test-set reads.</strong> A static audit of the code finds
            two evaluations against the held-out set, plus one non-evaluative
            read that lifted six rows for parity fixtures. Until 2026-08-12
            those reads were neither gated nor recorded, so the historical count
            cannot be certified from the code alone — three project documents
            gave three different answers. Reads now require a written reason and
            append to a log, and the test partition is fingerprinted so a change
            to it is refused rather than silently revaluing every number here.
            The split was always grouped and deterministic, so the separation
            held and these figures stand; it was the record-keeping that did
            not.
          </p>
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Two layers, kept separate</h2>
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="card p-5 text-sm">
            <h3 className="font-medium">Ranking ({pct(PERFORMANCE.rankerAccuracy)})</h3>
            <p className="mt-2 text-muted">
              A model over sentence embeddings. Accurate, and uninterpretable —
              it cannot tell you why.
            </p>
          </div>
          <div className="card p-5 text-sm">
            <h3 className="font-medium">
              Diagnostic ({pct(PERFORMANCE.moduleModelAccuracy)})
            </h3>
            <p className="mt-2 text-muted">
              Six constructs from published human word ratings. Explainable, and
              a weak predictor.
            </p>
          </div>
        </div>
        <p className="text-sm text-muted">
          <strong>The diagnostic profile does not explain the ranking.</strong>{" "}
          The ranking model never sees those features. Presenting one as the
          reason for the other would be post-hoc rationalisation, so the two are
          reported separately even when they disagree — and when they disagree,
          that is information worth having.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">The six constructs</h2>
        <div className="space-y-4">
          {MODULES.map((m) => (
            <div
              key={m.id}
              className="card p-5"
            >
              <div className="flex flex-wrap items-baseline gap-x-3">
                <h3 className="font-medium">{m.label}</h3>
                <span className="text-xs text-faint">{m.functionalReferent}</span>
                {m.response === "inverted-u" && (
                  <span className="rounded bg-sunk px-1.5 py-0.5 text-xs">
                    inverted-U
                  </span>
                )}
              </div>
              <p className="mt-2 text-sm text-muted">
                {m.detail}
              </p>
              <p className="mt-2 text-sm text-faint">
                <strong>Limitation:</strong> {m.caveat}
              </p>
              <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-faint">
                {m.sources.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </div>
          ))}
        </div>
        <p className="rounded-lg bg-sunk p-4 text-sm">
          Modules are <em>named</em> for the functional systems the literature
          associates with each construct. That is an association for naming, not
          a measurement of neural activity. MacLean&apos;s triune brain and
          left/right hemisphere dominance are deliberately excluded — both are
          discredited as neuroscience despite their popularity in neuromarketing
          writing.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Training data</h2>
        <p className="text-sm text-muted">
          {PERFORMANCE.trainingData}, 150,624 arms. Randomised experiments were
          chosen over ad-library data deliberately: arms within one test share
          article, image and publication moment, so the within-test contrast
          isolates the effect of the words. Observational advertising data cannot
          support that inference.
        </p>
        <p className="text-sm text-muted">
          Word ratings come from Warriner et al. (2013), 13,905 words rated for
          valence, arousal and dominance, and Brysbaert et al. (2014), 39,954
          words rated for concreteness.
        </p>
        <div className="rounded-lg border border-rule bg-pale-yellow p-4 text-sm text-pale-yellow-ink">
          <strong>Domain shift is the main limitation.</strong> The training data
          is 2013–15 viral media. A B2B software or luxury retail advertiser is a
          different world, and the constructs transfer more readily than the
          calibration does. Recalibrating on your own campaign results is the
          intended remedy, and a recalibrated model beating the global one should
          be expected rather than surprising.
        </div>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">What did not work</h2>
        <p className="text-sm text-muted">
          Four hypotheses tested and rejected. Included because a tool that
          reports only its successes has not earned anyone&apos;s trust.
        </p>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[40rem] border-collapse text-sm">
            <thead>
              <tr className="border-b border-rule text-left">
                <th className="py-2 pr-4 font-medium">Hypothesis</th>
                <th className="py-2 pr-4 font-medium">Result</th>
                <th className="py-2 font-medium">Decision</th>
              </tr>
            </thead>
            <tbody>
              {NEGATIVE_RESULTS.map((n) => (
                <tr
                  key={n.what}
                  className="border-b border-rule align-top"
                >
                  <td className="py-3 pr-4">
                    <div className="font-medium">{n.what}</div>
                    <div className="mt-1 text-xs text-faint">{n.detail}</div>
                  </td>
                  <td className="py-3 pr-4 font-mono text-xs tabular-nums">
                    {n.result}
                  </td>
                  <td className="py-3 text-xs text-muted">
                    {n.verdict}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <p className="text-sm text-muted">
          Taken together: interpretable psycholinguistic features plateau around
          56%, semantic embeddings reach 62% on validation. No interpretable
          feature separated the two models&apos; disagreements by more than 0.11
          standard deviations. The remaining gap appears to be semantic content
          that word-rating norms cannot represent.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Leakage controls</h2>
        <ul className="list-disc space-y-2 pl-5 text-sm text-muted">
          <li>
            The corpus was 49% exact duplicates, with 89% of items in
            near-duplicate clusters. Splitting is therefore done on the
            transitive closure of shared test-id and shared headline — never on
            individual rows.
          </li>
          <li>
            Verified that no row, cluster or headline string crosses a split
            boundary. The test set is SHA-256 fingerprinted and locked.
          </li>
          <li>
            Feature standardisation is fitted on training data only.
          </li>
          <li>
            The source experiments varied headline <em>and</em> image, so 48% of
            raw pairs differ only by picture. Those are excluded — they are
            unpredictable from text by construction, and including them once
            produced a spurious below-chance result.
          </li>
          <li>
            A shuffled-label control runs throughout. Its deviation from chance
            (about 0.018–0.023) is the noise floor any claimed improvement must
            exceed.
          </li>
        </ul>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Audience and demographics</h2>
        <p className="text-sm text-muted">
          {SEGMENT_LIMITATION}
        </p>
        <p className="text-sm text-muted">
          {AUDIENCE_LIMITATION}
        </p>
        <p className="text-sm text-muted">
          Measured honestly: the demographic axes individually move rankings less
          than the noise floor (0.5–1.3% of pairs). The adjustment that clearly
          does move the model is <strong>involvement</strong>, which is not a
          demographic at all — it is a property of the purchase that you supply.
        </p>
      </section>

      <section className="space-y-4">
        <h2 className="text-lg font-medium">Claims this tool will not make</h2>
        <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
          {PROHIBITED_CLAIMS.map((c) => (
            <li key={c}>{c}</li>
          ))}
        </ul>
        <p className="text-sm text-faint">
          These are enumerated in the codebase, not just in this document.
        </p>
      </section>
    </div>
  );
}
