/**
 * One-off: migrate the page components from Tailwind's zinc palette to the
 * semantic tokens in app/globals.css.
 *
 * Written as a script rather than done by hand because the same dozen
 * substitutions recur across six files, and a manual pass over ~140 sites is
 * where typos and missed `dark:` twins come from. Each token pair encodes a
 * MEANING — surface, rule, muted — so the dark variants disappear entirely:
 * the palette inverts once in CSS instead of at every element.
 *
 * Not intended to be re-run. Kept in the tree as the record of what changed.
 */

import { readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));

const FILES = [
  "app/compare/page.tsx",
  "app/analyse/page.tsx",
  "app/allocate/page.tsx",
  "app/track/page.tsx",
  "app/upload/page.tsx",
  "app/methodology/page.tsx",
];

/** Order matters: longer, more specific patterns first. */
const RULES = [
  // Paired light/dark declarations collapse to a single token.
  [/\btext-zinc-600 dark:text-zinc-400\b/g, "text-muted"],
  [/\btext-zinc-700 dark:text-zinc-300\b/g, "text-muted"],
  [/\btext-zinc-800 dark:text-zinc-200\b/g, "text-ink"],
  [/\btext-zinc-900 dark:text-zinc-100\b/g, "text-ink"],
  [/\bborder-zinc-200 dark:border-zinc-800\b/g, "border-rule"],
  [/\bborder-zinc-300 dark:border-zinc-700\b/g, "border-rule-strong"],
  [/\bborder-zinc-100 dark:border-zinc-900\b/g, "border-rule"],
  [/\bbg-zinc-100 dark:bg-zinc-900\b/g, "bg-sunk"],
  [/\bbg-zinc-200 dark:bg-zinc-800\b/g, "bg-sunk"],
  [
    /\bbg-white p-3 font-mono text-xs dark:border-zinc-700 dark:bg-zinc-900\b/g,
    "bg-surface p-3 font-mono text-xs",
  ],
  [/\bbg-white dark:bg-zinc-900\b/g, "bg-surface"],
  [/\bhover:bg-zinc-50 dark:hover:bg-zinc-900\b/g, "hover:bg-sunk"],
  [
    /\bbg-zinc-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-40 dark:bg-zinc-100 dark:text-zinc-900\b/g,
    "btn btn-primary disabled:opacity-40",
  ],

  // Then the unpaired stragglers.
  [/\btext-zinc-500\b/g, "text-faint"],
  [/\btext-zinc-600\b/g, "text-muted"],
  [/\btext-zinc-700\b/g, "text-muted"],
  [/\btext-zinc-900\b/g, "text-ink"],
  [/\bborder-zinc-200\b/g, "border-rule"],
  [/\bborder-zinc-300\b/g, "border-rule-strong"],
  [/\bborder-zinc-800\b/g, "border-rule"],
  [/\bborder-zinc-700\b/g, "border-rule-strong"],
  [/\bbg-zinc-100\b/g, "bg-sunk"],
  [/\bbg-white\b/g, "bg-surface"],

  // Semantic state colours move onto the pastel scale.
  [
    /\bbg-emerald-50 text-emerald-900 dark:bg-emerald-950 dark:text-emerald-200\b/g,
    "bg-pale-green text-pale-green-ink",
  ],
  [
    /\bbg-amber-50 text-amber-900 dark:bg-amber-950 dark:text-amber-200\b/g,
    "bg-pale-yellow text-pale-yellow-ink",
  ],
  [
    /\bborder-amber-300 bg-amber-50 p-4 text-sm text-amber-900 dark:border-amber-800 dark:bg-amber-950 dark:text-amber-200\b/g,
    "border-rule bg-pale-yellow p-4 text-sm text-pale-yellow-ink",
  ],
  [
    /\bborder-orange-300 bg-orange-50 p-4 text-sm text-orange-900 dark:border-orange-800 dark:bg-orange-950 dark:text-orange-200\b/g,
    "border-rule bg-pale-yellow p-4 text-sm text-pale-yellow-ink",
  ],
  [
    /\bborder-red-300 bg-red-50 p-4 text-sm text-red-900 dark:border-red-800 dark:bg-red-950 dark:text-red-200\b/g,
    "border-rule bg-pale-red p-4 text-sm text-pale-red-ink",
  ],
  [
    /\bbg-red-50 p-3 text-sm text-red-700 dark:bg-red-950 dark:text-red-300\b/g,
    "bg-pale-red p-3 text-sm text-pale-red-ink",
  ],
  [
    /\btext-orange-700 dark:text-orange-300\b/g,
    "text-pale-red-ink",
  ],
  [
    /\btext-emerald-700 dark:text-emerald-400\b/g,
    "text-pale-green-ink",
  ],
  [/\btext-red-600 dark:text-red-400\b/g, "text-pale-red-ink"],

  // Headings become editorial.
  [
    /className="text-2xl font-semibold tracking-tight"/g,
    'className="display text-3xl sm:text-4xl"',
  ],
  [/\brounded-lg border border-rule p-4\b/g, "card p-5"],

  // ---- second pass: the leftovers the first pass exposed -----------------
  // Semantic state colours that were not part of a recognised pair.
  [/\bbg-emerald-400\/50\b/g, "bg-pale-green-ink/40"],
  [/\bbg-zinc-400\/40 dark:bg-zinc-600\/40\b/g, "bg-rule-strong"],
  [/\bbg-zinc-900 dark:bg-sunk\b/g, "bg-ink"],
  [/\bborder-zinc-900 bg-zinc-900 text-white dark:border-zinc-100 dark:bg-sunk dark:text-ink\b/g,
    "border-ink bg-ink text-inverse"],
  [/\bbg-zinc-200 px-1\.5 py-0\.5 text-xs dark:bg-zinc-800\b/g,
    "bg-sunk px-1.5 py-0.5 text-xs"],
  [/\bhover:bg-zinc-50 disabled:opacity-40 dark:border-rule-strong dark:hover:bg-zinc-900\b/g,
    "hover:bg-sunk disabled:opacity-40"],
  [/\bborder-zinc-500\b/g, "border-faint"],
  [/\bbg-zinc-200\b/g, "bg-sunk"],
  [/\bbg-zinc-900\b/g, "bg-ink"],
  [/\btext-white\b/g, "text-inverse"],

  // Redundant dark: twins the token migration made meaningless. The palette
  // already inverts in CSS; leaving these would pin an element to one theme.
  [/ dark:(?:bg|text|border|hover:bg|hover:text)-(?:rule|rule-strong|sunk|ink|muted|faint|surface|inverse)\b/g, ""],
  [/ dark:hover:bg-zinc-900\b/g, ""],
  [/ dark:bg-zinc-900\b/g, ""],
  [/ dark:bg-zinc-800\b/g, ""],
  [/ dark:border-zinc-100\b/g, ""],

  // Radius conflicts: .btn already sets one, a utility beside it fights it.
  [/\brounded-md btn btn-primary\b/g, "btn btn-primary"],
];

let total = 0;
for (const rel of FILES) {
  const path = join(ROOT, rel);
  let src = await readFile(path, "utf-8");
  const before = src;
  for (const [pattern, replacement] of RULES) {
    src = src.replace(pattern, replacement);
  }
  if (src !== before) {
    await writeFile(path, src, "utf-8");
    const changed = before.split("\n").filter((l, i) => l !== src.split("\n")[i]).length;
    total += changed;
    console.log(`${rel}: ${changed} lines`);
  }
}

// A leftover `dark:` means a pair this script did not know about, which would
// render wrong in one theme only — the kind of thing nobody notices until a
// screenshot. Report rather than fail; the remainder gets handled by hand.
for (const rel of FILES) {
  const src = await readFile(join(ROOT, rel), "utf-8");
  const left = (src.match(/dark:|zinc-/g) ?? []).length;
  if (left) console.log(`  REMAINING in ${rel}: ${left}`);
}
console.log(`\n${total} lines rewritten`);
