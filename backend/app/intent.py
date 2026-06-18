"""Module 5 — Intent Forecasting Engine.

Predicts purchase / churn / upsell / engagement / support / advocacy intent plus
emotion-shift and trust-degradation risk. The research system uses a Temporal
Fusion Transformer + Mixture-of-Experts + Graph Transformers over the event
sequence. This reference implementation derives calibrated intent scores from
the fused emotion state, trust state and behavioural aggregates — interpretable
and fast, with the same IntentState contract a learned model would emit.
"""
from __future__ import annotations

import numpy as np

from .models import EmotionState, Event, IntentState, TrustState


def _sigmoid(x: float) -> float:
    return 1.0 / (1.0 + np.exp(-x))


def forecast_intent(events: list[Event],
                    emotion: EmotionState,
                    trust: TrustState,
                    behavior: dict[str, float]) -> IntentState:
    recency = behavior.get("recency_score", 0.5)
    frequency = behavior.get("frequency_score", 0.0)
    monetary = behavior.get("monetary_score", 0.0)
    funnel = behavior.get("funnel_depth", 0.0)
    aborts = behavior.get("abort_rate", 0.0)
    support_rate = behavior.get("support_rate", 0.0)

    e = emotion.scores

    purchase = _sigmoid(
        2.2 * e["purchase_confidence"] + 1.4 * funnel + 1.1 * frequency
        + 1.0 * recency - 1.6 * aborts - 0.6
    )
    churn = _sigmoid(
        1.9 * e["frustration"] + 1.7 * e["anger"] + 1.2 * support_rate
        - 1.8 * e["loyalty"] - 1.3 * recency + 0.8 * aborts - 0.4
    )
    upsell = _sigmoid(
        1.6 * e["satisfaction"] + 1.3 * e["loyalty"] + 1.2 * monetary
        + 0.8 * e["purchase_confidence"] - 1.2 * churn - 0.5
    )
    engagement = _sigmoid(
        1.4 * e["curiosity"] + 1.2 * e["excitement"] + 1.0 * recency
        + 0.8 * funnel - 0.4
    )
    support = _sigmoid(
        2.0 * e["frustration"] + 1.4 * e["anxiety"] + 1.5 * support_rate - 0.7
    )
    advocacy = _sigmoid(
        1.8 * e["loyalty"] + 1.4 * e["satisfaction"] + 1.2 * e["trust"] - 0.9
    )
    emotion_shift = float(np.clip(emotion.volatility * 0.7
                                  + (1 - emotion.confidence) * 0.3, 0, 1))
    trust_degradation = float(np.clip(
        0.6 * trust.fraud_probability + 0.4 * e["frustration"]
        + 0.3 * e["anxiety"] - 0.3 * e["trust"], 0, 1))

    return IntentState(
        purchase_intent=round(float(purchase), 4),
        churn_intent=round(float(churn), 4),
        upsell_intent=round(float(upsell), 4),
        engagement_intent=round(float(engagement), 4),
        support_intent=round(float(support), 4),
        advocacy_intent=round(float(advocacy), 4),
        emotion_shift_risk=round(emotion_shift, 4),
        trust_degradation_risk=round(trust_degradation, 4),
    )
