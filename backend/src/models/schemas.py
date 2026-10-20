"""Pydantic models for the sales forecasting API."""

from datetime import date, datetime
from typing import Any, Dict, List, Literal, Optional

from pydantic import BaseModel


class ForecastRecord(BaseModel):
    """One row from sales_ai.gold.forecast_results."""

    forecast_id: str
    forecast_date: date
    product_id: str
    category: str
    brand: str
    store_id: str
    store_name: str
    city: str
    forecast_horizon: int
    predicted_units: float
    prediction_timestamp: datetime
    model_name: str
    model_version: str


class ForecastListResponse(BaseModel):
    """Response body for GET /forecast."""

    count: int
    results: List[ForecastRecord]


class HealthResponse(BaseModel):
    """Response body for GET /health."""

    status: str
    databricks_connected: bool


class ForecastPoint(BaseModel):
    """One point on a merged actual/forecast timeline.

    actual_units is sourced from sales_ai.gold.sales_features (real observed
    sales); predicted_units is sourced from sales_ai.gold.forecast_results
    (model output). Exactly one of the two is populated per date.
    """

    date: date
    actual_units: Optional[float] = None
    predicted_units: Optional[float] = None


class ForecastTrendResponse(BaseModel):
    """Response body for GET /forecast when include_history=true."""

    product_id: str
    store_id: str
    history_days: int
    points: List[ForecastPoint]


class ProductForecastGroup(BaseModel):
    """All forecast_results rows for one product, for GET /forecast/trend/all."""

    product_id: str
    category: str
    records: List[ForecastRecord]


class Product(BaseModel):
    """One row from sales_ai.silver.products, for GET /products."""

    product_id: str
    product_name: str
    category: str


class Store(BaseModel):
    """One row from sales_ai.silver.stores, for GET /stores."""

    store_id: str
    store_name: str
    city: str
    region: str


class ExplainRequest(BaseModel):
    """Request body for POST /forecast/explain."""

    product_id: str
    store_id: str
    user_question: Optional[str] = None


class ForecastSummary(BaseModel):
    """The Step-1 computed numbers -- always these, never anything the LLM says."""

    avg_predicted_units: float
    total_predicted_units: float
    vs_recent_history_pct_change: Optional[float] = None


class ExplainResponse(BaseModel):
    """Response body for POST /forecast/explain."""

    product_id: str
    store_id: str
    forecast_summary: ForecastSummary
    explanation: str
    key_drivers: List[str]
    risks_or_opportunities: List[str]
    recommendation: str
    model_version: str


class ChatMessage(BaseModel):
    """One turn of prior conversation, for POST /chat's optional history."""

    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    """Request body for POST /chat."""

    message: str
    history: List[ChatMessage] = []
    store_id: Optional[str] = None
    store_name: Optional[str] = None


class ChatResponse(BaseModel):
    """Response body for POST /chat and POST /chat/quick -- same shape for
    both, so the frontend can render them in one unified conversation."""

    answer: str
    data: Dict[str, Any]
    functions_used: List[str]


class QuickActionRequest(BaseModel):
    """Request body for POST /chat/quick."""

    action: str
    params: Dict[str, Any] = {}


class TopCategoryStat(BaseModel):
    days: int
    category: Optional[str] = None
    total_units: Optional[float] = None


class TopProductStat(BaseModel):
    days: int
    product_id: Optional[str] = None
    product_name: Optional[str] = None
    total_units: Optional[float] = None


class PredictedRevenueStat(BaseModel):
    total_predicted_units: Optional[float] = None
    total_predicted_revenue: Optional[float] = None
    note: Optional[str] = None


class KPISummary(BaseModel):
    """Response body for GET /kpis."""

    top_category: TopCategoryStat
    top_product: TopProductStat
    predicted_revenue: PredictedRevenueStat
    at_risk_count: int


class UploadedFileInfo(BaseModel):
    """One file uploaded to the Bronze incoming Volume."""

    filename: str
    volume_path: str


class PipelineTriggerResponse(BaseModel):
    """Response body for POST /pipeline/trigger."""

    run_id: int
    status: str = "triggered"


class PipelineStatusResponse(BaseModel):
    """Response body for GET /pipeline/status/{run_id}."""

    run_id: int
    life_cycle_state: str
    result_state: Optional[str] = None
    state_message: Optional[str] = None


class PipelineUploadAndTriggerResponse(BaseModel):
    """Response body for POST /pipeline/upload-and-trigger."""

    files: List[UploadedFileInfo]
    run_id: int
    status: str = "triggered"


# ── Chemical Manufacturing AI schemas ─────────────────────────────────────────


class ForecastDeviation(BaseModel):
    """One SKU/region/customer_segment deviation from chem_ai.gold.forecast_deviations."""

    deviation_id: str
    sku: str
    region: str
    customer_segment: str
    deviation_pct: float
    direction: str  # "UP" or "DOWN"
    current_predicted_tonnes: float
    prior_predicted_tonnes: float
    detection_timestamp: datetime


class AgentRecommendation(BaseModel):
    """One agent recommendation from chem_ai.gold.agent_recommendations."""

    id: str
    sku: str
    region: str
    customer_segment: Optional[str] = None
    deviation_pct: Optional[float] = None
    direction: Optional[str] = None
    inventory_days_on_hand: Optional[float] = None
    capacity_utilisation_pct: Optional[float] = None
    supplier_lead_time_days: Optional[int] = None
    action_type: str
    description: str
    urgency: str  # HIGH | MEDIUM | LOW
    quantity_adjustment_tonnes: float
    affected_plants: Optional[str] = None  # stored as JSON string in Delta
    status: str  # PENDING | APPROVED | REJECTED
    approver: Optional[str] = None
    rejection_reason: Optional[str] = None
    created_at: Optional[datetime] = None


class ApprovalRequest(BaseModel):
    """Request body for POST /agent/recommendations/{id}/approve."""

    approver: str


class RejectionRequest(BaseModel):
    """Request body for POST /agent/recommendations/{id}/reject."""

    reason: str


class AgentCycleResult(BaseModel):
    """Response body for POST /agent/run."""

    deviations_found: int
    recommendations_created: int
    errors: int
    run_timestamp: str


class ChemicalSKU(BaseModel):
    """One chemical SKU from chem_ai.silver.demand_history."""

    product_code: str
    product_grade: str
    sku: str


class ChemicalPlant(BaseModel):
    """One chemical plant from chem_ai.bronze.production_capacity."""

    plant_id: str
    plant_name: str
    region: str
    country: str


class ChemicalKPISummary(BaseModel):
    """Response body for GET /chemical/kpis."""

    demand_at_risk_tonnes: Optional[float] = None
    avg_inventory_cover_days: Optional[float] = None
    forecast_mape_pct: Optional[float] = None
    pending_recommendations_count: int = 0
    deviation_threshold_pct: float
