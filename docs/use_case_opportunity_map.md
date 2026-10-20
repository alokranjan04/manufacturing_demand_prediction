# AI Use-Case Opportunity Map
## Chemical Manufacturing — Demand & Distribution Intelligence

**Version**: 1.0
**Date**: October 2026

---

## Opportunity Prioritisation Matrix

| # | Use Case | Value | Feasibility | Data Readiness | Priority |
|---|---|---|---|---|---|
| 1 | **Demand Sensing & Agentic Response** | ★★★★★ | ★★★★★ | ★★★★★ | **P0 — BUILT** |
| 2 | **Stockout / Excess Inventory Prediction** | ★★★★★ | ★★★★☆ | ★★★★☆ | **P1** |
| 3 | **Supply Disruption Prediction** | ★★★★☆ | ★★★☆☆ | ★★★☆☆ | **P2** |
| 4 | **Production Planning Optimisation** | ★★★★☆ | ★★★★☆ | ★★★★☆ | **P2** |
| 5 | **Distribution Optimisation** | ★★★☆☆ | ★★★☆☆ | ★★★☆☆ | **P3** |
| 6 | **Procurement Intelligence** | ★★★★☆ | ★★★☆☆ | ★★☆☆☆ | **P3** |
| 7 | **Invoice & Order Anomaly Detection** | ★★★☆☆ | ★★★★☆ | ★★★★☆ | **P3** |

---

## Use Case 1 — Demand Sensing & Agentic Response

> **Status: BUILT — see prototype section below**

| Dimension | Detail |
|---|---|
| **Business Problem** | Demand shifts go unnoticed between monthly S&OP cycles. By the time planners act, stockouts or excess inventory have already occurred. No systematic way to detect which SKU/region/segment changed and why. |
| **AI / Agent Approach** | LightGBM model predicts weekly demand per SKU + region. An agentic loop runs post-pipeline: detects deviations ≥ 10%, checks inventory cover and capacity constraints per SKU, calls LLM to generate structured supply recommendation (INCREASE_PRODUCTION / REDUCE_PRODUCTION / REBALANCE_DISTRIBUTION / MONITOR_ONLY). |
| **Data Required** | `order_transactions` (demand history), `inventory_levels` (stock on hand, reorder points), `production_capacity` (plant output, utilisation), `external_signals` (macro indicators) |
| **Action Taken** | Agent stores recommendation in `agent_recommendations` table with urgency (HIGH / MEDIUM / LOW), quantity adjustment, and affected plants. Human reviews in Agent Workflow UI. |
| **Human Involvement** | Demand planner reviews all recommendations. Approves or rejects with optional comment. Approved actions trigger downstream workflow (production schedule, distribution order). |
| **Measurable KPIs** | Forecast MAPE < 15%, deviation detection lag < 1 hour, % of HIGH-urgency recommendations reviewed within 24h, reduction in stockout events, reduction in excess inventory days |
| **Expected Business Benefit** | 10–20% reduction in safety stock cost, 15–30% fewer stockout events, faster S&OP cycle (daily vs monthly), planner time saved from manual deviation hunting |

---

## Use Case 2 — Stockout / Excess Inventory Prediction

| Dimension | Detail |
|---|---|
| **Business Problem** | Planners discover stockouts or bloated inventory reactively — after the event. No early-warning system flags SKUs at risk 2–4 weeks ahead when corrective action is still possible. |
| **AI / Agent Approach** | Classification model (LightGBM or logistic regression) predicts probability of stockout or excess within the next 2–4 weeks per SKU + warehouse. Agent monitors predictions daily and raises alerts when probability crosses threshold. LLM generates plain-language risk summary with recommended pre-action. |
| **Data Required** | `inventory_levels` (current stock, reorder points, shelf life), `demand_forecast` (predicted weekly demand), `production_capacity` (replenishment pipeline), `order_transactions` (historical stockout events as labels) |
| **Action Taken** | Risk alert raised per SKU with risk score, root cause (demand spike / low stock / long lead time), and recommended action (expedite replenishment / redirect from another warehouse / adjust production). |
| **Human Involvement** | Supply planner reviews risk dashboard weekly. Approves expedite orders or redistribution requests. High-risk SKUs trigger mandatory review within 48 hours. |
| **Measurable KPIs** | Stockout prediction precision / recall, days of advance warning (target: 14 days), stockout frequency (events per month), excess inventory value (£/tonne weeks held) |
| **Expected Business Benefit** | 25–40% reduction in stockout frequency, 10–15% reduction in expediting costs, £X reduction in excess inventory write-off, improved customer OTIF (On Time In Full) |

