"""Module 2 — Affective Computing Engine.

Infers a 10-dimensional emotional state from multimodal signals.

Design note
-----------
The full research system swaps in RoBERTa / DeBERTa (text), Wav2Vec2 / HuBERT
(voice) and ViT / CLIP (vision). Those are heavy and GPU-bound, so this module
ships with a deterministic, dependency-free reference implementation:

  * a lexicon-based text affect model over the 10 target emotions, and
  * a behavioural affect model that reads emotion out of event dynamics
    (cart abandons, refunds, repeat purchases, support volume, recency).

`infer_text_emotion` is the single seam where a transformer backend can be
plugged in (see TextEmotionBackend). The rest of the platform only depends on
the EmotionState contract, so the upgrade is local.
"""
from __future__ import annotations

import math
from collections import deque
from typing import Iterable

from .models import EMOTIONS, Event, EmotionState

# --- Lexicon: term -> per-emotion weights -----------------------------------
# Deliberately compact but covers the affective space the platform reasons over.
_LEXICON: dict[str, dict[str, float]] = {
    # positive
    "love": {"happiness": 0.9, "loyalty": 0.6, "trust": 0.4},
    "great": {"happiness": 0.7, "satisfaction": 0.6},
    "excellent": {"satisfaction": 0.8, "happiness": 0.6},
    "amazing": {"excitement": 0.8, "happiness": 0.7},
    "perfect": {"satisfaction": 0.85, "purchase_confidence": 0.5},
    "fast": {"satisfaction": 0.5, "purchase_confidence": 0.3},
    "recommend": {"loyalty": 0.7, "advocacy": 0.0, "trust": 0.5},
    "thanks": {"happiness": 0.5, "trust": 0.4},
    "reliable": {"trust": 0.8, "loyalty": 0.5},
    "easy": {"satisfaction": 0.6, "purchase_confidence": 0.4},
    "wow": {"excitement": 0.85, "curiosity": 0.4},
    "curious": {"curiosity": 0.85},
    "interesting": {"curiosity": 0.7, "excitement": 0.3},
    "confident": {"purchase_confidence": 0.8, "trust": 0.4},
    "buy": {"purchase_confidence": 0.5},
    # negative
    "hate": {"anger": 0.9, "frustration": 0.6},
    "terrible": {"frustration": 0.8, "anger": 0.6},
    "awful": {"frustration": 0.8, "anger": 0.5},
    "broken": {"frustration": 0.75, "anger": 0.4},
    "slow": {"frustration": 0.7},
    "scam": {"anger": 0.8, "anxiety": 0.6, "trust": -0.9},
    "fraud": {"anger": 0.7, "anxiety": 0.7, "trust": -0.9},
    "refund": {"frustration": 0.6, "anxiety": 0.4},
    "cancel": {"frustration": 0.5, "anxiety": 0.4, "loyalty": -0.5},
    "wait": {"frustration": 0.5, "anxiety": 0.3},
    "worried": {"anxiety": 0.85},
    "anxious": {"anxiety": 0.9},
    "confused": {"anxiety": 0.5, "frustration": 0.4},
    "disappointed": {"frustration": 0.7, "loyalty": -0.4},
    "never": {"anger": 0.4, "loyalty": -0.4},
    "unsafe": {"anxiety": 0.7, "trust": -0.7},
}

# Map "advocacy" lexicon hits onto loyalty (advocacy isn't an emotion dim here).
_ALIAS = {"advocacy": "loyalty"}

_VALENCE = {
    "happiness": 1.0, "satisfaction": 0.8, "excitement": 0.7, "curiosity": 0.3,
    "loyalty": 0.6, "trust": 0.7, "purchase_confidence": 0.6,
    "frustration": -0.8, "anger": -1.0, "anxiety": -0.6,
}
_AROUSAL = {
    "happiness": 0.6, "satisfaction": 0.3, "excitement": 0.95, "curiosity": 0.6,
    "loyalty": 0.3, "trust": 0.2, "purchase_confidence": 0.5,
    "frustration": 0.7, "anger": 0.9, "anxiety": 0.7,
}


