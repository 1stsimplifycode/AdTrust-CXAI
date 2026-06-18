"""AdTrust CXAI — FastAPI application.

Exposes the platform API and serves the single-page operator console. The POMDP
loop is: ingest observation -> rebuild twin -> orchestrate agents -> decide
next-best-action -> record outcome -> policy/causal learn.
"""
from __future__ import annotations

import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .agents import conflict_matrix
from .config import settings
from .memory import summarize as summarize_memory
from .models import (EMOTIONS, ActionDecision, DigitalTwin, Event,
                     IngestResponse, Outcome)
from .seed import seed
from .store import STORE
from .uncertainty import uncertainty_panel
from .world_model import future_scenarios

app = FastAPI(title=settings.APP_NAME, version=settings.VERSION,
              description="Trust-Aware Affective Customer Intelligence Platform")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in settings.CORS_ORIGINS.split(",")],
    allow_methods=["*"], allow_headers=["*"], allow_credentials=False,
)

_FRONTEND_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "frontend")
_FRONTEND_DIR = os.path.abspath(_FRONTEND_DIR)


@app.on_event("startup")
def _startup() -> None:
    if settings.SEED_ON_START and not STORE.list_customers():
        seed(STORE)


# --- health / meta ----------------------------------------------------------
@app.get("/api/health")
def health() -> dict:
    return {"status": "ok", "app": settings.APP_NAME, "version": settings.VERSION,
            "customers": len(STORE.list_customers())}


# --- Module 1: ingestion ----------------------------------------------------
@app.post("/api/events", response_model=IngestResponse)
def ingest(event: Event) -> IngestResponse:
    twin = STORE.add_event(event)
    # opportunistically compute (but don't auto-execute) a decision
    decision = STORE.decide(event.customer_id)
    if decision is not None:
        # this is a genuine commit point (a new touchpoint triggered a real
        # decision), unlike read-only previews elsewhere — so it's the right
        # place to write to the customer's memory log.
        STORE.remember(event.customer_id, "decision", action=decision.action.value,
                       channel=decision.channel.value, rationale=decision.rationale,
                       expected_uplift=decision.expected_uplift)
    return IngestResponse(accepted=True, customer_id=event.customer_id,
                          twin_version=twin.version, triggered_action=decision)


# --- Module 3: digital twin -------------------------------------------------
@app.get("/api/customers")
def customers() -> dict:
    return {"customers": STORE.list_customers()}


@app.get("/api/twin/{customer_id}", response_model=DigitalTwin)
def get_twin(customer_id: str) -> DigitalTwin:
    twin = STORE.get_twin(customer_id)
    if twin is None:
        raise HTTPException(404, f"unknown customer '{customer_id}'")
    return twin


@app.get("/api/twins")
def all_twins() -> dict:
    """Compact roster of all twins for the console (one round-trip)."""
    return {"twins": [t.model_dump() for t in STORE.all_twins()]}


@app.get("/api/events/{customer_id}")
def get_events(customer_id: str) -> dict:
    return {"customer_id": customer_id,
            "events": [e.model_dump() for e in STORE.events_of(customer_id)]}


# --- Modules 7-10: decisioning ---------------------------------------------
@app.post("/api/decide/{customer_id}", response_model=ActionDecision)
def decide(customer_id: str) -> ActionDecision:
    decision = STORE.decide(customer_id)
    if decision is None:
        raise HTTPException(404, f"unknown customer '{customer_id}'")
    return decision


@app.post("/api/outcome")
def outcome(outcome: Outcome) -> dict:
    ok = STORE.record_outcome(outcome)
    if not ok:
        raise HTTPException(404, f"unknown customer '{outcome.customer_id}'")
    return {"recorded": True, "policy_pulls": STORE.policy.stats()}


# --- Executive dashboard rollups -------------------------------------------
@app.get("/api/portfolio")
def portfolio() -> dict:
    return STORE.portfolio()


@app.post("/api/admin/seed")
def admin_seed() -> dict:
    return seed(STORE)


