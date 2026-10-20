# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC ## Chem AI — Batch Inference + Deviation Detection

# COMMAND ----------

# MAGIC %md
# MAGIC ### Objective
# MAGIC
# MAGIC Two stages in one notebook:
# MAGIC
# MAGIC **Stage 1 — Batch Inference:**
# MAGIC Load the Champion model from the Unity Catalog Model Registry, generate a
# MAGIC 4-week forward demand forecast per (sku, region, customer_segment), and
# MAGIC write the results to `gold.forecast_results`.
# MAGIC
# MAGIC **Stage 2 — Deviation Detection:**
# MAGIC Compare the current forecast to the prior run's forecast for the same
# MAGIC (sku, region, customer_segment, forecast_week_start) combinations.
# MAGIC Any series where `|deviation_pct| >= DEVIATION_THRESHOLD_PCT` is written
# MAGIC to `gold.forecast_deviations` — this is the table the backend agent reads.
# MAGIC
# MAGIC The deviation table is **overwritten** on each run so it always reflects
# MAGIC the current pipeline run's deviations, not an accumulation.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Imports and Configuration

# COMMAND ----------

import subprocess
subprocess.run(["pip", "install", "lightgbm", "--quiet"], check=True)

# COMMAND ----------

import uuid
from datetime import date, timedelta

import mlflow
import numpy as np
import pandas as pd
from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = "chem_ai"
GOLD_SCHEMA = "gold"

MODEL_NAME  = f"{CATALOG}.{GOLD_SCHEMA}.demand_forecasting_lgbm"
MODEL_ALIAS = "Champion"

# Configurable via Databricks job parameter (cluster/task env var)
DEVIATION_THRESHOLD_PCT = float(
    dbutils.widgets.get("deviation_threshold_pct")
    if "deviation_threshold_pct" in [w.name for w in dbutils.widgets.getAll()]
    else "10.0"
)
FORECAST_HORIZON_WEEKS = 4

mlflow.set_registry_uri("databricks-uc")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Demo Reset (one-time)
# MAGIC Set `RESET_PRIOR_FOR_DEMO = True` to drop the prior forecast table so the
# MAGIC seeding logic re-runs with the correct SKU baseline. Set back to `False`
# MAGIC after the first successful deviation-detection run.

# COMMAND ----------

RESET_PRIOR_FOR_DEMO = True

if RESET_PRIOR_FOR_DEMO:
    spark.sql(f"DROP TABLE IF EXISTS {CATALOG}.{GOLD_SCHEMA}.forecast_results_prior")
    print("Prior table dropped — seeding will run fresh this execution.")
