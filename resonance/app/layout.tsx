import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";
import { Reveal } from "./reveal";
import { PERFORMANCE } from "@/lib/constructs";

/**
 * Fonts come from app/globals.css as system-first stacks.
 *
 * `next/font/google` was removed and must not come back: it fetches from
 * fonts.gstatic.com at build time, which breaks the no-egress guarantee in
 * docs/SELF_HOSTING.md. A customer running with `--network none` to check that
 * claim would find the build failing.
 */

export const metadata: Metadata = {
  title: "Resonance — behavioural analysis for campaign copy",
  description:
    "Rank and diagnose marketing copy against published behavioural science. " +
    "A decision aid, not an outcome predictor.",
};

const NAV = [
  { href: "/compare", label: "Compare" },
  { href: "/analyse", label: "Analyse" },
  { href: "/allocate", label: "Split budget" },
  { href: "/track", label: "Track record" },
  { href: "/upload", label: "Upload" },
  { href: "/methodology", label: "Methodology" },
] as const;

export default function RootLayout({ children }: LayoutProps<"/">) {
  const pct = (x: number) => `${(x * 100).toFixed(1)}%`;

  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full flex flex-col bg-canvas text-ink">
        <div className="ambient" aria-hidden="true" />

        <header className="sticky top-0 z-20 border-b border-rule bg-canvas/80 backdrop-blur-md">
          <nav className="mx-auto flex max-w-6xl flex-wrap items-center gap-x-8 gap-y-2 px-6 py-4">
            <Link
              href="/"
              className="display text-lg tracking-[-0.02em] text-ink"
            >
              Resonance
            </Link>
            <div className="flex flex-wrap gap-x-5 gap-y-1 text-[0.8125rem]">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="text-muted transition-colors hover:text-ink"
                >
                  {n.label}
                </Link>
              ))}
            </div>
          </nav>
        </header>

        <main className="relative z-10 mx-auto w-full max-w-6xl flex-1 px-6 py-16 sm:py-24">
          {children}
        </main>

        {/* The limits belong on every page, not buried in a methodology tab. */}
        <footer className="relative z-10 border-t border-rule px-6 py-10">
          <div className="mx-auto flex max-w-6xl flex-col gap-3 text-xs leading-relaxed text-muted sm:flex-row sm:items-start sm:justify-between">
            <p className="max-w-2xl">
              Resonance ranks and diagnoses copy. It does not predict
              conversions, revenue or ROI, and it does not measure brain
              activity. Ranking accuracy is{" "}
              <span className="numeric text-ink">
                {pct(PERFORMANCE.rankerAccuracy)}
              </span>{" "}
              against a {pct(PERFORMANCE.chance)} baseline and a measured{" "}
              <span className="numeric text-ink">
                {pct(PERFORMANCE.oracleCeiling)}
              </span>{" "}
              ceiling — low because only ~
              {Math.round(PERFORMANCE.signalFraction * 100)}% of the variance in
              the training labels is signal rather than sampling noise.
            </p>
            <Link
              href="/methodology"
              className="shrink-0 text-ink underline decoration-rule-strong underline-offset-4 hover:decoration-ink"
            >
              How this was measured
            </Link>
          </div>
        </footer>

        <Reveal />
      </body>
    </html>
  );
}
