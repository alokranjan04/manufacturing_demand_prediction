# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC ## Chem AI — Bronze Layer: Data Ingestion

# COMMAND ----------

# MAGIC %md
# MAGIC ### Objective
# MAGIC
# MAGIC This notebook loads raw CSV files from the Unity Catalog Volume into
# MAGIC Bronze Delta tables using an idempotent merge pattern.
# MAGIC
# MAGIC Four datasets are ingested:
# MAGIC
# MAGIC - **`order_transactions`** — weekly chemical order volumes per SKU/region/customer segment
# MAGIC - **`inventory_levels`** — weekly inventory snapshots per plant/SKU
# MAGIC - **`production_capacity`** — weekly planned and actual capacity per plant/SKU
# MAGIC - **`external_signals`** — weekly macro indicators (PMI, feedstock price, freight index) per region
# MAGIC
# MAGIC All four tables use `MERGE INTO` (upsert) so re-running this notebook is
# MAGIC always safe — no duplicate rows are created on subsequent runs.

# COMMAND ----------

# MAGIC %md
# MAGIC ### Imports and Configuration

# COMMAND ----------

from pyspark.sql import functions as F
from pyspark.sql.types import (
    StructType, StructField,
    StringType, DoubleType, IntegerType, DateType, TimestampType
)
from delta.tables import DeltaTable

CATALOG = "chem_ai"
BRONZE_SCHEMA = "bronze"

RAW_PATH = f"/Volumes/{CATALOG}/{BRONZE_SCHEMA}/raw_files"
INCOMING_PATH = f"{RAW_PATH}/incoming"
PROCESSED_PATH = f"{INCOMING_PATH}/processed"

dbutils.fs.mkdirs(INCOMING_PATH)
dbutils.fs.mkdirs(PROCESSED_PATH)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Helper Functions

# COMMAND ----------

def read_csv_with_schema(path, schema):
    """Read a CSV from the volume, enforcing a schema and trimming whitespace."""
    return (
        spark.read.format("csv")
        .option("header", "true")
        .option("mode", "PERMISSIVE")
        .schema(schema)
        .load(path)
        .select([F.trim(F.col(c)).alias(c) if t == "string" else F.col(c)
                 for c, t in [(f.name, f.dataType.simpleString()) for f in schema.fields]])
    )


def list_incoming_files(prefix):
    """Return a list of volume paths for files in INCOMING_PATH whose
    filename starts with `prefix` (case-insensitive)."""
    try:
        all_files = dbutils.fs.ls(INCOMING_PATH)
    except Exception:
        return []
    return [
        f.path for f in all_files
        if f.name.lower().startswith(prefix.lower()) and f.name.endswith(".csv")
    ]


def archive_file(path):
    """Move a processed file to the processed/ subfolder."""
    filename = path.split("/")[-1]
    dbutils.fs.mv(path, f"{PROCESSED_PATH}/{filename}")
    print(f"  Archived: {filename}")


# COMMAND ----------

# MAGIC %md
# MAGIC ### 1. Order Transactions
# MAGIC
# MAGIC Incremental: new files land in `incoming/` with prefix `order_transactions`.
# MAGIC Merged on `transaction_id`.

# COMMAND ----------

ORDER_TRANSACTIONS_SCHEMA = StructType([
    StructField("transaction_id",   StringType(),  True),
    StructField("order_date",       DateType(),    True),
    StructField("product_code",     StringType(),  True),
    StructField("product_grade",    StringType(),  True),
    StructField("sku",              StringType(),  True),
    StructField("customer_id",      StringType(),  True),
    StructField("customer_segment", StringType(),  True),
    StructField("region",           StringType(),  True),
    StructField("plant_id",         StringType(),  True),
    StructField("volume_tonnes",    DoubleType(),  True),
    StructField("unit_price_usd",   DoubleType(),  True),
    StructField("order_type",       StringType(),  True),
])

order_files = list_incoming_files("order_transactions")
print(f"Order transaction files found: {len(order_files)}")

