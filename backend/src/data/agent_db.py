"""Databricks SQL query helpers for the chemical manufacturing agent layer.

Follows the exact same pattern as db.py: SQL constants at module level,
thin function wrappers that call run_query. Imports run_query and
connection_scope from db.py so connection management is shared.
"""

import logging
import os
import uuid
from datetime import datetime
from typing import Any, Optional

from src.data.db import connection_scope, run_query

logger = logging.getLogger("chem_ai_agent.agent_db")

CHEM_AI_CATALOG = os.getenv("CHEM_AI_CATALOG", "chem_ai")

# ── Read queries ──────────────────────────────────────────────────────────────

FETCH_DEVIATIONS_QUERY = f"""
    SELECT deviation_id, sku, region, customer_segment,
           deviation_pct, direction,
           current_predicted_tonnes, prior_predicted_tonnes,
           detection_timestamp
    FROM {CHEM_AI_CATALOG}.gold.forecast_deviations
    WHERE ABS(deviation_pct) >= :threshold_pct
    ORDER BY ABS(deviation_pct) DESC
"""

FETCH_INVENTORY_QUERY = f"""
    SELECT stock_on_hand_tonnes, days_on_hand,
           reorder_point_tonnes, shelf_life_remaining_days
    FROM {CHEM_AI_CATALOG}.silver.inventory_snapshot
    WHERE sku = :sku
    ORDER BY snapshot_date DESC
    LIMIT 1
"""

FETCH_CAPACITY_QUERY = f"""
    SELECT AVG(actual_utilisation_pct) AS capacity_utilisation_pct,
           MIN(planned_capacity_tonnes - actual_volume_tonnes) AS available_capacity_tonnes
    FROM {CHEM_AI_CATALOG}.bronze.production_capacity
    WHERE sku = :sku
      AND week_start_date >= date_sub(current_date(), 14)
"""

FETCH_PENDING_RECOMMENDATIONS_QUERY = f"""
    SELECT id, sku, region, customer_segment, deviation_pct, direction,
           inventory_days_on_hand, capacity_utilisation_pct, supplier_lead_time_days,
           action_type, description, urgency, quantity_adjustment_tonnes,
           affected_plants, status, approver, rejection_reason, created_at
    FROM {CHEM_AI_CATALOG}.gold.agent_recommendations
    WHERE status = 'PENDING'
    ORDER BY
        CASE urgency WHEN 'HIGH' THEN 1 WHEN 'MEDIUM' THEN 2 ELSE 3 END,
        ABS(deviation_pct) DESC
"""

FETCH_RECOMMENDATION_BY_ID_QUERY = f"""
    SELECT id, sku, region, customer_segment, deviation_pct, direction,
           inventory_days_on_hand, capacity_utilisation_pct, supplier_lead_time_days,
           action_type, description, urgency, quantity_adjustment_tonnes,
           affected_plants, status, approver, rejection_reason, created_at, decided_at
    FROM {CHEM_AI_CATALOG}.gold.agent_recommendations
    WHERE id = :id
"""

FETCH_AUDIT_LOG_QUERY = f"""
    SELECT event_id, recommendation_id, event_type, actor, timestamp, details
    FROM {CHEM_AI_CATALOG}.gold.agent_audit_log
    ORDER BY timestamp DESC
    LIMIT :limit_val
"""

FETCH_CHEMICAL_KPIS_QUERY = f"""
    SELECT
        COALESCE(SUM(CASE WHEN ABS(fd.deviation_pct) >= :threshold_pct
                     THEN fd.current_predicted_tonnes ELSE 0 END), 0)
            AS demand_at_risk_tonnes,
        COUNT(CASE WHEN ABS(fd.deviation_pct) >= :threshold_pct THEN 1 END)
            AS deviations_above_threshold
    FROM {CHEM_AI_CATALOG}.gold.forecast_deviations fd
"""

FETCH_INVENTORY_COVER_QUERY = f"""
    SELECT AVG(days_on_hand) AS avg_inventory_cover_days
    FROM {CHEM_AI_CATALOG}.silver.inventory_snapshot
"""

FETCH_FORECAST_MAPE_QUERY = f"""
    SELECT AVG(mape) AS forecast_mape_pct
    FROM {CHEM_AI_CATALOG}.gold.model_evaluation_results
    WHERE dataset_split = 'test'
"""

FETCH_PENDING_COUNT_QUERY = f"""
    SELECT COUNT(*) AS pending_count
    FROM {CHEM_AI_CATALOG}.gold.agent_recommendations
    WHERE status = 'PENDING'
"""

FETCH_CHEMICAL_SKUS_QUERY = f"""
    SELECT DISTINCT product_code, product_grade,
                    CONCAT(product_code, '-', product_grade) AS sku
    FROM {CHEM_AI_CATALOG}.silver.demand_history
    ORDER BY sku
"""

FETCH_CHEMICAL_PLANTS_QUERY = f"""
    SELECT DISTINCT plant_id,
                    plant_id AS plant_name,
                    '' AS region,
                    '' AS country
    FROM {CHEM_AI_CATALOG}.bronze.production_capacity
    ORDER BY plant_id
"""

# ── Write queries ─────────────────────────────────────────────────────────────

INSERT_RECOMMENDATION_QUERY = f"""
    INSERT INTO {CHEM_AI_CATALOG}.gold.agent_recommendations
        (id, sku, region, customer_segment, deviation_pct, direction,
         inventory_days_on_hand, capacity_utilisation_pct, supplier_lead_time_days,
         action_type, description, urgency, quantity_adjustment_tonnes,
         affected_plants, status, model_run_id)
    VALUES
        (:id, :sku, :region, :customer_segment, :deviation_pct, :direction,
         :inventory_days_on_hand, :capacity_utilisation_pct, :supplier_lead_time_days,
         :action_type, :description, :urgency, :quantity_adjustment_tonnes,
         :affected_plants, 'PENDING', :model_run_id)
"""

