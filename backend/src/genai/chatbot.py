"""LLM chat orchestration for POST /chat — chemical manufacturing variant.

Rather than tool-calling (which requires model support), we fetch all
relevant chemical context upfront and inject it into the system prompt.
This works with any text-generation model on OpenRouter, including free ones.
"""

import json
import logging
import re
from typing import Any, Optional

from src.data import agent_db
from src.genai.llm_client import call_chat_json

logger = logging.getLogger("sales_forecasting_api.chatbot")

# Kept for /chat/quick endpoint compatibility (now unused by the frontend)
QUICK_ACTIONS: dict = {}


def _fetch_chemical_context() -> dict[str, Any]:
    """Fetch all chemical manufacturing context needed to answer most questions.
    Failures are caught per-section so a missing table never kills the whole call."""

    ctx: dict[str, Any] = {}

    try:
        ctx["kpis"] = agent_db.fetch_chemical_kpis(threshold_pct=10.0)
    except Exception:
        logger.warning("Could not fetch chemical KPIs for chat context", exc_info=True)
        ctx["kpis"] = {}

    try:
        ctx["deviations"] = agent_db.fetch_deviations(threshold_pct=10.0)
    except Exception:
        logger.warning("Could not fetch deviations for chat context", exc_info=True)
        ctx["deviations"] = []

    try:
        ctx["pending_actions"] = agent_db.fetch_pending_recommendations()
    except Exception:
        logger.warning("Could not fetch pending recommendations for chat context", exc_info=True)
        ctx["pending_actions"] = []

    return ctx


def _build_system_prompt(ctx: dict[str, Any]) -> str:
    kpis = ctx.get("kpis", {})
    deviations = ctx.get("deviations", [])
    pending = ctx.get("pending_actions", [])

    kpi_block = json.dumps(kpis, default=str, indent=2) if kpis else "Not available."

    if deviations:
        dev_lines = "\n".join(
            f"  - {d.get('sku')} / {d.get('region')} / {d.get('customer_segment')}: "
            f"{d.get('direction')} {abs(d.get('deviation_pct', 0)):.1f}% "
            f"(current {d.get('current_predicted_tonnes', 0):.1f}t, "
            f"prior {d.get('prior_predicted_tonnes', 0):.1f}t)"
            for d in deviations[:20]
        )
        dev_block = f"{len(deviations)} deviations detected:\n{dev_lines}"
    else:
        dev_block = "No significant deviations detected."

    if pending:
        pend_lines = "\n".join(
            f"  - [{p.get('urgency')}] {p.get('sku')} / {p.get('region')}: "
            f"{p.get('action_type')} — {p.get('description', '')[:120]}"
            for p in pending[:10]
        )
        pend_block = f"{len(pending)} pending actions:\n{pend_lines}"
    else:
        pend_block = "No pending supply actions."

    return f"""You are a chemical manufacturing supply-chain analytics assistant for AaiTech.

Answer the user's question using ONLY the data provided below.
Never invent numbers, SKU names, regions, or plant names not present in the data.
If the data does not contain enough information to answer, say so clearly.

=== CURRENT KPIs ===
{kpi_block}

=== FORECAST DEVIATIONS (latest pipeline run) ===
{dev_block}

=== PENDING SUPPLY ACTIONS ===
{pend_block}

Respond with a single JSON object and nothing else:
{{"answer": "your plain-language answer here, markdown allowed"}}"""


def run_chat(
    message: str,
    history: Optional[list[dict[str, str]]] = None,
    store_id: Optional[str] = None,
    store_name: Optional[str] = None,
) -> dict[str, Any]:
    """Answer a free-text chemical manufacturing question.

    Fetches live chemical context from Databricks, injects it into the system
    prompt, and makes a single LLM call — no tool-calling required, so it
    works with any model. Returns {"answer": str, "data": dict, "functions_used": list}.
    """

    ctx = _fetch_chemical_context()
    system_prompt = _build_system_prompt(ctx)

    # Build the user message, optionally prepending history as context
    history_text = ""
    for turn in (history or []):
        if turn.get("role") in ("user", "assistant") and turn.get("content"):
            history_text += f"{turn['role'].capitalize()}: {turn['content']}\n"

    user_message = f"{history_text}User: {message}" if history_text else message

    raw = call_chat_json(system_prompt, user_message)

    # Parse the answer
    answer = None
    try:
        parsed = json.loads(raw)
        if isinstance(parsed, dict) and isinstance(parsed.get("answer"), str):
            answer = parsed["answer"]
    except (json.JSONDecodeError, TypeError):
        pass

    if answer is None:
        # Try to extract from anywhere in the response
        match = re.search(r'"answer"\s*:\s*"((?:[^"\\]|\\.)*)"', raw or "")
        answer = match.group(1) if match else (raw or "I was unable to generate an answer.")

    return {
        "answer": answer,
        "data": ctx,
        "functions_used": [k for k, v in ctx.items() if v],
    }


def run_quick_action(action: str, params: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    raise ValueError(f"Unknown quick action: {action}")