if order_files:
    new_orders = (
        spark.read.format("csv")
        .option("header", "true")
        .schema(ORDER_TRANSACTIONS_SCHEMA)
        .load(order_files)
        .filter(F.col("transaction_id").isNotNull())
        .filter(F.col("volume_tonnes") > 0)
        .withColumn("_ingested_at", F.current_timestamp())
    )
    print(f"  Rows to merge: {new_orders.count():,}")

    target_table = f"{CATALOG}.{BRONZE_SCHEMA}.order_transactions"

    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        delta_target.alias("target").merge(
            new_orders.alias("source"),
            "target.transaction_id = source.transaction_id"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
        print(f"  Merged into {target_table}")
    else:
        new_orders.write.format("delta").saveAsTable(target_table)
        print(f"  Created {target_table}")

    for f in order_files:
        archive_file(f)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 2. Inventory Levels
# MAGIC
# MAGIC Merged on `(snapshot_date, plant_id, sku)`.

# COMMAND ----------

INVENTORY_SCHEMA = StructType([
    StructField("snapshot_date",             DateType(),    True),
    StructField("plant_id",                  StringType(),  True),
    StructField("sku",                       StringType(),  True),
    StructField("product_code",              StringType(),  True),
    StructField("product_grade",             StringType(),  True),
    StructField("stock_on_hand_tonnes",      DoubleType(),  True),
    StructField("stock_in_transit_tonnes",   DoubleType(),  True),
    StructField("reorder_point_tonnes",      DoubleType(),  True),
    StructField("shelf_life_remaining_days", IntegerType(), True),
])

inventory_files = list_incoming_files("inventory_levels")
print(f"Inventory level files found: {len(inventory_files)}")

if inventory_files:
    new_inventory = (
        spark.read.format("csv")
        .option("header", "true")
        .schema(INVENTORY_SCHEMA)
        .load(inventory_files)
        .filter(F.col("snapshot_date").isNotNull())
        .filter(F.col("sku").isNotNull())
        .withColumn("_ingested_at", F.current_timestamp())
    )
    print(f"  Rows to merge: {new_inventory.count():,}")

    target_table = f"{CATALOG}.{BRONZE_SCHEMA}.inventory_levels"

    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        delta_target.alias("target").merge(
            new_inventory.alias("source"),
            "target.snapshot_date = source.snapshot_date "
            "AND target.plant_id = source.plant_id "
            "AND target.sku = source.sku"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
        print(f"  Merged into {target_table}")
    else:
        new_inventory.write.format("delta").saveAsTable(target_table)
        print(f"  Created {target_table}")

    for f in inventory_files:
        archive_file(f)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 3. Production Capacity
# MAGIC
# MAGIC Merged on `(week_start_date, plant_id, sku)`.

# COMMAND ----------

CAPACITY_SCHEMA = StructType([
    StructField("week_start_date",          DateType(),    True),
    StructField("plant_id",                 StringType(),  True),
    StructField("sku",                      StringType(),  True),
    StructField("product_code",             StringType(),  True),
    StructField("product_grade",            StringType(),  True),
    StructField("planned_capacity_tonnes",  DoubleType(),  True),
    StructField("actual_volume_tonnes",     DoubleType(),  True),
    StructField("actual_utilisation_pct",   DoubleType(),  True),
    StructField("changeover_days",          IntegerType(), True),
])

capacity_files = list_incoming_files("production_capacity")
print(f"Production capacity files found: {len(capacity_files)}")

if capacity_files:
    new_capacity = (
        spark.read.format("csv")
        .option("header", "true")
        .schema(CAPACITY_SCHEMA)
        .load(capacity_files)
        .filter(F.col("week_start_date").isNotNull())
        .withColumn("_ingested_at", F.current_timestamp())
    )
    print(f"  Rows to merge: {new_capacity.count():,}")

    target_table = f"{CATALOG}.{BRONZE_SCHEMA}.production_capacity"

    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        delta_target.alias("target").merge(
            new_capacity.alias("source"),
            "target.week_start_date = source.week_start_date "
            "AND target.plant_id = source.plant_id "
            "AND target.sku = source.sku"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
        print(f"  Merged into {target_table}")
    else:
        new_capacity.write.format("delta").saveAsTable(target_table)
        print(f"  Created {target_table}")

    for f in capacity_files:
        archive_file(f)

# COMMAND ----------

# MAGIC %md
# MAGIC ### 4. External Signals
# MAGIC
# MAGIC Merged on `(signal_date, region)`.

# COMMAND ----------

EXTERNAL_SIGNALS_SCHEMA = StructType([
    StructField("signal_date",           DateType(),   True),
    StructField("region",                StringType(), True),
    StructField("PMI_manufacturing",     DoubleType(), True),
    StructField("feedstock_price_index", DoubleType(), True),
    StructField("freight_index",         DoubleType(), True),
    StructField("consumer_confidence",   DoubleType(), True),
])

signal_files = list_incoming_files("external_signals")
print(f"External signal files found: {len(signal_files)}")

if signal_files:
    new_signals = (
        spark.read.format("csv")
        .option("header", "true")
        .schema(EXTERNAL_SIGNALS_SCHEMA)
        .load(signal_files)
        .filter(F.col("signal_date").isNotNull())
        .filter(F.col("region").isNotNull())
        .withColumn("_ingested_at", F.current_timestamp())
    )
    print(f"  Rows to merge: {new_signals.count():,}")

    target_table = f"{CATALOG}.{BRONZE_SCHEMA}.external_signals"

    if spark.catalog.tableExists(target_table):
        delta_target = DeltaTable.forName(spark, target_table)
        delta_target.alias("target").merge(
            new_signals.alias("source"),
            "target.signal_date = source.signal_date "
            "AND target.region = source.region"
        ).whenMatchedUpdateAll().whenNotMatchedInsertAll().execute()
        print(f"  Merged into {target_table}")
    else:
        new_signals.write.format("delta").saveAsTable(target_table)
        print(f"  Created {target_table}")

    for f in signal_files:
        archive_file(f)

# COMMAND ----------

# MAGIC %md
# MAGIC ### Verification

# COMMAND ----------

for table in ["order_transactions", "inventory_levels", "production_capacity", "external_signals"]:
    full_name = f"{CATALOG}.{BRONZE_SCHEMA}.{table}"
    if spark.catalog.tableExists(full_name):
        count = spark.table(full_name).count()
        print(f"  {full_name}: {count:,} rows")
    else:
        print(f"  {full_name}: NOT FOUND (no files were uploaded yet)")

# COMMAND ----------
