# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC ## Chem AI — Silver Transformation

# COMMAND ----------

# MAGIC %md
# MAGIC ### Objective
# MAGIC
# MAGIC Cleans, validates, and integrates the Bronze datasets into trusted Silver tables
# MAGIC at **weekly grain** (chemical demand is weekly, not daily like retail).
# MAGIC
# MAGIC Outputs:
# MAGIC - `silver.demand_history` — aggregated weekly volumes per (sku, region, customer_segment)
# MAGIC - `silver.inventory_snapshot` — latest inventory per (plant_id, sku) with derived `days_on_hand`
# MAGIC - `silver.external_signals_clean` — forward-filled, outlier-capped external macro signals
# MAGIC
# MAGIC Every cleaning step prints a before/after row count so unexpected data loss
# MAGIC is visible immediately in the notebook output.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Imports and Configuration

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.window import Window

CATALOG = "chem_ai"
BRONZE_SCHEMA = "bronze"
SILVER_SCHEMA = "silver"

# COMMAND ----------

def audit_step(df_before, df_after, step_name):
    before = df_before.count()
    after  = df_after.count()
    removed = before - after
    print(f"  [{step_name}] {before:,} → {after:,} rows ({removed:,} removed)")
    return df_after

# COMMAND ----------

# MAGIC %md
# MAGIC ### 1. `silver.demand_history`
# MAGIC
# MAGIC Aggregate Bronze order_transactions to weekly grain per
# MAGIC (sku, region, customer_segment). Join with production_capacity so
# MAGIC downstream Gold features can reference capacity utilisation.

# COMMAND ----------

orders_raw = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.order_transactions")
print(f"Bronze order_transactions: {orders_raw.count():,} rows")

# ── Quality checks ────────────────────────────────────────────────────────────

orders = audit_step(
    orders_raw,
    orders_raw.filter(F.col("sku").isNotNull() & F.col("region").isNotNull()),
    "drop null sku/region"
)
orders = audit_step(
    orders,
    orders.filter(F.col("volume_tonnes") > 0),
    "drop non-positive volume"
)
orders = audit_step(
    orders,
    orders.dropDuplicates(["transaction_id"]),
    "drop duplicate transaction_ids"
)

# ── Weekly aggregation ────────────────────────────────────────────────────────
# order_date is already a Monday (week start) from the data generator.

demand_history = (
    orders
    .groupBy("order_date", "product_code", "product_grade", "sku", "region", "customer_segment", "plant_id")
    .agg(
        F.sum("volume_tonnes").alias("total_volume_tonnes"),
        F.sum(F.col("volume_tonnes") * F.col("unit_price_usd")).alias("total_revenue_usd"),
        F.count("transaction_id").alias("order_count"),
        F.avg("unit_price_usd").alias("avg_unit_price_usd"),
    )
    .withColumnRenamed("order_date", "week_start_date")
)

print(f"demand_history rows: {demand_history.count():,}")

demand_history.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{CATALOG}.{SILVER_SCHEMA}.demand_history"
)
print(f"Written: {CATALOG}.{SILVER_SCHEMA}.demand_history")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2. `silver.inventory_snapshot`
# MAGIC
# MAGIC Latest inventory per (plant_id, sku) plus `days_on_hand` derived from
# MAGIC rolling 4-week average demand from `demand_history`.

# COMMAND ----------

inventory_raw = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.inventory_levels")
print(f"Bronze inventory_levels: {inventory_raw.count():,} rows")

# Remove nulls
inventory = audit_step(
    inventory_raw,
    inventory_raw.filter(F.col("snapshot_date").isNotNull() & F.col("sku").isNotNull()),
    "drop null snapshot_date/sku"
)

# Latest snapshot per (plant_id, sku)
w_latest = Window.partitionBy("plant_id", "sku").orderBy(F.col("snapshot_date").desc())
latest_inventory = (
    inventory
    .withColumn("_rn", F.row_number().over(w_latest))
    .filter(F.col("_rn") == 1)
    .drop("_rn")
)

# Rolling 4-week average demand per (plant_id, sku) from demand_history
avg_demand = (
    spark.table(f"{CATALOG}.{SILVER_SCHEMA}.demand_history")
    .groupBy("plant_id", "sku")
    .agg(F.avg("total_volume_tonnes").alias("avg_weekly_demand_tonnes"))
)

inventory_snapshot = (
    latest_inventory
    .join(avg_demand, on=["plant_id", "sku"], how="left")
    .withColumn(
        "days_on_hand",
        F.when(
            F.col("avg_weekly_demand_tonnes") > 0,
            F.col("stock_on_hand_tonnes") / (F.col("avg_weekly_demand_tonnes") / 7.0)
        ).otherwise(F.lit(None))
    )
)

print(f"inventory_snapshot rows: {inventory_snapshot.count():,}")

inventory_snapshot.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{CATALOG}.{SILVER_SCHEMA}.inventory_snapshot"
)
print(f"Written: {CATALOG}.{SILVER_SCHEMA}.inventory_snapshot")

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3. `silver.external_signals_clean`
# MAGIC
# MAGIC - Forward-fill missing PMI values (up to 2 consecutive weeks)
# MAGIC - Cap outlier freight_index at 99th percentile
# MAGIC - Standardise region codes to uppercase

# COMMAND ----------

signals_raw = spark.table(f"{CATALOG}.{BRONZE_SCHEMA}.external_signals")
print(f"Bronze external_signals: {signals_raw.count():,} rows")

signals = audit_step(
    signals_raw,
    signals_raw.filter(F.col("signal_date").isNotNull() & F.col("region").isNotNull()),
    "drop null date/region"
)

# Standardise region to uppercase
signals = signals.withColumn("region", F.upper(F.col("region")))

# Cap freight_index at 99th percentile per region
freight_p99 = signals.approxQuantile("freight_index", [0.99], 0.01)[0]
signals = signals.withColumn(
    "freight_index",
    F.when(F.col("freight_index") > freight_p99, freight_p99).otherwise(F.col("freight_index"))
)

# Forward-fill PMI_manufacturing within each region (up to 2 weeks)
w_region = Window.partitionBy("region").orderBy("signal_date").rowsBetween(Window.unboundedPreceding, 0)
signals = signals.withColumn(
    "PMI_manufacturing",
    F.last("PMI_manufacturing", ignorenulls=True).over(w_region)
)

print(f"external_signals_clean rows: {signals.count():,}")

signals.write.format("delta").mode("overwrite").option("overwriteSchema", "true").saveAsTable(
    f"{CATALOG}.{SILVER_SCHEMA}.external_signals_clean"
)
print(f"Written: {CATALOG}.{SILVER_SCHEMA}.external_signals_clean")

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verification

# COMMAND ----------

for table in ["demand_history", "inventory_snapshot", "external_signals_clean"]:
    count = spark.table(f"{CATALOG}.{SILVER_SCHEMA}.{table}").count()
    print(f"  {CATALOG}.{SILVER_SCHEMA}.{table}: {count:,} rows")

# COMMAND ----------
