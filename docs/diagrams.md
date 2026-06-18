# AdTrust CXAI — Diagrams

All diagrams render natively on GitHub. For local preview use the
[Mermaid Live Editor](https://mermaid.live) or the VS Code Mermaid extension.

---

## 1. System Architecture

```mermaid
flowchart TB
    subgraph Sources["Multimodal Sources (Module 1)"]
        CLK[Clickstream / Mobile]
        TXT[Reviews / Chat / Tickets]
        IMG[Images]
        AUD[Voice / Calls]
        CMP[Campaign / Ads]
    end

    subgraph Fabric["Data Fabric — store.py"]
        ING[Ingest + Normalize]
        EVT[(Event Log)]
    end

    subgraph Intelligence["Customer Intelligence Core"]
        AFF[Affective Engine<br/>Module 2]
        TRU[Trust Engine<br/>Module 6]
        INT[Intent Engine<br/>Module 5]
        TWN[Digital Twin + Repr.<br/>Modules 3 & 4]
    end

    subgraph Decision["Autonomous Decisioning"]
        AGT[9-Agent Orchestrator<br/>Module 7]
        POL[Affective Bandit / MARL seam<br/>Module 8]
        CAU[Causal Engine<br/>Module 9]
        XAI[Explainability<br/>Module 10]
    end

    subgraph Surface["Surfaces"]
        API[FastAPI REST]
        UI[Operator Console]
    end

    CLK & TXT & IMG & AUD & CMP --> ING --> EVT
    EVT --> AFF & TRU & INT
    AFF & TRU & INT --> TWN
    TWN --> AGT
    AGT --> TRU
    AGT --> POL
    POL --> CAU
    CAU --> XAI
    XAI --> API --> UI
    TWN --> API
```

---

## 2. POMDP Decision Loop

```mermaid
flowchart LR
    O[Observation<br/>event] --> B[Belief Update<br/>twin rebuild]
    B --> S{Trust Gate}
    S -- flagged --> DN[do_nothing<br/>protect customer]
    S -- trusted --> A[Action Selection<br/>LinUCB over 32-d twin]
    A --> EX[Execute / Simulate]
    EX --> R[Reward<br/>revenue·retention·trust·CSAT]
    R --> L[Policy + Causal Update]
    L --> O
    DN --> O
```

---

## 3. Entity Relationship (logical)

```mermaid
erDiagram
    CUSTOMER ||--o{ EVENT : emits
    CUSTOMER ||--|| DIGITAL_TWIN : has
    CUSTOMER ||--o{ DECISION : receives
    DECISION ||--o| OUTCOME : yields
    DIGITAL_TWIN ||--|| EMOTION_STATE : embeds
    DIGITAL_TWIN ||--|| TRUST_STATE : embeds
    DIGITAL_TWIN ||--|| INTENT_STATE : embeds

    CUSTOMER {
        string customer_id PK
        string segment
        float lifetime_value
    }
    EVENT {
        string event_id PK
        string customer_id FK
        string channel
        string event_type
        float ts
    }
    DIGITAL_TWIN {
        string customer_id FK
        string journey_stage
        float purchase_readiness
        blob embedding_32d
    }
    DECISION {
        string decision_id PK
        string customer_id FK
        string action
        float score
    }
    OUTCOME {
        string decision_id FK
        float reward
        bool converted
        float revenue
    }
```

---

## 4. 9-Agent Workflow (LangGraph-style)

```mermaid
stateDiagram-v2
    [*] --> CustomerUnderstanding
    CustomerUnderstanding --> EmotionAnalysis
    EmotionAnalysis --> TrustIntelligence
    TrustIntelligence --> gate
    state gate <<choice>>
    gate --> ExecutiveInsights : flagged (short-circuit)
    gate --> ChannelSelection : trusted
    ChannelSelection --> ContentPersonalization
    ContentPersonalization --> OfferOptimization
    OfferOptimization --> JourneyOrchestration
    JourneyOrchestration --> CausalAttribution
    CausalAttribution --> ExecutiveInsights
    ExecutiveInsights --> [*]
```

---

## 5. Ingest → Decision Sequence

```mermaid
sequenceDiagram
    participant C as Client
    participant API as FastAPI
    participant ST as Store
    participant AF as Affective
    participant TR as Trust
    participant OR as Orchestrator
    participant PO as Policy

    C->>API: POST /api/events
    API->>ST: add_event()
    ST->>AF: score emotion
    ST->>TR: assess trust
    ST->>ST: build_twin()
    API-->>C: IngestResponse (twin summary)

    C->>API: POST /api/decide/{id}
    API->>OR: run(twin)
    OR->>TR: integrity gate
    alt flagged
        OR-->>API: do_nothing + trace(5)
    else trusted
        OR->>PO: select(embedding)
        PO-->>OR: ranked actions
        OR-->>API: ActionDecision + trace(9)
    end
    API-->>C: decision + attributions

    C->>API: POST /api/outcome
    API->>PO: update(reward)
```
