"""
Fine-tune the encoder end-to-end — the one untried accuracy lever.

Every previous experiment varied something AROUND a frozen representation:
more features (v2, v3), pairwise interaction, a bigger frozen encoder. All four
failed. This changes the representation itself, which is the standard largest
win on a domain task and the thing we skipped.

CPU constraints shape the design:
  * PARTIAL fine-tuning. Only the last transformer layer plus the ranking head
    are unfrozen. Full fine-tuning of 23M parameters on CPU would take hours,
    and with ~8k training pairs it would overfit badly anyway. The last layer is
    where task-specific adaptation concentrates.
  * Subsampled pairs, few epochs, small batches, timeboxed.

Evaluated on the same dev split, same copy-only pairs, same clustered CIs as
every other experiment, so the number is directly comparable.

Pre-registered decision rule: keep only if the gain exceeds 0.02 (the measured
noise floor). A fine-tuned encoder is far more expensive to serve than a frozen
one plus a cached embedding, so a marginal gain does not justify it.
"""

from __future__ import annotations

import json
import os
import random
import sys
import time
from collections import defaultdict

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (base_split, build_pairs, carve_dev,  # noqa: E402
                           load_rows, MIN_GAP)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
MODEL_NAME = "sentence-transformers/all-MiniLM-L6-v2"

MAX_TRAIN_PAIRS = 6000
MAX_EVAL_PAIRS = 4000
EPOCHS = 2
BATCH = 16
LR_ENCODER = 2e-5      # small: pretrained weights are easy to destroy
LR_HEAD = 1e-3
MAX_LEN = 48           # headlines are short; padding to 512 would waste most compute
TIME_BUDGET_S = 1800   # 30 minutes, then stop wherever we are
KEEP_THRESHOLD = 0.02


def mean_pool(hidden, mask):
    m = mask.unsqueeze(-1).float()
    return (hidden * m).sum(1) / m.sum(1).clamp(min=1e-9)


class FineTuneRanker(nn.Module):
    def __init__(self, encoder, dim=384, hidden=128):
        super().__init__()
        self.encoder = encoder
        self.head = nn.Sequential(
            nn.Linear(dim, hidden), nn.ReLU(), nn.Dropout(0.2),
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, 1),
        )

    def forward(self, ids, mask):
        out = self.encoder(input_ids=ids, attention_mask=mask).last_hidden_state
        pooled = mean_pool(out, mask)
        pooled = pooled / pooled.norm(dim=-1, keepdim=True).clamp(min=1e-9)
        return self.head(pooled).squeeze(-1)


def clustered_acc(scores, pairs, tids):
    by_exp = defaultdict(list)
    for k, i in enumerate(pairs[:, 0]):
        by_exp[tids[i]].append(k)
    hi, lo = scores[pairs[:, 0]], scores[pairs[:, 1]]
    correct = (hi > lo).astype(float) + 0.5 * (hi == lo)
    per = [float(correct[np.array(ks)].mean()) for ks in by_exp.values()]
    a = np.array(per)
    m = float(a.mean())
    se = float(a.std(ddof=1) / np.sqrt(len(a)))
    return m, (m - 1.96 * se, m + 1.96 * se), len(a)


