# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC ## Chem AI — Gold Feature Engineering

# COMMAND ----------

# MAGIC %md
# MAGIC ### Objective
# MAGIC
# MAGIC Build the ML-ready feature table `gold.demand_features` — one row per
# MAGIC (sku, region, customer_segment, week_start_date).
# MAGIC
# MAGIC **Key differences from retail feature engineering:**
# MAGIC - Weekly grain (not daily)
# MAGIC - Target column: `total_volume_tonnes` (not `units_sold`)
# MAGIC - Longer lag features: 4w, 8w, 12w, 52w (chemical demand has longer memory)
# MAGIC - External signal lag features: PMI_lag_4w, feedstock_lag_2w, freight_lag_1w
# MAGIC - Demand volatility feature: rolling coefficient of variation
# MAGIC - Grade seasonal index: volume / mean volume for that sku × month combination
# MAGIC - Capacity utilisation as a supply-side signal
# MAGIC
# MAGIC Feature catalogue:
# MAGIC
# MAGIC | Feature | Type | Description |
# MAGIC |---|---|---|
# MAGIC | lag_4w | numeric | Demand 4 weeks ago |
# MAGIC | lag_8w | numeric | Demand 8 weeks ago |
# MAGIC | lag_12w | numeric | Demand 12 weeks ago |
# MAGIC | lag_52w | numeric | Demand 52 weeks ago (YoY) |
# MAGIC | rolling_mean_4w | numeric | 4-week rolling mean demand |
# MAGIC | rolling_mean_13w | numeric | 13-week (quarter) rolling mean |
# MAGIC | rolling_std_4w | numeric | 4-week rolling standard deviation |
# MAGIC | rolling_volatility_4w | numeric | rolling_std_4w / rolling_mean_4w |
# MAGIC | trend_4w | numeric | rolling_mean_4w minus its value 4 weeks prior |
# MAGIC | yoy_growth_pct | numeric | % change vs same week last year |
# MAGIC | PMI_lag_4w | numeric | PMI_manufacturing from 4 weeks ago |
# MAGIC | PMI_lag_8w | numeric | PMI_manufacturing from 8 weeks ago |
# MAGIC | feedstock_lag_2w | numeric | Feedstock price index 2 weeks ago |
# MAGIC | freight_lag_1w | numeric | Freight index 1 week ago |
# MAGIC | grade_seasonal_index | numeric | Volume / mean volume for sku×month |
# MAGIC | capacity_utilisation_lag_1w | numeric | Last week's plant utilisation % |
# MAGIC | week_of_year | integer | 1–52 |
# MAGIC | month | integer | 1–12 |
# MAGIC | quarter | integer | 1–4 |
# MAGIC | dataset_split | string | train / validation / test |

# COMMAND ----------

# MAGIC %md
# MAGIC ### Imports and Configuration

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = "chem_ai"
SILVER_SCHEMA = "silver"
GOLD_SCHEMA = "gold"

# Time-based dataset split fractions (no random split — preserves temporal order)
TRAIN_FRAC  = 0.80
VAL_FRAC    = 0.10
# TEST_FRAC = remaining 10%

# COMMAND ----------

# MAGIC %md
# MAGIC ### Load Silver Tables

# COMMAND ----------

demand = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.demand_history")
signals = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.external_signals_clean")
capacity = spark.table(f"{CATALOG}.bronze.production_capacity")

