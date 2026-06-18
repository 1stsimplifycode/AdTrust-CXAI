"""Domain models for AdTrust CXAI.

These pydantic schemas define the contract used across the data fabric,
the affective engine, trust engine, intent engine, agents and the API.
"""
from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


# --- The ten affective dimensions the platform reasons over -----------------
EMOTIONS = [
    "happiness",
    "satisfaction",
    "frustration",
    "excitement",
    "curiosity",
    "loyalty",
    "trust",
    "anger",
    "anxiety",
    "purchase_confidence",
]


class Channel(str, Enum):
    web = "web"
    mobile = "mobile"
    email = "email"
    sms = "sms"
    push = "push"
    support = "support"
    social = "social"
    voice = "voice"


class EventType(str, Enum):
    page_view = "page_view"
    click = "click"
    search = "search"
    add_to_cart = "add_to_cart"
    purchase = "purchase"
    review = "review"
    support_message = "support_message"
    social_post = "social_post"
    email_open = "email_open"
    email_click = "email_click"
    cart_abandon = "cart_abandon"
    refund = "refund"
    voice_call = "voice_call"


class Action(str, Enum):
    recommend_product = "recommend_product"
    send_email = "send_email"
    push_notification = "push_notification"
    sms = "sms"
    offer_discount = "offer_discount"
    trigger_retention = "trigger_retention"
    do_nothing = "do_nothing"


# --- Observations ------------------------------------------------------------
class Event(BaseModel):
    """A single observation in the POMDP (Module 1: Data Fabric)."""
    customer_id: str
    event_type: EventType
    channel: Channel = Channel.web
    text: Optional[str] = None        # review / chat / social / support body
    value: float = 0.0                # monetary value where relevant
    metadata: dict[str, Any] = Field(default_factory=dict)
    ts: str = Field(default_factory=_now)


class IngestResponse(BaseModel):
    accepted: bool
    customer_id: str
    twin_version: int
    triggered_action: Optional["ActionDecision"] = None


# --- Affective layer (Module 2) ---------------------------------------------
class EmotionState(BaseModel):
    scores: dict[str, float]          # emotion -> [0,1]
    dominant: str
    valence: float                    # [-1, 1]
    arousal: float                    # [0, 1]
    volatility: float                 # how unstable recent emotion has been
    confidence: float                 # model confidence in this reading
    trajectory: list[float] = Field(default_factory=list)  # recent valence


# --- Trust layer (Module 6) -------------------------------------------------
class TrustState(BaseModel):
    trust_score: float                # [0,1] higher == more trustworthy
    fraud_probability: float          # [0,1]
    authenticity_score: float         # [0,1]
    signals: list[str] = Field(default_factory=list)
    is_flagged: bool = False


# --- Intent layer (Module 5) ------------------------------------------------
class IntentState(BaseModel):
    purchase_intent: float
    churn_intent: float
    upsell_intent: float
    engagement_intent: float
    support_intent: float
    advocacy_intent: float
    emotion_shift_risk: float
    trust_degradation_risk: float


# --- Digital twin (Module 3) ------------------------------------------------
class DigitalTwin(BaseModel):
    customer_id: str
    version: int
    emotion: EmotionState
    trust: TrustState
    intent: IntentState
    behavior: dict[str, float]
    channel_preferences: dict[str, float]
    purchase_readiness: float
    lifetime_value: float
    journey_stage: str
    embedding: list[float]            # unified customer embedding (Module 4)
    updated_at: str = Field(default_factory=_now)


# --- Action / orchestration (Modules 7, 8, 9, 10) ---------------------------
class ActionDecision(BaseModel):
    customer_id: str
    action: Action
    channel: Channel
    expected_uplift: float            # causal incremental lift estimate
    propensity: float                 # policy probability
    rationale: str                    # natural-language explanation
    feature_attributions: dict[str, float]
    agent_trace: list[dict[str, Any]]
    decided_at: str = Field(default_factory=_now)


class Outcome(BaseModel):
    """Feedback used to update the online RL-lite policy."""
    customer_id: str
    action: Action
    reward: float                     # blended revenue/retention/trust signal


IngestResponse.model_rebuild()
