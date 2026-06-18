"""Module 8 — (Multi-Agent) Reinforcement Learning policy.

The research framing is MARL (MAPPO/QMIX/MADDPG) over the digital-twin state.
That needs an environment and offline training. To stay genuinely *online and
learning* inside a single deployable service, this module implements a
LinUCB-style contextual bandit: it picks the next-best-action from the twin
embedding (context) and updates from realised rewards. It is a real
exploration/exploitation learner — the same Action / reward contract a deeper
MARL policy would expose — and is the documented swap-in seam for MAPPO.
"""
from __future__ import annotations

import numpy as np

from .models import Action, DigitalTwin

# Actions the policy can choose between (do_nothing is the holdout arm).
_ARMS = [
    Action.recommend_product,
    Action.send_email,
    Action.push_notification,
    Action.sms,
    Action.offer_discount,
    Action.trigger_retention,
    Action.do_nothing,
]

_CONTEXT_DIM = 32  # matches twin.embedding length


class ContextualBanditPolicy:
    """LinUCB: one ridge model per arm with an upper-confidence bonus."""

    def __init__(self, alpha: float = 0.6) -> None:
        self.alpha = alpha
        d = _CONTEXT_DIM
        self.A = {a: np.identity(d) for a in _ARMS}        # d x d
        self.b = {a: np.zeros((d, 1)) for a in _ARMS}      # d x 1
        self.pulls = {a: 0 for a in _ARMS}

    def _context(self, twin: DigitalTwin) -> np.ndarray:
        x = np.array(twin.embedding, dtype=float).reshape(-1, 1)
        if x.shape[0] != _CONTEXT_DIM:
            # pad/truncate defensively
            v = np.zeros((_CONTEXT_DIM, 1))
            v[:min(_CONTEXT_DIM, x.shape[0])] = x[:_CONTEXT_DIM]
            x = v
        return x

    def _feasible(self, twin: DigitalTwin) -> list[Action]:
        arms = list(_ARMS)
        # don't push retention to obviously-happy loyal customers; don't SMS bots
        if twin.trust.is_flagged:
            return [Action.do_nothing]
        if twin.intent.churn_intent < 0.2 and Action.trigger_retention in arms:
            arms.remove(Action.trigger_retention)
        return arms

    def rank(self, twin: DigitalTwin) -> list[tuple[Action, float]]:
        x = self._context(twin)
        scored = []
        for a in self._feasible(twin):
            A_inv = np.linalg.inv(self.A[a])
            theta = A_inv @ self.b[a]
            mean = float((theta.T @ x)[0, 0])
            bonus = self.alpha * float(np.sqrt((x.T @ A_inv @ x)[0, 0]))
            scored.append((a, mean + bonus))
        scored.sort(key=lambda t: t[1], reverse=True)
        return scored

    def select(self, twin: DigitalTwin) -> tuple[Action, float, list[tuple[Action, float]]]:
        ranked = self.rank(twin)
        best, score = ranked[0]
        # softmax over UCB scores -> propensity (for off-policy correction)
        scores = np.array([s for _, s in ranked])
        ex = np.exp(scores - scores.max())
        probs = ex / ex.sum()
        propensity = float(probs[0])
        return best, propensity, ranked

    def update(self, twin: DigitalTwin, action: Action, reward: float) -> None:
        if action not in self.A:
            return
        x = self._context(twin)
        self.A[action] += x @ x.T
        self.b[action] += reward * x
        self.pulls[action] += 1

    def stats(self) -> dict[str, int]:
        return {a.value: self.pulls[a] for a in _ARMS}
