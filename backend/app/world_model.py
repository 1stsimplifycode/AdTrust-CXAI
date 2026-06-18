"""Module 12 — World Model (short-horizon forward simulator).

The rest of the platform answers "what's the single best next action right
now?" This module answers the model-based-RL question instead: "if we commit
to a strategy and let it play out over the next H touchpoints, what
trajectory of states and rewards do we expect, and does it actually pay off
downstream?" That requires a *dynamics model* — a function that predicts the
next state given the current state and an action — which is exactly what a
world model is.

This reference dynamics model is intentionally simple and explicit (linear
trust/valence drift per action, churn-modulated survival) rather than a
learned latent-state model (e.g. a Dreamer-style RSSM) — the same
"interpretable reference now, swap-in seam for a learned version later"
pattern used throughout this codebase (see CausalEngine, ContextualBandit).
Critically, the *reward* at every simulated step is not invented for this
module: it is read from the same CausalEngine uplift table the live
decisioning path uses, so a strategy can only look good here if it also
looks good to the system that is actually deciding.
"""
from __future__ import annotations

from .causal import CausalEngine
from .models import Action, DigitalTwin

HORIZON = 5  # touchpoints simulated forward

# Named strategies -> the action committed to at every simulated touchpoint.
_STRATEGIES: dict[str, Action] = {
    "aggressive_growth": Action.offer_discount,
    "trust_first": Action.send_email,
    "retention_focus": Action.trigger_retention,
    "product_led": Action.recommend_product,
    "hold_steady": Action.do_nothing,
}


def _step_reward(causal: CausalEngine, twin: DigitalTwin, action: Action,
                 trust: float, valence: float) -> float:
    """Blended reward for one simulated touchpoint. The uplift term comes
    straight from CausalEngine.uplift — the same online-learned table the
    bandit's reward signal is built from (see /api/rl-state reward_weights
    for the same revenue/trust/affect blend, scaled for one touchpoint)."""
    uplift = causal.uplift(twin, action)
    return 100.0 * uplift + 20.0 * valence + 10.0 * (trust - 0.5)


def _transition(action: Action, trust: float, valence: float, churn: float,
                t: int) -> tuple[float, float, float]:
    """One step of the (simplified, explicit) state-transition model."""
    if action == Action.offer_discount:
        trust += 0.01 if t == 0 else -0.012   # novelty once, erosion on repeat
        valence += 0.05
        churn = max(0.0, churn - 0.02)
    elif action == Action.trigger_retention:
        trust += 0.015
        valence += 0.02
        churn = max(0.0, churn - 0.06)
    elif action == Action.recommend_product:
        trust += 0.004
        valence += 0.025
        churn = max(0.0, churn - 0.015)
    elif action == Action.send_email:
        trust += 0.006
        valence += 0.01
        churn = max(0.0, churn - 0.01)
    else:  # do_nothing — affect decays toward neutral, churn drifts up
        valence *= 0.96
        churn = min(1.0, churn + 0.01)
    trust = min(1.0, max(0.0, trust))
    valence = min(1.0, max(-1.0, valence))
    churn = min(1.0, max(0.0, churn))
    return trust, valence, churn


def simulate_scenario(causal: CausalEngine, twin: DigitalTwin, action: Action,
                      horizon: int = HORIZON) -> dict:
    trust = twin.trust.trust_score
    valence = twin.emotion.valence
    churn = twin.intent.churn_intent
    survival = 1.0  # P(customer hasn't churned by this step)
    cumulative = 0.0
    steps = []
    for t in range(horizon):
        trust, valence, churn = _transition(action, trust, valence, churn, t)
        survival *= (1.0 - churn * 0.2)  # churn_intent is a risk rate, not a per-step hazard
        reward = _step_reward(causal, twin, action, trust, valence) * survival
        cumulative += reward
        steps.append({
            "step": t + 1,
            "trust": round(trust, 4),
            "valence": round(valence, 4),
            "churn_risk": round(churn, 4),
            "survival_probability": round(survival, 4),
            "step_reward": round(reward, 3),
            "cumulative_reward": round(cumulative, 3),
        })
    return {
        "action": action.value,
        "steps": steps,
        "total_reward": round(cumulative, 3),
        "ending_trust": steps[-1]["trust"],
        "ending_churn_risk": steps[-1]["churn_risk"],
        "survival_probability": steps[-1]["survival_probability"],
    }


def future_scenarios(causal: CausalEngine, twin: DigitalTwin,
                     horizon: int = HORIZON) -> dict:
    scenarios = []
    for name, action in _STRATEGIES.items():
        sim = simulate_scenario(causal, twin, action, horizon)
        sim["scenario"] = name
        scenarios.append(sim)
    scenarios.sort(key=lambda s: s["total_reward"], reverse=True)
    for i, s in enumerate(scenarios):
        s["rank"] = i + 1
    best, worst = scenarios[0], scenarios[-1]
    return {
        "customer_id": twin.customer_id,
        "horizon": horizon,
        "scenarios": scenarios,
        "recommended_scenario": best["scenario"],
        "rationale": (
            f"Rolling {horizon} touchpoints forward under each strategy with "
            f"the live causal-uplift table as the reward signal, "
            f"'{best['scenario']}' (action={best['action']}) yields the "
            f"highest expected cumulative reward ({best['total_reward']:+.1f}) "
            f"while holding {best['survival_probability']:.0%} survival "
            f"probability — vs '{worst['scenario']}' at "
            f"{worst['total_reward']:+.1f}."
        ),
    }
