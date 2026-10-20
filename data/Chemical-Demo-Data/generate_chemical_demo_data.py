"""
Generates realistic synthetic chemical manufacturing demo data.

Run from the repo root:
    python data/Chemical-Demo-Data/generate_chemical_demo_data.py

Outputs 4 CSV files in the same directory as this script:
    order_transactions.csv
    inventory_levels.csv
    production_capacity.csv
    external_signals.csv

The data covers 104 weeks (2 years) ending at the current date.
A deliberate +20% demand shock is injected into PROP-GLYCOL/USP/APAC
in the final 4 weeks so the deviation detection agent has interesting
material to work with on first run.
"""

import math
import uuid
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

OUTPUT_DIR = Path(__file__).parent
SEED = 42
rng = np.random.default_rng(SEED)

# ── Domain constants ──────────────────────────────────────────────────────────

SKUS = [
    {"product_code": "ETH-OXIDE",   "product_grade": "INDUSTRIAL", "base_tpw": 120, "unit_price": 850},
    {"product_code": "ETH-OXIDE",   "product_grade": "PHARMA",     "base_tpw": 45,  "unit_price": 2100},
    {"product_code": "PROP-GLYCOL", "product_grade": "USP",        "base_tpw": 80,  "unit_price": 1650},
    {"product_code": "PROP-GLYCOL", "product_grade": "TECH",       "base_tpw": 200, "unit_price": 780},
    {"product_code": "CAUSTIC-SODA","product_grade": "MEMBRANE",   "base_tpw": 350, "unit_price": 420},
    {"product_code": "HCL-32PCT",   "product_grade": "INDUSTRIAL", "base_tpw": 90,  "unit_price": 310},
]

REGIONS = ["APAC", "EMEA", "AMER"]

# Regional demand split (sums to ~1 per SKU)
REGION_SPLIT = {"APAC": 0.40, "EMEA": 0.35, "AMER": 0.25}

CUSTOMER_SEGMENTS = ["BULK_CONTRACT", "SPOT", "PHARMA_OEM"]

# Segment demand split
SEGMENT_SPLIT = {
    "BULK_CONTRACT": 0.65,
    "SPOT":          0.25,
    "PHARMA_OEM":    0.10,
}

PLANTS = {
    "APAC": "PLANT_APAC_01",
    "EMEA": "PLANT_EMEA_01",
    "AMER": "PLANT_AMER_01",
}

WEEKS = 104  # 2 years of weekly data


# ── Date spine ────────────────────────────────────────────────────────────────

def _week_dates(n_weeks: int) -> list[date]:
    """Return a list of Monday dates for the last n_weeks weeks."""
    today = date.today()
    # Roll back to last Monday
    last_monday = today - timedelta(days=today.weekday())
    return [last_monday - timedelta(weeks=(n_weeks - 1 - i)) for i in range(n_weeks)]


WEEK_DATES = _week_dates(WEEKS)


# ── External signals ─────────────────────────────────────────────────────────

def generate_external_signals() -> pd.DataFrame:
    """
    Weekly external signals per region.

    PMI_manufacturing:   base 52, AR(1) mean-reverting process, range 44–58
    feedstock_price_index: base 100, random walk with upward drift, range 80–145
    freight_index:       base 100, correlated with feedstock (0.6), range 85–135
    consumer_confidence: base 98, slow mean-reversion
    """
    rows = []
    for region in REGIONS:
        pmi = 52.0
        feedstock = 100.0
        freight = 100.0
        confidence = 98.0

        for week_date in WEEK_DATES:
            # PMI: AR(1) with phi=0.85, noise=1.5
            pmi = 0.85 * pmi + 0.15 * 52.0 + rng.normal(0, 1.5)
            pmi = float(np.clip(pmi, 44, 58))

            # Feedstock: random walk, slight upward drift of 0.05%/week
            feedstock = feedstock * (1 + 0.0005 + rng.normal(0, 0.012))
            feedstock = float(np.clip(feedstock, 80, 145))

            # Freight: correlated with feedstock (0.6), own noise (0.4)
            freight_shock = 0.6 * (feedstock / 100 - 1) + 0.4 * rng.normal(0, 0.015)
            freight = 100.0 * (1 + freight_shock)
            freight = float(np.clip(freight, 85, 135))

            # Consumer confidence: slow AR(1)
            confidence = 0.95 * confidence + 0.05 * 98.0 + rng.normal(0, 0.8)
            confidence = float(np.clip(confidence, 90, 106))

            rows.append({
                "signal_date":            week_date.isoformat(),
                "region":                 region,
                "PMI_manufacturing":      round(pmi, 2),
                "feedstock_price_index":  round(feedstock, 2),
                "freight_index":          round(freight, 2),
                "consumer_confidence":    round(confidence, 2),
            })

    df = pd.DataFrame(rows)
    print(f"  external_signals:    {len(df):,} rows")
    return df


