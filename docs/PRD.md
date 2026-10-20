# Product Requirements Document
## Chemical Manufacturing AI — Demand & Distribution Intelligence Platform

**Version**: 1.0
**Date**: October 2026
**Owner**: AaiTech

---

## 1. Executive Summary

Chemical manufacturers face compounding complexity: volatile raw-material costs, long lead times, capacity constraints across multiple plants, and demand signals that shift faster than monthly S&OP cycles can absorb. This platform delivers an AI-powered demand and distribution intelligence layer on top of Databricks, replacing spreadsheet-driven planning with automated forecasting, deviation alerting, and agentic supply recommendations — all accessible through a self-service web UI.

---

## 2. Problem Statement

| Pain Point | Current State | Impact |
|---|---|---|
| Demand forecasting | Manual Excel models, updated monthly | Stockouts, excess inventory, missed revenue |
| Deviation detection | Ad-hoc analyst review | Deviations spotted days/weeks late |
| Supply response | Email chains, weekly meetings | Slow corrective action, high expediting cost |
| Data silos | ERP, WMS, MES on separate systems | No unified view of demand-to-supply chain |
| Knowledge access | Tribal knowledge in planning team | New hires / leadership can't self-serve insights |

---

## 3. Goals & Success Metrics

### Goals
1. Automate weekly demand forecasting across all SKUs and regions
2. Surface significant forecast deviations immediately after each pipeline run
3. Provide AI-generated supply recommendations for human approval
4. Enable any stakeholder to query supply-chain data in plain language
5. Reduce time-to-insight from days to minutes

### Success Metrics

| Metric | Baseline | Target |
|---|---|---|
| Forecast MAPE | ~25% (manual) | <15% (LightGBM) |
| Deviation detection lag | 3–5 days | <1 hour post-pipeline |
| Pipeline run time | N/A (manual) | <30 minutes end-to-end |
| Recommendations reviewed per week | 0 (no system) | 100% of `urgent` within 24h |
| Chat questions answered without analyst | 0% | >80% self-served |

---

## 4. Users & Personas

| Persona | Role | Primary Need |
|---|---|---|
| **CDO / VP Supply Chain** | Executive sponsor | High-level KPIs, deviation summary, agent recommendation status |
| **Demand Planner** | Day-to-day user | Detailed SKU/region forecasts, deviation drill-down, approve/reject recommendations |
| **Production Scheduler** | Operations | Capacity utilisation, constraint alerts, approved supply actions |
| **Data Engineer** | Pipeline owner | Upload data, trigger pipeline, monitor job status |
| **Business Analyst** | Ad-hoc queries | Natural-language chat for questions without needing SQL |

---

## 5. Features & Requirements

### 5.1 Data Pipeline

| ID | Requirement | Priority |
|---|---|---|
| P-01 | Accept CSV uploads for 4 source file types: `order_transactions`, `inventory_levels`, `production_capacity`, `external_signals` | Must |
| P-02 | Validate file prefix before accepting upload | Must |
| P-03 | Ingest raw CSVs into Bronze Delta tables without transformation | Must |
| P-04 | Transform Bronze → Silver: clean nulls, join datasets, calculate derived fields (e.g. `days_on_hand`) | Must |
| P-05 | Aggregate Silver → Gold: forecast output, inventory summary, capacity utilisation | Must |
| P-06 | Train LightGBM model on demand history + external signals features | Must |
| P-07 | Register trained model in MLflow with `Champion` alias | Must |
| P-08 | Run batch inference to populate `demand_forecast` Gold table | Must |
| P-09 | Compute week-over-week forecast deviations and flag those ≥ 10% | Must |
| P-10 | Expose pipeline trigger and status polling via REST API | Must |
| P-11 | Show live pipeline run status in the UI with auto-refresh | Should |

### 5.2 Forecasting & KPIs

| ID | Requirement | Priority |
|---|---|---|
| F-01 | Display aggregate KPIs: total forecast demand (tonnes), MAPE, deviation count, pending action count | Must |
| F-02 | Show week-over-week forecast by SKU and region with interactive chart | Must |
| F-03 | List significant forecast deviations (≥ 10%) with direction, magnitude, SKU, region, segment | Must |
| F-04 | Generate LLM narrative explanation for any selected deviation | Should |
| F-05 | Allow filtering deviations by region, SKU, direction | Should |

### 5.3 Inventory Management

| ID | Requirement | Priority |
|---|---|---|
| I-01 | Show inventory cover (days on hand) per SKU and region | Must |
| I-02 | Flag SKUs below reorder point | Must |
| I-03 | Show capacity utilisation per plant with bottleneck indicators | Should |
| I-04 | Display inventory constraints summary (count of SKUs at risk) | Should |

### 5.4 Agentic Recommendation Loop

| ID | Requirement | Priority |
|---|---|---|
| A-01 | On demand, run agentic loop: fetch deviations + constraints → LLM → generate recommendations | Must |
| A-02 | Store recommendations in Databricks with urgency level (`critical`, `high`, `medium`) | Must |
| A-03 | Expose recommendations list in UI with status (pending / approved / rejected) | Must |
| A-04 | Allow demand planners to approve or reject individual recommendations | Must |
| A-05 | LLM must only generate recommendations grounded in actual data (no hallucination) | Must |
| A-06 | Recommendations include: action type, SKU, region, description, urgency, expected impact | Should |

### 5.5 Analytics Chat

