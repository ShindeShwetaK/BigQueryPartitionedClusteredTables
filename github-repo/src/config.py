"""Project settings. Override with environment variables or a local .env file."""

from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
load_dotenv(ROOT / ".env")

PROJECT_ID = os.environ.get("GCP_PROJECT_ID", "").strip()
LOCATION = os.environ.get("BQ_LOCATION", "US").strip() or "US"
DATASET = "taxi_analytics"

PARQUET_DIR = ROOT / "dataset"
PARQUET_GLOB = "yellow_tripdata_*.parquet"

# Three months is enough: Test A filters June and can skip May + July.
# Do not load a full year; four copies would exceed the 10 GB free storage cap.
LOAD_MONTHS = ("2026-05", "2026-06", "2026-07")
LOAD_START = "2026-05-01"
LOAD_END = "2026-07-31"

# Middle month: partition pruning should skip May and July.
TEST_DATE_START = "2026-06-01"
TEST_DATE_END = "2026-06-30"

# TLC zone 237 = Upper East Side South.
TEST_LOCATION_ID = 237

RAW_TABLE = "raw_taxi_trips"
CURATED_TABLE = "curated_taxi_trips"
PARTITIONED_TABLE = "partitioned_taxi_trips"
OPTIMIZED_TABLE = "optimized_taxi_trips"

SQL_DIR = ROOT / "sql"
RESULTS_DIR = ROOT / "results"
DATA_SOURCE = "local dataset/yellow_tripdata_2026-05.parquet through 2026-07"

ON_DEMAND_USD_PER_TIB = 6.25


def require_project_id() -> str:
    if not PROJECT_ID or PROJECT_ID == "your-gcp-project-id":
        raise SystemExit(
            "Set GCP_PROJECT_ID in your environment or in a .env file. "
            "See .env.example."
        )
    return PROJECT_ID


def table_id(table_name: str) -> str:
    return f"{require_project_id()}.{DATASET}.{table_name}"
