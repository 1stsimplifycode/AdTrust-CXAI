# Architecture

AdTrust CXAI is a single FastAPI service that implements the full POMDP control
loop in-process. This document maps each of the ten modules to its code, states
the contract it exposes, and names the **swap-in seam** where the heavy research
backend replaces the reference implementation without touching the rest of the
system.

The guiding principle is **contract stability**: every module communicates via
the pydantic models in `backend/app/models.py` (`EmotionState`, `TrustState`,
`IntentState`, `DigitalTwin`, `ActionDecision`). As long as a replacement honours
the contract, it is a local change.

```
                    ┌───────────────────────────────────────────────┐
   events  ───────▶ │  Module 1  Data Fabric (store.py)             │
                    └───────────────┬───────────────────────────────┘
                                    ▼  rebuild on every event
        ┌──────────────┬──────────────┬───────────────┐
        ▼              ▼              ▼               ▼
   M2 Affective   M6 Trust      M5 Intent       M3/M4 Twin+Embedding
   (affective.py) (trust.py)    (intent.py)     (twin.py)
        └──────────────┴──────────────┴───────────────┘
                                    ▼  DigitalTwin
                    ┌───────────────────────────────────────────────┐
                    │  Module 7  Agent Graph (agents.py)            │
                    │  ├─ trust gate (M6) ── flagged ─▶ hold out    │
                    │  ├─ channel select                            │
                    │  ├─ M8 policy (policy.py)  propose action     │
                    │  ├─ M9 causal (causal.py)  uplift + cfactual  │
                    │  └─ M10 explain (explain.py) rationale+attrib │
                    └───────────────┬───────────────────────────────┘
                                    ▼  ActionDecision
                          outcome ──▶ policy.update + causal.observe  (online learning)
```

## Module 1 — Multimodal Data Fabric
**Code:** `store.py`, `models.Event`
**Contract:** append-only event log per customer; `add_event` triggers a twin rebuild.
**Reference:** thread-safe in-memory dict.
**Seam:** swap `Store` methods for PostgreSQL (events/outcomes), Kafka (ingestion
stream), Redis (twin cache), Qdrant (embedding ANN search), Neo4j (identity/trust
graphs). The API layer only calls `Store` methods, so persistence is pluggable.

## Module 2 — Affective Computing Engine
**Code:** `affective.py` → `EmotionState`
**Contract:** events → 10 emotion scores, dominant, valence, arousal, volatility,
confidence, valence trajectory.
**Reference:** lexicon text model (with negation + intensity) late-fused with a
behavioural-affect model (cart abandons, refunds, support volume, funnel).
**Seam:** `TextEmotionBackend.score()` — subclass with RoBERTa / DeBERTa /
EmotionBERT for text; add Wav2Vec2 / HuBERT for voice and ViT / CLIP for vision
as additional backends fused in `infer_emotion`.

## Modules 3 & 4 — Digital Twin + Representation Learning
**Code:** `twin.py` → `DigitalTwin`
**Contract:** assembles emotion+trust+intent+behaviour into a versioned twin and a
32-d unified embedding; updates on every event.
**Reference:** deterministic concatenation of normalised feature blocks
(emotion 14, trust 3, intent 8, behaviour 7).
**Seam:** replace `_embedding()` with a learned cross-modal-attention encoder
(TabTransformer for structured, text/image/audio encoders, multimodal
transformer fusion). Downstream code only consumes `twin.embedding`.

## Module 5 — Intent Forecasting
**Code:** `intent.py` → `IntentState`
**Contract:** six intents + emotion-shift and trust-degradation risk in [0,1].
**Reference:** calibrated logistic combinations of emotion/trust/behaviour features.
**Seam:** drop in a Temporal Fusion Transformer + Mixture-of-Experts over the
event sequence; emit the same `IntentState`.

## Module 6 — Trust Intelligence
**Code:** `trust.py` → `TrustState`
**Contract:** trust, fraud probability, authenticity, signals, `is_flagged`;
plus `campaign_integrity` rollup.
**Reference:** interpretable fraud rules (synthetic-persona, bot timing, refund
abuse, impossible velocity, single-channel flood) blended with an unsupervised
IsolationForest baseline fitted on the population.
**Seam:** replace with GraphSAGE / GAT over the customer–campaign–channel trust
graph and a Bayesian trust network; keep the `TrustState` output.

## Module 7 — Multi-Agent System
**Code:** `agents.py`
**Contract:** runs nine agents on a directed graph with a **conditional trust
gate** (flagged → short-circuit to `do_nothing`), returns one `ActionDecision`
with an ordered `agent_trace`.
**Reference:** pure-Python orchestration mirroring a LangGraph `StateGraph`
(shared blackboard, node functions, conditional edge).
**Seam:** lift the node functions into a real LangGraph graph with tool-calling
LLM agents and shared memory; the node boundaries already match.

## Module 8 — Reinforcement Learning Policy
**Code:** `policy.py`
**Contract:** `select(twin) → (action, propensity, ranking)`; `update(twin, action, reward)`.
**Reference:** LinUCB contextual bandit over the twin embedding — a genuine
online explore/exploit learner with per-arm ridge models and a UCB bonus.
**Seam:** replace with MAPPO / QMIX / MADDPG trained against a twin-state
environment; expose the same `select`/`update` interface for online serving.

## Module 9 — Causal Engine
**Code:** `causal.py`
**Contract:** `uplift(twin, action)` (incremental lift vs. do-nothing) and
`counterfactual(...)` narrative; learns online from outcomes.
**Reference:** segment-conditioned online two-model uplift with Bayesian
shrinkage toward action priors.
**Seam:** swap for Double ML / causal forests / uplift trees with an SCM; keep
the uplift + counterfactual contract.

## Module 10 — Explainable AI
**Code:** `explain.py`
**Contract:** signed feature attributions + natural-language rationale on the
decision.
**Reference:** transparent additive attributions over twin features and an
LLM-style templated rationale.
**Seam:** replace attributions with SHAP/attention values and the rationale with
an LLM summary; the `ActionDecision` shape is unchanged.

## Why in-memory by default
A reviewer or hackathon judge can run the entire system with one command and see
real affect inference, real fraud gating, real online learning and real causal
uplift. Persistence and heavy models are deployment concerns, deliberately kept
behind stable seams so the *research* — the trust-aware affective control loop —
is what you read first.
