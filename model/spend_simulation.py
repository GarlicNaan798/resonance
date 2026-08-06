"""
What is a 59%-accurate model actually WORTH in money?

The objection is fair: a 41% miss rate sounds unusable when the pitch is "spend
less". But that framing assumes the model is used as a COMMITMENT — pick one
variant, run it, live with it. Used that way a 59% model is worth little.

Used as a PRIOR inside an adaptive test, the same model is worth a lot, because
being wrong is recoverable: real click data corrects the prior within the test.
The saving shows up as fewer impressions burned on the losing variant before you
know which one wins.

This measures that directly on real experiments, comparing three strategies:

  1. FULL A/B      - 50/50 split for the entire budget. What most teams do.
  2. BANDIT        - Thompson sampling, no model. Adapts from data alone.
  3. MODEL+BANDIT  - Thompson sampling warm-started with the model's prior.

Metric: REGRET — impressions served to the inferior arm. That is the money
wasted, and it is what "hedge your bets" actually means in numbers.

Everything runs on held-out experiments the ranker never trained on. Outcomes are
resampled from each arm's observed click rate, so the simulated clicks are drawn
from real measured behaviour rather than invented.
"""

from __future__ import annotations

import json
import os
import sys
from collections import defaultdict

import numpy as np
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from accuracy_push import (PointwiseRanker, base_split, carve_dev,  # noqa: E402
                           load_rows, train, build_pairs, MIN_GAP)

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROC = os.path.join(ROOT, "data", "processed")

BUDGET = 10_000          # impressions available per experiment
ROUNDS = 50              # allocation decisions across the budget
N_SIM = 200              # simulated runs per experiment (averaged)
SEED = 20260805

# How strongly to trust the model when seeding the bandit. Expressed as
# pseudo-observations: a 59% model does not deserve many.
PRIOR_STRENGTH = 40.0


def thompson(true_rates, budget, rounds, rng, prior=None):
    """Thompson sampling over Beta posteriors. Returns impressions per arm.

    `prior` is (alpha0, beta0) per arm — this is where the model's opinion
    enters. With no prior every arm starts at Beta(1,1), i.e. total ignorance.
    """
    k = len(true_rates)
    if prior is None:
        alpha = np.ones(k)
        beta = np.ones(k)
    else:
        alpha, beta = prior[0].copy(), prior[1].copy()

    served = np.zeros(k)
    per_round = budget // rounds

    for _ in range(rounds):
        draws = rng.beta(alpha, beta)
        pick = int(draws.argmax())
        clicks = rng.binomial(per_round, true_rates[pick])
        alpha[pick] += clicks
        beta[pick] += per_round - clicks
        served[pick] += per_round
    return served


def model_prior(scores, k, strength=PRIOR_STRENGTH, base_rate=0.0125):
    """Turn ranker scores into Beta priors.

    Softmax over scores gives a relative preference; that shifts each arm's
    prior click rate around the corpus base rate. `strength` caps how much
    influence the model gets — with a 59% model, a confident prior would be
    actively harmful when it is wrong.
    """
    s = np.array(scores, dtype=float)
    s = (s - s.mean()) / (s.std() + 1e-9)
    weights = np.exp(s) / np.exp(s).sum()
    # Spread priors around the base rate proportional to model preference.
    tilt = 1.0 + 0.5 * (weights * k - 1.0)
    rates = np.clip(base_rate * tilt, 1e-4, 0.5)
    alpha = rates * strength
    beta = (1.0 - rates) * strength
    return alpha, beta


