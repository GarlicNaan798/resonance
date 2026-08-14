"""
Self-check for the human-baseline scorer. Run before any human sees the quiz.

A bug here does not crash; it produces a plausible-looking percentage that is
wrong, and that number is destined for the front of the README. So the scorer
is driven with simulated responders whose true accuracy is known in advance:

  perfect        - always picks the winner            -> 100%
  inverted       - always picks the loser             -> 0%   (catches a flipped key)
  position-0     - always picks the first option      -> ~50% ONLY if positions
                                                        are balanced; anything
                                                        else means the quiz
                                                        leaks the answer through
                                                        presentation order
  coin           - random                             -> near 50%

Uses the real key, a temp directory for responses, and touches nothing else.
"""

from __future__ import annotations

import io
import json
import os
import random
import sys
import tempfile
from contextlib import redirect_stdout

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "model"))

import human_baseline as hb  # noqa: E402


def responses_for(key_items, kind, rng):
    out = []
    for k in key_items:
        w = k["winner_position"]
        if kind == "perfect":
            c = w
        elif kind == "inverted":
            c = 1 - w
        elif kind == "position0":
            c = 0
        else:
            c = rng.randint(0, 1)
        out.append({"id": k["id"], "choice": c})
    return out


def run(tmp, key_file, kinds, rng):
    paths = []
    for kind in kinds:
        p = os.path.join(tmp, f"{kind}.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"seed": key_file["seed"], "n": key_file["n"],
                       "answers": responses_for(key_file["items"], kind, rng)}, fh)
        paths.append(p)
    buf = io.StringIO()
    with redirect_stdout(buf):
        hb.score(paths)
    return buf.getvalue()


def main() -> None:
    if not os.path.exists(hb.KEY_JSON):
        raise SystemExit("No key. Run: python model/human_baseline.py build")
    with open(hb.KEY_JSON, encoding="utf-8") as fh:
        key_file = json.load(fh)
    items = key_file["items"]
    n = len(items)
    rng = random.Random(1)

    # --- positions must be balanced, or position0 is not a chance-level probe
    second = sum(k["winner_position"] for k in items)
    assert abs(second - n / 2) <= 1, (
        f"winner shown second in {second}/{n} — positions are not balanced")

    with tempfile.TemporaryDirectory() as tmp:
        out = run(tmp, key_file, ["perfect"], rng)
        assert "100.0%" in out, out
        assert "Humans are better than chance" in out, out

        out = run(tmp, key_file, ["inverted"], rng)
        assert "0.0%" in out, out
        # The scorer must SAY an inverted key is suspicious rather than quietly
        # reporting 0% as if it were a finding.
        assert "WORSE than chance" in out and "inverted key" in out, out

        out = run(tmp, key_file, ["position0"], rng)
        # Exactly 50% by construction when positions are balanced.
        assert f"{n // 2}/{n} = 50.0%" in out, out

        out = run(tmp, key_file, ["coin"], rng)
        assert "not distinguishable from chance" in out, out

        # Several participants pool into one n.
        out = run(tmp, key_file, ["perfect", "coin", "position0"], rng)
        assert f"{3 * n} answered items" in out, out

        # A FEW skips must be dropped, not scored as wrong.
        def write(name, answers, **extra):
            path = os.path.join(tmp, name)
            with open(path, "w", encoding="utf-8") as fh:
                json.dump({"seed": key_file["seed"], "n": n,
                           "answers": answers, **extra}, fh)
            return path

        skips = 3
        answers = responses_for(items, "perfect", rng)
        for a in answers[:skips]:
            a["choice"] = None
        buf = io.StringIO()
        with redirect_stdout(buf):
            hb.score([write("light-skipper.json", answers)])
        out = buf.getvalue()
        assert "100.0%" in out, "a few skips must not count against the participant"
        assert f"{n - skips} answered items" in out, out

        # ---- pre-registered exclusions (docs/PREREGISTRATION.md section 8) ----
        # Below the completion floor: excluded, and said out loud.
        answers = responses_for(items, "perfect", rng)
        for a in answers[: n // 3]:
            a["choice"] = None
        try:
            with redirect_stdout(io.StringIO()):
                hb.score([write("heavy-skipper.json", answers)])
        except SystemExit as exc:
            assert "no responses survived" in str(exc), str(exc)
        else:
            raise AssertionError("a 67%-complete response was scored anyway")

        # Clicking through without reading: excluded on median time.
        fast = [dict(a, ms=400) for a in responses_for(items, "perfect", rng)]
        try:
            with redirect_stdout(io.StringIO()):
                hb.score([write("speedrunner.json", fast)])
        except SystemExit:
            pass
        else:
            raise AssertionError("a 400ms-per-item response was scored anyway")

        # The rule must be BLIND to accuracy. A slow, careful participant is kept
        # whether they agree with the model or contradict it completely — if this
        # ever became accuracy-dependent the whole study would be riggable.
        for kind in ("perfect", "inverted"):
            slow = [dict(a, ms=9000) for a in responses_for(items, kind, rng)]
            buf = io.StringIO()
            with redirect_stdout(buf):
                hb.score([write(f"slow-{kind}.json", slow)])
            assert "EXCLUDED" not in buf.getvalue(), f"{kind} was excluded on merit"

        # Experience is captured and reported, because the pre-registration
        # promises a breakdown by it.
        buf = io.StringIO()
        with redirect_stdout(buf):
            hb.score([write("pro.json", responses_for(items, "perfect", rng),
                            profile={"years": 7, "paid": True})])
        assert "yrs" in buf.getvalue() and "yes" in buf.getvalue(), buf.getvalue()

        # A response built from a different sample must be refused, not scored
        # against items it never saw.
        p = os.path.join(tmp, "wrongseed.json")
        with open(p, "w", encoding="utf-8") as fh:
            json.dump({"seed": key_file["seed"] + 1, "n": n,
                       "answers": responses_for(items, "perfect", rng)}, fh)
        try:
            with redirect_stdout(io.StringIO()):
                hb.score([p])
        except SystemExit as exc:
            assert "seed" in str(exc), str(exc)
        else:
            raise AssertionError("a mismatched seed was scored anyway")

    # --- McNemar, independently of the file plumbing
    assert hb.mcnemar_exact(0, 0) == 1.0
    assert hb.mcnemar_exact(5, 5) > 0.9           # perfectly tied
    assert hb.mcnemar_exact(20, 2) < 0.001        # lopsided
    assert hb.mcnemar_exact(2, 20) == hb.mcnemar_exact(20, 2)   # symmetric

    lo, hi = hb.wilson(30, 60)
    assert lo < 0.5 < hi and 0 <= lo and hi <= 1

    print(f"human_baseline: all checks passed (n={n} items in the key)")


if __name__ == "__main__":
    main()