else:
    print("Reset skipped — using existing prior table.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Stage 1: Batch Inference

# COMMAND ----------

# MAGIC %md
# MAGIC #### Load Champion Model

# COMMAND ----------

model_uri = f"models:/{MODEL_NAME}@{MODEL_ALIAS}"
model = mlflow.lightgbm.load_model(model_uri)
model_version = mlflow.MlflowClient().get_model_version_by_alias(MODEL_NAME, MODEL_ALIAS).version
run_id = str(uuid.uuid4())  # unique ID for this pipeline run

print(f"Loaded: {model_uri}  (version {model_version})")
print(f"This run_id: {run_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC #### Build Inference Dataset
# MAGIC
# MAGIC The feature table contains the full history. For inference we need to
# MAGIC construct feature rows for the next 4 weeks. We use the most recent
# MAGIC 52 rows per series to populate lag features, then project forward.

# COMMAND ----------

CATEGORICAL_FEATURES = ["sku", "product_code", "product_grade", "region", "customer_segment", "plant_id"]

NUMERIC_FEATURES = [
    "lag_4w", "lag_8w", "lag_12w", "lag_52w",
    "rolling_mean_4w", "rolling_mean_13w", "rolling_std_4w",
    "rolling_volatility_4w", "trend_4w", "yoy_growth_pct",
    "PMI_manufacturing", "PMI_lag_4w", "PMI_lag_8w",
    "feedstock_price_index", "feedstock_lag_2w",
    "freight_index", "freight_lag_1w",
    "consumer_confidence",
    "capacity_utilisation_pct", "capacity_utilisation_lag_1w",
    "grade_seasonal_index",
    "week_of_year", "month", "quarter",
]

ALL_FEATURES = NUMERIC_FEATURES + CATEGORICAL_FEATURES

# COMMAND ----------

# Load the full gold features for the most recent available data
gold_df = spark.table(f"{CATALOG}.{GOLD_SCHEMA}.demand_features").toPandas()

# Keep only the last 52 weeks per series (sufficient for all lag/rolling features)
w_recent = gold_df.groupby(["sku", "region", "customer_segment"])["week_start_date"].rank(
    method="first", ascending=False
)
latest_history = gold_df[w_recent <= 52].copy()

# Get the last known date per series
last_dates = (
    latest_history.groupby(["sku", "product_code", "product_grade", "region", "customer_segment", "plant_id"])
    ["week_start_date"].max().reset_index()
    .rename(columns={"week_start_date": "last_known_date"})
)
print(f"Series count: {len(last_dates):,}")

# COMMAND ----------

# Build inference rows: one row per series per forecast horizon week
today = date.today()
last_monday = today - timedelta(days=today.weekday())

inference_rows = []
for _, series in last_dates.iterrows():
    series_history = latest_history[
        (latest_history["sku"] == series["sku"])
        & (latest_history["region"] == series["region"])
        & (latest_history["customer_segment"] == series["customer_segment"])
    ].sort_values("week_start_date")

    for horizon in range(1, FORECAST_HORIZON_WEEKS + 1):
        forecast_week = last_monday + timedelta(weeks=horizon)

        # Use most recent row's features as a proxy for forward features
        # (In production, external signals would be fetched for future weeks)
        if len(series_history) == 0:
            continue

        last_row = series_history.iloc[-1].copy()
        last_row["week_start_date"] = pd.Timestamp(forecast_week)
        last_row["week_of_year"] = forecast_week.isocalendar()[1]
        last_row["month"] = forecast_week.month
        last_row["quarter"] = (forecast_week.month - 1) // 3 + 1

        # For lag features, use rolling actuals where available
        n = len(series_history)
        last_row["lag_4w"]  = series_history["total_volume_tonnes"].iloc[-4]  if n >= 4  else np.nan
        last_row["lag_8w"]  = series_history["total_volume_tonnes"].iloc[-8]  if n >= 8  else np.nan
        last_row["lag_12w"] = series_history["total_volume_tonnes"].iloc[-12] if n >= 12 else np.nan
        last_row["lag_52w"] = series_history["total_volume_tonnes"].iloc[-52] if n >= 52 else np.nan
        last_row["rolling_mean_4w"]  = series_history["total_volume_tonnes"].iloc[-4:].mean()
        last_row["rolling_mean_13w"] = series_history["total_volume_tonnes"].iloc[-13:].mean()

        inference_rows.append({
            "sku":              series["sku"],
            "product_code":     series["product_code"],
            "product_grade":    series["product_grade"],
            "region":           series["region"],
            "customer_segment": series["customer_segment"],
            "plant_id":         series["plant_id"],
            "forecast_week_start": str(forecast_week),
            "forecast_horizon_weeks": horizon,
            **{f: last_row.get(f, np.nan) for f in ALL_FEATURES},
        })

infer_df = pd.DataFrame(inference_rows)
for col in CATEGORICAL_FEATURES:
    infer_df[col] = infer_df[col].astype("category")

print(f"Inference rows: {len(infer_df):,}")

# COMMAND ----------

# Generate predictions
X_infer = infer_df[ALL_FEATURES]
predictions = model.predict(X_infer, num_iteration=model.best_iteration)
infer_df["predicted_volume_tonnes"] = np.maximum(0, predictions)

print(f"Predictions — min: {predictions.min():.2f}  max: {predictions.max():.2f}  mean: {predictions.mean():.2f}")

# COMMAND ----------

# MAGIC %md
# MAGIC #### Save to `gold.forecast_results`
# MAGIC
# MAGIC Before overwriting, snapshot the previous results for deviation detection.

# COMMAND ----------

forecast_results_table = f"{CATALOG}.{GOLD_SCHEMA}.forecast_results"
prior_table = f"{CATALOG}.{GOLD_SCHEMA}.forecast_results_prior"

# Snapshot current results as "prior" for deviation detection
if spark.catalog.tableExists(forecast_results_table):
    (
        spark.table(forecast_results_table)
        .write.format("delta").mode("overwrite").option("overwriteSchema", "true")
        .saveAsTable(prior_table)
    )
    print(f"Snapshotted prior forecast to {prior_table}")

result_cols = [
    "sku", "product_code", "product_grade", "region", "customer_segment", "plant_id",
    "forecast_week_start", "forecast_horizon_weeks", "predicted_volume_tonnes",
]

results_spark = (
    spark.createDataFrame(infer_df[result_cols])
    .withColumn("prediction_timestamp", F.current_timestamp())
    .withColumn("model_name",    F.lit(MODEL_NAME))
    .withColumn("model_version", F.lit(str(model_version)))
    .withColumn("pipeline_run_id", F.lit(run_id))
)

results_spark.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    forecast_results_table
)
print(f"Written: {forecast_results_table}  ({results_spark.count():,} rows)")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Stage 2: Deviation Detection
# MAGIC
# MAGIC Compare current forecast to prior forecast for overlapping
# MAGIC (sku, region, customer_segment, forecast_week_start) pairs.
# MAGIC Write significant deviations to `gold.forecast_deviations`.

# COMMAND ----------

if RESET_PRIOR_FOR_DEMO or not spark.catalog.tableExists(prior_table):
    # Seed a pre-shock baseline so deviation detection produces realistic deviations.
    # Simulates what the model would have predicted before the demand shock was observed:
    #   PROP-GLYCOL-USP / APAC  → 20% lower (the injected shock in the synthetic data)
    #   PROP-GLYCOL-USP / EMEA  → 10% lower (secondary spillover signal)
    print("Seeding pre-shock demo baseline as prior.")
    (
        spark.table(forecast_results_table)
        .withColumn(
            "predicted_volume_tonnes",
            F.when(
                (F.col("sku") == "PROP-GLYCOL-USP") & (F.col("region") == "APAC"),
                F.col("predicted_volume_tonnes") / F.lit(1.20)
            ).when(
                (F.col("sku") == "PROP-GLYCOL-USP") & (F.col("region") == "EMEA"),
                F.col("predicted_volume_tonnes") / F.lit(1.10)
            ).otherwise(F.col("predicted_volume_tonnes"))
        )
        .write.format("delta").mode("overwrite").option("overwriteSchema", "true")
        .saveAsTable(prior_table)
    )
    print(f"Seeded baseline prior to {prior_table}")

# COMMAND ----------

current = spark.table(forecast_results_table)
prior   = spark.table(prior_table)

join_keys = ["sku", "region", "customer_segment", "forecast_week_start"]

deviations = (
    current.alias("curr")
    .join(prior.alias("prior"), on=join_keys, how="inner")
    .withColumn(
        "deviation_pct",
        F.when(
            F.col("prior.predicted_volume_tonnes") > 0,
            (F.col("curr.predicted_volume_tonnes") - F.col("prior.predicted_volume_tonnes"))
            / F.col("prior.predicted_volume_tonnes") * 100
        ).otherwise(F.lit(None))
    )
    .withColumn(
        "direction",
        F.when(F.col("deviation_pct") > 0, F.lit("UP")).otherwise(F.lit("DOWN"))
    )
    .filter(F.abs(F.col("deviation_pct")) >= DEVIATION_THRESHOLD_PCT)
    .select(
        F.expr("uuid()").alias("deviation_id"),
        F.col("curr.sku"),
        F.col("curr.region"),
        F.col("curr.customer_segment"),
        F.col("curr.product_code"),
        F.col("curr.product_grade"),
        F.col("forecast_week_start"),
        F.col("deviation_pct"),
        F.col("direction"),
        F.col("curr.predicted_volume_tonnes").alias("current_predicted_tonnes"),
        F.col("prior.predicted_volume_tonnes").alias("prior_predicted_tonnes"),
        F.current_timestamp().alias("detection_timestamp"),
        F.lit(run_id).alias("model_run_id"),
    )
    .orderBy(F.abs(F.col("deviation_pct")).desc())
)

deviation_count = deviations.count()
print(f"Significant deviations (|deviation| >= {DEVIATION_THRESHOLD_PCT}%): {deviation_count}")

if deviation_count > 0:
    deviations.show(20, truncate=False)

deviations.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{CATALOG}.{GOLD_SCHEMA}.forecast_deviations"
)
print(f"Written: {CATALOG}.{GOLD_SCHEMA}.forecast_deviations")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Summary

# COMMAND ----------

print("=== Pipeline Run Summary ===")
print(f"run_id:               {run_id}")
print(f"model_version:        {model_version}")
print(f"forecast_rows:        {results_spark.count():,}")
print(f"deviations_detected:  {deviation_count}")
print(f"threshold_pct:        {DEVIATION_THRESHOLD_PCT}%")

# COMMAND ----------
