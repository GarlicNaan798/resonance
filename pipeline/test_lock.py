"""
The real test-set lock, for the corpus the models actually use.

WHY THIS EXISTS. pipeline/splits.py implements a lock, a SHA-256 fingerprint
and an unlock_test(reason) gate, for `data/interim/ads_*.jsonl`, the
HuggingFace ads corpus the project abandoned. `data/splits/test.jsonl` holds
2,806 rows of LLM instruction prompts that no model was ever trained on or
evaluated against. It had zero callers.

Meanwhile every model script split the Upworthy rows in-process via
`train_final.split_indices()`, grouped and deterministic, so the separation
was genuine, but ungated and unrecorded. The consequence was not leakage; it
was that nobody could say how many times the test set had been opened, which
is why three documents in this repo gave three different answers.

This module closes that gap for the corpus in use:

  1. ONE definition of the split, imported everywhere rather than re-derived.
  2. FINGERPRINTED. The test partition is hashed and pinned, so a change to
     the corpus or the seed is detected instead of silently revaluing every
     number ever reported.
  3. GATED, reads require a written reason.
  4. RECORDED. Every read appends to data/processed/test_reads.jsonl. The
     count is now a fact on disk rather than a recollection.

The historical reads are seeded into that log from the audit in the docstring
of `read_log()`, so the record starts honest rather than starting at zero.
"""

from __future__ import annotations

import hashlib
import json
import os
import random
from collections import defaultdict
from datetime import datetime, timezone

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
LOCK_PATH = os.path.join(PROC, "upworthy_test.lock.json")
READ_LOG = os.path.join(PROC, "test_reads.jsonl")

SEED = 20260805
TRAIN, VAL = 0.70, 0.15

MIN_REASON = 20


def split_indices(rows: list[dict]) -> dict[str, np.ndarray]:
    """Canonical grouped split. The single definition; do not re-derive it.

    The unit is `row["group"]`. The transitive closure over shared test-id and
    shared headline. Splitting on rows would leak, because ~50% of headlines
    recur across experiments.
    """
    members: dict[object, list[int]] = defaultdict(list)
    for i, r in enumerate(rows):
        members[r["group"]].append(i)
    gids = sorted(members)
    random.Random(SEED).shuffle(gids)
    n = len(gids)
    n_tr, n_va = int(round(n * TRAIN)), int(round(n * VAL))
    parts = {
        "train": gids[:n_tr],
        "val": gids[n_tr:n_tr + n_va],
        "test": gids[n_tr + n_va:],
    }
    return {
        k: np.array(sorted(i for g in v for i in members[g]), dtype=np.int64)
        for k, v in parts.items()
    }


def fingerprint(rows: list[dict], idx: np.ndarray) -> str:
    """Hash the test partition by content, not by index.

    Indices are meaningless if the corpus is reordered; the headline text is
    what must not change.
    """
    h = hashlib.sha256()
    for i in idx:
        h.update(" ".join(rows[int(i)]["headline"].lower().split()).encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()


def lock(rows: list[dict], *, quiet: bool = False) -> str:
    """Create the lock, or verify the test partition still matches it."""
    idx = split_indices(rows)["test"]
    fp = fingerprint(rows, idx)

    if os.path.exists(LOCK_PATH):
        with open(LOCK_PATH, encoding="utf-8") as fh:
            existing = json.load(fh)
        if existing["fingerprint"] != fp:
            raise SystemExit(
                "\nTEST SET CHANGED.\n"
                f"  locked: {existing['fingerprint'][:16]}...\n"
                f"  now   : {fp[:16]}...\n"
                "Every test number previously reported was measured against the "
                "locked partition. If the corpus genuinely grew, delete the lock "
                "deliberately and treat those numbers as void.\n")
        if not quiet:
            print(f"lock: test partition matches ({fp[:16]}..., n={len(idx)})")
        return fp

    os.makedirs(PROC, exist_ok=True)
    with open(LOCK_PATH, "w", encoding="utf-8") as fh:
        json.dump({"fingerprint": fp, "n": int(len(idx)), "seed": SEED}, fh, indent=1)
    print(f"lock: test partition sealed ({fp[:16]}..., n={len(idx)})")
    return fp


def read_log() -> list[dict]:
    """Every recorded read, oldest first.

    Reads predating this module are seeded by seed_history() from an audit of
    which scripts index idx["test"]:

      train_final.py        pairwise ranker 0.5942 and module model 0.5346
      test_read_listwise.py listwise ensemble 0.6176, pre-registered
      export_ensemble.py    six rows lifted for TS/PyTorch parity fixtures,
                            not an evaluation

    Two evaluations and one fixture extraction. That is the answer the project
    could not previously give.
    """
    if not os.path.exists(READ_LOG):
        return []
    with open(READ_LOG, encoding="utf-8") as fh:
        return [json.loads(l) for l in fh if l.strip()]


def _append(entry: dict) -> None:
    os.makedirs(PROC, exist_ok=True)
    with open(READ_LOG, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(entry, ensure_ascii=False) + "\n")


def unlock_test(rows: list[dict], reason: str, *, evaluation: bool = True) -> np.ndarray:
    """Return the test indices. Requires a written reason, and records the read.

    `evaluation=False` marks a read that does not produce a reported number
    (fixture extraction, shape checks). Recorded either way. The distinction
    is reported, not used to hide anything.
    """
    if not reason or len(reason.strip()) < MIN_REASON:
        raise SystemExit(
            f"unlock_test() needs an explicit reason (>={MIN_REASON} chars). "
            "Touching test during development is how models get oversold.")

    fp = lock(rows, quiet=True)
    idx = split_indices(rows)["test"]

    _append({
        "at": datetime.now(timezone.utc).isoformat(),
        "reason": reason.strip(),
        "evaluation": evaluation,
        "fingerprint": fp,
        "n": int(len(idx)),
    })

    prior = len(read_log())
    kind = "EVALUATION" if evaluation else "non-evaluative"
    print(f"!! TEST SET OPENED ({kind}, read #{prior}): {reason.strip()}")
    return idx


def seed_history(rows: list[dict]) -> None:
    """Write the three historical reads into an empty log, once.

    Starting the counter at zero would be its own small dishonesty: the reads
    happened, and the record should say so.
    """
    if read_log():
        print(f"read log already has {len(read_log())} entries; not seeding")
        return
    fp = lock(rows, quiet=True)
    n = int(len(split_indices(rows)["test"]))
    for reason, evaluation in [
        ("historical: train_final.py, pairwise ranker and module model", True),
        ("historical: test_read_listwise.py, pre-registered listwise ensemble", True),
        ("historical: export_ensemble.py, six rows for parity fixtures", False),
    ]:
        _append({
            "at": "2026-08-06T00:00:00+00:00",
            "reason": reason,
            "evaluation": evaluation,
            "fingerprint": fp,
            "backfilled": True,
            "n": n,
        })
    print(f"seeded {len(read_log())} historical reads")


def main() -> None:
    import sys
    sys.path.insert(0, os.path.join(ROOT, "model"))
    from accuracy_push import load_rows  # noqa: E402

    rows = load_rows()
    lock(rows)
    seed_history(rows)

    entries = read_log()
    evals = sum(1 for e in entries if e.get("evaluation"))
    print(f"\ntest reads on record: {len(entries)} ({evals} evaluations)")
    for e in entries:
        mark = "eval" if e.get("evaluation") else "    "
        print(f"  [{mark}] {e['at'][:10]}  {e['reason']}")


if __name__ == "__main__":
    main()
