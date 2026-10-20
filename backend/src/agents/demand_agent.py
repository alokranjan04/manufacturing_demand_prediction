"""Demand Sensing & Agentic Response agent for the Chemical Manufacturing platform.

Implements the agentic loop:
    detect_deviations  →  check_supply_constraints  →  generate_recommendation
    →  create_recommendation_record  →  (human review in UI)

Design mirrors chatbot.py and forecast_explainer.py:
  - All data comes from real DB queries (agent_db.py), never invented
  - LLM is called only to narrate/structure data it was explicitly given
  - Fallback logic ensures the loop never crashes on a malformed LLM response
  - LLMConfigError and DB errors propagate for the caller (main.py) to handle
"""

import json
import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from src.data import agent_db
from src.genai.llm_client import LLMConfigError, call_chat_json

logger = logging.getLogger("chem_ai_agent.demand")

DEVIATION_THRESHOLD_PCT = float(os.getenv("DEVIATION_THRESHOLD_PCT", "10.0"))

# ── LLM prompt ────────────────────────────────────────────────────────────────

RECOMMENDATION_SYSTEM_PROMPT = """You are a chemical manufacturing supply chain planning assistant.
You are given a demand forecast deviation and current supply constraints
for a specific chemical SKU and region. Based ONLY on the data provided,
generate a structured recommendation for the supply planner.

Respond with a single JSON object with exactly these keys and no others:
{
  "action_type": "INCREASE_PRODUCTION | REDUCE_PRODUCTION | REBALANCE_DISTRIBUTION | MONITOR_ONLY",
  "description": "Plain language description of the recommended action (2-3 sentences, no invented facts)",
  "urgency": "HIGH | MEDIUM | LOW",
  "quantity_adjustment_tonnes": <number — positive = increase, negative = decrease, 0 if MONITOR_ONLY>,
  "affected_plants": ["plant_id_1"]
}

Rules:
- If inventory_days_on_hand < 14 and direction is UP, urgency MUST be HIGH
- If capacity_utilisation_pct > 90 and direction is UP, mention the constraint in description
- quantity_adjustment_tonnes must be derived from the deviation data provided (not invented)
- affected_plants must come from the plant_id in the data provided
- Return nothing except the JSON object"""

REQUIRED_KEYS = {"action_type", "description", "urgency", "quantity_adjustment_tonnes", "affected_plants"}
VALID_ACTION_TYPES = {"INCREASE_PRODUCTION", "REDUCE_PRODUCTION", "REBALANCE_DISTRIBUTION", "MONITOR_ONLY"}
VALID_URGENCY_LEVELS = {"HIGH", "MEDIUM", "LOW"}


# ── Validation helpers ────────────────────────────────────────────────────────

def _parse_recommendation(raw_content: Optional[str]) -> Optional[dict[str, Any]]:
    """Parse and validate the LLM's JSON recommendation.
    Returns None if parsing fails or required keys / valid values are missing.
    Mirrors _parse_and_validate in forecast_explainer.py."""
    if not raw_content:
        return None
    try:
        parsed = json.loads(raw_content)
    except (json.JSONDecodeError, TypeError):
        return None
    if not isinstance(parsed, dict):
        return None
    if not REQUIRED_KEYS.issubset(parsed.keys()):
        return None
    if parsed.get("action_type") not in VALID_ACTION_TYPES:
        return None
    if parsed.get("urgency") not in VALID_URGENCY_LEVELS:
        return None
    if not isinstance(parsed.get("quantity_adjustment_tonnes"), (int, float)):
        return None
    if not isinstance(parsed.get("affected_plants"), list):
        return None
    return parsed


