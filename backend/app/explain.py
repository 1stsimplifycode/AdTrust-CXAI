"""Module 10 — Explainable AI.

Produces human-readable rationale + feature attributions for each decision.
The research system uses SHAP + attention visualisation + LLM summaries. Here we
compute transparent, additive feature contributions from the policy context and
twin state, and render an LLM-style natural-language summary deterministically.
"""
from __future__ import annotations

from .models import Action, ActionDecision, DigitalTwin


def feature_attributions(twin: DigitalTwin, action: Action) -> dict[str, float]:
    """Additive contributions (signed) toward choosing `action`."""
    i = twin.intent
    e = twin.emotion
    contribs: dict[str, float] = {
        "purchase_intent": round(0.9 * i.purchase_intent, 3),
        "churn_intent": round(0.9 * i.churn_intent, 3),
        "upsell_intent": round(0.6 * i.upsell_intent, 3),
        "emotion_valence": round(0.5 * e.valence, 3),
        "frustration": round(-0.6 * e.scores["frustration"], 3),
        "trust_score": round(0.4 * twin.trust.trust_score, 3),
        "purchase_readiness": round(0.7 * twin.purchase_readiness, 3),
        "fraud_probability": round(-1.0 * twin.trust.fraud_probability, 3),
    }
    # keep the strongest 6 by magnitude
    top = sorted(contribs.items(), key=lambda kv: abs(kv[1]), reverse=True)[:6]
    return dict(top)


def rationale(twin: DigitalTwin, action: Action, uplift: float,
              counterfactual: str) -> str:
    e = twin.emotion
    i = twin.intent
    bits = [
        f"Customer {twin.customer_id} is in the '{twin.journey_stage}' stage with "
        f"dominant emotion '{e.dominant}' (valence {e.valence:+.2f}, "
        f"confidence {e.confidence:.2f}).",
    ]
    if twin.trust.is_flagged:
        bits.append("Trust engine flagged this profile "
                    f"(fraud p={twin.trust.fraud_probability:.2f}: "
                    f"{'; '.join(twin.trust.signals) or 'anomalous pattern'}); "
                    "the policy holds out paid interventions.")
    else:
        bits.append(
            f"Intent signals — purchase {i.purchase_intent:.2f}, "
            f"churn {i.churn_intent:.2f}, upsell {i.upsell_intent:.2f} — "
            f"with purchase-readiness {twin.purchase_readiness:.2f}.")
        verb = {
            Action.recommend_product: "surface a tailored product recommendation",
            Action.offer_discount: "extend a targeted discount",
            Action.trigger_retention: "launch a retention play",
            Action.send_email: "send a nurture email",
            Action.push_notification: "send a push nudge",
            Action.sms: "send an SMS nudge",
            Action.do_nothing: "hold out (no intervention)",
        }.get(action, action.value)
        bits.append(f"Chosen action: {verb}, with estimated incremental "
                    f"uplift {uplift:+.3f}.")
    bits.append(counterfactual)
    return " ".join(bits)


def assemble_decision(twin: DigitalTwin, action: Action, channel,
                      propensity: float, uplift: float, counterfactual: str,
                      agent_trace) -> ActionDecision:
    return ActionDecision(
        customer_id=twin.customer_id,
        action=action,
        channel=channel,
        expected_uplift=uplift,
        propensity=round(propensity, 4),
        rationale=rationale(twin, action, uplift, counterfactual),
        feature_attributions=feature_attributions(twin, action),
        agent_trace=agent_trace,
    )
