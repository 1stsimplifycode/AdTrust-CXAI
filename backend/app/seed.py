"""Synthetic multimodal data generator.

Creates a believable population of customers (loyal, at-risk, new, plus a few
bots / fraud personas) so the dashboard has something to show on first boot and
so the trust anomaly detector has a baseline to fit against.
"""
from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone

from .models import Channel, Event, EventType, Outcome, Action
from .store import Store

_POSITIVE_TEXT = [
    "Absolutely love this product, works perfectly and so fast!",
    "Great experience, the team was reliable and helpful, thanks!",
    "Amazing quality, I would recommend this to everyone.",
    "Excellent service, very confident buying again.",
]
_NEGATIVE_TEXT = [
    "Terrible experience, the app is broken and so slow.",
    "I am worried this is a scam, I want a refund now.",
    "Really disappointed, I will never buy here again.",
    "Confused and frustrated, support made me wait forever.",
]
_NEUTRAL_TEXT = [
    "Curious about the new features, looks interesting.",
    "Comparing a few options before I decide.",
]


def _ts(days_ago: float) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def _loyal(store: Store, cid: str) -> None:
    for d in range(20, 0, -1):
        if random.random() < 0.5:
            store.add_event(Event(customer_id=cid, event_type=EventType.page_view,
                                  channel=Channel.web, ts=_ts(d)))
        if random.random() < 0.3:
            store.add_event(Event(customer_id=cid, event_type=EventType.purchase,
                                  channel=Channel.web, value=random.uniform(40, 220),
                                  ts=_ts(d)))
    store.add_event(Event(customer_id=cid, event_type=EventType.review,
                          channel=Channel.social, text=random.choice(_POSITIVE_TEXT),
                          ts=_ts(1)))


def _at_risk(store: Store, cid: str) -> None:
    # used to buy, now slipping away
    for d in (30, 28):
        store.add_event(Event(customer_id=cid, event_type=EventType.purchase,
                              channel=Channel.web, value=random.uniform(60, 150),
                              ts=_ts(d)))
    for d in range(25, 5, -1):
        if random.random() < 0.4:
            store.add_event(Event(customer_id=cid, event_type=EventType.cart_abandon,
                                  channel=Channel.mobile, ts=_ts(d)))
    store.add_event(Event(customer_id=cid, event_type=EventType.support_message,
                          channel=Channel.support, text=random.choice(_NEGATIVE_TEXT),
                          ts=_ts(6)))
    store.add_event(Event(customer_id=cid, event_type=EventType.refund,
                          channel=Channel.support, value=-80, ts=_ts(5)))


def _new(store: Store, cid: str) -> None:
    for d in range(3, 0, -1):
        store.add_event(Event(customer_id=cid, event_type=EventType.search,
                              channel=Channel.web, ts=_ts(d)))
    # half of the new cohort browses deeper -> 'consideration'
    if int(cid.split("_")[-1]) % 2 == 0:
        for _ in range(6):
            store.add_event(Event(customer_id=cid, event_type=EventType.page_view,
                                  channel=Channel.web, ts=_ts(1)))
        store.add_event(Event(customer_id=cid, event_type=EventType.add_to_cart,
                              channel=Channel.web, ts=_ts(0.5)))
    store.add_event(Event(customer_id=cid, event_type=EventType.social_post,
                          channel=Channel.social, text=random.choice(_NEUTRAL_TEXT),
                          ts=_ts(1)))


def _bot(store: Store, cid: str) -> None:
    base = datetime.now(timezone.utc) - timedelta(hours=2)
    for i in range(40):
        ts = (base + timedelta(seconds=i * 1)).isoformat()  # metronomic 1s
        et = EventType.purchase if i % 3 == 0 else EventType.click
        store.add_event(Event(customer_id=cid, event_type=et, channel=Channel.web,
                              value=10 if et == EventType.purchase else 0, ts=ts))


def seed(store: Store, n_loyal: int = 6, n_risk: int = 5,
         n_new: int = 5, n_bot: int = 3, train_policy: bool = True) -> dict:
    random.seed(13)
    for i in range(n_loyal):
        _loyal(store, f"loyal_{i:02d}")
    for i in range(n_risk):
        _at_risk(store, f"risk_{i:02d}")
    for i in range(n_new):
        _new(store, f"new_{i:02d}")
    for i in range(n_bot):
        _bot(store, f"bot_{i:02d}")

    store.fit_trust_baseline()

    # Warm-start the bandit + causal engine with a few simulated outcomes so the
    # policy isn't cold on first load (rewards reflect plausible dynamics).
    if train_policy:
        for _ in range(200):
            cid = random.choice(store.list_customers())
            twin = store.get_twin(cid)
            if twin is None or twin.trust.is_flagged:
                continue
            decision = store.decide(cid)
            if decision is None:
                continue
            r = _simulate_reward(twin, decision.action)
            store.remember(cid, "decision", action=decision.action.value,
                          channel=decision.channel.value,
                          rationale=decision.rationale,
                          expected_uplift=decision.expected_uplift)
            store.record_outcome(Outcome(customer_id=cid, action=decision.action,
                                         reward=r))

    return {
        "customers": len(store.list_customers()),
        "portfolio": store.portfolio(),
    }


def _simulate_reward(twin, action: Action) -> float:
    """A simple environment: reward depends on matching action to twin state."""
    if action == Action.do_nothing:
        return 0.05 if twin.intent.churn_intent < 0.3 else 0.0
    if action == Action.trigger_retention:
        return 0.6 * twin.intent.churn_intent
    if action == Action.offer_discount:
        return 0.4 * twin.purchase_readiness + 0.2 * twin.intent.churn_intent
    if action == Action.recommend_product:
        return 0.5 * twin.intent.purchase_intent
    if action in (Action.send_email, Action.push_notification, Action.sms):
        return 0.25 * twin.intent.engagement_intent
    return 0.0
