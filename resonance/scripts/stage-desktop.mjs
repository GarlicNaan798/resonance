/**
 * Finish the standalone build so it can actually serve.
 *
 * `next build` with output:"standalone" traces the server's dependencies but
 * deliberately leaves out two directories, because a containerised deployment
 * usually serves them from a CDN:
 *
 *   .next/static  — the JS and CSS the browser loads
 *   public        — static assets
 *
 * A desktop app has no CDN. Without this step the window opens to an unstyled
 * page with no client JS, which looks like a broken app rather than a missing
 * copy step. Documented Next behaviour, and the single most common way a
 * standalone build ships broken.
 */

import { cp, access } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const STANDALONE = join(ROOT, ".next", "standalone");

async function exists(p) {
  try {
    await access(p);
    return true;
  } catch {
    return false;
  }
}

if (!(await exists(join(STANDALONE, "server.js")))) {
  console.error(
    "No .next/standalone/server.js — run `next build` with " +
      'output: "standalone" in next.config.ts first.',
  );
  process.exit(1);
}

await cp(join(ROOT, ".next", "static"), join(STANDALONE, ".next", "static"), {
  recursive: true,
});
console.log("copied .next/static");

if (await exists(join(ROOT, "public"))) {
  await cp(join(ROOT, "public"), join(STANDALONE, "public"), { recursive: true });
  console.log("copied public");
}

// The encoder is the whole no-egress claim. A desktop build that ships without
// it would fall back to... nothing, since the runtime is locked offline — the
// app would start and then fail on first inference. Better to fail here.
if (!(await exists(join(ROOT, "models", "Xenova", "all-MiniLM-L6-v2", "onnx", "model.onnx")))) {
  console.error("Encoder weights missing. Run `npm run fetch-encoder`.");
  process.exit(1);
}
console.log("encoder present");
console.log("staged. `electron .` will now serve a complete app.");