---

## Use Case 3 — Supply Disruption Prediction

| Dimension | Detail |
|---|---|
| **Business Problem** | Supply chain disruptions (raw material shortages, logistics failures, supplier delays, energy price spikes) arrive without warning. No system connects external signals to internal supply risk before impact is felt. |
| **AI / Agent Approach** | Anomaly detection + classification model monitors external signals (energy cost index, logistics disruption index, geopolitical risk scores, supplier lead time trends). When a risk pattern is detected, an agent cross-references affected SKUs and regions, estimates impact on production schedule, and generates contingency options. |
| **Data Required** | `external_signals` (energy cost, logistics disruption, demand seasonality), `production_capacity` (supplier dependencies, input materials per SKU), `order_transactions` (customer order commitments), third-party risk feeds (future integration) |
| **Action Taken** | Disruption risk card created with affected SKUs, estimated tonnes at risk, lead time impact, and 3 contingency options ranked by feasibility. Planner selects and approves preferred response. |
| **Human Involvement** | Supply chain risk manager reviews weekly disruption dashboard. Triggered alerts require response within 24h for HIGH-rated risks. Agent cannot auto-trigger supplier switches or production changes without approval. |
| **Measurable KPIs** | Disruption prediction lead time (days of advance warning), number of disruptions caught vs missed, recovery time after disruption, cost of unplanned production stoppages |
| **Expected Business Benefit** | 20–30% faster disruption response, reduction in unplanned stoppages, stronger supplier negotiation position (data-backed lead time benchmarks), lower air freight / expedite costs |

---

## Use Case 4 — Production Planning Optimisation

| Dimension | Detail |
|---|---|
| **Business Problem** | Production schedules are built manually in spreadsheets, disconnected from the latest demand forecast. Planners over-produce to hedge against uncertainty, driving up inventory and cost. Capacity constraints across plants are not jointly optimised. |
| **AI / Agent Approach** | Optimisation model (linear programming or constraint-based solver) takes demand forecast, plant capacities, changeover times, and raw material availability as inputs. Produces an optimal production plan per plant per SKU per week that minimises cost while meeting service levels. Agent detects when the live forecast diverges from the current plan and flags replanning triggers. |
| **Data Required** | `demand_forecast` (weekly demand per SKU/region), `production_capacity` (plant capacities, efficiency rates, planned vs actual), `inventory_levels` (current stock, safety stock targets), changeover matrix (future integration), raw material availability (future integration) |
| **Action Taken** | Agent generates a revised production schedule recommendation per plant, highlights capacity bottlenecks, and estimates cost delta vs current plan. Planner compares options and approves. |
| **Human Involvement** | Production planner reviews plan weekly before the S&OP freeze. Bottleneck alerts reviewed within 24h. Final sign-off always required — agent never auto-commits to the MES. |
| **Measurable KPIs** | Capacity utilisation % (target: 80–90%), production plan adherence %, changeover time per week, over-production tonnes per month, planning cycle time (hours) |
| **Expected Business Benefit** | 5–15% improvement in capacity utilisation, 10–20% reduction in over-production, planning cycle time reduced from days to hours, fewer last-minute schedule changes |

---

## Use Case 5 — Distribution Optimisation

