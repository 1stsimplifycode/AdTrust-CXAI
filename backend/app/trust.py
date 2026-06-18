"""Module 6 — Trust Intelligence Engine.

Scores customer authenticity and campaign integrity, and flags fraud /
manipulation. The research system uses GNNs + Bayesian trust networks + GAT
over the customer/campaign/channel trust graphs. This reference implementation
combines:

  * interpretable behavioural fraud rules (velocity, conversion-without-funnel,
    refund abuse, bot-like timing), and
  * an unsupervised IsolationForest over engineered features (anomaly score),

into a calibrated trust / fraud / authenticity triple. Rules give explanations;
the IsolationForest catches novel anomalies the rules miss.
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

import numpy as np

from .models import Event, TrustState

try:
    from sklearn.ensemble import IsolationForest
    _HAVE_SK = True
except Exception:  # pragma: no cover
    _HAVE_SK = False


def _feature_vector(events: list[Event]) -> np.ndarray:
    n = max(len(events), 1)
    types = [e.event_type for e in events]
    clicks = sum(1 for t in types if t in ("click", "page_view"))
    purchases = sum(1 for t in types if t == "purchase")
    refunds = sum(1 for t in types if t == "refund")
    aborts = sum(1 for t in types if t == "cart_abandon")
    distinct_channels = len({e.channel for e in events})

    # inter-event timing regularity (bots are metronomic)
    ts = []
    for e in events:
        try:
            ts.append(datetime.fromisoformat(e.ts).timestamp())
        except Exception:
            pass
    ts.sort()
    gaps = np.diff(ts) if len(ts) > 1 else np.array([60.0])
    gap_std = float(np.std(gaps)) if len(gaps) else 0.0
    gap_mean = float(np.mean(gaps)) if len(gaps) else 60.0
    regularity = 1.0 / (1.0 + gap_std / (gap_mean + 1e-6))  # ->1 == metronomic

    conv_ratio = purchases / n
    funnel_ratio = clicks / n
    refund_ratio = refunds / max(purchases, 1)

    return np.array([
        n, conv_ratio, funnel_ratio, refund_ratio, aborts / n,
        distinct_channels, regularity, gap_mean,
    ], dtype=float)


class TrustEngine:
    def __init__(self) -> None:
        self._iforest: Optional["IsolationForest"] = None

    def fit_baseline(self, customer_event_lists: list[list[Event]]) -> None:
        """Fit the anomaly detector on a population of 'normal' customers."""
        if not _HAVE_SK or not customer_event_lists:
            return
        X = np.array([_feature_vector(evts) for evts in customer_event_lists])
        if len(X) < 8:
            return
        self._iforest = IsolationForest(
            n_estimators=120, contamination=0.08, random_state=7
        ).fit(X)

    def score(self, events: list[Event]) -> TrustState:
        signals: list[str] = []
        x = _feature_vector(events)
        (n, conv_ratio, funnel_ratio, refund_ratio,
         abort_ratio, channels, regularity, gap_mean) = x

        fraud = 0.0
        # Rule 1: conversion without browsing funnel (synthetic persona)
        if conv_ratio > 0.5 and funnel_ratio < 0.1 and n > 4:
            fraud += 0.35
            signals.append("high conversion with near-zero funnel (synthetic persona)")
        # Rule 2: metronomic timing (bot)
        if regularity > 0.85 and n > 6:
            fraud += 0.3
            signals.append("metronomic event timing (bot-like)")
        # Rule 3: refund abuse
        if refund_ratio > 0.5 and n > 3:
            fraud += 0.2
            signals.append("excessive refund ratio (refund abuse)")
        # Rule 4: impossible velocity
        if gap_mean < 1.5 and n > 5:
            fraud += 0.25
            signals.append("impossible click velocity (<1.5s mean gap)")
        # Rule 5: single-channel flood
        if channels <= 1 and n > 15:
            fraud += 0.1
            signals.append("single-channel high-volume flooding")

        # Unsupervised anomaly contribution
        anomaly = 0.0
        if self._iforest is not None:
            raw = float(self._iforest.score_samples(x.reshape(1, -1))[0])
            # score_samples: higher == more normal. Map to [0,1] anomaly.
            anomaly = float(np.clip((-(raw) - 0.3) * 1.2, 0.0, 1.0))
            if anomaly > 0.55:
                signals.append(f"statistical anomaly (iforest={anomaly:.2f})")

        fraud_probability = float(np.clip(0.6 * fraud + 0.4 * anomaly, 0.0, 1.0))
        authenticity = float(np.clip(1.0 - fraud_probability, 0.0, 1.0))
        # trust blends authenticity with positive tenure signal
        tenure_bonus = float(np.clip(n / 60.0, 0.0, 0.25))
        trust = float(np.clip(authenticity * 0.85 + tenure_bonus, 0.0, 1.0))

        return TrustState(
            trust_score=round(trust, 4),
            fraud_probability=round(fraud_probability, 4),
            authenticity_score=round(authenticity, 4),
            signals=signals,
            is_flagged=fraud_probability >= 0.5,
        )

    def campaign_integrity(self, customer_trusts: list[float]) -> float:
        """Campaign Trust Graph rollup -> integrity score in [0,1]."""
        if not customer_trusts:
            return 1.0
        return round(float(np.mean(customer_trusts)), 4)
