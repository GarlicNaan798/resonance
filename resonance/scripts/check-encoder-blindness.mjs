/**
 * Is the encoder blind to capitalisation and punctuation?
 *
 * The ranker just preferred "URGENT!!! SLASH YOUR BILLS TODAY!!!" over calm
 * copy, which contradicts our own strongest single-feature finding (fewer
 * exclamation marks correlated with BETTER click-through on the same data).
 *
 * Before blaming domain shift, check the mechanical explanation:
 * all-MiniLM-L6-v2 is an UNCASED model. If so, "URGENT" and "urgent" produce
 * identical vectors, the ranker cannot see shouting at all, and it is
 * responding purely to word choice. That is a very different problem — and a
 * fixable one — from "the model learned that shouting works".
 */

import { pipeline } from "@huggingface/transformers";

const PAIRS = [
  ["URGENT SLASH YOUR BILLS TODAY", "urgent slash your bills today"],
  ["Save money now", "SAVE MONEY NOW"],
  ["Save money now", "Save money now!!!"],
  ["Save money now", "Save money now."],
  ["Cut your bill", "Cut your bill?"],
];

const cosine = (a, b) => {
  let dot = 0;
  for (let i = 0; i < a.length; i++) dot += a[i] * b[i];
  return dot; // vectors are normalised
};

const extractor = await pipeline(
  "feature-extraction",
  "Xenova/all-MiniLM-L6-v2",
  { dtype: "fp32" },
);

console.log("cosine similarity between surface variants (1.0 = identical)\n");

for (const [a, b] of PAIRS) {
  const out = await extractor([a, b], { pooling: "mean", normalize: true });
  const [va, vb] = out.tolist();
  const sim = cosine(va, vb);
  const identical = sim > 0.9999;
  console.log(`${sim.toFixed(6)} ${identical ? "IDENTICAL" : "         "}  ` +
    `"${a}"  vs  "${b}"`);
}

console.log(
  "\nIf case variants are IDENTICAL, the encoder is uncased and the ranker " +
  "is structurally blind to shouting.",
);
