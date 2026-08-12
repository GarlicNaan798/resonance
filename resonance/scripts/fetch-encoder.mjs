/**
 * One-time encoder download. Run before building or packaging.
 *
 *   node scripts/fetch-encoder.mjs
 *
 * Why this exists. transformers.js will happily fetch a model from the
 * HuggingFace hub the first time it is asked for one, and cache it inside
 * node_modules. That is convenient and completely incompatible with the claim
 * in docs/SELF_HOSTING.md that nothing is fetched at runtime — the app was
 * making an outbound call on first inference, into a directory that is not part
 * of any build artifact.
 *
 * So the download becomes an explicit, auditable setup step, and the runtime is
 * locked to local files only (see lib/inference/ranker.ts). The app now fails
 * loudly on a missing encoder rather than quietly reaching for the network.
 *
 * The weights are NOT committed — ~90 MB has no business in a git history. This
 * script reproduces them, and the desktop build copies them into the bundle.
 */

import { existsSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = dirname(dirname(fileURLToPath(import.meta.url)));
const MODELS = join(ROOT, "models");

// Read the model id from the same file the app reads, so the two can never
// drift apart and leave the runtime looking for something that was never
// fetched.
const ranker = JSON.parse(
  await (await import("node:fs/promises")).readFile(
    join(ROOT, "lib", "inference", "ranker.json"),
    "utf-8",
  ),
);
const MODEL_ID = ranker.embedding_model;

const target = join(MODELS, MODEL_ID.replace("/", "-"));
if (existsSync(join(MODELS, MODEL_ID, "onnx", "model.onnx"))) {
  console.log(`already present: ${MODEL_ID}`);
  process.exit(0);
}

console.log(`fetching ${MODEL_ID} -> ${MODELS}`);
console.log("This is the only time anything is downloaded. Runtime is offline.");

const { pipeline, env } = await import("@huggingface/transformers");
env.cacheDir = MODELS;
env.allowRemoteModels = true; // explicitly, and only, here

await pipeline("feature-extraction", MODEL_ID, { dtype: "fp32" });

if (!existsSync(join(MODELS, MODEL_ID, "onnx", "model.onnx"))) {
  console.error(`FAILED: expected weights under ${target}`);
  process.exit(1);
}
console.log("done. `npm run dev` will now run without network access.");
