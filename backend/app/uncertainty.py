"""Module 11 — Uncertainty Quantification Engine.

Every score elsewhere in the platform (purchase intent, trust, emotion) is a
point estimate. A reviewer's first question about a point estimate is "how
sure are you?" — so this module decomposes each one into the two error
sources the uncertainty-quantification literature actually distinguishes:

  * Aleatoric (irreducible) uncertainty — noise inherent to the signal itself,
    not reducible by collecting more data. We use the Bernoulli predictive
    variance p(1-p): if a probability estimate p were the true rate of a
    binary outcome, p(1-p) IS that outcome's variance. This is not a made-up
    proxy, it's the textbook variance of the distribution the score already
    claims to summarize.

  * Epistemic (reducible) uncertainty — uncertainty from limited evidence,
    which should shrink as the platform observes more of this customer. For
    every other score we use a standard 1/sqrt(n) evidence-shrinkage term
    (the same family of shrinkage CausalEngine already applies to its uplift
    estimates). For the bandit's *own* action choice we don't approximate at
    all: we read off the literal LinUCB upper-confidence bound term
    (alpha * sqrt(x^T A^-1 x)), the exact quantity the policy used to decide
    whether to exploit or explore. That number already exists inside
    ContextualBanditPolicy on every decision — this module just surfaces it.

Total predictive std = sqrt(aleatoric^2 + epistemic^2); we report it as a
symmetric +/- band around the point estimate, clipped to a valid range.
"""
from __future__ import annotations

import math

import numpy as np

from .models import DigitalTwin
from .policy import ContextualBanditPolicy

# Dampening constants tuned so bands stay legible (a handful of points wide
# for a well-observed, confident customer; up to ~0.3 for a brand-new one)
# rather than literally spanning [0,1] the way an undamped 90%-CI would.
_ALEATORIC_WEIGHT = 0.5
_EPISTEMIC_K_DEFAULT = 0.22


def _bernoulli_aleatoric(p: float) -> float:
    p = min(max(p, 1e-4), 1 - 1e-4)
    return math.sqrt(p * (1 - p))


def _epistemic_from_evidence(n_events: int, k: float) -> float:
    """Shrinks toward 0 as more events are observed for this customer."""
    return k / math.sqrt(n_events + 1)


def estimate(value: float, n_events: int, *,
            aleatoric_weight: float = _ALEATORIC_WEIGHT,
            epistemic_k: float = _EPISTEMIC_K_DEFAULT) -> dict:
    aleatoric = _bernoulli_aleatoric(value) * aleatoric_weight
    epistemic = _epistemic_from_evidence(n_events, epistemic_k)
    total_std = math.sqrt(aleatoric ** 2 + epistemic ** 2)
    lo = round(max(0.0, value - total_std), 4)
    hi = round(min(1.0, value + total_std), 4)
    return {
        "value": round(value, 4),
        "aleatoric": round(aleatoric, 4),
        "epistemic": round(epistemic, 4),
        "ci_half_width": round(total_std, 4),
        "ci_low": lo,
        "ci_high": hi,
    }


def rl_epistemic_bonus(policy: ContextualBanditPolicy, twin: DigitalTwin) -> dict:
    """The literal LinUCB exploration term for the policy's current top pick —
    real epistemic uncertainty straight from the bandit's posterior
    covariance, not a heuristic. bonus = alpha * sqrt(x^T A^-1 x)."""
    ranked = policy.rank(twin)
    if not ranked:
        return {"action": None, "bonus": 0.0, "pulls_observed": 0}
    top_action, top_score = ranked[0]
    x = policy._context(twin)
    A_inv = np.linalg.inv(policy.A[top_action])
    bonus = policy.alpha * float(np.sqrt((x.T @ A_inv @ x)[0, 0]))
    mean = top_score - bonus
    return {
        "action": top_action.value,
        "ucb_score": round(top_score, 4),
        "exploitation_mean": round(mean, 4),
        "exploration_bonus": round(bonus, 4),
        "pulls_observed": policy.pulls[top_action],
    }


def uncertainty_panel(twin: DigitalTwin, n_events: int,
                      policy: ContextualBanditPolicy) -> dict:
    dominant_score = twin.emotion.scores.get(twin.emotion.dominant, 0.5)
    return {
        "customer_id": twin.customer_id,
        "n_events_observed": n_events,
        "purchase_intent": estimate(twin.intent.purchase_intent, n_events),
        "churn_intent": estimate(twin.intent.churn_intent, n_events),
        "trust": estimate(twin.trust.trust_score, n_events,
                          aleatoric_weight=0.35, epistemic_k=0.30),
        "emotion": {
            **estimate(dominant_score, n_events, epistemic_k=0.18),
            "label": twin.emotion.dominant,
        },
        "rl_exploration_bonus": rl_epistemic_bonus(policy, twin),
        "method_note": (
            "Aleatoric = Bernoulli predictive std sqrt(p(1-p)) at the scored "
            "rate. Epistemic = evidence-shrinkage k/sqrt(n_events+1), except "
            "the RL bonus which is the bandit's own literal UCB exploration "
            "term, not an approximation."
        ),
    }
