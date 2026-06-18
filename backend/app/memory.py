"""Module 13 — Customer Memory Layer.

The digital twin (Module 3) is the customer's *current* state. Memory is the
durable record of how that state arrived, so agents can condition on history
instead of re-deciding from a blank slate every time.

Deliberately, nothing here is synthesized after the fact. The Store appends
to three real streams as a side effect of normal operation, each tied to the
event that actually caused it:

  * decision   — every action the platform actually committed to (at
                  ingestion time and during bandit training), not a
                  reconstruction.
  * outcome    — every reward the policy/causal engine actually observed for
                  an action on this customer (the same observations that
                  update ContextualBanditPolicy and CausalEngine).
  * trust_shift / emotion_shift — captured at twin-rebuild time, the instant
                  trust crossed a +/-3pp move or the dominant emotion
                  changed, tagged with the real triggering event type.

`summarize` turns those streams into the short natural-language brief the
multi-agent system's MemoryRecallAgent conditions on (see agents.py).
"""
from __future__ import annotations

from collections import Counter, defaultdict


def summarize(customer_id: str, log: list[dict],
             channel_preferences: dict[str, float]) -> dict:
    decisions = [m for m in log if m["type"] == "decision"]
    outcomes = [m for m in log if m["type"] == "outcome"]
    trust_shifts = [m for m in log if m["type"] == "trust_shift"]
    emotion_shifts = [m for m in log if m["type"] == "emotion_shift"]

    lines: list[str] = []

    if channel_preferences:
        top = max(channel_preferences, key=channel_preferences.get)
        lines.append(f"Prefers the {top} channel "
                     f"({channel_preferences[top]:.0%} of touchpoints).")

    if outcomes:
        by_action: dict[str, list[float]] = defaultdict(list)
        for o in outcomes:
            by_action[o["action"]].append(o["reward"])
        avg_by_action = {a: sum(rs) / len(rs) for a, rs in by_action.items()}
        best = max(avg_by_action, key=avg_by_action.get)
        worst = min(avg_by_action, key=avg_by_action.get)
        if avg_by_action[best] >= 0.15:
            lines.append(f"Responds positively to '{best}' "
                        f"(avg reward {avg_by_action[best]:+.2f} across "
                        f"{len(by_action[best])} exposure(s)).")
        if worst != best and avg_by_action[worst] < 0.05:
            lines.append(f"'{worst}' has historically underperformed for "
                        f"this customer (avg reward {avg_by_action[worst]:+.2f}).")

    if trust_shifts:
        drops = [t for t in trust_shifts if t["delta"] < 0]
        if drops:
            worst_drop = min(drops, key=lambda t: t["delta"])
            lines.append(f"Sharpest trust drop ({worst_drop['delta']:+.2f}) "
                        f"followed a '{worst_drop['trigger_event_type']}' event.")
        gains = [t for t in trust_shifts if t["delta"] > 0]
        if gains:
            lines.append(f"Trust has recovered {len(gains)} time(s) since.")

    if emotion_shifts:
        frustration_hits = [e for e in emotion_shifts
                            if e["new_emotion"] in ("frustration", "anger", "anxiety")]
        if frustration_hits:
            lines.append(
                f"Has shifted into a negative emotional state "
                f"{len(frustration_hits)} time(s), most recently after a "
                f"'{frustration_hits[-1]['trigger_event_type']}' event.")
        last = emotion_shifts[-1]
        lines.append(f"Most recent emotional shift: "
                    f"{last['previous_emotion']} -> {last['new_emotion']} "
                    f"(trigger: {last['trigger_event_type']}).")

    if decisions:
        most_common, n = Counter(d["action"] for d in decisions).most_common(1)[0]
        lines.append(f"Has been offered '{most_common}' {n} time(s) historically.")

    if not lines:
        lines.append("Limited interaction history — memory will build as "
                    "more touchpoints are observed.")

    return {
        "customer_id": customer_id,
        "summary_lines": lines,
        "decision_log": list(reversed(decisions[-10:])),
        "outcome_log": list(reversed(outcomes[-10:])),
        "trust_history": list(reversed(trust_shifts[-10:])),
        "emotion_transitions": list(reversed(emotion_shifts[-10:])),
        "memory_depth": len(log),
    }
