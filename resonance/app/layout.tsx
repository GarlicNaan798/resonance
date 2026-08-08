import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

/**
 * System fonts, deliberately — `next/font/google` was removed.
 *
 * It fetches from fonts.gstatic.com at build time, which breaks the no-egress
 * guarantee in docs/SELF_HOSTING.md: a customer running with `--network none`
 * to verify that claim would find the build failing. Self-hosted deployments
 * must make no outbound calls, and that has to include the font pipeline.
 *
 * It also means the app builds in an air-gapped environment, which is how it
 * surfaced.
 */
const FONT_STACK =
  'ui-sans-serif, system-ui, -apple-system, "Segoe UI", Roboto, ' +
  '"Helvetica Neue", Arial, sans-serif';

export const metadata: Metadata = {
  title: "Resonance — behavioural analysis for campaign copy",
  description:
    "Score and compare marketing copy against published behavioural science. " +
    "A decision aid, not an outcome predictor.",
};

const NAV = [
  { href: "/analyse", label: "Analyse" },
  { href: "/compare", label: "Compare" },
  { href: "/allocate", label: "Split budget" },
  { href: "/upload", label: "Upload data" },
  { href: "/methodology", label: "Methodology" },
] as const;

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html lang="en" className="h-full antialiased">
      <body
        style={{ fontFamily: FONT_STACK }}
        className="min-h-full flex flex-col bg-zinc-50 text-zinc-900 dark:bg-zinc-950 dark:text-zinc-100"
      >
        <header className="border-b border-zinc-200 dark:border-zinc-800">
          <nav className="mx-auto flex max-w-5xl items-center gap-6 px-6 py-4">
            <Link href="/" className="font-semibold tracking-tight">
              Resonance
            </Link>
            <div className="flex gap-4 text-sm">
              {NAV.map((n) => (
                <Link
                  key={n.href}
                  href={n.href}
                  className="text-zinc-600 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
                >
                  {n.label}
                </Link>
              ))}
            </div>
          </nav>
        </header>

        <main className="mx-auto w-full max-w-5xl flex-1 px-6 py-10">
          {children}
        </main>

        {/* The limits belong on every page, not buried in a methodology tab. */}
        <footer className="border-t border-zinc-200 px-6 py-6 text-xs leading-relaxed text-zinc-500 dark:border-zinc-800 dark:text-zinc-400">
          <div className="mx-auto max-w-5xl">
            Resonance ranks and diagnoses copy. It does not predict conversions,
            revenue or ROI, and it does not measure brain activity. Ranking
            accuracy is 59.4% against a 50% baseline and a measured 66.2%
            ceiling — the ceiling is low because only ~12% of the variance in
            the training labels is signal rather than sampling noise.{" "}
            <Link href="/methodology" className="underline">
              How this was measured
            </Link>
            .
          </div>
        </footer>
      </body>
    </html>
  );
}