| ID | Requirement | Priority |
|---|---|---|
| C-01 | Free-text Q&A interface accessible to all roles | Must |
| C-02 | Context-injection pattern: KPIs + deviations + pending actions injected into every system prompt | Must |
| C-03 | LLM must answer only from provided context — never invent data | Must |
| C-04 | Provide 5 chemical-domain quick-action buttons for common queries | Should |
| C-05 | Maintain conversation history within a session | Should |
| C-06 | Work with any OpenRouter-compatible model (configurable via env var) | Must |

### 5.6 Non-Functional Requirements

| ID | Requirement |
|---|---|
| NF-01 | Backend API response time < 2s for all read endpoints (excluding LLM calls) |
| NF-02 | LLM-dependent endpoints (chat, explain, agent/run) < 30s timeout |
| NF-03 | CORS restricted to configured origins (no wildcard in production) |
| NF-04 | All credentials stored in environment variables — never hardcoded |
| NF-05 | Frontend must work on Chrome, Edge, Firefox (latest 2 versions) |
| NF-06 | Databricks token must have `all-apis` scope for Jobs API access |
| NF-07 | System must degrade gracefully if any Databricks table is unavailable (fallback to empty, not crash) |

---

## 6. Technical Architecture Summary

See [architecture.md](architecture.md) for the full architecture diagram and layer-by-layer breakdown.

**Key decisions:**
- **Databricks Medallion Architecture** (Bronze → Silver → Gold) for data reliability and auditability
- **Context-injection chatbot** (not tool-calling) — works with any text-generation model, more reliable, lower latency
- **OpenRouter** as LLM gateway — model-agnostic, supports free tiers for demos, OpenAI-compatible API
- **Human-in-the-loop** for all agent recommendations — AI proposes, human approves

---

## 7. Data Model

### Source Files (CSV input)

| File Prefix | Description | Key Fields |
|---|---|---|
| `order_transactions` | Customer demand history | `sku_id`, `region`, `customer_segment`, `order_date`, `quantity_kg` |
| `inventory_levels` | Warehouse stock snapshots | `sku_id`, `warehouse_id`, `region`, `quantity_on_hand_kg`, `reorder_point_kg` |
| `production_capacity` | Plant output vs plan | `plant_id`, `region`, `sku_id`, `planned_capacity_kg`, `actual_output_kg` |
| `external_signals` | Macro/market indicators | `region`, `indicator_type`, `indicator_value`, `signal_date` |

### Key Delta Tables

| Table | Layer | Description |
|---|---|---|
| `order_transactions` | Bronze | Raw order data |
| `demand_history` | Silver | Cleaned, daily demand per SKU + region |
| `inventory_snapshot` | Silver | Current inventory with `days_on_hand` |
| `demand_forecast` | Gold | Weekly LightGBM predictions |
| `forecast_deviations` | Gold | Significant week-over-week changes |
| `agent_recommendations` | Gold | AI-generated supply actions + approval status |

---

## 8. API Contract Summary

| Method | Path | Description |
|---|---|---|
| `GET` | `/forecast/kpis` | Aggregate KPIs |
| `GET` | `/forecast/deviations` | Significant forecast changes |
| `POST` | `/forecast/explain` | LLM explanation for a deviation |
| `GET` | `/inventory/summary` | Inventory cover by region |
| `POST` | `/pipeline/upload` | Upload CSV to Databricks Volume |
| `POST` | `/pipeline/trigger` | Start Databricks job |
| `GET` | `/pipeline/status/{run_id}` | Poll job status |
| `POST` | `/agent/run` | Run agentic recommendation loop |
| `GET` | `/agent/recommendations` | List recommendations |
| `POST` | `/agent/recommendations/{id}/approve` | Approve recommendation |
| `POST` | `/agent/recommendations/{id}/reject` | Reject recommendation |
| `POST` | `/chat` | Free-text Q&A |

---

## 9. Out of Scope (v1.0)

- Real-time streaming ingestion (batch pipeline only)
- Automated execution of approved recommendations (ERP write-back)
- Multi-tenant / multi-catalog support
- Mobile-optimised UI
- Role-based access control (RBAC) within the web app
- Automated retraining on schedule (manual trigger only)
- Integration with external ERP/WMS systems (CSV import only)

---

## 10. Dependencies & Risks

| Item | Risk | Mitigation |
|---|---|---|
| Databricks PAT token | Token expiry breaks all API calls | Rotate tokens before expiry; document scope requirement (`all-apis`) |
| OpenRouter model availability | Free model may be deprecated or rate-limited | Keep `OPENROUTER_MODEL` configurable; test fallback models |
| LightGBM on Serverless compute | Library not pre-installed | Add `lightgbm` to job task Libraries/Environment |
| Data quality | Missing/malformed CSVs fail Silver transforms | Add validation step in Bronze notebook |
| LLM hallucination | Agent recommends actions not grounded in data | System prompt enforces data-only answers; human approval required before action |

---

## 11. Glossary

| Term | Definition |
|---|---|
| **SKU** | Stock Keeping Unit — a specific chemical product variant |
| **MAPE** | Mean Absolute Percentage Error — forecast accuracy metric |
| **Medallion Architecture** | Bronze (raw) → Silver (clean) → Gold (aggregated) data layering pattern |
| **Deviation** | A forecast change ≥ 10% between the current and prior pipeline run |
| **Champion model** | The production-grade model version registered in MLflow with the `Champion` alias |
| **Context injection** | Pattern where live data is embedded in the LLM system prompt rather than using tool-calling |
| **Agentic loop** | Automated multi-step AI reasoning: observe → analyse → recommend → await human approval |
| **DABS** | Databricks Asset Bundles — CI/CD framework for Databricks jobs and notebooks |