def _fallback_recommendation(
    deviation: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """Rule-based fallback when the LLM response cannot be parsed twice.

    Ensures run_agent_cycle() always produces a recommendation rather than
    silently dropping a deviation. Logic:
      - UP + low inventory (< 14 days) → INCREASE_PRODUCTION, HIGH
      - UP + inventory ok              → INCREASE_PRODUCTION, MEDIUM
      - DOWN + large deviation (> 20%) → REDUCE_PRODUCTION, MEDIUM
      - otherwise                      → MONITOR_ONLY, LOW
    """
    direction = deviation.get("direction", "UP")
    deviation_pct = abs(deviation.get("deviation_pct", 0))
    current_tonnes = deviation.get("current_predicted_tonnes", 0)
    inv_days = constraints.get("inventory_days_on_hand")
    plant_id = deviation.get("plant_id", "UNKNOWN_PLANT")

    qty_adj = (deviation_pct / 100) * current_tonnes

    if direction == "UP":
        if inv_days is not None and inv_days < 14:
            action, urgency = "INCREASE_PRODUCTION", "HIGH"
            desc = (
                f"Demand forecast for {deviation['sku']} in {deviation['region']} has increased "
                f"by {deviation_pct:.1f}%. With only {inv_days:.1f} days of inventory cover, "
                f"an immediate production increase of approximately {qty_adj:.0f} tonnes is recommended."
            )
        else:
            action, urgency = "INCREASE_PRODUCTION", "MEDIUM"
            desc = (
                f"Demand forecast for {deviation['sku']} in {deviation['region']} has increased "
                f"by {deviation_pct:.1f}%. A production increase of approximately {qty_adj:.0f} tonnes "
                f"is recommended to maintain service levels."
            )
        qty = qty_adj
    elif direction == "DOWN" and deviation_pct > 20:
        action, urgency, qty = "REDUCE_PRODUCTION", "MEDIUM", -qty_adj
        desc = (
            f"Demand forecast for {deviation['sku']} in {deviation['region']} has decreased "
            f"by {deviation_pct:.1f}%. A production reduction of approximately {qty_adj:.0f} tonnes "
            f"is recommended to avoid inventory build-up."
        )
    else:
        action, urgency, qty = "MONITOR_ONLY", "LOW", 0.0
        desc = (
            f"Demand forecast for {deviation['sku']} in {deviation['region']} shows a "
            f"{deviation_pct:.1f}% {direction.lower()} deviation. Monitor closely over the next 2 weeks."
        )

    return {
        "action_type":               action,
        "description":               desc,
        "urgency":                   urgency,
        "quantity_adjustment_tonnes": round(qty, 1),
        "affected_plants":           [plant_id] if plant_id != "UNKNOWN_PLANT" else [],
    }


# ── Core functions ────────────────────────────────────────────────────────────

def detect_deviations(threshold_pct: float = DEVIATION_THRESHOLD_PCT) -> list[dict[str, Any]]:
    """Fetch all SKU/region/customer_segment pairs where the forecast deviated
    by >= threshold_pct vs the prior pipeline run.

    Returns an empty list on DB error (logs a warning) so the agent cycle
    can complete gracefully rather than crashing.
    """
    try:
        return agent_db.fetch_deviations(threshold_pct)
    except Exception:
        logger.warning("fetch_deviations failed — returning empty list.", exc_info=True)
        return []


def check_supply_constraints(sku: str) -> dict[str, Any]:
    """Assemble the supply constraint snapshot for one SKU:
      - inventory_days_on_hand (from silver.inventory_snapshot)
      - capacity_utilisation_pct (2-week average from bronze.production_capacity)

    Returns a dict with all keys present (None values for missing data).
    Never raises — missing constraints become context for the LLM.
    """
    constraints: dict[str, Any] = {
        "inventory_days_on_hand":     None,
        "capacity_utilisation_pct":   None,
        "available_capacity_tonnes":  None,
    }

    try:
        inv = agent_db.fetch_inventory_constraints(sku)
        if inv:
            constraints["inventory_days_on_hand"] = inv.get("days_on_hand")
    except Exception:
        logger.warning("fetch_inventory_constraints failed for sku=%s", sku, exc_info=True)

    try:
        cap = agent_db.fetch_capacity_constraints(sku)
        if cap:
            constraints["capacity_utilisation_pct"]  = cap.get("capacity_utilisation_pct")
            constraints["available_capacity_tonnes"]  = cap.get("available_capacity_tonnes")
    except Exception:
        logger.warning("fetch_capacity_constraints failed for sku=%s", sku, exc_info=True)

    return constraints


def generate_recommendation(
    deviation: dict[str, Any],
    constraints: dict[str, Any],
) -> dict[str, Any]:
    """Call the LLM with the deviation + constraints as grounded context.

    Retries once on a malformed response, then falls back to the rule-based
    _fallback_recommendation. LLMConfigError and network errors propagate
    so the caller (run_agent_cycle) can count them as errors.
    """
    user_message = (
        "Chemical demand deviation and supply constraints (the only facts you may use):\n"
        + json.dumps({"deviation": deviation, "constraints": constraints}, indent=2, default=str)
        + "\n\nGenerate a structured supply planning recommendation."
    )

    for attempt in range(2):
        try:
            raw = call_chat_json(RECOMMENDATION_SYSTEM_PROMPT, user_message)
        except LLMConfigError:
            raise  # propagate — let run_agent_cycle log it
        except Exception:
            logger.warning("LLM call failed on attempt %d for sku=%s", attempt + 1, deviation.get("sku"), exc_info=True)
            continue

        parsed = _parse_recommendation(raw)
        if parsed is not None:
            return parsed
        logger.warning("Recommendation parse failed on attempt %d: %r", attempt + 1, raw)

    logger.warning("LLM failed twice; using rule-based fallback for sku=%s", deviation.get("sku"))
    return _fallback_recommendation(deviation, constraints)


def create_recommendation_record(
    deviation: dict[str, Any],
    constraints: dict[str, Any],
    recommendation: dict[str, Any],
    model_run_id: str,
) -> str:
    """Persist the full recommendation to agent_recommendations (status=PENDING).
    Also writes a CREATED event to the audit log.
    Returns the new recommendation ID.
    """
    rec_id = str(uuid.uuid4())

    rec_row = {
        "id":                          rec_id,
        "sku":                         deviation.get("sku", ""),
        "region":                      deviation.get("region", ""),
        "customer_segment":            deviation.get("customer_segment", ""),
        "deviation_pct":               deviation.get("deviation_pct"),
        "direction":                   deviation.get("direction"),
        "inventory_days_on_hand":      constraints.get("inventory_days_on_hand"),
        "capacity_utilisation_pct":    constraints.get("capacity_utilisation_pct"),
        "supplier_lead_time_days":     None,  # not yet queried; available for future extension
        "action_type":                 recommendation["action_type"],
        "description":                 recommendation["description"],
        "urgency":                     recommendation["urgency"],
        "quantity_adjustment_tonnes":  recommendation["quantity_adjustment_tonnes"],
        "affected_plants":             str(recommendation.get("affected_plants", [])),
        "model_run_id":                model_run_id,
    }

    agent_db.insert_recommendation(rec_row)

    agent_db.insert_audit_log(
        event_type="CREATED",
        recommendation_id=rec_id,
        actor="AGENT",
        details=json.dumps({
            "sku":          rec_row["sku"],
            "deviation_pct": rec_row["deviation_pct"],
            "action_type":  rec_row["action_type"],
            "urgency":      rec_row["urgency"],
        }),
    )

    return rec_id


def run_agent_cycle(
    threshold_pct: float = DEVIATION_THRESHOLD_PCT,
) -> dict[str, Any]:
    """Orchestrate one full agent cycle:
      1. detect_deviations(threshold_pct)
      2. For each deviation: check_supply_constraints → generate_recommendation
         → create_recommendation_record
      3. Return summary: {deviations_found, recommendations_created, errors, run_timestamp}

    Errors on individual SKUs are caught and counted; the cycle continues
    for remaining SKUs rather than aborting entirely.
    """
    run_id = str(uuid.uuid4())
    deviations = detect_deviations(threshold_pct)
    recommendations_created = 0
    errors = 0

    logger.info(
        "Agent cycle started — run_id=%s deviations_found=%d threshold_pct=%s",
        run_id, len(deviations), threshold_pct
    )

    for deviation in deviations:
        sku = deviation.get("sku", "unknown")
        try:
            constraints = check_supply_constraints(sku)
            recommendation = generate_recommendation(deviation, constraints)
            create_recommendation_record(deviation, constraints, recommendation, run_id)
            recommendations_created += 1
            logger.info(
                "Recommendation created — sku=%s region=%s deviation_pct=%.1f action=%s urgency=%s",
                sku, deviation.get("region"), deviation.get("deviation_pct", 0),
                recommendation["action_type"], recommendation["urgency"],
            )
        except LLMConfigError:
            logger.error("LLM not configured — stopping agent cycle early.")
            errors += 1
            break  # no point continuing if LLM is down for all SKUs
        except Exception:
            logger.exception("Agent cycle error for sku=%s — continuing with next deviation.", sku)
            errors += 1

    logger.info(
        "Agent cycle complete — run_id=%s recommendations_created=%d errors=%d",
        run_id, recommendations_created, errors,
    )

    return {
        "deviations_found":       len(deviations),
        "recommendations_created": recommendations_created,
        "errors":                  errors,
        "run_timestamp":           datetime.utcnow().isoformat(),
    }
