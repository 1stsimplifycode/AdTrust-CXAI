"""Module 9 — Causal AI Engine.

Estimates the *incremental* effect of an intervention rather than correlation.
The research system uses Structural Causal Models + Double ML + uplift trees.
This reference implementation maintains an online two-model uplift estimator per
action: it tracks the conversion/retention reward under treatment vs. a control
("do_nothing") baseline, conditioned on a coarse customer segment, and returns
the difference as expected incremental lift with a counterfactual narrative.
"""
from __future__ import annotations

from collections import defaultdict

from .models import Action, DigitalTwin


def _segment(twin: DigitalTwin) -> str:
    """Coarse causal segment so uplift is conditioned on context."""
    stage = twin.journey_stage
    risk = "churny" if twin.intent.churn_intent > 0.5 else "stable"
    ready = "ready" if twin.purchase_readiness > 0.5 else "cold"
    return f"{stage}|{risk}|{ready}"


class CausalEngine:
    """Online uplift: E[reward | treatment, segment] - E[reward | control, segment]."""

    def __init__(self) -> None:
        # (segment, action) -> [sum_reward, count]
        self._stats: dict[tuple[str, str], list[float]] = defaultdict(lambda: [0.0, 0.0])
        self._priors = {
            Action.offer_discount: 0.18,
            Action.trigger_retention: 0.22,
            Action.recommend_product: 0.12,
            Action.send_email: 0.06,
            Action.push_notification: 0.05,
            Action.sms: 0.04,
            Action.do_nothing: 0.0,
        }

    def observe(self, twin: DigitalTwin, action: Action, reward: float) -> None:
        key = (_segment(twin), action.value)
        s = self._stats[key]
        s[0] += reward
        s[1] += 1.0

    def _expected(self, segment: str, action: Action) -> float:
        s = self._stats.get((segment, action.value))
        prior = self._priors.get(action, 0.05)
        if not s or s[1] < 3:
            return prior  # fall back to prior until we have evidence
        empirical = s[0] / s[1]
        # shrink toward prior with light Bayesian smoothing
        w = s[1] / (s[1] + 5.0)
        return w * empirical + (1 - w) * prior

    def uplift(self, twin: DigitalTwin, action: Action) -> float:
        seg = _segment(twin)
        treat = self._expected(seg, action)
        control = self._expected(seg, Action.do_nothing)
        return round(treat - control, 4)

    def counterfactual(self, twin: DigitalTwin, action: Action) -> str:
        seg = _segment(twin)
        u = self.uplift(twin, action)
        if action == Action.do_nothing:
            return ("Counterfactual: intervening now is not estimated to beat the "
                    "natural baseline for this segment; holding out preserves budget.")
        direction = "more" if u >= 0 else "less"
        return (f"Counterfactual: a customer in segment '{seg}' who receives "
                f"'{action.value}' is estimated {abs(u)*100:.1f}pp {direction} likely "
                f"to convert/retain than an identical customer left untouched "
                f"(incremental lift, not raw conversion).")