print(f"demand_history:          {demand.count():,} rows")
print(f"external_signals_clean:  {signals.count():,} rows")
print(f"production_capacity:     {capacity.count():,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Join External Signals
# MAGIC
# MAGIC Join on (region, week_start_date). Signals are at region grain;
# MAGIC demand is at (sku, region, customer_segment) grain — a left join
# MAGIC fans out correctly.

# COMMAND ----------

signals_weekly = signals.withColumnRenamed("signal_date", "week_start_date")

df = demand.join(signals_weekly, on=["region", "week_start_date"], how="left")
print(f"After signal join: {df.count():,} rows")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Join Capacity Utilisation

# COMMAND ----------

capacity_agg = (
    capacity
    .groupBy("week_start_date", "sku")
    .agg(F.avg("actual_utilisation_pct").alias("capacity_utilisation_pct"))
)

df = df.join(capacity_agg, on=["sku", "week_start_date"], how="left")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Compute Lag and Rolling Features
# MAGIC
# MAGIC All window functions partition by (sku, region, customer_segment) and
# MAGIC order by week_start_date so features never leak across series.

# COMMAND ----------

w_series = (
    Window.partitionBy("sku", "region", "customer_segment")
    .orderBy("week_start_date")
)

# ── Lag features ──────────────────────────────────────────────────────────────
df = (
    df
    .withColumn("lag_4w",  F.lag("total_volume_tonnes",  4).over(w_series))
    .withColumn("lag_8w",  F.lag("total_volume_tonnes",  8).over(w_series))
    .withColumn("lag_12w", F.lag("total_volume_tonnes", 12).over(w_series))
    .withColumn("lag_52w", F.lag("total_volume_tonnes", 52).over(w_series))
)

# ── Rolling statistics ────────────────────────────────────────────────────────
w_4w  = w_series.rowsBetween(-3, 0)   # current week + 3 prior = 4 weeks
w_13w = w_series.rowsBetween(-12, 0)  # current week + 12 prior = 13 weeks

df = (
    df
    .withColumn("rolling_mean_4w",  F.avg("total_volume_tonnes").over(w_4w))
    .withColumn("rolling_mean_13w", F.avg("total_volume_tonnes").over(w_13w))
    .withColumn("rolling_std_4w",   F.stddev_pop("total_volume_tonnes").over(w_4w))
    .withColumn(
        "rolling_volatility_4w",
        F.when(
            F.col("rolling_mean_4w") > 0,
            F.col("rolling_std_4w") / F.col("rolling_mean_4w")
        ).otherwise(F.lit(0.0))
    )
)

# ── Demand trend: rolling_mean_4w vs 4 weeks prior ───────────────────────────
df = df.withColumn(
    "trend_4w",
    F.col("rolling_mean_4w") - F.lag("rolling_mean_4w", 4).over(w_series)
)

# ── YoY growth ────────────────────────────────────────────────────────────────
df = df.withColumn(
    "yoy_growth_pct",
    F.when(
        F.col("lag_52w").isNotNull() & (F.col("lag_52w") > 0),
        (F.col("total_volume_tonnes") - F.col("lag_52w")) / F.col("lag_52w") * 100
    ).otherwise(F.lit(None))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### External Signal Lag Features
# MAGIC
# MAGIC PMI leads chemical demand by ~4 weeks; feedstock price by ~2 weeks;
# MAGIC freight index by ~1 week.

# COMMAND ----------

w_region_time = Window.partitionBy("region").orderBy("week_start_date")

df = (
    df
    .withColumn("PMI_lag_4w",       F.lag("PMI_manufacturing",    4).over(w_series))
    .withColumn("PMI_lag_8w",       F.lag("PMI_manufacturing",    8).over(w_series))
    .withColumn("feedstock_lag_2w", F.lag("feedstock_price_index",2).over(w_series))
    .withColumn("freight_lag_1w",   F.lag("freight_index",        1).over(w_series))
)

# ── Capacity utilisation lag (1 week) ─────────────────────────────────────────
w_sku_time = Window.partitionBy("sku").orderBy("week_start_date")
df = df.withColumn(
    "capacity_utilisation_lag_1w",
    F.lag("capacity_utilisation_pct", 1).over(w_sku_time)
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Grade Seasonal Index
# MAGIC
# MAGIC Captures the typical monthly demand pattern per SKU.
# MAGIC Computed as: volume / mean(volume for this sku × month combination).

# COMMAND ----------

df = df.withColumn("month", F.month("week_start_date"))

monthly_mean = (
    df
    .groupBy("sku", "month")
    .agg(F.avg("total_volume_tonnes").alias("sku_month_mean"))
)

df = df.join(monthly_mean, on=["sku", "month"], how="left")
df = df.withColumn(
    "grade_seasonal_index",
    F.when(
        F.col("sku_month_mean") > 0,
        F.col("total_volume_tonnes") / F.col("sku_month_mean")
    ).otherwise(F.lit(1.0))
).drop("sku_month_mean")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Calendar Features

# COMMAND ----------

df = (
    df
    .withColumn("week_of_year", F.weekofyear("week_start_date"))
    .withColumn("quarter",      F.quarter("week_start_date"))
)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Time-Based Dataset Split
# MAGIC
# MAGIC Ordered by week_start_date per series. Train uses first 80%, validation
# MAGIC next 10%, test the final 10%. No random split — temporal order must be
# MAGIC preserved to avoid data leakage.

# COMMAND ----------

# Rank weeks globally (not per-series) so the split point is consistent
week_rank = (
    df.select("week_start_date").distinct()
    .withColumn("_rank", F.dense_rank().over(Window.orderBy("week_start_date")))
)
total_weeks = week_rank.count()
train_cutoff = int(total_weeks * TRAIN_FRAC)
val_cutoff   = int(total_weeks * (TRAIN_FRAC + VAL_FRAC))

week_rank = (
    week_rank
    .withColumn(
        "dataset_split",
        F.when(F.col("_rank") <= train_cutoff, "train")
         .when(F.col("_rank") <= val_cutoff,   "validation")
         .otherwise("test")
    )
    .drop("_rank")
)

df = df.join(week_rank, on="week_start_date", how="left")

print(f"Total unique weeks: {total_weeks}")
print(f"Train cutoff: week {train_cutoff}  |  Val cutoff: week {val_cutoff}")
df.groupBy("dataset_split").count().show()

# COMMAND ----------

# MAGIC %md
# MAGIC ### Write Gold Feature Table

# COMMAND ----------

feature_cols = [
    "week_start_date", "sku", "product_code", "product_grade",
    "region", "customer_segment", "plant_id",
    "total_volume_tonnes",
    # lag features
    "lag_4w", "lag_8w", "lag_12w", "lag_52w",
    # rolling features
    "rolling_mean_4w", "rolling_mean_13w", "rolling_std_4w",
    "rolling_volatility_4w", "trend_4w", "yoy_growth_pct",
    # external signal features
    "PMI_manufacturing", "PMI_lag_4w", "PMI_lag_8w",
    "feedstock_price_index", "feedstock_lag_2w",
    "freight_index", "freight_lag_1w",
    "consumer_confidence",
    # supply-side
    "capacity_utilisation_pct", "capacity_utilisation_lag_1w",
    # seasonal
    "grade_seasonal_index",
    # calendar
    "week_of_year", "month", "quarter",
    # split
    "dataset_split",
]

gold_features = df.select([c for c in feature_cols if c in df.columns])

gold_features.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{CATALOG}.{GOLD_SCHEMA}.demand_features"
)

print(f"Written: {CATALOG}.{GOLD_SCHEMA}.demand_features  ({gold_features.count():,} rows)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verification

# COMMAND ----------

spark.table(f"{CATALOG}.{GOLD_SCHEMA}.demand_features").describe(
    "total_volume_tonnes", "lag_4w", "PMI_lag_4w", "rolling_volatility_4w"
).show()

# COMMAND ----------
