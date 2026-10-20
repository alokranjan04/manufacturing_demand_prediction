# Chemical Manufacturing AI — System Architecture

## Overview

A full-stack AI platform for chemical manufacturing demand & distribution intelligence. It ingests raw CSV data, processes it through a Databricks Medallion pipeline, trains a LightGBM forecasting model, runs an agentic deviation-detection loop, and surfaces insights through a FastAPI backend + React frontend.

---

## Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DATA SOURCES (CSV)                           │
│  order_transactions  inventory_levels  production_capacity          │
│  external_signals                                                   │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  POST /pipeline/upload
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│              DATABRICKS UNITY CATALOG  (chem_ai catalog)            │
│                                                                     │
│  ┌─────────────┐    ┌──────────────────┐    ┌───────────────────┐  │
│  │   BRONZE    │    │      SILVER       │    │       GOLD        │  │
│  │  (raw Delta)│───▶│  (clean/joined)  │───▶│  (aggregated)     │  │
│  │             │    │                  │    │                   │  │
│  │ order_trans │    │ demand_history   │    │ demand_forecast   │  │
│  │ inventory   │    │ inventory_snap   │    │ inventory_summary │  │
│  │ production  │    │ ext_signals_clean│    │ capacity_util     │  │
│  │ ext_signals │    │                  │    │ forecast_deviations│ │
│  └─────────────┘    └──────────────────┘    └───────────────────┘  │
│                                                        │            │
│                     ┌──────────────────┐              │            │
│                     │   ML TRAINING    │◀─────────────┘            │
│                     │  (LightGBM)      │                            │
│                     │  04_feature_eng  │                            │
│                     │  05_train_model  │──▶ MLflow Model Registry   │
│                     │  06_batch_infer  │    (Champion alias)        │
│                     │  07_deviations   │──▶ forecast_deviations     │
│                     └──────────────────┘                            │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  Databricks SQL Connector
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                    FASTAPI BACKEND  (port 8001)                     │
│                                                                     │
│  /pipeline/*    — upload CSV, trigger job, poll status              │
│  /forecast/*    — KPIs, deviations, explain (LLM)                  │
│  /inventory/*   — inventory snapshots, constraints                  │
│  /agent/*       — run agentic loop, list/approve/reject recs        │
│  /chat          — free-text Q&A (context-injection LLM)             │
│                                                                     │
│  src/data/databricks_client.py  — SQL query runner                 │
│  src/data/agent_db.py           — chemical SQL queries              │
│  src/data/databricks_jobs.py    — Jobs API (trigger/poll)           │
│  src/genai/llm_client.py        — OpenRouter client                 │
│  src/genai/chatbot.py           — context-injection chat loop       │
│  src/genai/agent.py             — agentic recommendation loop       │
└───────────────────────────┬─────────────────────────────────────────┘
                            │  REST API (axios)
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                   REACT FRONTEND  (port 5173)                       │
│                                                                     │
│  DashboardPage       — KPI cards, deviation chart, map              │
│  ForecastPage        — SKU/region demand forecast chart             │
│  InventoryPage       — inventory cover, constraints table           │
│  PipelineControl     — upload CSV, trigger job, live status         │
│  AnalyticsChatPage   — free-text chat with chemical context         │
│  AgentPage           — agentic recommendations, approve/reject      │
└─────────────────────────────────────────────────────────────────────┘
                            │
                            ▼
┌─────────────────────────────────────────────────────────────────────┐
│                      LLM  (OpenRouter)                              │
│  Model: minimax/minimax-m3.1-flash:free (configurable)             │
│  Used by: POST /chat, POST /forecast/explain, POST /agent/run       │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Layer-by-Layer Breakdown

### Layer 1 — Data Ingestion (Bronze)

Raw CSV files uploaded via the frontend are written to a Databricks Volume (`/Volumes/chem_ai/.../incoming/`), then ingested as-is into Delta Lake Bronze tables.

| Bronze Table | Key Columns |
|---|---|
| `order_transactions` | `transaction_id`, `sku_id`, `customer_id`, `region`, `customer_segment`, `order_date`, `quantity_kg`, `unit_price_usd`, `order_status`, `sales_channel`, `lead_time_days`, `discount_pct` |
| `inventory_levels` | `snapshot_date`, `sku_id`, `warehouse_id`, `region`, `quantity_on_hand_kg`, `reorder_point_kg`, `max_capacity_kg`, `unit_cost_usd`, `last_replenishment_date` |
| `production_capacity` | `plant_id`, `region`, `sku_id`, `date`, `planned_capacity_kg`, `actual_output_kg`, `downtime_hours`, `shift_count`, `efficiency_rate` |
| `external_signals` | `signal_date`, `region`, `indicator_type`, `indicator_value`, `source`, `notes` |

### Layer 2 — Transformation (Silver)

Cleaned, joined, and enriched tables ready for ML feature engineering.

| Silver Table | Description |
|---|---|
| `demand_history` | Validated orders joined with customer/product metadata, daily aggregated demand per SKU + region |
| `inventory_snapshot` | Latest inventory state per SKU + warehouse, including `days_on_hand` calculated field |
| `external_signals_clean` | Standardised external macro signals (energy cost index, logistics disruption index, demand seasonality) |

### Layer 3 — Aggregation & Forecasting (Gold)

| Gold Table | Description |
|---|---|
| `demand_forecast` | LightGBM model output: predicted demand (tonnes) per SKU + region + week, with confidence intervals |
| `inventory_summary` | Aggregated inventory KPIs per region: avg days on hand, SKUs below reorder, coverage % |
| `capacity_utilisation` | Plant-level efficiency, planned vs actual output, bottleneck flags |
| `forecast_deviations` | Week-over-week delta between current and prior forecast run, filtered to ≥ 10% absolute change |

### Layer 4 — ML Model

- **Algorithm**: LightGBM (gradient-boosted trees)
- **Target**: `quantity_kg` (weekly demand per SKU + region)
- **Features**: lag features (1w, 4w, 13w), rolling mean/std, day-of-week, month, inventory cover, external signals
- **Registry**: MLflow on Databricks, published with `Champion` alias
- **Inference**: Batch scoring via notebook `06_batch_inference_and_deviation.py`

### Layer 5 — Agentic Loop

`POST /agent/run` triggers a multi-step loop:

1. Fetch `forecast_deviations` (>10% change)
2. Fetch inventory constraints (SKUs below reorder)
3. Fetch capacity constraints (plants >90% utilisation)
4. LLM (OpenRouter) synthesises context → generates recommendations
5. Recommendations stored in `agent_recommendations` table with `pending` status
6. Human reviews in Agent page → approve / reject

### Layer 6 — Backend API

| Endpoint Group | Purpose |
|---|---|
| `GET /forecast/kpis` | Aggregate KPIs: total forecast demand, MAPE, deviation count |
| `GET /forecast/deviations` | List significant week-over-week forecast changes |
| `POST /forecast/explain` | LLM narrative for a specific deviation |
| `GET /inventory/summary` | Inventory cover per region |
| `GET /inventory/constraints` | SKUs below reorder point |
| `POST /pipeline/upload` | Upload CSV to Databricks Volume |
| `POST /pipeline/trigger` | Start Databricks job run |
| `GET /pipeline/status/{run_id}` | Poll job run state |
| `POST /pipeline/upload-and-trigger` | Combined upload + trigger |
| `POST /agent/run` | Execute agentic recommendation loop |
| `GET /agent/recommendations` | List pending/approved/rejected recommendations |
| `POST /agent/recommendations/{id}/approve` | Approve a recommendation |
| `POST /agent/recommendations/{id}/reject` | Reject a recommendation |
| `POST /chat` | Free-text Q&A with chemical context injection |

### Layer 7 — Frontend

| Page | Components |
|---|---|
| Dashboard | KPI cards (total demand, MAPE, deviations, pending actions), deviation heatmap, regional map |
| Forecast | Demand forecast chart by SKU + region, week-over-week delta |
| Inventory | Inventory cover table, constraint flags, days-on-hand trend |
| Pipeline | CSV uploader (drag-and-drop), trigger button, live run status polling |
| Analytics Chat | Free-text chat, 5 chemical quick-action buttons, conversation history |
| Agent | Pending recommendations list, approve/reject controls, urgency badges |

---

## Technology Stack

| Layer | Technology |
|---|---|
| Data Platform | Databricks (Serverless SQL Warehouse + Jobs) |
| Storage | Delta Lake (Unity Catalog — `chem_ai` catalog) |
| ML Framework | LightGBM + MLflow Model Registry |
| Backend | Python 3.11 · FastAPI · Databricks SQL Connector · `databricks-sdk` |
| LLM | OpenRouter API (OpenAI-compatible) — model configurable via `OPENROUTER_MODEL` |
| Frontend | React 18 · TypeScript · Vite · Recharts · Axios |
| Auth | Databricks PAT token (all-apis scope) · OpenRouter API key |
| Dev | `uv` (Python package manager) · `pnpm` · Uvicorn |
| CI/CD | Databricks Asset Bundles (DABS) |

---

## Data Flow Summary

```
CSV Upload
  → Databricks Volume (incoming/)
    → Bronze Delta tables (raw)
      → Silver Delta tables (clean/joined)
        → Gold Delta tables (aggregated)
          → LightGBM training (Champion model in MLflow)
            → Batch inference → demand_forecast
              → Deviation detection → forecast_deviations
                → Agent loop (LLM) → agent_recommendations
                  → Human approval/rejection
                    → Dashboard / Chat / Inventory UI
```