def main() -> None:
    rows = load_rows()
    parts, members = base_split(rows)
    inner, dev = carve_dev(parts["train"], members)

    y = np.array([r["target"] for r in rows], dtype=np.float32)
    t = np.array([r["test_id"] for r in rows])
    heads = np.array([" ".join(r["headline"].lower().split()) for r in rows])
    _, inv = np.unique(heads, return_inverse=True)
    ident = inv.reshape(-1, 1).astype(np.float32)
    E = np.load(os.path.join(PROC, "embeddings.npz"))["E"]

    p_in = build_pairs(y[inner], t[inner], MIN_GAP, ident[inner])
    model = train(PointwiseRanker(E.shape[1]), E[inner], p_in, epochs=25, lr=1e-3)
    with torch.no_grad():
        scores_all = model.net(
            torch.tensor(E, dtype=torch.float32)
        ).squeeze(-1).numpy()

    # Group held-out dev rows into experiments with 2+ distinct-copy arms.
    by_test = defaultdict(list)
    for i in dev:
        by_test[t[i]].append(int(i))

    experiments = []
    for tid, idxs in by_test.items():
        seen, keep = set(), []
        for i in idxs:
            key = float(ident[i][0])
            if key not in seen:
                seen.add(key)
                keep.append(i)
        if len(keep) < 2:
            continue
        rates = np.array([rows[i]["clicks"] / rows[i]["impressions"] for i in keep])
        if rates.max() <= 0:
            continue
        experiments.append({"idx": keep, "rates": rates,
                            "scores": scores_all[keep]})

    print(f"held-out experiments simulated: {len(experiments):,}")
    print(f"budget {BUDGET:,} impressions, {ROUNDS} allocation rounds, "
          f"{N_SIM} sims each\n")

    rng = np.random.default_rng(SEED)
    regret = {"full_ab": [], "bandit": [], "model_bandit": []}
    picked_best = {"full_ab": [], "bandit": [], "model_bandit": []}

    for exp in experiments:
        rates = exp["rates"]
        k = len(rates)
        best = int(rates.argmax())
        prior = model_prior(exp["scores"], k)

        for _ in range(N_SIM):
            # 1. Full A/B: even split for the whole budget.
            even = np.full(k, BUDGET / k)
            regret["full_ab"].append(BUDGET - even[best])
            picked_best["full_ab"].append(1.0 / k)

            # 2. Bandit, no model.
            served = thompson(rates, BUDGET, ROUNDS, rng)
            regret["bandit"].append(BUDGET - served[best])
            picked_best["bandit"].append(float(served.argmax() == best))

            # 3. Bandit seeded with the model's prior.
            served = thompson(rates, BUDGET, ROUNDS, rng, prior=prior)
            regret["model_bandit"].append(BUDGET - served[best])
            picked_best["model_bandit"].append(float(served.argmax() == best))

    print(f"{'strategy':<16}{'wasted impressions':>20}{'% of budget':>13}"
          f"{'ends on best':>14}")
    out = {}
    for name in ("full_ab", "bandit", "model_bandit"):
        r = float(np.mean(regret[name]))
        p = float(np.mean(picked_best[name]))
        out[name] = {"mean_regret": r, "pct_budget": r / BUDGET,
                     "ends_on_best": p}
        print(f"{name:<16}{r:>20,.0f}{r/BUDGET:>12.1%}{p:>14.1%}")

    ab = out["full_ab"]["mean_regret"]
    bd = out["bandit"]["mean_regret"]
    mb = out["model_bandit"]["mean_regret"]

    print(f"\nsaving vs full A/B:")
    print(f"  bandit alone      {(ab-bd)/ab:+.1%}  ({ab-bd:,.0f} impressions)")
    print(f"  model + bandit    {(ab-mb)/ab:+.1%}  ({ab-mb:,.0f} impressions)")
    print(f"  model's own contribution {(bd-mb)/ab:+.1%}")

    print(f"\nAt a $10 CPM and {BUDGET:,} impressions per test, the model+bandit "
          f"saving is\n  ${(ab-mb)/1000*10:,.2f} per experiment versus a "
          f"conventional 50/50 A/B test.")

    with open(os.path.join(PROC, "spend_simulation.json"), "w",
              encoding="utf-8") as fh:
        json.dump({"budget": BUDGET, "experiments": len(experiments),
                   "results": out}, fh, indent=1)


if __name__ == "__main__":
    main()
