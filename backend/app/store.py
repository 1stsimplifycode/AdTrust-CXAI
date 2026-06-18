"""Module 1 — Multimodal Customer Data Fabric (in-memory reference store).

Holds the event log per customer and caches the latest twin. In production this
is replaced by PostgreSQL (events/outcomes), Neo4j (identity/trust graphs),
Qdrant (embedding search) and Kafka (ingestion) — see docs/DATABASE_SCHEMA.md.
The Store exposes the same methods regardless of backend, so the API layer is
storage-agnostic.
"""
from __future__ import annotations

import threading
from collections import defaultdict
from datetime import datetime, timezone
from typing import Optional

from .agents import JourneyOrchestrator
from .causal import CausalEngine
from .models import (ActionDecision, DigitalTwin, Event, Outcome)
from .policy import ContextualBanditPolicy
from .trust import TrustEngine
from .twin import build_twin

# Trust swings below this magnitude are noise, not a memorable "shift".
_TRUST_SHIFT_THRESHOLD = 0.03


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._events: dict[str, list[Event]] = defaultdict(list)
        self._twins: dict[str, DigitalTwin] = {}
        self._versions: dict[str, int] = defaultdict(int)
        self._memory_log: dict[str, list[dict]] = defaultdict(list)
        self.trust_engine = TrustEngine()
        self.policy = ContextualBanditPolicy()
        self.causal = CausalEngine()
        self.orchestrator = JourneyOrchestrator(self.policy, self.causal)

    # --- ingestion ----------------------------------------------------------
    def add_event(self, event: Event) -> DigitalTwin:
        with self._lock:
            self._events[event.customer_id].append(event)
            return self._rebuild(event.customer_id, trigger=event)

    def _rebuild(self, customer_id: str, trigger: Optional[Event] = None) -> DigitalTwin:
        self._versions[customer_id] += 1
        prior = self._twins.get(customer_id)
        traj = prior.emotion.trajectory if prior else None
        twin = build_twin(customer_id, self._events[customer_id],
                          self.trust_engine, self._versions[customer_id], traj)
        self._twins[customer_id] = twin
        if prior is not None:
            self._note_shifts(customer_id, prior, twin, trigger)
        return twin

    def _note_shifts(self, customer_id: str, prior: DigitalTwin,
                     twin: DigitalTwin, trigger: Optional[Event]) -> None:
        """Real memory, captured at the instant it happens: a >=3pp trust
        swing or a dominant-emotion change, tagged with whatever event (if
        any) triggered this rebuild."""
        trigger_type = trigger.event_type.value if trigger else "baseline_recompute"
        delta = round(twin.trust.trust_score - prior.trust.trust_score, 4)
        if abs(delta) >= _TRUST_SHIFT_THRESHOLD:
            self.remember(customer_id, "trust_shift",
                         previous_trust=round(prior.trust.trust_score, 4),
                         new_trust=round(twin.trust.trust_score, 4),
                         delta=delta, trigger_event_type=trigger_type)
        if twin.emotion.dominant != prior.emotion.dominant:
            self.remember(customer_id, "emotion_shift",
                         previous_emotion=prior.emotion.dominant,
                         new_emotion=twin.emotion.dominant,
                         trigger_event_type=trigger_type)

    # --- memory ---------------------------------------------------------
    def remember(self, customer_id: str, kind: str, **fields) -> dict:
        entry = {"type": kind, "ts": _now(), **fields}
        log = self._memory_log[customer_id]
        log.append(entry)
        if len(log) > 300:
            del log[: len(log) - 300]
        return entry

    def memory_of(self, customer_id: str) -> list[dict]:
        return list(self._memory_log.get(customer_id, []))

    # --- reads --------------------------------------------------------------
    def get_twin(self, customer_id: str) -> Optional[DigitalTwin]:
        return self._twins.get(customer_id)

    def list_customers(self) -> list[str]:
        return list(self._twins.keys())

    def all_twins(self) -> list[DigitalTwin]:
        return list(self._twins.values())

    def events_of(self, customer_id: str) -> list[Event]:
        return list(self._events.get(customer_id, []))

    # --- decisioning --------------------------------------------------------
    def decide(self, customer_id: str) -> Optional[ActionDecision]:
        twin = self.get_twin(customer_id)
        if twin is None:
            return None
        return self.orchestrator.run(twin, self.memory_of(customer_id))

    def record_outcome(self, outcome: Outcome) -> bool:
        twin = self.get_twin(outcome.customer_id)
        if twin is None:
            return False
        self.policy.update(twin, outcome.action, outcome.reward)
        self.causal.observe(twin, outcome.action, outcome.reward)
        self.remember(outcome.customer_id, "outcome", action=outcome.action.value,
                      reward=round(outcome.reward, 4))
        return True

    # --- baseline fit for the trust anomaly detector ------------------------
    def fit_trust_baseline(self) -> None:
        self.trust_engine.fit_baseline(list(self._events.values()))
        # refresh twins so trust scores reflect the fitted detector
        with self._lock:
            for cid in list(self._twins.keys()):
                self._rebuild(cid)

    # --- portfolio rollups for the executive dashboard ----------------------
    def portfolio(self) -> dict:
        twins = self.all_twins()
        if not twins:
            return {"customers": 0}
        n = len(twins)
        flagged = [t for t in twins if t.trust.is_flagged]
        avg = lambda f: round(sum(f(t) for t in twins) / n, 4)
        integrity = self.trust_engine.campaign_integrity(
            [t.trust.trust_score for t in twins])
        return {
            "customers": n,
            "flagged": len(flagged),
            "campaign_integrity": integrity,
            "avg_trust": avg(lambda t: t.trust.trust_score),
            "avg_purchase_intent": avg(lambda t: t.intent.purchase_intent),
            "avg_churn_intent": avg(lambda t: t.intent.churn_intent),
            "avg_valence": avg(lambda t: t.emotion.valence),
            "total_ltv": round(sum(t.lifetime_value for t in twins), 2),
            "policy_pulls": self.policy.stats(),
            "stage_distribution": _stage_dist(twins),
        }


def _stage_dist(twins) -> dict[str, int]:
    from collections import Counter
    return dict(Counter(t.journey_stage for t in twins))


STORE = Store()