| Dimension | Detail |
|---|---|
| **Business Problem** | Finished goods are distributed from plants to regional warehouses using fixed allocation rules that don't account for shifting demand. Some regions run short while others hold excess, leading to costly inter-warehouse transfers. |
| **AI / Agent Approach** | Network flow optimisation model recommends optimal allocation of production output across warehouses per region, minimising transport cost and inventory imbalance. Agent monitors regional inventory cover daily and flags rebalancing opportunities. LLM explains trade-offs in plain language for logistics planners. |
| **Data Required** | `demand_forecast` (regional weekly demand), `inventory_levels` (warehouse stock per region), `production_capacity` (plant output per week), transport cost matrix (future integration), warehouse capacity limits |
| **Action Taken** | Agent generates a rebalancing proposal: which SKU moves from which plant/warehouse to which region, in what quantity, by when. Logistics planner approves and triggers the transfer order. |
| **Human Involvement** | Logistics planner reviews rebalancing proposals 2x per week. Agent recommends; planner decides. Transfer orders require approval before creation in TMS/ERP. |
| **Measurable KPIs** | Inter-warehouse transfer cost per month, regional inventory imbalance score, transport cost per tonne-km, distribution fill rate per region |
| **Expected Business Benefit** | 10–20% reduction in inter-warehouse transfer costs, higher regional fill rates, reduced safety stock across the network, lower demurrage and storage charges |

---

## Use Case 6 — Procurement Intelligence

| Dimension | Detail |
|---|---|
| **Business Problem** | Raw material procurement decisions are driven by buyer intuition and long-term contracts. No system uses demand forecast data to time purchases optimally, benchmark supplier pricing, or flag when spot-buy opportunities exist. |
| **AI / Agent Approach** | Demand-driven procurement model calculates forward raw material requirements from the demand forecast + current stock. ML model predicts price movement risk for key inputs based on external signals. Agent recommends buy/hold/defer decisions per raw material per supplier with confidence scores. |
| **Data Required** | `demand_forecast` (finished goods demand → back-calculated raw material needs), `external_signals` (commodity price indices, energy cost), `inventory_levels` (raw material stock), supplier lead time history (future integration), historical purchase prices (future integration) |
| **Action Taken** | Agent generates weekly procurement recommendation: materials to buy this week, volumes, preferred supplier, and buy-vs-wait rationale. Buyer reviews and approves purchase order. |
| **Human Involvement** | Procurement buyer reviews weekly recommendation report. Spot-buy decisions require line manager approval above £X threshold. Agent cannot place purchase orders without human sign-off. |
| **Measurable KPIs** | Raw material cost vs benchmark, % of purchases on contract vs spot, procurement cycle time (days), raw material stockout frequency, price variance vs forecast |
| **Expected Business Benefit** | 3–8% reduction in raw material cost, fewer emergency spot buys at premium pricing, better supplier negotiation with data-backed benchmarks, reduced raw material carrying cost |

---

## Use Case 7 — Invoice & Order Anomaly Detection

| Dimension | Detail |
|---|---|
| **Business Problem** | Manual invoice checking misses pricing errors, duplicate orders, and unusual order patterns. Fraudulent or erroneous transactions are caught late (if at all), leading to revenue leakage and audit risk. |
| **AI / Agent Approach** | Anomaly detection model (isolation forest or autoencoder) learns normal order and invoice patterns per customer, SKU, and region. Flags statistically unusual transactions: duplicate orders, price deviations from contract, unusual quantities, orders outside business hours. Agent generates a structured anomaly report per flagged transaction with severity score and explanation. |
| **Data Required** | `order_transactions` (order history — price, quantity, customer, date, channel, discount), invoice data (future integration), contract price tables (future integration), customer purchasing history |
| **Action Taken** | Flagged transactions queued for finance/commercial review with anomaly type, severity score, and recommended action (investigate / approve / escalate). Dashboard shows trend of anomaly volume over time. |
| **Human Involvement** | Finance analyst reviews flagged transactions daily. Accepts or escalates each anomaly. High-severity flags (e.g. duplicate invoice > £10k) require manager sign-off. |
| **Measurable KPIs** | Precision/recall of anomaly detection, value of recovered billing errors per quarter, average review time per anomaly, false-positive rate (analyst efficiency) |
| **Expected Business Benefit** | Recovery of revenue leakage from billing errors, reduced audit risk, faster invoice cycle, early detection of unusual customer behaviour patterns |

