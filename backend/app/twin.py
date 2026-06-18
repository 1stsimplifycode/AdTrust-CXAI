"""Modules 3 & 4 — Customer Digital Twin + Multimodal Representation Learning.

`build_twin` assembles the continuously-evolving twin from the affective, trust
and intent layers plus behavioural aggregates, and produces a unified customer
embedding. The research system learns the embedding via cross-modal attention
over text/image/audio/behaviour/structured encoders; here we build a compact,
deterministic 32-d embedding by concatenating normalised feature blocks so the
downstream policy and similarity search have a stable vector to consume.
"""
from __future__ import annotations

from datetime import datetime, timezone
import math

import numpy as np

from .affective import infer_emotion
from .intent import forecast_intent
from .models import (EMOTIONS, DigitalTwin, EmotionState, Event, IntentState,
                     TrustState)
from .trust import TrustEngine


def compute_behavior(events: list[Event]) -> dict[str, float]:
    n = max(len(events), 1)
    types = [e.event_type for e in events]
    purchases = [e for e in events if e.event_type == "purchase"]
    monetary_total = sum(e.value for e in purchases)
    aborts = sum(1 for t in types if t == "cart_abandon")
    support = sum(1 for t in types if t == "support_message")
    funnel = sum(1 for t in types if t in ("search", "page_view", "click", "add_to_cart"))

    # recency: how fresh the latest event is (decays over ~14 days)
    recency_score = 0.5
    if events:
        try:
            last = datetime.fromisoformat(events[-1].ts)
            if last.tzinfo is None:
                last = last.replace(tzinfo=timezone.utc)
            age_days = (datetime.now(timezone.utc) - last).total_seconds() / 86400.0
            recency_score = math.exp(-age_days / 14.0)
        except Exception:
            pass

    return {
        "event_count": float(len(events)),
        "purchase_count": float(len(purchases)),
        "monetary_total": float(monetary_total),
        "monetary_score": float(np.tanh(monetary_total / 500.0)),
        "frequency_score": float(np.tanh(len(events) / 30.0)),
        "recency_score": round(float(recency_score), 4),
        "funnel_depth": float(np.tanh(funnel / 20.0)),
        "abort_rate": round(aborts / n, 4),
        "support_rate": round(support / n, 4),
    }


def _journey_stage(behavior: dict[str, float], intent: IntentState) -> str:
    if behavior["purchase_count"] == 0 and behavior["funnel_depth"] < 0.2:
        return "awareness"
    if behavior["purchase_count"] == 0:
        return "consideration"
    if intent.churn_intent > 0.6:
        return "at_risk"
    if intent.advocacy_intent > 0.6:
        return "advocacy"
    if behavior["purchase_count"] >= 2:
        return "loyalty"
    return "conversion"


def _channel_prefs(events: list[Event]) -> dict[str, float]:
    from collections import Counter
    if not events:
        return {}
    c = Counter(e.channel for e in events)
    total = sum(c.values())
    return {(k.value if hasattr(k, "value") else str(k)): round(v / total, 4) for k, v in c.items()}


def _embedding(emotion: EmotionState, trust: TrustState,
               intent: IntentState, behavior: dict[str, float]) -> list[float]:
    emo_vec = [emotion.scores[e] for e in EMOTIONS]                # 10
    emo_meta = [(emotion.valence + 1) / 2, emotion.arousal,
                emotion.volatility, emotion.confidence]            # 4
    trust_vec = [trust.trust_score, trust.fraud_probability,
                 trust.authenticity_score]                        # 3
    intent_vec = [intent.purchase_intent, intent.churn_intent,
                  intent.upsell_intent, intent.engagement_intent,
                  intent.support_intent, intent.advocacy_intent,
                  intent.emotion_shift_risk,
                  intent.trust_degradation_risk]                   # 8
    beh_vec = [behavior["frequency_score"], behavior["recency_score"],
               behavior["monetary_score"], behavior["funnel_depth"],
               behavior["abort_rate"], behavior["support_rate"],
               min(behavior["purchase_count"] / 10.0, 1.0)]        # 7
    vec = emo_vec + emo_meta + trust_vec + intent_vec + beh_vec    # 32
    return [round(float(x), 4) for x in vec]


def _ltv(behavior: dict[str, float], intent: IntentState) -> float:
    base = behavior["monetary_total"]
    horizon = 1.0 + 2.5 * intent.upsell_intent + 1.5 * intent.advocacy_intent
    retention = 1.0 - 0.7 * intent.churn_intent
    return round(base * horizon * retention + 25.0 * intent.purchase_intent, 2)


def build_twin(customer_id: str,
               events: list[Event],
               trust_engine: TrustEngine,
               version: int,
               prior_trajectory: list[float] | None = None) -> DigitalTwin:
    emotion = infer_emotion(events, prior_trajectory)
    trust = trust_engine.score(events)
    behavior = compute_behavior(events)
    intent = forecast_intent(events, emotion, trust, behavior)
    embedding = _embedding(emotion, trust, intent, behavior)

    purchase_readiness = round(float(
        0.6 * intent.purchase_intent
        + 0.25 * emotion.scores["purchase_confidence"]
        + 0.15 * behavior["funnel_depth"]
    ), 4)

    return DigitalTwin(
        customer_id=customer_id,
        version=version,
        emotion=emotion,
        trust=trust,
        intent=intent,
        behavior={k: round(v, 4) for k, v in behavior.items()},
        channel_preferences=_channel_prefs(events),
        purchase_readiness=purchase_readiness,
        lifetime_value=_ltv(behavior, intent),
        journey_stage=_journey_stage(behavior, intent),
        embedding=embedding,
    )
