"""
Is the 0.788 ceiling right? Two independent checks.

The ceiling has become load-bearing: it frames every accuracy claim, it caught a
train/test leak, and it underpins the argument that we are near the limit of
this data. It deserves scrutiny rather than repetition.

noise_ceiling.py estimates it by split-half replication, taking each arm's
OBSERVED click rate as its true rate and drawing two independent binomial
samples. The weak point is that assumption. Observed rate = true rate + noise,
so

    Var(observed) = Var(true) + Var(noise)

Simulating from observed rates therefore spreads the arms further apart than
reality does, which makes the ordering easier to recover and INFLATES the
ceiling. If so, the real ceiling is lower and we are closer to it than claimed.

Two checks:

  1. ANALYTIC. Decompose the variance of the observed within-test contrast into
     signal and noise using the standard log-odds standard error, then compute
     replication agreement directly from that signal-to-noise ratio. This uses
     no simulation at all, so it is an independent route to the same quantity.

  2. DECONVOLVED SIMULATION. Repeat the split-half simulation, but shrink each
     arm's rate toward its experiment mean by the amount attributable to
     sampling noise (empirical-Bayes style). That removes the inflation and
     gives a more honest ceiling.

If check 1 and the deconvolved check 2 agree with each other but sit below
0.788, the reported ceiling should be revised down.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import load_rows  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")
MIN_GAP = 0.05
N_SIM = 5


def log_odds(c, n):
    p = (c + 0.5) / (n + 1.0)
    return np.log(p / (1.0 - p))


def analytic_ceiling(rows):
    """Ceiling from the signal-to-noise ratio of the within-test contrast."""
    impressions = np.array([r["impressions"] for r in rows], dtype=float)
    clicks = np.array([r["clicks"] for r in rows], dtype=float)
    target = np.array([r["target"] for r in rows], dtype=float)

    # SE of each arm's log-odds, then of a difference between two arms.
    se_arm = np.sqrt(1.0 / (clicks + 0.5) + 1.0 / (impressions - clicks + 0.5))
    noise_var_contrast = float(np.mean(se_arm ** 2)) * 2.0

    observed_var = float(np.var(target))
    signal_var = max(observed_var - noise_var_contrast, 1e-9)

    sd_signal = np.sqrt(signal_var)
    sd_noise = np.sqrt(noise_var_contrast)

    print("  observed contrast variance : {:.4f} (sd {:.4f})".format(
        observed_var, np.sqrt(observed_var)))
    print("  noise variance             : {:.4f} (sd {:.4f})".format(
        noise_var_contrast, sd_noise))
    print("  inferred signal variance   : {:.4f} (sd {:.4f})".format(
        signal_var, sd_signal))
    print("  signal-to-noise (sd ratio) : {:.3f}".format(sd_signal / sd_noise))

    # Two independent replications of the same true difference d:
    #   each observes d + e, e ~ N(0, sd_noise^2)
    #   they agree when both land on the same side of zero.
    rng = np.random.default_rng(0)
    n = 2_000_000
    d = rng.normal(0.0, sd_signal, n)
    a = d + rng.normal(0.0, sd_noise, n)
    b = d + rng.normal(0.0, sd_noise, n)
    keep = np.abs(b) >= MIN_GAP          # mirror the dataset's own filter
    agree = (np.sign(a[keep]) == np.sign(b[keep])).mean()
    print(f"  => analytic ceiling        : {agree:.4f}  "
          f"({keep.mean():.1%} of pairs pass the filter)")
    return float(agree)


def simulate(rows, shrink: bool, rng):
    """Split-half replication. `shrink` deconvolves the noise from the rates."""
    by_test = defaultdict(list)
    for i, r in enumerate(rows):
        by_test[r["test_id"]].append(i)

    impressions = np.array([r["impressions"] for r in rows], dtype=float)
    clicks = np.array([r["clicks"] for r in rows], dtype=float)
    p_obs = clicks / impressions

    p_true = p_obs.copy()
    if shrink:
        # Empirical-Bayes style: pull each arm toward its experiment mean by the
        # share of its spread attributable to sampling noise.
        for idxs in by_test.values():
            if len(idxs) < 2:
                continue
            idxs = np.array(idxs)
            mean_p = float(np.average(p_obs[idxs], weights=impressions[idxs]))
            obs_var = float(np.var(p_obs[idxs]))
            noise_var = float(np.mean(mean_p * (1 - mean_p) / impressions[idxs]))
            # Fraction of observed spread that is real signal.
            w = max(0.0, (obs_var - noise_var)) / obs_var if obs_var > 0 else 0.0
            p_true[idxs] = mean_p + w * (p_obs[idxs] - mean_p)
        p_true = np.clip(p_true, 1e-6, 1.0)

    cA = rng.binomial(impressions.astype(int), p_true)
    cB = rng.binomial(impressions.astype(int), p_true)
    loA, loB = log_odds(cA, impressions), log_odds(cB, impressions)

    agree = total = 0
    for idxs in by_test.values():
        if len(idxs) < 2:
            continue
        for a in range(len(idxs)):
            for b in range(a + 1, len(idxs)):
                i, j = idxs[a], idxs[b]
                gB = loB[i] - loB[j]
                if abs(gB) < MIN_GAP:
                    continue
                gA = loA[i] - loA[j]
                if gA == 0:
                    continue
                agree += int((gA > 0) == (gB > 0))
                total += 1
    return agree / max(total, 1)


def main() -> None:
    rows = load_rows()
    print(f"{len(rows):,} arms\n")

    print("CHECK 1 - analytic, from signal-to-noise")
    analytic = analytic_ceiling(rows)

    print("\nCHECK 2 - split-half simulation")
    raw, shrunk = [], []
    for s in range(N_SIM):
        rng = np.random.default_rng(s)
        raw.append(simulate(rows, shrink=False, rng=rng))
        rng = np.random.default_rng(1000 + s)
        shrunk.append(simulate(rows, shrink=True, rng=rng))
    raw_m, shr_m = float(np.mean(raw)), float(np.mean(shrunk))
    print(f"  observed-as-true (current method) : {raw_m:.4f}")
    print(f"  noise-deconvolved                 : {shr_m:.4f}")

    print("\nSUMMARY")
    print(f"  reported ceiling        : 0.7880")
    print(f"  analytic                : {analytic:.4f}")
    print(f"  deconvolved simulation  : {shr_m:.4f}")
    spread = max(analytic, shr_m, raw_m) - min(analytic, shr_m, raw_m)
    print(f"  spread across methods   : {spread:.4f}")

    if shr_m < raw_m - 0.01:
        print("\n  The current method IS inflated: treating observed rates as")
        print("  true spreads the arms further apart than reality. The honest")
        print(f"  ceiling is nearer {min(analytic, shr_m):.3f} than 0.788, which")
        print("  means we are CLOSER to the limit than previously claimed.")
    else:
        print("\n  The methods agree; 0.788 stands.")

    with open(os.path.join(PROC, "ceiling_robustness.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"analytic": analytic, "simulation_raw": raw_m,
                   "simulation_deconvolved": shr_m}, fh, indent=1)


if __name__ == "__main__":
    main()