APPROVE_RECOMMENDATION_QUERY = f"""
    UPDATE {CHEM_AI_CATALOG}.gold.agent_recommendations
    SET status = 'APPROVED',
        approver = :approver,
        decided_at = current_timestamp()
    WHERE id = :id
      AND status = 'PENDING'
"""

REJECT_RECOMMENDATION_QUERY = f"""
    UPDATE {CHEM_AI_CATALOG}.gold.agent_recommendations
    SET status = 'REJECTED',
        rejection_reason = :reason,
        decided_at = current_timestamp()
    WHERE id = :id
      AND status = 'PENDING'
"""

INSERT_AUDIT_LOG_QUERY = f"""
    INSERT INTO {CHEM_AI_CATALOG}.gold.agent_audit_log
        (event_id, recommendation_id, event_type, actor, details)
    VALUES
        (:event_id, :recommendation_id, :event_type, :actor, :details)
"""


# ── Public functions ──────────────────────────────────────────────────────────

def fetch_deviations(threshold_pct: float) -> list[dict[str, Any]]:
    """Return all current forecast deviations above the threshold, largest first."""
    return run_query(FETCH_DEVIATIONS_QUERY, {"threshold_pct": threshold_pct})


def fetch_inventory_constraints(sku: str) -> Optional[dict[str, Any]]:
    """Latest inventory snapshot for a SKU, or None if not found."""
    rows = run_query(FETCH_INVENTORY_QUERY, {"sku": sku})
    return rows[0] if rows else None


def fetch_capacity_constraints(sku: str) -> Optional[dict[str, Any]]:
    """2-week average capacity utilisation and available capacity for a SKU."""
    rows = run_query(FETCH_CAPACITY_QUERY, {"sku": sku})
    return rows[0] if rows else None


def fetch_pending_recommendations() -> list[dict[str, Any]]:
    """All PENDING recommendations, sorted by urgency then deviation magnitude."""
    return run_query(FETCH_PENDING_RECOMMENDATIONS_QUERY)


def fetch_recommendation_by_id(rec_id: str) -> Optional[dict[str, Any]]:
    """Single recommendation row by ID, or None if not found."""
    rows = run_query(FETCH_RECOMMENDATION_BY_ID_QUERY, {"id": rec_id})
    return rows[0] if rows else None


def insert_recommendation(rec: dict[str, Any]) -> None:
    """Persist one new agent recommendation with status=PENDING."""
    run_query(INSERT_RECOMMENDATION_QUERY, rec)


def approve_recommendation(rec_id: str, approver: str) -> int:
    """Set status=APPROVED. Returns number of rows updated (0 if not found/already decided)."""
    rows = run_query(APPROVE_RECOMMENDATION_QUERY, {"id": rec_id, "approver": approver})
    return len(rows) if rows else 0


def reject_recommendation(rec_id: str, reason: str) -> int:
    """Set status=REJECTED. Returns number of rows updated (0 if not found/already decided)."""
    rows = run_query(REJECT_RECOMMENDATION_QUERY, {"id": rec_id, "reason": reason})
    return len(rows) if rows else 0


def insert_audit_log(
    event_type: str,
    recommendation_id: str,
    actor: str,
    details: str,
) -> None:
    """Append one event to the immutable audit log."""
    run_query(
        INSERT_AUDIT_LOG_QUERY,
        {
            "event_id":          str(uuid.uuid4()),
            "recommendation_id": recommendation_id,
            "event_type":        event_type,
            "actor":             actor,
            "details":           details,
        },
    )


def fetch_audit_log(limit: int = 100) -> list[dict[str, Any]]:
    """Most recent audit log entries, newest first."""
    return run_query(FETCH_AUDIT_LOG_QUERY, {"limit_val": limit})


def fetch_chemical_kpis(threshold_pct: float) -> dict[str, Any]:
    """Aggregate KPIs for the chemical dashboard header."""
    with connection_scope() as conn:
        kpi_rows = run_query(FETCH_CHEMICAL_KPIS_QUERY, {"threshold_pct": threshold_pct}, connection=conn)
        cover_rows = run_query(FETCH_INVENTORY_COVER_QUERY, connection=conn)
        mape_rows = run_query(FETCH_FORECAST_MAPE_QUERY, connection=conn)
        pending_rows = run_query(FETCH_PENDING_COUNT_QUERY, connection=conn)

    kpis = kpi_rows[0] if kpi_rows else {}
    return {
        "demand_at_risk_tonnes":       kpis.get("demand_at_risk_tonnes"),
        "avg_inventory_cover_days":    (cover_rows[0] or {}).get("avg_inventory_cover_days") if cover_rows else None,
        "forecast_mape_pct":           (mape_rows[0] or {}).get("forecast_mape_pct") if mape_rows else None,
        "pending_recommendations_count": (pending_rows[0] or {}).get("pending_count", 0) if pending_rows else 0,
        "deviation_threshold_pct":     threshold_pct,
    }


def fetch_chemical_skus() -> list[dict[str, Any]]:
    """All chemical SKUs (product_code, product_grade, sku) for the frontend selector."""
    return run_query(FETCH_CHEMICAL_SKUS_QUERY)


def fetch_chemical_plants() -> list[dict[str, Any]]:
    """All plant IDs for the frontend selector."""
    return run_query(FETCH_CHEMICAL_PLANTS_QUERY)
