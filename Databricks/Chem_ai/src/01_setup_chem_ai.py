# Databricks notebook source
# /// script
# [tool.databricks.environment]
# environment_version = "5"
# ///
# MAGIC %md
# MAGIC # Chem AI — Databricks Environment Setup
# MAGIC
# MAGIC This notebook initializes the Databricks environment for the
# MAGIC **Chemical Manufacturing AI Platform** (Demand & Distribution Intelligence).
# MAGIC
# MAGIC ### Objectives
# MAGIC
# MAGIC - Create the project catalog (`chem_ai`)
# MAGIC - Create Medallion Architecture schemas (bronze / silver / gold)
# MAGIC - Create a Volume for raw CSV files
# MAGIC - Create the agent operational tables (recommendations + audit log)
# MAGIC - Verify the created resources

# COMMAND ----------

# MAGIC %md
# MAGIC ## 1. Create Catalog

# COMMAND ----------

# spark and dbutils are Databricks built-in globals — injected by the runtime.
# The "not defined" IDE warnings below are false positives; safe to ignore.

spark.sql("CREATE CATALOG IF NOT EXISTS chem_ai")
print("Catalog: chem_ai — OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 2. Create Medallion Architecture Schemas
# MAGIC
# MAGIC | Schema | Purpose |
# MAGIC |--------|---------|
# MAGIC | `bronze` | Raw ingested data, minimal transformation |
# MAGIC | `silver` | Cleaned, validated, weekly-grain data |
# MAGIC | `gold`   | ML features, forecasts, deviations, agent tables |

# COMMAND ----------

spark.sql("CREATE SCHEMA IF NOT EXISTS chem_ai.bronze")
spark.sql("CREATE SCHEMA IF NOT EXISTS chem_ai.silver")
spark.sql("CREATE SCHEMA IF NOT EXISTS chem_ai.gold")
print("Schemas: bronze, silver, gold — OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 3. Create Raw Data Volume
# MAGIC
# MAGIC Raw CSV files are uploaded here and then consumed by the Bronze ingestion notebook.

# COMMAND ----------

spark.sql("CREATE VOLUME IF NOT EXISTS chem_ai.bronze.raw_files")
print("Volume: chem_ai.bronze.raw_files — OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 4. Create Agent Operational Tables
# MAGIC
# MAGIC ### `agent_recommendations`
# MAGIC One row per agent-generated recommendation, progressing through
# MAGIC `PENDING` → `APPROVED` / `REJECTED`.
# MAGIC
# MAGIC ### `agent_audit_log`
# MAGIC Immutable append-only log of every event (CREATED, APPROVED, REJECTED).

# COMMAND ----------

spark.sql("""
CREATE TABLE IF NOT EXISTS chem_ai.gold.agent_recommendations (
    id                          STRING        NOT NULL,
    sku                         STRING        NOT NULL,
    region                      STRING        NOT NULL,
    customer_segment            STRING,
    deviation_pct               DOUBLE,
    direction                   STRING,
    inventory_days_on_hand      DOUBLE,
    capacity_utilisation_pct    DOUBLE,
    supplier_lead_time_days     INT,
    action_type                 STRING,
    description                 STRING,
    urgency                     STRING,
    quantity_adjustment_tonnes  DOUBLE,
    affected_plants             ARRAY<STRING>,
    status                      STRING        NOT NULL DEFAULT 'PENDING',
    approver                    STRING,
    rejection_reason            STRING,
    created_at                  TIMESTAMP     NOT NULL DEFAULT current_timestamp(),
    decided_at                  TIMESTAMP,
    model_run_id                STRING
)
USING DELTA
TBLPROPERTIES (
    'delta.enableChangeDataFeed' = 'true',
    'delta.feature.allowColumnDefaults' = 'supported'
)
""")
print("Table: chem_ai.gold.agent_recommendations — OK")

# COMMAND ----------

spark.sql("""
CREATE TABLE IF NOT EXISTS chem_ai.gold.agent_audit_log (
    event_id            STRING    NOT NULL,
    recommendation_id   STRING    NOT NULL,
    event_type          STRING    NOT NULL,
    actor               STRING    NOT NULL,
    timestamp           TIMESTAMP NOT NULL DEFAULT current_timestamp(),
    details             STRING
)
USING DELTA
TBLPROPERTIES ('delta.feature.allowColumnDefaults' = 'supported')
""")
print("Table: chem_ai.gold.agent_audit_log — OK")

# COMMAND ----------

# MAGIC %md
# MAGIC ## 5. Verify Resources

# COMMAND ----------

print("=== Schemas in chem_ai ===")
spark.sql("SHOW SCHEMAS IN chem_ai").show()

print("=== Volumes in chem_ai.bronze ===")
spark.sql("SHOW VOLUMES IN chem_ai.bronze").show()

print("=== Tables in chem_ai.gold ===")
spark.sql("SHOW TABLES IN chem_ai.gold").show()

# COMMAND ----------