# ── Order transactions ────────────────────────────────────────────────────────

def generate_order_transactions(external_signals: pd.DataFrame) -> pd.DataFrame:
    """
    Weekly chemical order volumes per (product_code, product_grade, region,
    customer_segment). Each row is one synthetic order transaction.

    Demand drivers applied:
    - Base weekly volume from SKUS[base_tpw] × regional split × segment split
    - Seasonal multiplier: Q1 uplift (+15%) for construction/agriculture chemicals,
      Q3 slight dip (-8%) for EMEA in summer
    - PMI correlation: demand tracks PMI with a 4-week lag
    - Pharma grade is less volatile (σ=3%) than industrial (σ=12%)
    - PROP-GLYCOL/USP/APAC gets a +20% demand shock in the final 4 weeks
      (the trigger for the demo agent cycle)
    """

    # Build a PMI lookup keyed by (region, week_date) — 4-week lagged
    pmi_lookup: dict[tuple, float] = {}
    for region in REGIONS:
        region_pmi = (
            external_signals[external_signals["region"] == region]
            .sort_values("signal_date")["PMI_manufacturing"]
            .tolist()
        )
        for i, week_date in enumerate(WEEK_DATES):
            lag_idx = max(0, i - 4)
            pmi_lookup[(region, week_date.isoformat())] = region_pmi[lag_idx]

    rows = []
    for sku in SKUS:
        is_pharma = sku["product_grade"] in ("PHARMA", "USP")
        noise_sigma = 0.03 if is_pharma else 0.12

        for region in REGIONS:
            for segment in CUSTOMER_SEGMENTS:
                base_vol = (
                    sku["base_tpw"]
                    * REGION_SPLIT[region]
                    * SEGMENT_SPLIT[segment]
                )
                # Pharma OEM only applies to pharma-grade products
                if segment == "PHARMA_OEM" and not is_pharma:
                    base_vol = 0.0

                for week_idx, week_date in enumerate(WEEK_DATES):
                    if base_vol == 0.0:
                        continue

                    # Seasonal: Q1 (+15%), Q3 EMEA (-8%)
                    month = week_date.month
                    seasonal = 1.0
                    if month in (1, 2, 3):
                        seasonal = 1.15
                    elif month in (7, 8) and region == "EMEA":
                        seasonal = 0.92

                    # PMI influence: normalise PMI around 52 baseline
                    pmi_val = pmi_lookup.get((region, week_date.isoformat()), 52.0)
                    pmi_factor = 1.0 + 0.4 * (pmi_val - 52.0) / 52.0

                    # Demand shock: PROP-GLYCOL/USP/APAC final 4 weeks
                    shock = 1.0
                    if (
                        sku["product_code"] == "PROP-GLYCOL"
                        and sku["product_grade"] == "USP"
                        and region == "APAC"
                        and week_idx >= WEEKS - 4
                    ):
                        shock = 1.20

                    # Final volume with noise
                    vol = base_vol * seasonal * pmi_factor * shock
                    vol = max(0.1, vol * (1 + rng.normal(0, noise_sigma)))

                    # Spot orders: fewer in number but higher variance
                    n_orders = 1 if segment != "SPOT" else rng.integers(1, 4)
                    for _ in range(int(n_orders)):
                        order_vol = vol / n_orders * (1 + rng.normal(0, 0.05))
                        # Price: base + feedstock noise
                        price_noise = 1 + rng.normal(0, 0.04)
                        spot_premium = 1.08 if segment == "SPOT" else 1.0

                        rows.append({
                            "transaction_id":  str(uuid.uuid4()),
                            "order_date":      week_date.isoformat(),
                            "product_code":    sku["product_code"],
                            "product_grade":   sku["product_grade"],
                            "sku":             f"{sku['product_code']}-{sku['product_grade']}",
                            "customer_id":     f"CUST_{region}_{segment[:4]}_{rng.integers(1,20):03d}",
                            "customer_segment":segment,
                            "region":          region,
                            "plant_id":        PLANTS[region],
                            "volume_tonnes":   round(max(0.1, order_vol), 3),
                            "unit_price_usd":  round(sku["unit_price"] * price_noise * spot_premium, 2),
                            "order_type":      "SPOT" if segment == "SPOT" else "CONTRACT",
                        })

    df = pd.DataFrame(rows)
    print(f"  order_transactions:  {len(df):,} rows")
    return df


