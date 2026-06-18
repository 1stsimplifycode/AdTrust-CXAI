"""AdTrust CXAI smoke test.

Boots the app in-process (no server needed) and exercises the full POMDP loop:
ingest -> twin -> decide -> outcome/learn, plus trust gating and portfolio.
Run from the project root:  python scripts/smoke_test.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

from fastapi.testclient import TestClient  # noqa: E402
from app.main import app  # noqa: E402

FAIL = 0


def check(name, cond):
    global FAIL
    print(("  PASS  " if cond else "  FAIL  ") + name)
    if not cond:
        FAIL += 1


with TestClient(app) as c:
    print("== health ==")
    h = c.get("/api/health").json()
    check("health ok", h.get("status") == "ok")
    check("population seeded", h.get("customers", 0) > 10)

    print("== portfolio rollup ==")
    p = c.get("/api/portfolio").json()
    check("has campaign integrity", "campaign_integrity" in p)
    check("detected fraud profiles", p.get("flagged", 0) >= 1)
    check("multiple journey stages", len(p.get("stage_distribution", {})) >= 3)

    print("== digital twin ==")
    t = c.get("/api/twin/loyal_00").json()
    check("twin has 10 emotions", len(t["emotion"]["scores"]) == 10)
    check("twin embedding is 32-d", len(t["embedding"]) == 32)
    check("loyal customer trusted", t["trust"]["trust_score"] > 0.6)

    print("== trust gating ==")
    bot = c.get("/api/twin/bot_00").json()
    check("bot flagged as fraud", bot["trust"]["is_flagged"] is True)
    bd = c.post("/api/decide/bot_00").json()
    check("flagged profile -> do_nothing", bd["action"] == "do_nothing")

    print("== affective ingest (text) ==")
    r = c.post("/api/events", json={
        "customer_id": "smoke_user", "event_type": "review",
        "channel": "social",
        "text": "Absolutely love it, fast and reliable, highly recommend!"}).json()
    check("ingest accepted", r["accepted"] is True)
    st = c.get("/api/twin/smoke_user").json()
    check("positive valence inferred", st["emotion"]["valence"] > 0)

    print("== decisioning + explanation ==")
    d = c.post("/api/decide/smoke_user").json()
    check("9-agent trace", len(d["agent_trace"]) == 9)
    check("has rationale", len(d["rationale"]) > 40)
    check("has feature attributions", len(d["feature_attributions"]) >= 4)

    print("== online learning ==")
    before = c.get("/api/portfolio").json()["policy_pulls"]["recommend_product"]
    c.post("/api/outcome", json={"customer_id": "smoke_user",
                                 "action": "recommend_product", "reward": 0.9})
    after = c.get("/api/portfolio").json()["policy_pulls"]["recommend_product"]
    check("policy updated from outcome", after == before + 1)

print()
if FAIL:
    print(f"SMOKE TEST FAILED ({FAIL} failures)")
    sys.exit(1)
print("ALL SMOKE TESTS PASSED")