---

---

# Prototype: Use Case 1 — Demand Sensing & Agentic Response

> This use case is fully implemented in the current platform. The sections below document the exact design and code architecture.

---

## Full Agentic Flow

```
┌─────────────────────────────────────────────────────────────────┐
│                     DATA LAYER (Databricks)                     │
│                                                                 │
│  order_transactions  +  inventory_levels                        │
│  production_capacity  +  external_signals                       │
│              │                                                  │
│              ▼  (Medallion Pipeline — notebooks 01–07)          │
│  Bronze → Silver → Gold                                         │
│              │                                                  │
│              ▼                                                  │
│  LightGBM Champion Model  →  demand_forecast (Gold)            │
│              │                                                  │
│              ▼                                                  │
│  Deviation detection (≥ 10% week-over-week)                     │
│        →  forecast_deviations (Gold)                            │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    │  POST /agent/run
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    AGENTIC LOOP (demand_agent.py)               │
│                                                                 │
│  Step 1: detect_deviations(threshold_pct=10%)                   │
│          → fetch forecast_deviations from Gold                  │
│          → returns list of {sku, region, segment,               │
│                             deviation_pct, direction,           │
│                             current_tonnes, prior_tonnes}       │
│                    │                                            │
│  Step 2: For each deviation:                                    │
│          check_supply_constraints(sku)                          │
│          → fetch inventory_snapshot (days_on_hand)              │
│          → fetch production_capacity (utilisation %)           │
│                    │                                            │
│  Step 3: generate_recommendation(deviation, constraints)        │
│          → Build grounded context message                       │
│          → Call LLM (OpenRouter) with system prompt             │
│          → LLM outputs structured JSON:                         │
│            {                                                    │
│              "action_type": "INCREASE_PRODUCTION",              │
│              "description": "...",                              │
│              "urgency": "HIGH",                                 │
│              "quantity_adjustment_tonnes": 45.0,                │
│              "affected_plants": ["PLANT_DE_01"]                 │
│            }                                                    │
│          → Validates JSON schema                                │
│          → Falls back to rule-based logic if LLM fails twice    │
│                    │                                            │
│  Step 4: create_recommendation_record(...)                      │
│          → INSERT into agent_recommendations (status=PENDING)   │
│          → INSERT into agent_audit_log (event=CREATED)          │
└───────────────────┬─────────────────────────────────────────────┘
                    │
                    │  GET /agent/recommendations
                    ▼
┌─────────────────────────────────────────────────────────────────┐
│                  HUMAN REVIEW (Agent Workflow UI)               │
│                                                                 │
│  Planner sees recommendation card:                              │
│  ┌─────────────────────────────────────────────┐               │
│  │ [HIGH] SKU-CHE-001 / Europe                 │               │
│  │ INCREASE_PRODUCTION — +45 tonnes            │               │
│  │ Demand up 23% · 8 days inventory cover      │               │
│  │ Affected plants: PLANT_DE_01                │               │
│  │                                             │               │
│  │  [✓ Approve]          [✗ Reject]            │               │
│  └─────────────────────────────────────────────┘               │
│                    │                                            │
│  POST /agent/recommendations/{id}/approve                       │
│  → UPDATE status = APPROVED, decided_at = now()                 │
│  → INSERT audit log (event=APPROVED, actor=planner)             │
└─────────────────────────────────────────────────────────────────┘
```

---

## LLM Decision Logic

The agent uses a **grounded context-injection** pattern — the LLM never invents data:

```
System prompt:
  "You are a chemical manufacturing supply chain planning assistant.
   Based ONLY on the data provided, generate a structured recommendation.
   Rules:
   - If inventory_days_on_hand < 14 and direction is UP → urgency MUST be HIGH
   - If capacity_utilisation_pct > 90 and direction is UP → mention constraint
   - quantity_adjustment_tonnes must be derived from the deviation data provided
   - Return nothing except the JSON object"

User message:
  {
    "deviation": {
      "sku": "CHE-001",
      "region": "Europe",
      "deviation_pct": 23.4,
      "direction": "UP",
      "current_predicted_tonnes": 450.0,
      "prior_predicted_tonnes": 364.5
    },
    "constraints": {
      "inventory_days_on_hand": 8.2,
      "capacity_utilisation_pct": 74.0,
      "available_capacity_tonnes": 120.0
    }
  }
```

