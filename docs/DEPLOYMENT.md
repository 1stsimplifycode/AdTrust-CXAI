# AdTrust CXAI — Deployment Guide

The reference implementation is a single FastAPI service with **no external
dependencies**. It serves both the JSON API and the operator console. That makes
deployment trivial on any platform that runs a container or a Python process.

---

## 0. Local (fastest path)

**Windows**
```bat
scripts\setup.bat
scripts\run.bat
```

**macOS / Linux**
```bash
bash scripts/setup.sh
cd backend && uvicorn app.main:app --reload --port 8000
```

Open <http://localhost:8000> — the console loads with ~19 seeded customers.
Health: <http://localhost:8000/api/health>.

**Smoke test (no server needed):**
```bash
cd backend && python ../scripts/smoke_test.py   # 17 in-process assertions
```

---

## 1. Docker

```bash
docker compose up --build
# or just the app image:
docker build -t adtrust ./backend
docker run -p 8000:8000 adtrust
```

`docker-compose.yml` ships the app service live; Postgres / Neo4j / Qdrant /
Redis / Kafka are included **commented-out** as the production topology. Uncomment
them only after wiring the corresponding adapters described in
[DATABASE_SCHEMA.md](DATABASE_SCHEMA.md).

---

## 2. Render (primary target)

`render.yaml` is committed at repo root:

```yaml
services:
  - type: web
    name: adtrust-cxai
    runtime: docker
    dockerfilePath: ./backend/Dockerfile
    healthCheckPath: /api/health
    envVars:
      - key: SEED_ON_START
        value: "true"
```

Steps:
1. Push the repo to GitHub.
2. Render → **New → Blueprint** → point at the repo. It reads `render.yaml`.
3. Deploy. The free Docker web service boots in ~1–2 min; the health check at
   `/api/health` flips it live. The console is served at the service root URL.

No env vars are required. Set `SEED_ON_START=false` for an empty instance.

---

## 3. Railway

```bash
railway init
railway up
```
Railway autodetects the Dockerfile under `backend/`. Set the start command to
`uvicorn app.main:app --host 0.0.0.0 --port $PORT` if not using the Dockerfile,
and expose `$PORT` (the app already reads it from `config.py`).

---

## 4. AWS / Azure / GCP

The image is platform-agnostic. Minimal paths:

- **AWS App Runner / ECS Fargate** — push `./backend` image to ECR, point a
  service at it, health check `/api/health`, port 8000.
- **Azure Container Apps** — `az containerapp up --source ./backend`, ingress on
  8000, health probe `/api/health`.
- **GCP Cloud Run** — `gcloud run deploy --source ./backend`, Cloud Run injects
  `$PORT` which `config.py` honors.

For the full production topology (managed Postgres, Neo4j Aura, Qdrant Cloud,
ElastiCache/Redis, MSK/Kafka) wire each adapter at its swap seam, then move the
datastores behind the service in the same VPC/project.

---

## 5. CI/CD (reference pipeline)

A minimal GitHub Actions workflow that gates merges on the smoke test:

```yaml
name: ci
on: [push, pull_request]
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with: { python-version: "3.12" }
      - run: pip install -r backend/requirements.txt
      - run: cd backend && python ../scripts/smoke_test.py
  deploy:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - run: echo "Render auto-deploys on push to main via Blueprint."
```

Render's Blueprint auto-deploys on push to `main`, so the deploy job is a no-op
placeholder; for Railway/Cloud Run swap in their respective deploy actions.

---

## 6. Monitoring

- **Liveness/readiness:** `/api/health` returns `{status, customers, seeded}`.
- **Portfolio telemetry:** `/api/portfolio` exposes live stage distribution,
  flagged counts, and policy stats — scrape it or panel it in Grafana.
- For production, add an ASGI Prometheus middleware and ship the LinUCB
  `policy.stats()` (per-action pulls/reward) as gauges; alert on
  `flagged_rate` spikes (campaign-integrity degradation) and on
  `do_nothing` share climbing (trust gate tightening).