class TextEmotionBackend:
    """Pluggable text emotion model. Default == lexicon. Swap for a transformer.

    To use a HuggingFace model, subclass and override `score`:

        class RobertaBackend(TextEmotionBackend):
            def score(self, text): ...  # return dict[emotion -> 0..1]
    """

    def score(self, text: str) -> dict[str, float]:
        scores = {e: 0.0 for e in EMOTIONS}
        if not text:
            return scores
        tokens = [t.strip(".,!?;:()\"'").lower() for t in text.split()]
        negate = False
        for tok in tokens:
            if tok in ("not", "no", "never", "dont", "don't", "cant", "can't"):
                negate = True
                continue
            weights = _LEXICON.get(tok)
            if not weights:
                negate = False
                continue
            sign = -1.0 if negate else 1.0
            for emo, w in weights.items():
                emo = _ALIAS.get(emo, emo)
                if emo in scores:
                    scores[emo] = _clip01(scores[emo] + sign * w)
            negate = False
        # mild exclamation amplification of arousal-linked emotions
        if "!" in text:
            for emo in ("excitement", "anger", "frustration"):
                scores[emo] = _clip01(scores[emo] * 1.15)
        return scores


_TEXT_BACKEND = TextEmotionBackend()


def _clip01(x: float) -> float:
    return max(0.0, min(1.0, x))


def _behavioural_affect(events: list[Event]) -> dict[str, float]:
    """Read emotion out of behaviour dynamics, not words."""
    scores = {e: 0.0 for e in EMOTIONS}
    if not events:
        return scores
    recent = events[-25:]
    n = len(recent)
    purchases = sum(1 for e in recent if e.event_type == "purchase")
    aborts = sum(1 for e in recent if e.event_type == "cart_abandon")
    refunds = sum(1 for e in recent if e.event_type == "refund")
    support = sum(1 for e in recent if e.event_type == "support_message")
    reviews = sum(1 for e in recent if e.event_type == "review")

    scores["purchase_confidence"] = _clip01(0.2 + 0.3 * purchases)
    scores["loyalty"] = _clip01(0.15 * purchases - 0.2 * refunds)
    scores["satisfaction"] = _clip01(0.25 * purchases - 0.15 * support)
    scores["frustration"] = _clip01(0.25 * aborts + 0.3 * refunds + 0.1 * support)
    scores["anxiety"] = _clip01(0.2 * refunds + 0.15 * support)
    scores["excitement"] = _clip01(0.2 * reviews + 0.1 * purchases)
    scores["curiosity"] = _clip01(0.1 * sum(1 for e in recent
                                            if e.event_type in ("search", "page_view")) / max(n, 1))
    return scores


def infer_emotion(events: list[Event],
                  prior_trajectory: Iterable[float] | None = None) -> EmotionState:
    """Fuse text + behavioural affect into a single EmotionState."""
    text_scores = {e: 0.0 for e in EMOTIONS}
    text_events = [e for e in events if e.text]
    for ev in text_events[-10:]:
        s = _TEXT_BACKEND.score(ev.text or "")
        for emo in EMOTIONS:
            text_scores[emo] = max(text_scores[emo], s[emo])

    beh_scores = _behavioural_affect(events)

    # Late-fusion: text dominates where present, behaviour fills the rest.
    has_text = len(text_events) > 0
    w_text = 0.65 if has_text else 0.0
    fused = {}
    for emo in EMOTIONS:
        fused[emo] = _clip01(w_text * text_scores[emo] + (1 - w_text) * beh_scores[emo])

    dominant = max(fused, key=fused.get) if any(fused.values()) else "curiosity"

    # Valence / arousal as weighted aggregates of the emotion vector.
    total = sum(fused.values()) or 1.0
    valence = sum(fused[e] * _VALENCE[e] for e in EMOTIONS) / total
    arousal = sum(fused[e] * _AROUSAL[e] for e in EMOTIONS) / total

    traj = list(prior_trajectory or [])
    traj.append(round(valence, 4))
    traj = traj[-20:]
    volatility = _volatility(traj)

    # confidence: more signal (esp. text) -> more confident
    confidence = _clip01(0.4 + 0.05 * len(events) + (0.2 if has_text else 0.0))

    return EmotionState(
        scores={k: round(v, 4) for k, v in fused.items()},
        dominant=dominant,
        valence=round(valence, 4),
        arousal=round(arousal, 4),
        volatility=round(volatility, 4),
        confidence=round(confidence, 4),
        trajectory=traj,
    )


def _volatility(traj: list[float]) -> float:
    if len(traj) < 2:
        return 0.0
    diffs = [abs(traj[i] - traj[i - 1]) for i in range(1, len(traj))]
    mean = sum(diffs) / len(diffs)
    return _clip01(mean * 1.5)
