# AdTrust CXAI

### Trust-Aware Affective Customer Intelligence & Autonomous Journey Orchestration

AdTrust CXAI builds a continuously-evolving **emotional digital twin** of every
customer, scores **trust / fraud** on every interaction, forecasts **intent**,
and lets a fleet of cooperating agents choose a **fraud-gated, causally-justified
next-best-action** — with a full explanation for every decision.

It is built around one idea: traditional MarTech understands *behaviour*; AdTrust
CXAI also understands *emotion, intent and trust*, and acts on them autonomously.

> **What this repository is.** A **runnable reference implementation** of the full
> architecture. Every module is implemented end-to-end and boots with **zero
> external services** (no GPU, no Kafka/Neo4j/Qdrant required) so it deploys on a
> free Render dyno and runs locally in seconds. The heavy research backends
> (RoBERTa/Wav2Vec2/ViT for affect, GNN/Bayesian trust nets, MAPPO/QMIX MARL,
> SCM/Double-ML causal) are wired as **documented swap-in seams** — see
> [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) for the exact extension points.

---

## The POMDP loop

Customer engagement is modelled as a Partially Observable Markov Decision Process.

```
observe (event)  ->  rebuild digital twin  ->  run 9-agent graph  ->  decide NBA  ->  record outcome  ->  policy + causal learn
   Module 1            Modules 2,3,4,5,6          Module 7            Modules 8,9,10        feedback
```

| State | Observations | Actions | Rewards |
|---|---|---|---|
| behavioural, emotional, intent, trust, journey | clicks, purchases, reviews, chats, social, support, voice | recommend, email, push, sms, discount, retention, do-nothing | revenue, retention, engagement, trust, CLV |

## The ten modules

1. **Multimodal Data Fabric** — unified event ingestion (`store.py`, `models.py`)
2. **Affective Computing Engine** — 10-emotion state, valence/arousal, volatility, trajectory (`affective.py`)
3. **Customer Digital Twin** — live twin + 32-d unified embedding (`twin.py`)
4. **Multimodal Representation Learning** — feature-block fusion into the embedding (`twin.py`)
5. **Intent Forecasting** — purchase/churn/upsell/engagement/support/advocacy + shift risks (`intent.py`)
6. **Trust Intelligence** — rules + IsolationForest → trust/fraud/authenticity, campaign integrity (`trust.py`)
7. **Multi-Agent System** — 9 agents on a LangGraph-style graph with a trust gate (`agents.py`)
8. **RL Policy** — online LinUCB contextual bandit over the twin embedding (`policy.py`)
9. **Causal Engine** — online two-model uplift + counterfactuals (`causal.py`)
10. **Explainable AI** — SHAP-style attributions + LLM-style rationale (`explain.py`)

A futuristic operator **console** (vanilla TS-free SPA, served by the API) renders
the twin glyph, emotional spectrum, intent forecast, and the live agent trace.

---

## Quickstart

### Windows (`.bat`)
```bat
scripts\setup.bat     :: create venv + install deps
scripts\run.bat       :: start at http://localhost:8000
scripts\test.bat      :: run the smoke test suite
```

### macOS / Linux
```bash
bash scripts/setup.sh           # setup + run
python scripts/smoke_test.py    # smoke tests (from repo root)
```

### Docker
```bash
docker compose up --build       # http://localhost:8000
```

Open **http://localhost:8000** for the console, **/docs** for the OpenAPI explorer.
The app auto-seeds a synthetic population (loyal / at-risk / new / bot personas)
so the dashboard is populated on first load.

---

## API surface

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/health` | liveness + population size |
| `POST` | `/api/events` | ingest an observation; returns updated twin + proposed action |
| `GET`  | `/api/twins` | all digital twins (console roster) |
| `GET`  | `/api/twin/{id}` | one digital twin |
| `GET`  | `/api/events/{id}` | raw event log |
| `POST` | `/api/decide/{id}` | run the agent graph → next-best-action + trace + explanation |
| `POST` | `/api/outcome` | record reward → policy + causal learn online |
| `GET`  | `/api/portfolio` | executive rollups (integrity, intents, LTV, stages) |
| `POST` | `/api/admin/seed` | (re)seed the synthetic population |

Example:
```bash
curl -X POST localhost:8000/api/events -H 'content-type: application/json' \
  -d '{"customer_id":"c1","event_type":"review","channel":"social",
       "text":"love it, fast and reliable, highly recommend!"}'

curl -X POST localhost:8000/api/decide/c1
```

---

## Deploy

- **Render** — push to GitHub, then *New + → Blueprint* on [`render.yaml`](render.yaml). Health check is `/api/health`.
- **Railway / Fly / AWS / Azure / GCP** — any Docker host runs [`backend/Dockerfile`](backend/Dockerfile); bind to `$PORT`.

See [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) for per-platform steps and the
production datastore wiring.

---

## Documentation

- [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) — module-by-module design + swap-in seams
- [`docs/diagrams.md`](docs/diagrams.md) — system / ER / sequence / LangGraph / POMDP (Mermaid)
- [`docs/DATABASE_SCHEMA.md`](docs/DATABASE_SCHEMA.md) — PostgreSQL + Neo4j graph schema
- [`docs/RESEARCH_PAPER.md`](docs/RESEARCH_PAPER.md) — paper draft (problem, method, contributions, eval plan)
- [`docs/PRD.md`](docs/PRD.md) — product requirements
- [`docs/PITCH_DECK.md`](docs/PITCH_DECK.md) — investor deck content
- [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md) — deployment + ops

## License

Provided as a reference implementation for evaluation and extension.