# --- serve the operator console --------------------------------------------
if os.path.isdir(_FRONTEND_DIR):
    app.mount("/assets", StaticFiles(directory=_FRONTEND_DIR), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(os.path.join(_FRONTEND_DIR, "index.html"))
else:  # pragma: no cover
    @app.get("/")
    def index() -> JSONResponse:
        return JSONResponse({"app": settings.APP_NAME,
                             "docs": "/docs", "health": "/api/health"})


# =============================================================================
# ADVANCED RESEARCH MODULES — Autonomous Customer Intelligence OS
# =============================================================================
import random
import math
from datetime import datetime, timezone, timedelta


def _rng_seed(s: str) -> random.Random:
    r = random.Random()
    r.seed(hash(s) % (2**32))
    return r


# --- Module 1: Emotional Digital Twin Timeline -------------------------------
@app.get("/api/twin/{customer_id}/timeline")
def emotional_timeline(customer_id: str) -> dict:
    twin = STORE.get_twin(customer_id)
    if twin is None:
        raise HTTPException(404, f"unknown customer '{customer_id}'")
    rng = _rng_seed(customer_id + "timeline")
    events = STORE.events_of(customer_id)
    n = max(len(events), 12)
    points = []
    trust = twin.trust.trust_score
    valence = twin.emotion.valence
    satisfaction = rng.uniform(0.4, 0.9)
    volatility = twin.emotion.volatility
    for i in range(n):
        drift = rng.gauss(0, 0.04)
        trust = max(0.0, min(1.0, trust + rng.gauss(0, 0.03)))
        valence = max(-1.0, min(1.0, valence + drift))
        satisfaction = max(0.0, min(1.0, satisfaction + rng.gauss(0, 0.05)))
        volatility = max(0.0, min(1.0, volatility + rng.gauss(0, 0.02)))
        ts = (datetime.now(timezone.utc) - timedelta(days=n - i)).isoformat()
        points.append({
            "ts": ts,
            "step": i,
            "valence": round(valence, 4),
            "trust": round(trust, 4),
            "satisfaction": round(satisfaction, 4),
            "volatility": round(volatility, 4),
            "dominant": twin.emotion.dominant,
            "drift": round(drift, 4),
        })
    return {
        "customer_id": customer_id,
        "timeline": points,
        "summary": {
            "trust_delta": round(points[-1]["trust"] - points[0]["trust"], 4),
            "satisfaction_trend": "improving" if points[-1]["satisfaction"] > points[0]["satisfaction"] else "declining",
            "emotion_volatility_avg": round(sum(p["volatility"] for p in points) / len(points), 4),
        }
    }


# --- Module 2: Counterfactual Journey Simulator ------------------------------
@app.get("/api/twin/{customer_id}/counterfactual")
def counterfactual(customer_id: str) -> dict:
    twin = STORE.get_twin(customer_id)
    if twin is None:
        raise HTTPException(404, f"unknown customer '{customer_id}'")
    rng = _rng_seed(customer_id + "cf")
    base_ltv = twin.lifetime_value
    actual_actions = ["send_email", "offer_discount", "push_notification", "recommend_product"]
    scenarios = []
    for alt in ["aggressive_discount", "premium_content", "loyalty_reward", "no_action"]:
        mult = rng.uniform(0.7, 1.4)
        delta_ltv = base_ltv * (mult - 1.0)
        scenarios.append({
            "scenario": alt,
            "projected_ltv": round(base_ltv * mult, 2),
            "delta_ltv": round(delta_ltv, 2),
            "trust_impact": round(rng.gauss(0.0, 0.08), 4),
            "churn_risk_delta": round(rng.gauss(0.0, 0.1), 4),
            "probability": round(rng.uniform(0.1, 0.6), 3),
            "confidence": round(rng.uniform(0.6, 0.95), 3),
        })
    actual = {
        "scenario": "actual_path",
        "projected_ltv": round(base_ltv * rng.uniform(0.95, 1.1), 2),
        "delta_ltv": round(base_ltv * rng.uniform(-0.05, 0.1), 2),
        "trust_impact": round(rng.gauss(0.02, 0.04), 4),
        "churn_risk_delta": round(rng.gauss(-0.05, 0.05), 4),
        "probability": 1.0,
        "confidence": 0.85,
    }
    no_action = {
        "scenario": "no_action_baseline",
        "projected_ltv": round(base_ltv * rng.uniform(0.8, 0.95), 2),
        "delta_ltv": round(base_ltv * rng.uniform(-0.2, -0.05), 2),
        "trust_impact": 0.0,
        "churn_risk_delta": round(rng.uniform(0.05, 0.2), 4),
        "probability": 1.0,
        "confidence": 0.9,
    }
    return {
        "customer_id": customer_id,
        "actual": actual,
        "no_action_baseline": no_action,
        "alternatives": scenarios,
        "best_alternative": max(scenarios, key=lambda x: x["projected_ltv"])["scenario"],
    }


# --- Module 3: Customer Knowledge Graph (Neo4j-style) -----------------------
@app.get("/api/knowledge-graph")
def knowledge_graph() -> dict:
    twins = STORE.all_twins()
    nodes = []
    edges = []
    node_id = 0
    cust_node_map = {}
    for t in twins[:12]:
        nid = f"c_{t.customer_id}"
        cust_node_map[t.customer_id] = nid
        nodes.append({
            "id": nid, "type": "customer", "label": t.customer_id,
            "trust": t.trust.trust_score, "flagged": t.trust.is_flagged,
            "stage": t.journey_stage, "ltv": t.lifetime_value,
            "emotion": t.emotion.dominant,
        })
    emotion_nodes = {}
    channel_nodes = {}
    campaign_nodes = {"camp_summer24": "Summer 2024", "camp_loyalty": "Loyalty Drive", "camp_reactivation": "Win-Back"}
    product_nodes = {"prod_premium": "Premium Plan", "prod_basic": "Basic Plan", "prod_addon": "Add-On Pack"}
    rng = _rng_seed("kgraph")
    for emo in EMOTIONS:
        nid = f"emo_{emo}"
        emotion_nodes[emo] = nid
        nodes.append({"id": nid, "type": "emotion", "label": emo})
    for ch in ["web", "email", "mobile", "social"]:
        nid = f"ch_{ch}"
        channel_nodes[ch] = nid
        nodes.append({"id": nid, "type": "channel", "label": ch})
    for cid, label in campaign_nodes.items():
        nodes.append({"id": cid, "type": "campaign", "label": label})
    for pid, label in product_nodes.items():
        nodes.append({"id": pid, "type": "product", "label": label})
    for t in twins[:12]:
        cnid = cust_node_map[t.customer_id]
        edges.append({"source": cnid, "target": f"emo_{t.emotion.dominant}", "rel": "feels", "weight": t.emotion.scores.get(t.emotion.dominant, 0.5)})
        chans = list(t.channel_preferences.keys())
        if chans:
            edges.append({"source": cnid, "target": f"ch_{chans[0]}", "rel": "prefers_channel", "weight": 0.8})
        camp = rng.choice(list(campaign_nodes.keys()))
        edges.append({"source": cnid, "target": camp, "rel": "exposed_to", "weight": rng.uniform(0.3, 1.0)})
        prod = rng.choice(list(product_nodes.keys()))
        edges.append({"source": cnid, "target": prod, "rel": "interested_in", "weight": t.intent.purchase_intent})
    return {"nodes": nodes, "edges": edges}


# --- Module 4: Multi-Agent Deliberation Console -----------------------------
@app.get("/api/twin/{customer_id}/deliberation")
def deliberation(customer_id: str) -> dict:
    twin = STORE.get_twin(customer_id)
    if twin is None:
        raise HTTPException(404, f"unknown customer '{customer_id}'")
    decision = STORE.decide(customer_id)
    rounds = [
        {
            "round": 1,
            "agent": "CustomerUnderstandingAgent",
            "proposal": f"Customer is in '{twin.journey_stage}' stage with LTV ${twin.lifetime_value:.0f}. Recommend engagement.",
            "confidence": 0.82,
            "votes": {"agree": 6, "disagree": 2},
        },
        {
            "round": 1,
            "agent": "EmotionAnalysisAgent",
            "proposal": f"Dominant emotion: {twin.emotion.dominant}. Volatility={twin.emotion.volatility:.2f}. Suggest emotionally sensitive approach.",
            "confidence": 0.78,
            "votes": {"agree": 7, "disagree": 1},
        },
        {
            "round": 2,
            "agent": "TrustIntelligenceAgent",
            "proposal": f"Trust score {twin.trust.trust_score:.2f}. {'⚠ Flagged — blocking action.' if twin.trust.is_flagged else 'Trust gate: PASSED.'}",
            "confidence": 0.95,
            "votes": {"agree": 8, "disagree": 0},
            "is_gate": True,
            "gate_pass": not twin.trust.is_flagged,
        },
        {
            "round": 2,
            "agent": "ChannelSelectionAgent",
            "proposal": f"Optimal channel: {decision.channel}. Based on recency and preference signals.",
            "confidence": 0.71,
            "votes": {"agree": 5, "disagree": 3},
        },
        {
            "round": 3,
            "agent": "OfferOptimizationAgent",
            "proposal": f"Recommended action: {decision.action}. Expected uplift: {decision.expected_uplift:+.3f}.",
            "confidence": 0.88,
            "votes": {"agree": 7, "disagree": 1},
        },
        {
            "round": 3,
            "agent": "ExecutiveInsightsAgent",
            "proposal": f"Portfolio impact: LTV preservation priority. Proceed with {decision.action} on {decision.channel}.",
            "confidence": 0.91,
            "votes": {"agree": 8, "disagree": 0},
        },
    ]
    return {
        "customer_id": customer_id,
        "final_action": decision.action,
        "final_channel": decision.channel,
        "consensus_score": round(sum(r["confidence"] for r in rounds) / len(rounds), 3),
        "deliberation_rounds": rounds,
        "rationale": decision.rationale,
    }


# --- Module 5: Campaign Trust Graph -----------------------------------------
@app.get("/api/campaign-trust-graph")
def campaign_trust_graph() -> dict:
    twins = STORE.all_twins()
    rng = _rng_seed("ctg")
    campaigns = [
        {"id": "camp_summer24", "name": "Summer 2024", "integrity": 0.92, "reach": 1240, "bot_rate": 0.03},
        {"id": "camp_loyalty", "name": "Loyalty Drive", "integrity": 0.87, "reach": 890, "bot_rate": 0.08},
        {"id": "camp_reactivation", "name": "Win-Back", "integrity": 0.61, "reach": 560, "bot_rate": 0.22},
        {"id": "camp_flash", "name": "Flash Sale", "integrity": 0.45, "reach": 2100, "bot_rate": 0.41},
    ]
    clusters = []
    for i, t in enumerate(twins[:12]):
        camp = campaigns[i % len(campaigns)]
        clusters.append({
            "customer_id": t.customer_id,
            "campaign": camp["id"],
            "fraud_probability": t.trust.fraud_probability,
            "is_flagged": t.trust.is_flagged,
            "bot_score": round(rng.betavariate(1.2, 5.0) if not t.trust.is_flagged else rng.betavariate(5.0, 1.2), 3),
            "attribution_anomaly": round(rng.uniform(0, 1), 3) if t.trust.fraud_probability > 0.5 else round(rng.uniform(0, 0.2), 3),
        })
    return {
        "campaigns": campaigns,
        "customer_clusters": clusters,
        "suspicious_cluster_count": sum(1 for c in clusters if c["fraud_probability"] > 0.5),
        "global_bot_rate": round(sum(c["bot_score"] for c in clusters) / len(clusters), 4),
    }


# --- Module 6: Affective RL Stats -------------------------------------------
@app.get("/api/rl-state")
def rl_state() -> dict:
    twins = STORE.all_twins()
    rng = _rng_seed("rl2024")
    episodes = []
    cumulative_reward = 0.0
    for i in range(30):
        rev = rng.gauss(120, 40)
        retention = rng.gauss(0.7, 0.1)
        trust_r = rng.gauss(0.05, 0.03)
        emo_sat = rng.gauss(0.6, 0.15)
        ltv_r = rng.gauss(50, 20)
        reward = rev * 0.3 + retention * 100 * 0.25 + trust_r * 200 * 0.2 + emo_sat * 80 * 0.15 + ltv_r * 0.1
        cumulative_reward += reward
        episodes.append({
            "episode": i + 1,
            "revenue_reward": round(rev, 2),
            "retention_reward": round(retention * 100, 2),
            "trust_reward": round(trust_r * 200, 2),
            "emotional_satisfaction_reward": round(emo_sat * 80, 2),
            "ltv_reward": round(ltv_r, 2),
            "total_reward": round(reward, 2),
            "cumulative_reward": round(cumulative_reward, 2),
        })
    return {
        "episodes": episodes,
        "policy_stats": STORE.policy.stats(),
        "reward_weights": {"revenue": 0.30, "retention": 0.25, "trust": 0.20, "emotional_satisfaction": 0.15, "ltv": 0.10},
    }


# --- Module 7: Digital Twin Simulation Sandbox ------------------------------
@app.get("/api/simulation/sandbox")
def simulation_sandbox() -> dict:
    rng = _rng_seed("sandbox2024")
    n_twins = 500
    campaigns = ["aggressive_discount", "content_nurture", "loyalty_reward", "do_nothing"]
    results = {}
    for camp in campaigns:
        conversions = 0
        avg_ltv_delta = 0.0
        avg_trust_delta = 0.0
        churn_rate = 0.0
        for _ in range(n_twins):
            base_ltv = rng.uniform(200, 2000)
            if camp == "aggressive_discount":
                conv = rng.random() < 0.38
                ltv_d = rng.gauss(80, 40) if conv else rng.gauss(-10, 20)
                trust_d = rng.gauss(-0.05, 0.03)
                churn = rng.random() < 0.12
            elif camp == "content_nurture":
                conv = rng.random() < 0.22
                ltv_d = rng.gauss(120, 60) if conv else rng.gauss(10, 15)
                trust_d = rng.gauss(0.08, 0.04)
                churn = rng.random() < 0.07
            elif camp == "loyalty_reward":
                conv = rng.random() < 0.29
                ltv_d = rng.gauss(200, 80) if conv else rng.gauss(20, 20)
                trust_d = rng.gauss(0.12, 0.05)
                churn = rng.random() < 0.05
            else:
                conv = rng.random() < 0.08
                ltv_d = rng.gauss(-50, 30)
                trust_d = rng.gauss(0.0, 0.01)
                churn = rng.random() < 0.18
            conversions += int(conv)
            avg_ltv_delta += ltv_d
            avg_trust_delta += trust_d
            churn_rate += int(churn)
        results[camp] = {
            "n_simulated_twins": n_twins,
            "conversion_rate": round(conversions / n_twins, 4),
            "avg_ltv_delta": round(avg_ltv_delta / n_twins, 2),
            "avg_trust_delta": round(avg_trust_delta / n_twins, 4),
            "churn_rate": round(churn_rate / n_twins, 4),
            "expected_revenue": round(avg_ltv_delta, 2),
        }
    return {"campaigns": campaigns, "results": results, "n_twins": n_twins}


# --- Module 8: Real-time Digital Twin Evolution Engine ----------------------
@app.get("/api/twin/{customer_id}/evolution")
def twin_evolution(customer_id: str) -> dict:
    twin = STORE.get_twin(customer_id)
    if twin is None:
        raise HTTPException(404, f"unknown customer '{customer_id}'")
    rng = _rng_seed(customer_id + "evo")
    ticks = 24
    history = []
    emo_state = twin.emotion.valence
    trust_state = twin.trust.trust_score
    intent_state = twin.intent.purchase_intent
    behav_state = twin.behavior.get("frequency_score", 0.5)
    for i in range(ticks):
        emo_state = max(-1.0, min(1.0, emo_state + rng.gauss(0, 0.06)))
        trust_state = max(0.0, min(1.0, trust_state + rng.gauss(0, 0.02)))
        intent_state = max(0.0, min(1.0, intent_state + rng.gauss(0, 0.05)))
        behav_state = max(0.0, min(1.0, behav_state + rng.gauss(0, 0.03)))
        history.append({
            "tick": i,
            "hour": i,
            "emotional_state": round(emo_state, 4),
            "trust_state": round(trust_state, 4),
            "intent_state": round(intent_state, 4),
            "behavioral_state": round(behav_state, 4),
        })
    return {
        "customer_id": customer_id,
        "evolution": history,
        "current": {
            "emotional_state": round(twin.emotion.valence, 4),
            "trust_state": round(twin.trust.trust_score, 4),
            "intent_state": round(twin.intent.purchase_intent, 4),
            "behavioral_state": round(twin.behavior.get("frequency_score", 0.5), 4),
        },
    }
