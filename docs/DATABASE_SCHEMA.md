# AdTrust CXAI — Database Schema

The reference implementation runs entirely on a thread-safe **in-memory store**
(`backend/app/store.py`) so the platform boots with zero external services. This
document specifies the **production datastore schema** that the in-memory store
is a drop-in stand-in for. Each section maps to a swap-in seam already present in
the code.

---

## 1. PostgreSQL — system of record

```sql
CREATE TABLE customer (
    customer_id     TEXT PRIMARY KEY,
    segment         TEXT NOT NULL DEFAULT 'unknown',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    lifetime_value  NUMERIC(12,2) NOT NULL DEFAULT 0
);

CREATE TABLE event (
    event_id     BIGSERIAL PRIMARY KEY,
    customer_id  TEXT NOT NULL REFERENCES customer(customer_id),
    channel      TEXT NOT NULL,          -- web|mobile|email|sms|call|social|support|ads
    event_type   TEXT NOT NULL,          -- click|purchase|review|...
    ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
    text         TEXT,                   -- free text for affect (nullable)
    value        NUMERIC(12,2),          -- monetary value if any
    meta         JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX event_customer_ts ON event (customer_id, ts DESC);
CREATE INDEX event_type_idx    ON event (event_type);

CREATE TABLE digital_twin (
    customer_id        TEXT PRIMARY KEY REFERENCES customer(customer_id),
    journey_stage      TEXT NOT NULL,     -- awareness|consideration|conversion|loyalty|at_risk|advocacy
    purchase_readiness REAL NOT NULL,
    dominant_emotion   TEXT NOT NULL,
    valence            REAL NOT NULL,
    arousal            REAL NOT NULL,
    trust_score        REAL NOT NULL,
    fraud_probability  REAL NOT NULL,
    flagged            BOOLEAN NOT NULL DEFAULT false,
    embedding          REAL[] NOT NULL,   -- 32-d; see Qdrant mirror below
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE decision (
    decision_id   BIGSERIAL PRIMARY KEY,
    customer_id   TEXT NOT NULL REFERENCES customer(customer_id),
    action        TEXT NOT NULL,
    score         REAL NOT NULL,
    rationale     TEXT,
    attributions  JSONB NOT NULL DEFAULT '{}',
    agent_trace   JSONB NOT NULL DEFAULT '[]',
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE outcome (
    decision_id  BIGINT PRIMARY KEY REFERENCES decision(decision_id),
    reward       REAL NOT NULL,
    converted    BOOLEAN NOT NULL DEFAULT false,
    revenue      NUMERIC(12,2) NOT NULL DEFAULT 0,
    recorded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

**Emotion / Intent / Trust state.** In the reference impl these live inside the
twin object. At production scale, denormalize the full 10-emotion vector and the
6-intent vector into append-only history tables for trajectory analytics:

```sql
CREATE TABLE emotion_history (
    customer_id TEXT NOT NULL REFERENCES customer(customer_id),
    ts          TIMESTAMPTZ NOT NULL DEFAULT now(),
    scores      JSONB NOT NULL,   -- {happiness:.., trust:.., anxiety:..}
    valence REAL, arousal REAL, volatility REAL, confidence REAL
);
CREATE INDEX emotion_hist_cust_ts ON emotion_history (customer_id, ts DESC);
```

---

## 2. Qdrant — vector mirror (Module 4)

The 32-d twin embedding (`twin._embedding`) is the unit of similarity search for
look-alike targeting and segment discovery.

```python
# collection: customer_twins
VectorParams(size=32, distance=Distance.COSINE)
# payload: {customer_id, segment, journey_stage, flagged, trust_score}
```

Swap seam: `store.STORE` exposes every twin's embedding; a production adapter
upserts on each `build_twin()` and queries top-k for the ChannelSelection /
look-alike agents.

---

## 3. Neo4j — graph schema (Modules 3 & 6)

The six graphs from the spec (Identity / Behavior / Intent / Trust / Emotion /
Journey) collapse onto one labeled property graph.

```cypher
// Nodes
(:Customer {customer_id, segment, trust_score, flagged})
(:Device   {device_id, fingerprint})
(:Campaign {campaign_id, integrity_score})
(:Channel  {name})
(:Product  {product_id, category})
(:Stage    {name})        // journey stages

// Relationships
(:Customer)-[:USES]->(:Device)
(:Customer)-[:EXPOSED_TO]->(:Campaign)
(:Customer)-[:ENGAGED_ON]->(:Channel)
(:Customer)-[:PURCHASED {ts, value}]->(:Product)
(:Customer)-[:AT_STAGE {since}]->(:Stage)
(:Customer)-[:SIMILAR_TO {score}]->(:Customer)   // from twin embedding
(:Device)-[:SHARED_BY]->(:Customer)               // synthetic-persona signal
```

**Fraud queries the Trust Engine approximates inline** (and that Neo4j makes
exact at scale):

```cypher
// Synthetic persona ring: many customers behind one device fingerprint
MATCH (d:Device)<-[:USES]-(c:Customer)
WITH d, count(c) AS shared
WHERE shared > 5
RETURN d.fingerprint, shared ORDER BY shared DESC;

// Campaign integrity: share of flagged customers driving a campaign
MATCH (c:Customer)-[:EXPOSED_TO]->(k:Campaign)
WITH k, avg(CASE WHEN c.flagged THEN 1.0 ELSE 0.0 END) AS fraud_rate
SET k.integrity_score = 1.0 - fraud_rate
RETURN k.campaign_id, k.integrity_score;
```

---

## 4. Redis — hot belief cache

| Key pattern | Value | TTL |
|---|---|---|
| `twin:{customer_id}` | serialized twin | 1h, refreshed on event |
| `policy:linucb` | bandit A/b matrices | none (periodic snapshot) |
| `stream:events` | Redis Stream of raw events | capped |

Swap seam: `store.STORE` is the single object a Redis/Kafka adapter shadows;
nothing else in the code holds state.
