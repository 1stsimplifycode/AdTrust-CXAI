# AdTrust CXAI — Product Requirements Document

**Status:** reference implementation (v0.1) · **Owner:** Platform · **Doc type:** PRD

---

## 1. Problem

Enterprise MarTech optimizes clicks and last-touch attribution. It is blind to
two things that actually drive lifetime value: **how a customer feels** and
**whether the engagement signal is real**. The result is over-messaging of
frustrated customers, budget poured into fraudulent traffic, and "personalization"
that is correlational, not causal.

AdTrust CXAI reframes customer engagement as a **POMDP**: maintain a belief state
(the Digital Twin) over each customer's behavioral, emotional, intent, trust, and
journey state, and choose the intervention that maximizes long-run reward —
revenue, retention, **and trust** — while refusing to act on manipulated signals.

## 2. Goals / Non-goals

**Goals**
- Maintain a continuously-updated emotional + trust-aware twin per customer.
- Choose next-best-action autonomously, with a trust gate that can choose to *not*
  act to protect the customer and the budget.
- Make every decision explainable (attributions + rationale + agent trace).
- Quantify *incremental* causal lift, not correlation.
- Run anywhere, instantly, with production swap-seams for heavy models.

**Non-goals (v0.1)**
- Shipping trained transformer/GNN/MARL weights (documented seams, not trained).
- Real channel execution (email/SMS sends are simulated outcomes).
- Multi-tenant auth, billing, PII governance (enterprise hardening, later).

## 3. Users

| Persona | Need | Surface |
|---|---|---|
| Growth / Lifecycle marketer | Who to engage, on what channel, with what offer | Console roster + NBA card |
| Trust & Safety analyst | Which engagement is synthetic; campaign integrity | Trust dots, flagged trace |
| Data scientist | Swap in real models; inspect attributions | Module seams + API |
| Executive | Portfolio health, journey-stage mix, lift | Portfolio endpoint / KPIs |

## 4. Functional requirements

1. **Ingest** any event (8 channels × event types) and update the twin in real time.
2. **Affect:** infer 10 emotions, valence/arousal, volatility, confidence, trajectory.
3. **Trust:** produce trust score, fraud probability, authenticity, campaign integrity;
   flag synthetic personas, bot timing, refund abuse, velocity, single-channel floods.
4. **Intent:** forecast 6 intents + emotion-shift and trust-degradation risk.
5. **Twin:** 32-d embedding, journey stage (6), purchase readiness, LTV.
6. **Decide:** 9-agent orchestration with a hard trust gate → flagged customers get
   `do_nothing`; trusted customers get a ranked, bandit-selected action.
7. **Explain:** SHAP-style attributions + natural-language rationale + full agent trace.
8. **Learn:** record outcome → update policy (online) and causal priors.
9. **Causal:** segment-conditioned uplift + counterfactual narrative per decision.

## 5. Non-functional requirements

- **Cold-boot < 2 s**, zero external services; deploys on a free Render web service.
- **Deterministic-enough** seed for demos (stable roster + warm-started bandit).
- **Stateless swap seams:** one in-memory `Store` is the only stateful object;
  Postgres/Redis/Neo4j/Qdrant/Kafka adapters shadow it without touching module code.
- 17 in-process smoke assertions gate every change.

## 6. Success metrics

- *Product:* +incremental conversion vs last-touch control (holdout via `do_nothing`),
  reduction in messages-to-frustrated-customers, flagged-traffic budget reclaimed.
- *System:* p95 decide latency, twin-update lag, smoke-suite green.
- *Trust:* campaign integrity score trend; false-flag rate on known-good cohorts.

## 7. Release plan

- **v0.1 (this):** runnable reference impl, console, docs, deploy. ✅
- **v0.2:** real text-affect backend (RoBERTa) at `TextEmotionBackend.score()`;
  Qdrant look-alike; Postgres persistence.
- **v0.3:** MAPPO/QMIX policy behind the `ContextualBanditPolicy` interface;
  Neo4j fraud graph; Double-ML causal upgrade.
- **v1.0:** Next.js/TS console, multi-tenant, channel execution connectors, CI/CD.

## 8. Risks

| Risk | Mitigation |
|---|---|
| Affect/Trust models mis-fire on edge cohorts | Confidence scores + trust gate defaults to inaction |
| Online policy exploits a reward proxy | Holdout arm + causal uplift cross-check |
| Heavy models break free-tier deploy | Seams keep them optional; reference runs CPU-only |
