"""Create the taxi_analytics dataset and the three core tables plus the partition-only experiment fixture."""

from __future__ import annotations

import argparse

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from src import config
from src.bq import client, format_bytes, render_sql, run_sql
from src.load_raw import load_raw


def ensure_dataset(bq: bigquery.Client) -> None:
    dataset_id = f"{config.require_project_id()}.{config.DATASET}"
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = config.LOCATION
    dataset.description = (
        "NYC yellow taxi experiment: compare unoptimized, partitioned, "
        "and partitioned+clustered tables."
    )
    dataset = bq.create_dataset(dataset, exists_ok=True)
    dataset.default_table_expiration_ms = None
    dataset.default_partition_expiration_ms = None
    try:
        bq.update_dataset(
            dataset,
            ["default_table_expiration_ms", "default_partition_expiration_ms"],
        )
        print(f"Dataset ready: {dataset_id} ({config.LOCATION}), no auto-expiration")
    except Exception as exc:
        print(f"Dataset ready: {dataset_id} ({config.LOCATION})")
        print(
            "Could not turn off the 60-day sandbox expiration. "
            "Billing is not fully linked to this project yet."
        )
        print(f"  ({exc.__class__.__name__})")


def print_table_summary(bq: bigquery.Client) -> None:
    print("\n=== Table summary ===")
    for name in (
        config.RAW_TABLE,
        config.CURATED_TABLE,
        config.PARTITIONED_TABLE,
        config.OPTIMIZED_TABLE,
    ):
        table = bq.get_table(config.table_id(name))
        partitioning = "none"
        if table.time_partitioning and table.time_partitioning.field:
            partitioning = f"DATE({table.time_partitioning.field})"
        clustering = ",".join(table.clustering_fields or []) or "none"
        print(
            f"{name:24} rows={table.num_rows:>12,}  "
            f"size={format_bytes(table.num_bytes):>12}  "
            f"partition={partitioning:20}  cluster={clustering}"
        )


def build_derived_tables(bq: bigquery.Client) -> None:
    run_sql(
        bq,
        render_sql(
            "02_curated_taxi_trips.sql",
            load_start=config.LOAD_START,
            load_end=config.LOAD_END,
        ),
        "Build curated_taxi_trips",
    )
    run_sql(
        bq,
        render_sql("03_partitioned_taxi_trips.sql"),
        "Build partitioned_taxi_trips (experiment fixture)",
    )
    run_sql(bq, render_sql("04_optimized_taxi_trips.sql"), "Build optimized_taxi_trips")
    for name in (config.PARTITIONED_TABLE, config.OPTIMIZED_TABLE):
        table = bq.get_table(config.table_id(name))
        if not table.num_rows:
            raise SystemExit(
                f"{name} has 0 rows. Billing/sandbox partition expiration is still "
                "dropping May–July 2026 partitions. Link billing to this project and rerun."
            )


def reset_dataset(bq: bigquery.Client) -> None:
    dataset_id = f"{config.require_project_id()}.{config.DATASET}"
    print(f"Deleting {dataset_id} so we can reload May–July 2026 from scratch.")
    bq.delete_dataset(dataset_id, delete_contents=True, not_found_ok=True)
    ensure_dataset(bq)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build raw, curated, partitioned, and optimized taxi tables."
    )
    parser.add_argument(
        "--skip-load",
        action="store_true",
        help="Do not reload parquet. Use the raw table already in BigQuery.",
    )
    parser.add_argument(
        "--free-tier",
        action="store_true",
        help=(
            "Keep Jan–Mar 2025 only so copies fit in the 10 GB free storage quota. "
            "This is the default unless LOAD_ALL_MONTHS=1."
        ),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    bq = client()
    ensure_dataset(bq)

    using_free_tier = args.free_tier or not getattr(config, "LOAD_ALL_MONTHS", False)
    print(
        "Loading "
        f"{config.LOAD_START} to {config.LOAD_END} "
        "(three months: enough for partition pruning, small enough for free storage)."
    )

    raw_exists = True
    try:
        bq.get_table(config.table_id(config.RAW_TABLE))
    except NotFound:
        raw_exists = False

    if args.skip_load and not raw_exists:
        raise SystemExit("raw_taxi_trips does not exist yet. Run without --skip-load.")

    if args.skip_load:
        print("Skipping parquet load.")
    elif using_free_tier:
        reset_dataset(bq)
        load_raw(bq)
    else:
        load_raw(bq)

    build_derived_tables(bq)
    print_table_summary(bq)

    raw = bq.get_table(config.table_id(config.RAW_TABLE))
    curated = bq.get_table(config.table_id(config.CURATED_TABLE))
    if raw.num_rows:
        keep_rate = curated.num_rows / raw.num_rows
        print(
            f"\nData quality: raw_rows={raw.num_rows:,}  "
            f"curated_rows={curated.num_rows:,}  "
            f"keep_rate={keep_rate:.1%}"
        )
    print("\nBuild complete. Next: python -m src.run_experiments")


if __name__ == "__main__":
    main()
