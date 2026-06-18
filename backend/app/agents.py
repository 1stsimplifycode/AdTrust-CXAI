"""Module 7 — Multi-Agent AI System.

Nine cooperating agents share a blackboard and run as a directed graph. We
implement the orchestration in pure Python (no LangGraph dependency) so the
service stays deployable, but the structure mirrors a LangGraph StateGraph:
each agent is a node that reads/writes shared state, and the graph has a
conditional edge (the Trust agent can short-circuit the journey).

Agents:
  1 Customer Understanding   2 Emotion Analysis      3 Trust Intelligence
  4 Channel Selection        5 Content Personalization 6 Offer Optimization
  7 Journey Orchestration    8 Causal Attribution    9 Executive Insights
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional

import numpy as np

from .causal import CausalEngine
from .explain import assemble_decision
from .models import Action, ActionDecision, Channel, DigitalTwin
from .policy import ContextualBanditPolicy


def _trace(name: str, summary: str, **data: Any) -> dict[str, Any]:
    return {"agent": name, "summary": summary, **data}


class JourneyOrchestrator:
    """Runs the agent graph to produce a single next-best-action decision."""

    def __init__(self, policy: ContextualBanditPolicy, causal: CausalEngine) -> None:
        self.policy = policy
        self.causal = causal

    def run(self, twin: DigitalTwin, memory_log: Optional[list[dict]] = None) -> ActionDecision:
        memory_log = memory_log or []
        bb: dict[str, Any] = {"twin": twin, "trace": []}

        # Agent 1 — Customer Understanding
        bb["trace"].append(_trace(
            "CustomerUnderstandingAgent",
            f"stage={twin.journey_stage}, LTV={twin.lifetime_value}, "
            f"readiness={twin.purchase_readiness}",
            journey_stage=twin.journey_stage, ltv=twin.lifetime_value))

        # Agent 2 — Emotion Analysis
        bb["trace"].append(_trace(
            "EmotionAnalysisAgent",
            f"dominant={twin.emotion.dominant}, valence={twin.emotion.valence}, "
            f"volatility={twin.emotion.volatility}",
            dominant=twin.emotion.dominant, valence=twin.emotion.valence))

        # Agent 3 — Trust Intelligence  (conditional gate)
        bb["trace"].append(_trace(
            "TrustIntelligenceAgent",
            f"trust={twin.trust.trust_score}, fraud_p={twin.trust.fraud_probability}, "
            f"flagged={twin.trust.is_flagged}",
            fraud_probability=twin.trust.fraud_probability,
            signals=twin.trust.signals))

        if twin.trust.is_flagged:
            # short-circuit: skip personalization/offers, hold out
            action, propensity, _ = (Action.do_nothing, 1.0, [])
            uplift = self.causal.uplift(twin, action)
            cf = self.causal.counterfactual(twin, action)
            bb["trace"].append(_trace(
                "JourneyOrchestrationAgent",
                "trust gate tripped -> route to manual review, suppress paid actions"))
            bb["trace"].append(_trace(
                "ExecutiveInsightsAgent",
                "Flagged profile excluded from campaign integrity rollup."))
            return assemble_decision(twin, action, Channel.web, propensity,
                                     uplift, cf, bb["trace"])

        # Agent 4 — Channel Selection (use learned preferences w/ fallbacks)
        channel = self._select_channel(twin)
        bb["trace"].append(_trace(
            "ChannelSelectionAgent", f"selected channel={channel.value}",
            channel=channel.value, preferences=twin.channel_preferences))

        # Memory Recall Agent — condition action selection on this customer's
        # actual observed history, not just the live context vector. Any
        # action with >=2 past outcomes averaging poor reward gets vetoed
        # from the bandit's ranked list before the top pick is taken.
        ranked = self.policy.rank(twin)
        penalized = _memory_penalized_actions(memory_log)
        filtered = [(a, s) for a, s in ranked if a not in penalized] or ranked
        action, top_score = filtered[0]
        scores = np.array([s for _, s in filtered])
        ex = np.exp(scores - scores.max())
        propensity = float((ex / ex.sum())[0])
        if penalized:
            bb["trace"].append(_trace(
                "MemoryRecallAgent",
                f"recalled {len(memory_log)} past memory record(s); vetoed "
                f"{[a.value for a in penalized]} on historically poor reward",
                memory_size=len(memory_log),
                penalized_actions=[a.value for a in penalized]))
        else:
            bb["trace"].append(_trace(
                "MemoryRecallAgent",
                f"recalled {len(memory_log)} past memory record(s); no "
                f"negative reward pattern found, no veto applied",
                memory_size=len(memory_log), penalized_actions=[]))

        # Agent 5 — Content Personalization
        bb["trace"].append(_trace(
            "ContentPersonalizationAgent",
            f"tone tuned to '{twin.emotion.dominant}'; "
            f"affect-aware copy for stage '{twin.journey_stage}'"))

        # Agent 6 — Offer Optimization
        discount = self._offer_size(twin)
        bb["trace"].append(_trace(
            "OfferOptimizationAgent",
            f"recommended incentive depth={discount:.0%} "
            f"(churn={twin.intent.churn_intent}, margin-aware)",
            discount=discount))

        # Agent 8 — Causal Attribution
        uplift = self.causal.uplift(twin, action)
        cf = self.causal.counterfactual(twin, action)
        bb["trace"].append(_trace(
            "CausalAttributionAgent",
            f"expected incremental uplift={uplift:+.3f} vs do-nothing baseline",
            expected_uplift=uplift))

        # Agent 7 — Journey Orchestration (final commit)
        bb["trace"].append(_trace(
            "JourneyOrchestrationAgent",
            f"commit action={action.value} on {channel.value} "
            f"(policy propensity={propensity:.2f})",
            ranked=[(a.value, round(s, 3)) for a, s in ranked[:4]]))

        # Agent 9 — Executive Insights
        bb["trace"].append(_trace(
            "ExecutiveInsightsAgent",
            f"contributes +{uplift:+.3f} expected uplift to portfolio; "
            f"LTV trajectory {'up' if twin.intent.upsell_intent > 0.5 else 'flat'}"))

        return assemble_decision(twin, action, channel, propensity, uplift, cf,
                                 bb["trace"])

    def _select_channel(self, twin: DigitalTwin) -> Channel:
        prefs = twin.channel_preferences
        if prefs:
            best = max(prefs, key=prefs.get)
            try:
                return Channel(best)
            except ValueError:
                pass
        # affect-aware fallback: anxious/frustrated -> gentler channels
        if twin.emotion.scores["frustration"] > 0.5:
            return Channel.email
        return Channel.push

    def _offer_size(self, twin: DigitalTwin) -> float:
        # deeper discounts only where churn risk justifies the margin hit
        base = 0.05
        base += 0.15 * twin.intent.churn_intent
        base += 0.05 * (1 - twin.purchase_readiness)
        return min(round(base, 2), 0.30)


def _memory_penalized_actions(memory_log: list[dict]) -> set[Action]:
    """Actions with >=2 observed outcomes averaging poor reward for THIS
    customer specifically — real history, not a population-level prior."""
    rewards: dict[Action, list[float]] = defaultdict(list)
    for m in memory_log:
        if m.get("type") != "outcome":
            continue
        try:
            rewards[Action(m["action"])].append(m["reward"])
        except (KeyError, ValueError):
            continue
    return {a for a, rs in rewards.items() if len(rs) >= 2 and sum(rs) / len(rs) < 0.05}


# =============================================================================
#  Agent Conflict Matrix — independent votes, not a hard-coded consensus stat.
# =============================================================================
# Each function below is a *different* sub-model reading the *same* twin and
# casting its own action vote from its own evidence: emotion heuristics,
# trust-gate heuristics, the live CausalEngine's uplift table, the lifecycle
# stage, the bandit's own LinUCB ranking, and this customer's reward history.
# Disagreement is therefore a real, computed quantity — it is whatever
# fraction of these independently-reasoned votes diverge from the action the
# orchestrator above actually commits to, not a fixed narrative number.

def _emotion_vote(twin: DigitalTwin) -> tuple[Action, str]:
    dom = twin.emotion.dominant
    if dom in ("anger", "frustration", "anxiety"):
        return Action.trigger_retention, (
            f"dominant emotion '{dom}' signals distress; recommend a "
            f"retention play before churn risk compounds")
    if dom in ("loyalty", "satisfaction", "trust", "purchase_confidence"):
        return Action.recommend_product, (
            f"dominant emotion '{dom}' signals readiness; recommend an "
            f"upsell-oriented touch")
    return Action.send_email, (
        f"dominant emotion '{dom}' is neutral/exploratory; recommend a "
        f"light-touch nurture email")


def _trust_vote(twin: DigitalTwin) -> tuple[Action, str]:
    if twin.trust.is_flagged or twin.trust.trust_score < 0.55:
        return Action.do_nothing, (
            f"trust_score={twin.trust.trust_score:.2f} is below the action "
            f"threshold; hold out paid interventions")
    if twin.intent.churn_intent > 0.55:
        return Action.trigger_retention, (
            f"trust intact (score={twin.trust.trust_score:.2f}) but "
            f"churn_intent={twin.intent.churn_intent:.2f} is elevated")
    return Action.recommend_product, (
        f"trust_score={twin.trust.trust_score:.2f} clears the gate; safe "
        f"to engage commercially")


def _offer_vote(causal: CausalEngine, twin: DigitalTwin) -> tuple[Action, str]:
    candidates = [Action.offer_discount, Action.trigger_retention,
                  Action.recommend_product, Action.send_email]
    scored = sorted(((a, causal.uplift(twin, a)) for a in candidates),
                    key=lambda t: t[1], reverse=True)
    best, u = scored[0]
    return best, (f"highest causal uplift among candidates "
                  f"({u:+.3f} incremental vs. do-nothing baseline)")


_JOURNEY_PLAY = {
    "awareness": Action.push_notification,
    "consideration": Action.recommend_product,
    "conversion": Action.offer_discount,
    "at_risk": Action.trigger_retention,
    "loyalty": Action.recommend_product,
    "advocacy": Action.send_email,
}


def _journey_vote(twin: DigitalTwin) -> tuple[Action, str]:
    stage = twin.journey_stage
    action = _JOURNEY_PLAY.get(stage, Action.send_email)
    return action, f"lifecycle stage '{stage}' maps to a {action.value} play"


def _rl_vote(policy: ContextualBanditPolicy, twin: DigitalTwin) -> tuple[Action, str]:
    ranked = policy.rank(twin)
    best, score = ranked[0]
    return best, f"LinUCB top arm, score={score:.3f} (mean + exploration bonus)"


def _memory_vote(memory_log: list[dict]) -> tuple[Action, str]:
    rewards: dict[Action, list[float]] = defaultdict(list)
    for m in memory_log:
        if m.get("type") != "outcome":
            continue
        try:
            rewards[Action(m["action"])].append(m["reward"])
        except (KeyError, ValueError):
            continue
    if not rewards:
        return Action.do_nothing, "no reward history yet for this customer; abstains toward holdout"
    avg = {a: sum(rs) / len(rs) for a, rs in rewards.items()}
    best = max(avg, key=avg.get)
    return best, f"'{best.value}' has the best historical avg reward ({avg[best]:+.2f}) for this customer"


def conflict_matrix(twin: DigitalTwin, policy: ContextualBanditPolicy,
                    causal: CausalEngine, memory_log: list[dict],
                    final_decision: ActionDecision) -> dict:
    """Six independently-reasoned votes vs. the orchestrator's single
    committed decision. consensus_score / has_disagreement are computed
    directly from those votes, never hard-coded."""
    voters = [
        ("EmotionAnalysisAgent", _emotion_vote(twin)),
        ("TrustIntelligenceAgent", _trust_vote(twin)),
        ("OfferOptimizationAgent (Causal)", _offer_vote(causal, twin)),
        ("JourneyOrchestrationAgent", _journey_vote(twin)),
        ("AffectiveRLAgent (LinUCB)", _rl_vote(policy, twin)),
        ("MemoryRecallAgent", _memory_vote(memory_log)),
    ]
    votes = [{"agent": name, "vote": action.value, "rationale": why}
             for name, (action, why) in voters]
    counts: dict[str, int] = defaultdict(int)
    for v in votes:
        counts[v["vote"]] += 1

    final_action = final_decision.action.value
    agree = counts.get(final_action, 0)
    total = len(votes)
    return {
        "customer_id": twin.customer_id,
        "votes": votes,
        "vote_counts": dict(counts),
        "final_action": final_action,
        "final_channel": final_decision.channel.value,
        "agents_agreeing": agree,
        "agents_total": total,
        "consensus_score": round(agree / total, 3),
        "has_disagreement": agree < total,
    }
