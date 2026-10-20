# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC ## Chem AI — Model Training

# COMMAND ----------

# MAGIC %md
# MAGIC ### Objective
# MAGIC
# MAGIC Train a **single global LightGBM model** on `chem_ai.gold.demand_features`
# MAGIC to predict `total_volume_tonnes` per (sku, region, customer_segment, week).
# MAGIC
# MAGIC The global model shares learning across all SKU/region combinations
# MAGIC (e.g. "how PMI affects demand" generalises across product grades) while
# MAGIC `sku`, `region`, and `customer_segment` are categorical features so the
# MAGIC model still learns each series' distinct pattern.
# MAGIC
# MAGIC Steps:
# MAGIC 1. Load the Gold feature table; split by the pre-computed `dataset_split` column
# MAGIC 2. Establish a naive baseline (last 4-week average) — the model must beat this
# MAGIC 3. Train LightGBM with early stopping on the validation set
# MAGIC 4. Evaluate on validation and test (MAE / RMSE / MAPE / WAPE in tonnes)
# MAGIC 5. Log to MLflow; register in Unity Catalog Model Registry
# MAGIC 6. Promote to `Champion` alias only if it beats the current Champion on WAPE

# COMMAND ----------

# MAGIC %md
# MAGIC ### Imports and Configuration

# COMMAND ----------

!pip install lightgbm

# COMMAND ----------

import numpy as np
import pandas as pd
import lightgbm as lgb
import mlflow
from mlflow import MlflowClient

CATALOG = "chem_ai"
GOLD_SCHEMA = "gold"

MODEL_NAME        = f"{CATALOG}.{GOLD_SCHEMA}.demand_forecasting_lgbm"
EXPERIMENT_NAME   = "/Shared/chem_ai_demand_forecasting"
TARGET_COLUMN     = "total_volume_tonnes"

mlflow.set_registry_uri("databricks-uc")
mlflow.set_experiment(EXPERIMENT_NAME)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Load Gold Feature Table

# COMMAND ----------

