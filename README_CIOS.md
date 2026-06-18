# AdTrust CIOS — Autonomous Customer Intelligence Operating System

**Bloomberg Terminal × Palantir Foundry × Tesla Fleet Intelligence × AI OS**

## 9 Advanced Research Modules

1. **Emotional Digital Twin Timeline** — `/api/twin/{id}/timeline`
   Emotion drift, volatility, trust evolution, satisfaction trajectories

2. **Counterfactual Journey Simulator** — `/api/twin/{id}/counterfactual`
   Actual vs. alternative actions vs. no-action baseline comparison

3. **Neo4j Customer Knowledge Graph** — `/api/knowledge-graph`
   D3 force-directed graph: customers, emotions, campaigns, channels, products, intents

4. **Multi-Agent Deliberation Console** — `/api/twin/{id}/deliberation`
   Round-by-round agent reasoning, voting, negotiation, consensus scoring

5. **Campaign Trust Graph** — `/api/campaign-trust-graph`
   Fraud detection, bot rate, attribution anomalies, suspicious cluster visualization

6. **Affective Reinforcement Learning** — `/api/rl-state`
   Rewards: revenue × retention × trust × emotional satisfaction × LTV

7. **Digital Twin Simulation Sandbox** — `/api/simulation/sandbox`
   500 synthetic twins per campaign, pre-deployment outcome estimation

8. **Real-time Twin Evolution Engine** — `/api/twin/{id}/evolution`
   24-hour continuous state evolution: emotional, intent, trust, behavioral

9. **Enterprise Futuristic UI**
   Bloomberg Terminal × Palantir Foundry aesthetic, JetBrains Mono, full dark OS chrome

## Run

```bash
cd adtrust-cios-v2
pip install -r backend/requirements.txt
uvicorn backend.app.main:app --reload
# → http://localhost:8000
```