# ── Inventory levels ──────────────────────────────────────────────────────────

def generate_inventory_levels(order_transactions: pd.DataFrame) -> pd.DataFrame:
    """
    Weekly inventory snapshot per (plant_id, sku).

    Inventory dynamics:
    - Starts at 6 weeks of average demand
    - Decreases by that week's shipment volume
    - Replenishment order arrives every 3 weeks (lead time = 2 weeks)
    - Shelf life: PHARMA/USP grades = 180 days; INDUSTRIAL/TECH = 365 days
    - Occasional deliberate low-stock events (at weeks 20, 55, 85)
    """
    # Weekly demand per (plant, sku)
    weekly_demand = (
        order_transactions
        .groupby(["order_date", "plant_id", "sku"])["volume_tonnes"]
        .sum()
        .reset_index()
        .rename(columns={"volume_tonnes": "weekly_volume"})
    )

    rows = []
    for plant in PLANTS.values():
        for sku_def in SKUS:
            sku = f"{sku_def['product_code']}-{sku_def['product_grade']}"
            is_pharma = sku_def["product_grade"] in ("PHARMA", "USP")
            shelf_life_days = 180 if is_pharma else 365

            # Average weekly demand for this plant/sku
            mask = (weekly_demand["plant_id"] == plant) & (weekly_demand["sku"] == sku)
            avg_demand = weekly_demand.loc[mask, "weekly_volume"].mean()
            if math.isnan(avg_demand) or avg_demand == 0:
                avg_demand = sku_def["base_tpw"] * REGION_SPLIT["APAC"] * 0.3

            stock = avg_demand * 6  # start at 6 weeks cover
            reorder_point = avg_demand * 3

            for week_idx, week_date in enumerate(WEEK_DATES):
                # Shipment this week
                row_mask = (
                    (weekly_demand["order_date"] == week_date.isoformat())
                    & (weekly_demand["plant_id"] == plant)
                    & (weekly_demand["sku"] == sku)
                )
                shipment = weekly_demand.loc[row_mask, "weekly_volume"].sum()
                stock = max(0.0, stock - shipment)

                # Replenishment every 3 weeks (2-week lead time)
                if week_idx % 3 == 0:
                    replenish = avg_demand * 4.5 * (1 + rng.normal(0, 0.05))
                    stock += max(0, replenish)

                # Deliberate low-stock events for demo realism
                if week_idx in (20, 55, 85):
                    stock = avg_demand * 1.5  # ~1.5 weeks cover

                # In-transit estimate: ~30% of weekly demand
                in_transit = avg_demand * 0.3 * (1 + rng.normal(0, 0.1))

                # Shelf life remaining: degrades by 7 days per week
                shelf_remaining = max(
                    14,
                    shelf_life_days - (week_idx % (shelf_life_days // 7)) * 7
                )

                rows.append({
                    "snapshot_date":            week_date.isoformat(),
                    "plant_id":                 plant,
                    "sku":                      sku,
                    "product_code":             sku_def["product_code"],
                    "product_grade":            sku_def["product_grade"],
                    "stock_on_hand_tonnes":     round(max(0, stock), 3),
                    "stock_in_transit_tonnes":  round(max(0, in_transit), 3),
                    "reorder_point_tonnes":     round(reorder_point, 3),
                    "shelf_life_remaining_days": int(shelf_remaining),
                })

    df = pd.DataFrame(rows)
    print(f"  inventory_levels:    {len(df):,} rows")
    return df


# ── Production capacity ───────────────────────────────────────────────────────

def generate_production_capacity(order_transactions: pd.DataFrame) -> pd.DataFrame:
    """
    Weekly production capacity per (plant_id, sku).

    - Planned capacity: constant per quarter, set at 110% of average demand
    - Actual utilisation: 65–95% with Q4 higher (year-end fill)
    - Changeover days: 0–3 days/week (sequence-dependent, random)
    """
    weekly_demand = (
        order_transactions
        .groupby(["order_date", "plant_id", "sku"])["volume_tonnes"]
        .sum()
        .reset_index()
        .rename(columns={"volume_tonnes": "weekly_volume"})
    )

    rows = []
    for plant in PLANTS.values():
        for sku_def in SKUS:
            sku = f"{sku_def['product_code']}-{sku_def['product_grade']}"

            mask = (weekly_demand["plant_id"] == plant) & (weekly_demand["sku"] == sku)
            avg_demand = weekly_demand.loc[mask, "weekly_volume"].mean()
            if math.isnan(avg_demand) or avg_demand == 0:
                avg_demand = sku_def["base_tpw"] * REGION_SPLIT["APAC"] * 0.3

            planned_capacity = avg_demand * 1.10

            for week_idx, week_date in enumerate(WEEK_DATES):
                # Quarterly capacity updates (slight variation)
                quarter_idx = week_idx // 13
                quarterly_factor = 1.0 + rng.normal(0, 0.03)
                planned = planned_capacity * quarterly_factor

                # Utilisation: base 78%, higher in Q4 (Oct–Dec)
                base_util = 0.88 if week_date.month in (10, 11, 12) else 0.78
                util = float(np.clip(rng.normal(base_util, 0.07), 0.55, 0.98))

                actual_volume = planned * util

                # Changeover days: 0-3, weighted toward 0
                changeover = int(rng.choice([0, 1, 2, 3], p=[0.55, 0.25, 0.15, 0.05]))

                rows.append({
                    "week_start_date":        week_date.isoformat(),
                    "plant_id":               plant,
                    "sku":                    sku,
                    "product_code":           sku_def["product_code"],
                    "product_grade":          sku_def["product_grade"],
                    "planned_capacity_tonnes":round(planned, 3),
                    "actual_volume_tonnes":   round(actual_volume, 3),
                    "actual_utilisation_pct": round(util * 100, 1),
                    "changeover_days":        changeover,
                })

    df = pd.DataFrame(rows)
    print(f"  production_capacity: {len(df):,} rows")
    return df


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    print("Generating chemical manufacturing demo data...")
    print(f"  Weeks: {WEEKS} ({WEEK_DATES[0]} → {WEEK_DATES[-1]})")
    print(f"  SKUs: {len(SKUS)}  Regions: {len(REGIONS)}  Segments: {len(CUSTOMER_SEGMENTS)}")
    print()

    external_signals = generate_external_signals()
    order_transactions = generate_order_transactions(external_signals)
    inventory_levels = generate_inventory_levels(order_transactions)
    production_capacity = generate_production_capacity(order_transactions)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    external_signals.to_csv(OUTPUT_DIR / "external_signals.csv", index=False)
    order_transactions.to_csv(OUTPUT_DIR / "order_transactions.csv", index=False)
    inventory_levels.to_csv(OUTPUT_DIR / "inventory_levels.csv", index=False)
    production_capacity.to_csv(OUTPUT_DIR / "production_capacity.csv", index=False)

    print()
    print("Done. Files written to:", OUTPUT_DIR)
    print()
    print("Demand shock verification (PROP-GLYCOL/USP/APAC, final 4 weeks):")
    shock_rows = order_transactions[
        (order_transactions["product_code"] == "PROP-GLYCOL")
        & (order_transactions["product_grade"] == "USP")
        & (order_transactions["region"] == "APAC")
    ].groupby("order_date")["volume_tonnes"].sum().tail(8)
    print(shock_rows.to_string())


if __name__ == "__main__":
    main()