gold_df = spark.table(f"{CATALOG}.{GOLD_SCHEMA}.demand_features").toPandas()
print(f"Total rows: {len(gold_df):,}")
print(f"Dataset split distribution:\n{gold_df['dataset_split'].value_counts()}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Feature and Target Definition

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

# Encode categoricals as category dtype for LightGBM
for col in CATEGORICAL_FEATURES:
    gold_df[col] = gold_df[col].astype("category")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Train / Validation / Test Split

# COMMAND ----------

train_df = gold_df[gold_df["dataset_split"] == "train"].dropna(subset=["lag_4w"])
val_df   = gold_df[gold_df["dataset_split"] == "validation"].dropna(subset=["lag_4w"])
test_df  = gold_df[gold_df["dataset_split"] == "test"].dropna(subset=["lag_4w"])

X_train, y_train = train_df[ALL_FEATURES], train_df[TARGET_COLUMN]
X_val,   y_val   = val_df[ALL_FEATURES],   val_df[TARGET_COLUMN]
X_test,  y_test  = test_df[ALL_FEATURES],  test_df[TARGET_COLUMN]

print(f"Train:      {len(X_train):,}  |  Val: {len(X_val):,}  |  Test: {len(X_test):,}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Naive Baseline (4-week rolling average)

# COMMAND ----------

def compute_metrics(y_true: pd.Series, y_pred: np.ndarray, label: str) -> dict:
    """Compute MAE, RMSE, MAPE (%), WAPE (%) — standard supply chain forecast metrics."""
    mae   = np.mean(np.abs(y_true - y_pred))
    rmse  = np.sqrt(np.mean((y_true - y_pred) ** 2))
    mape  = np.mean(np.abs((y_true - y_pred) / y_true.clip(lower=0.001))) * 100
    wape  = np.sum(np.abs(y_true - y_pred)) / np.sum(np.abs(y_true)) * 100
    print(f"  {label} — MAE: {mae:.2f}t  RMSE: {rmse:.2f}t  MAPE: {mape:.1f}%  WAPE: {wape:.1f}%")
    return {"mae": mae, "rmse": rmse, "mape": mape, "wape": wape}

# Baseline: use lag_4w as prediction
val_baseline   = val_df["lag_4w"].fillna(val_df["lag_4w"].median())
test_baseline  = test_df["lag_4w"].fillna(test_df["lag_4w"].median())

print("Naive baseline (lag_4w):")
baseline_val_metrics  = compute_metrics(y_val,  val_baseline.values,  "Validation")
baseline_test_metrics = compute_metrics(y_test, test_baseline.values, "Test      ")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Train LightGBM

# COMMAND ----------

lgb_params = {
    "objective":          "regression_l1",  # MAE loss — robust to volume outliers
    "metric":             ["mae", "rmse"],
    "learning_rate":      0.05,
    "num_leaves":         63,
    "min_child_samples":  20,
    "feature_fraction":   0.8,
    "bagging_fraction":   0.8,
    "bagging_freq":       5,
    "reg_alpha":          0.1,
    "reg_lambda":         0.1,
    "verbose":            -1,
}

train_data = lgb.Dataset(X_train, label=y_train, categorical_feature=CATEGORICAL_FEATURES)
val_data   = lgb.Dataset(X_val,   label=y_val,   categorical_feature=CATEGORICAL_FEATURES, reference=train_data)

with mlflow.start_run() as run:
    mlflow.log_params(lgb_params)
    mlflow.log_param("n_features", len(ALL_FEATURES))
    mlflow.log_param("train_rows", len(X_train))
    mlflow.log_param("target_column", TARGET_COLUMN)

    callbacks = [
        lgb.early_stopping(stopping_rounds=50, verbose=True),
        lgb.log_evaluation(period=50),
    ]

    model = lgb.train(
        lgb_params,
        train_data,
        num_boost_round=1000,
        valid_sets=[train_data, val_data],
        valid_names=["train", "validation"],
        callbacks=callbacks,
    )

    # ── Evaluate ──────────────────────────────────────────────────────────────
    val_preds  = model.predict(X_val,  num_iteration=model.best_iteration)
    test_preds = model.predict(X_test, num_iteration=model.best_iteration)

    print("\nLightGBM model:")
    val_metrics  = compute_metrics(y_val,  val_preds,  "Validation")
    test_metrics = compute_metrics(y_test, test_preds, "Test      ")

    for k, v in val_metrics.items():
        mlflow.log_metric(f"val_{k}", v)
    for k, v in test_metrics.items():
        mlflow.log_metric(f"test_{k}", v)
    mlflow.log_metric("best_iteration", model.best_iteration)

    # ── Log model ─────────────────────────────────────────────────────────────
    signature = mlflow.models.infer_signature(X_train, val_preds)
    mlflow.lightgbm.log_model(
        model,
        artifact_path="model",
        registered_model_name=MODEL_NAME,
        signature=signature,
    )

    run_id = run.info.run_id
    print(f"\nMLflow run_id: {run_id}")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Champion / Challenger Promotion
# MAGIC
# MAGIC Promote the new model to the `Champion` alias only if its test WAPE
# MAGIC is better (lower) than the current Champion. Otherwise it is registered
# MAGIC as a Candidate for manual review.

# COMMAND ----------

client = MlflowClient()

# Get the latest version just registered in this run
latest_versions = client.search_model_versions(f"name='{MODEL_NAME}'")
new_version = max(int(v.version) for v in latest_versions)
print(f"New model version: {new_version}  (test WAPE: {test_metrics['wape']:.1f}%)")

# Check if a Champion already exists
try:
    champion_mv = client.get_model_version_by_alias(MODEL_NAME, "Champion")
    champion_run = client.get_run(champion_mv.run_id)
    champion_wape = float(champion_run.data.metrics.get("test_wape", 999))
    print(f"Current Champion version: {champion_mv.version}  (test WAPE: {champion_wape:.1f}%)")
    has_champion = True
except Exception:
    has_champion = False
    print("No existing Champion found.")

if not has_champion or test_metrics["wape"] < champion_wape:
    client.set_registered_model_alias(MODEL_NAME, "Champion", new_version)
    print(f"Promoted version {new_version} to Champion.")
else:
    client.set_registered_model_alias(MODEL_NAME, "Candidate", new_version)
    print(f"New model did not beat Champion. Registered as Candidate for review.")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Save Evaluation Results to Gold

# COMMAND ----------

eval_rows = [
    {"model_name": MODEL_NAME, "model_version": str(new_version), "run_id": run_id,
     "dataset_split": "validation", **{k: float(v) for k, v in val_metrics.items()}},
    {"model_name": MODEL_NAME, "model_version": str(new_version), "run_id": run_id,
     "dataset_split": "test",       **{k: float(v) for k, v in test_metrics.items()}},
]
eval_df = spark.createDataFrame(pd.DataFrame(eval_rows))
eval_df.write.format("delta").mode("append").saveAsTable(f"{CATALOG}.{GOLD_SCHEMA}.model_evaluation_results")
print(f"Evaluation results saved to {CATALOG}.{GOLD_SCHEMA}.model_evaluation_results")

# COMMAND ----------
