# Chemical Manufacturing AI — Demand & Distribution Intelligence Platform

An AI-powered platform for chemical manufacturing supply-chain planning: automated demand forecasting, deviation alerting, agentic supply recommendations, and plain-language analytics chat — all built on Databricks + FastAPI + React.

![Dashboard](./images/dashboard.png)

## Overview

**Chem AI** helps chemical manufacturers:

- **Forecast demand** using a LightGBM model trained on order history, inventory, production capacity, and external macro signals
- **Detect deviations** automatically — flags any SKU/region where the latest forecast shifted ≥ 10% vs the prior run
- **Generate AI recommendations** via an agentic loop (deviations + constraints → LLM → human-approved supply actions)
- **Answer supply-chain questions** in plain language through an analytics chat interface
- **Run end-to-end pipelines** with a single click — from raw CSV upload through Bronze → Silver → Gold → ML training

## Architecture

```
CSV Upload → Databricks Volume
  → Bronze Delta tables (raw)
    → Silver Delta tables (clean/joined)
      → Gold Delta tables (aggregated forecasts + deviations)
        → LightGBM Champion model (MLflow Registry)
          → Agentic loop (OpenRouter LLM) → Recommendations
            → FastAPI backend (port 8001)
              → React frontend (port 5173)
```

See [docs/architecture.md](docs/architecture.md) for the full diagram and layer-by-layer breakdown.
See [docs/PRD.md](docs/PRD.md) for product requirements, personas, and success metrics.

## Tech Stack

| Layer | Technology |
|---|---|
| Data Platform | Databricks (Serverless SQL Warehouse + Jobs) |
| Storage | Delta Lake — Unity Catalog (`chem_ai` catalog) |
| ML | LightGBM + MLflow Model Registry |
| Backend | Python 3.11 · FastAPI · Databricks SQL Connector |
| LLM | OpenRouter (OpenAI-compatible) — model configurable |
| Frontend | React 18 · TypeScript · Vite · Recharts |
| CI/CD | Databricks Asset Bundles (DABS) |

## Prerequisites

- Python 3.11+
- Node.js 18+
- [uv](https://docs.astral.sh/uv/getting-started/)
- Databricks workspace with Unity Catalog enabled
- OpenRouter API key ([openrouter.ai/keys](https://openrouter.ai/keys))

## Setup

### 1. Configure Environment Variables

Copy `backend/.env.example` to `backend/.env` and fill in your values:

```bash
cp backend/.env.example backend/.env
```

Required variables:

```env
# Databricks SQL Warehouse
DATABRICKS_SERVER_HOSTNAME=<your-workspace>.cloud.databricks.com
DATABRICKS_HTTP_PATH=/sql/1.0/warehouses/<warehouse-id>
DATABRICKS_TOKEN=<PAT token with all-apis scope>

# Databricks Jobs
DATABRICKS_JOB_ID=<Chem_AI_pipeline job ID>
DATABRICKS_VOLUME_INCOMING_PATH=/Volumes/chem_ai/<schema>/<volume>/incoming

# OpenRouter LLM
OPENROUTER_API_KEY=<your key>
OPENROUTER_MODEL=anthropic/claude-3.5-sonnet-20241022

# CORS
ALLOWED_ORIGINS=http://localhost:5173,http://localhost:3000
```

> **Note:** The Databricks PAT token must have the `all-apis` scope to trigger Jobs via the REST API.

### 2. Install Backend Dependencies

```bash
uv sync
```

### 3. Start Backend

```bash
cd backend && uvicorn main:app --reload --port 8001
```

API docs: [http://localhost:8001/docs](http://localhost:8001/docs)

### 4. Install & Start Frontend

```bash
cd frontend && npm install && npm run dev
```

Frontend: [http://localhost:5173](http://localhost:5173)

## Databricks Pipeline Setup

The pipeline consists of 7 Python script tasks in a Databricks Job (`Chem_AI_pipeline`):

| Task | Script | Description |
|---|---|---|
| `setup` | `01_setup_chem_ai.py` | Create catalog, schemas, volumes |
| `bronze` | `02_bronze_ingestion.py` | Ingest raw CSVs into Bronze Delta |
| `silver` | `03_silver_transformation.py` | Clean and join into Silver tables |
| `gold` | `04_feature_engineering.py` | Aggregate into Gold tables |
| `train` | `05_train_model.py` | Train LightGBM, register Champion model |
| `inference` | `06_batch_inference_and_deviation.py` | Score demand, compute deviations |
| `agent` | `07_agent_recommendations.py` | Run agentic recommendation loop |

Scripts are located at `/Workspace/Users/<your-user>/Chem_AI/src/` in the Databricks workspace.

> **Note:** Add `lightgbm` to the train task's Libraries/Environment tab in the Databricks Jobs UI.

## Source Data Files

Upload CSVs via the Pipeline page. Accepted file prefixes:

| Prefix | Description |
|---|---|
| `order_transactions` | Customer demand history |
| `inventory_levels` | Warehouse stock snapshots |
| `production_capacity` | Plant output vs plan |
| `external_signals` | Macro/market indicators |

## Key API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/pipeline/upload-and-trigger` | Upload CSV + start pipeline run |
| `GET` | `/pipeline/status/{run_id}` | Poll job run state |
| `GET` | `/forecast/kpis` | Aggregate KPIs (MAPE, demand, deviations) |
| `GET` | `/forecast/deviations` | Significant forecast changes |
| `POST` | `/agent/run` | Generate AI supply recommendations |
| `GET` | `/agent/recommendations` | List pending/approved recommendations |
| `POST` | `/chat` | Free-text supply-chain Q&A |

## License

MIT License

---

**Follow along:** [AaiTech - Sandesh Hase](https://youtube.com/@sandesh-hase?si=oaopw_Sq6xZKDsca)