**Fallback logic** (rule-based, triggered when LLM fails twice):

| Condition | Action | Urgency |
|---|---|---|
| Direction=UP + inventory < 14 days | INCREASE_PRODUCTION | HIGH |
| Direction=UP + inventory ≥ 14 days | INCREASE_PRODUCTION | MEDIUM |
| Direction=DOWN + deviation > 20% | REDUCE_PRODUCTION | MEDIUM |
| Otherwise | MONITOR_ONLY | LOW |

---

## Code Structure

```
backend/
├── src/
│   ├── agents/
│   │   └── demand_agent.py        ← Agentic loop orchestration
│   ├── data/
│   │   └── agent_db.py            ← All SQL: deviations, inventory,
│   │                                 capacity, recommendations, audit log
│   └── genai/
│       ├── llm_client.py          ← OpenRouter client (call_chat_json)
│       └── chatbot.py             ← Context-injection chat (separate flow)
└── main.py                        ← FastAPI routes: /agent/*

Databricks/Chem_ai/src/
├── 01_setup_chem_ai.py            ← Create catalog, schemas, tables
├── 02_bronze_ingestion.py         ← Raw CSV → Bronze Delta
├── 03_silver_transformation.py    ← Bronze → Silver (clean, join)
├── 05_gold_feature_engineering.py ← Silver → Gold (aggregated)
├── 06_model_training.py           ← LightGBM train → MLflow Champion
└── 07_batch_inference_and_deviation.py ← Batch score → deviations

frontend/src/
├── pages/AgentWorkflowPage.tsx    ← Recommendation review UI
└── api/agent.ts                   ← API calls: run, list, approve, reject
```

---

## API Endpoints

| Method | Path | Description |
|---|---|---|
| `POST` | `/agent/run` | Trigger one full agent cycle (detect → recommend → store) |
| `GET` | `/agent/recommendations` | List all PENDING recommendations, sorted by urgency |
| `POST` | `/agent/recommendations/{id}/approve` | Approve a recommendation (requires `approver` in body) |
| `POST` | `/agent/recommendations/{id}/reject` | Reject with optional `reason` |
| `GET` | `/agent/audit-log` | Full immutable audit trail of all agent and human actions |

---

## Key Design Decisions

| Decision | Rationale |
|---|---|
| **Context injection (not tool-calling)** | Works with any LLM on OpenRouter including free models; no model-specific tool-call syntax required |
| **Rule-based fallback** | Agent never silently drops a deviation — if LLM fails twice, a rule-based recommendation is generated instead |
| **Human-in-the-loop always** | Agent cannot auto-trigger production or distribution changes; every recommendation requires planner approval |
| **Immutable audit log** | Every CREATE, APPROVE, REJECT event is written to `agent_audit_log` — full traceability for compliance |
| **Per-SKU constraint fetch** | Inventory and capacity are fetched fresh per SKU during the cycle, not cached — ensures recommendations reflect latest data |
| **Graceful degradation** | DB errors per SKU are caught and counted; cycle continues for remaining SKUs rather than aborting entirely |

---

## Measurable KPIs (Prototype Targets)

| KPI | Measurement | Target |
|---|---|---|
| Forecast MAPE | `AVG(mape)` from `model_evaluation_results` | < 15% |
| Deviation detection lag | Time from pipeline completion to recommendations created | < 1 hour |
| Recommendation coverage | Recommendations created / deviations detected | > 95% |
| High-urgency review time | Time from CREATED to APPROVED/REJECTED for HIGH urgency | < 24 hours |
| Agent cycle errors | `errors` count in `/agent/run` response | < 5% of deviations |
| Stockout events (post-deployment) | Monthly count of SKUs reaching zero stock | Reduce by 20% in 90 days |
| Excess inventory days | Average days on hand for non-critical SKUs | Reduce by 10% in 90 days |
