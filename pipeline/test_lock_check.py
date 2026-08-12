"""
Self-check for the test lock. Run: python pipeline/test_lock_check.py

The previous lock apparatus was never exercised and never called, so nobody
noticed it guarded the wrong corpus. A gate with no test is decoration, which
is the failure mode this whole change exists to correct.

Uses a synthetic corpus and a temporary directory — it must never touch the
real lock file or append to the real read log.
"""

from __future__ import annotations

import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import test_lock  # noqa: E402


def fake_rows(n: int = 400) -> list[dict]:
    # Several rows per group, so grouping has something to do.
    return [
        {"group": i // 4, "headline": f"headline number {i}", "target": 0.0}
        for i in range(n)
    ]


def main() -> None:
    rows = fake_rows()

    with tempfile.TemporaryDirectory() as tmp:
        test_lock.LOCK_PATH = os.path.join(tmp, "lock.json")
        test_lock.READ_LOG = os.path.join(tmp, "reads.jsonl")
        test_lock.PROC = tmp

        # --- the split is a partition, grouped, and stable ------------------
        idx = test_lock.split_indices(rows)
        allidx = sorted([*idx["train"], *idx["val"], *idx["test"]])
        assert allidx == list(range(len(rows))), "split must cover every row once"

        side = {}
        for name in ("train", "val", "test"):
            for i in idx[name]:
                g = rows[int(i)]["group"]
                assert side.setdefault(g, name) == name, f"group {g} spans splits"

        again = test_lock.split_indices(rows)
        assert list(again["test"]) == list(idx["test"]), "split must be deterministic"

        # --- locking -------------------------------------------------------
        fp1 = test_lock.lock(rows, quiet=True)
        fp2 = test_lock.lock(rows, quiet=True)
        assert fp1 == fp2, "re-locking an unchanged corpus must agree"

        # --- a changed TEST row must be REFUSED, not silently re-locked -----
        # Mutate a row that is actually in the test partition. The first draft
        # of this check edited rows[-1], which landed in train, so the lock
        # correctly did not care and the check failed for the wrong reason.
        mutated = [dict(r) for r in rows]
        mutated[int(idx["test"][0])]["headline"] = "a headline that was not there"
        try:
            test_lock.lock(mutated, quiet=True)
        except SystemExit as exc:
            assert "TEST SET CHANGED" in str(exc), str(exc)
        else:
            raise AssertionError("a changed test partition was accepted")

        # ...and the converse: editing TRAIN must NOT trip the lock, or the
        # fingerprint would block ordinary work on the training corpus.
        train_edit = [dict(r) for r in rows]
        train_edit[int(idx["train"][0])]["headline"] = "training copy, changed"
        assert test_lock.lock(train_edit, quiet=True) == fp1, (
            "a train-only edit must not invalidate the test lock")

        # --- the gate ------------------------------------------------------
        for bad in ("", "too short", "   " + "x" * 5):
            try:
                test_lock.unlock_test(rows, bad)
            except SystemExit:
                pass
            else:
                raise AssertionError(f"gate accepted a bad reason: {bad!r}")
        assert test_lock.read_log() == [], "refused reads must not be logged"

        # --- a real read is recorded ----------------------------------------
        got = test_lock.unlock_test(
            rows, "checking that a legitimate read is recorded properly")
        assert list(got) == list(idx["test"]), "unlock must return the test split"
        log = test_lock.read_log()
        assert len(log) == 1, log
        assert log[0]["evaluation"] is True
        assert log[0]["fingerprint"] == fp1

        test_lock.unlock_test(
            rows, "a non-evaluative read for fixtures, recorded as such",
            evaluation=False)
        log = test_lock.read_log()
        assert len(log) == 2 and log[1]["evaluation"] is False

        # --- seeding is idempotent ------------------------------------------
        before = len(test_lock.read_log())
        test_lock.seed_history(rows)
        assert len(test_lock.read_log()) == before, "seeding must not double-write"

    print("test_lock: all checks passed")


if __name__ == "__main__":
    main()