def main() -> None:
    from transformers import AutoModel, AutoTokenizer

    rows = load_rows()
    parts, members = base_split(rows)
    inner, dev = carve_dev(parts["train"], members)

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = [r["headline"] for r in rows]
    norm = np.array([" ".join(h.lower().split()) for h in heads])
    _, inv = np.unique(norm, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)

    # build_pairs returns indices LOCAL to the subset it was given. This script
    # indexes the GLOBAL `heads` list when tokenising, so the local indices must
    # be remapped to global row ids or the model scores unrelated headlines —
    # which is exactly what happened on the second attempt and produced a
    # chance-level baseline that looked like a modelling failure.
    #
    # Other scripts avoid this because they index subset arrays (E[inner],
    # E[dev]) throughout. Here the mapping has to be explicit.
    p_in = inner[build_pairs(y[inner], t[inner], MIN_GAP, ident[inner])]
    p_dev = dev[build_pairs(y[dev], t[dev], MIN_GAP, ident[dev])]

    rng = random.Random(20260805)
    if len(p_in) > MAX_TRAIN_PAIRS:
        p_in = p_in[rng.sample(range(len(p_in)), MAX_TRAIN_PAIRS)]
    if len(p_dev) > MAX_EVAL_PAIRS:
        p_dev = p_dev[rng.sample(range(len(p_dev)), MAX_EVAL_PAIRS)]
    print(f"train pairs {len(p_in):,}   dev pairs {len(p_dev):,}")

    tok = AutoTokenizer.from_pretrained(MODEL_NAME)
    encoder = AutoModel.from_pretrained(MODEL_NAME)

    # Freeze everything except the final transformer layer.
    for p in encoder.parameters():
        p.requires_grad = False
    last = encoder.encoder.layer[-1]
    for p in last.parameters():
        p.requires_grad = True

    model = FineTuneRanker(encoder)

    # Warm-start the head from a frozen-embedding ranker trained on INNER ONLY.
    #
    # Three attempts were needed to get this right; the failures are instructive.
    #
    #  1. Random head init: both sides scored ~0.505 and loss never left ln(2).
    #     750 steps cannot train a head from scratch. Measured nothing.
    #  2. Local/global index mix-up: build_pairs returns subset-local indices,
    #     used to index the global headline list. The model scored unrelated
    #     text. Chance again.
    #  3. Warm start from final_ranker.pt: that model was fit on train+val, and
    #     `dev` here is carved OUT of train — so the baseline was scoring data it
    #     had memorised. It read 0.8315, above the 0.788 ceiling, which is the
    #     tell: no held-out number can exceed the ceiling.
    #
    # Correct version: fit the frozen-embedding head on `inner` only, exactly as
    # accuracy_push.py does, so `dev` is genuinely held out from both the warm
    # start and the fine-tuning.
    from accuracy_push import PointwiseRanker, train as train_frozen

    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]
    print("training frozen-embedding head on inner split (for warm start)...")
    # build_pairs on the subset, since the frozen ranker indexes E[inner].
    p_in_local = build_pairs(y[inner], t[inner], MIN_GAP, ident[inner])
    frozen = train_frozen(PointwiseRanker(E.shape[1]), E[inner], p_in_local,
                          epochs=25, lr=1e-3)
    with torch.no_grad():
        for dst, src in ((0, 0), (3, 3), (5, 5)):
            model.head[dst].weight.copy_(frozen.net[src].weight)
            model.head[dst].bias.copy_(frozen.net[src].bias)
    print("head warm-started from inner-only frozen ranker")

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    print(f"trainable {trainable:,} of {total:,} parameters "
          f"({trainable/total:.1%})")

    opt = torch.optim.AdamW([
        {"params": [p for p in last.parameters()], "lr": LR_ENCODER},
        {"params": model.head.parameters(), "lr": LR_HEAD},
    ], weight_decay=1e-4)

    def encode_batch(indices):
        texts = [heads[i] for i in indices]
        enc = tok(texts, padding=True, truncation=True,
                  max_length=MAX_LEN, return_tensors="pt")
        return enc["input_ids"], enc["attention_mask"]

    @torch.no_grad()
    def dev_scores():
        """Score every row referenced by p_dev, returned in GLOBAL row order."""
        model.eval()
        uniq = sorted({int(i) for pr in p_dev for i in pr})
        full = np.zeros(len(rows), dtype=np.float32)
        for s in range(0, len(uniq), 64):
            chunk = uniq[s:s + 64]
            ids, mask = encode_batch(chunk)
            scores = model(ids, mask).numpy()
            for k, g in enumerate(chunk):
                full[g] = scores[k]
        return full

    print("\nbaseline (trained head, FROZEN encoder) - the incumbent:")
    base_acc, base_ci, n_exp = clustered_acc(dev_scores(), p_dev, t)
    print(f"  {base_acc:.4f}  95% CI [{base_ci[0]:.4f}, {base_ci[1]:.4f}]  "
          f"({n_exp:,} experiments)")
    # Two-sided sanity check. A baseline at chance means the warm start or the
    # index mapping is broken; a baseline above the ceiling means the evaluation
    # data leaked into training. Both have happened in this script.
    if base_acc < 0.55:
        raise SystemExit(
            f"  ABORT: baseline {base_acc:.4f} is near chance. The warm start "
            "did not take, or indices are mismapped. Fix before trusting any "
            "delta measured against this.")
    if base_acc > 0.788:
        raise SystemExit(
            f"  ABORT: baseline {base_acc:.4f} exceeds the 0.788 oracle ceiling, "
            "which is impossible on held-out data. The evaluation set has leaked "
            "into training.")
    print("  baseline is in the plausible range (0.55-0.788)")

    start = time.time()
    stopped_early = False
    for epoch in range(EPOCHS):
        model.train()
        order = list(range(len(p_in)))
        rng.shuffle(order)
        run_loss, seen = 0.0, 0
        for s in range(0, len(order), BATCH):
            if time.time() - start > TIME_BUDGET_S:
                stopped_early = True
                break
            sel = p_in[order[s:s + BATCH]]
            ids_hi, m_hi = encode_batch(sel[:, 0])
            ids_lo, m_lo = encode_batch(sel[:, 1])
            opt.zero_grad(set_to_none=True)
            d = model(ids_hi, m_hi) - model(ids_lo, m_lo)
            loss = nn.functional.softplus(-d).mean()
            loss.backward()
            nn.utils.clip_grad_norm_(
                [p for p in model.parameters() if p.requires_grad], 1.0)
            opt.step()
            run_loss += float(loss)
            seen += 1
            if seen % 50 == 0:
                print(f"  epoch {epoch} batch {seen}/{len(order)//BATCH} "
                      f"loss {run_loss/seen:.4f} "
                      f"({time.time()-start:.0f}s)", flush=True)
        if stopped_early:
            print(f"  time budget reached at {time.time()-start:.0f}s")
            break

    acc, ci, _ = clustered_acc(dev_scores(), p_dev, t)
    delta = acc - base_acc
    print(f"\nfine-tuned : {acc:.4f}  95% CI [{ci[0]:.4f}, {ci[1]:.4f}]")
    print(f"baseline   : {base_acc:.4f}")
    print(f"gain       : {delta:+.4f}  (threshold {KEEP_THRESHOLD})")
    print(f"elapsed    : {time.time()-start:.0f}s"
          + ("  [STOPPED EARLY]" if stopped_early else ""))
    print("\nVERDICT: " + (
        "KEEP fine-tuning - gain clears the noise floor"
        if delta > KEEP_THRESHOLD else
        "KEEP frozen embeddings - fine-tuning does not justify its serving cost"))

    with open(os.path.join(PROC, "finetune_result.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"baseline": base_acc, "finetuned": acc, "delta": delta,
                   "train_pairs": int(len(p_in)), "epochs": EPOCHS,
                   "stopped_early": stopped_early}, fh, indent=1)


if __name__ == "__main__":
    main()
