"""Run the same analytical queries against unoptimized, partitioned, and optimized tables.

Records bytes processed and elapsed time. Does not invent results: the CSV is
written only after BigQuery jobs finish.
"""

from __future__ import annotations

import csv
from dataclasses import asdict, dataclass
from datetime import datetime, timezone

from google.api_core.exceptions import NotFound
from google.cloud import bigquery

from src import config
from src.bq import client, format_bytes, render_sql


@dataclass
class ExperimentResult:
    test_id: str
    test_name: str
    table_name: str
    partitioned: str
    clustered: str
    bytes_processed: int
    bytes_processed_pretty: str
    elapsed_ms: int
    slot_ms: int
    estimated_on_demand_usd: float
    job_id: str
    row_count: int


TESTS = (
    ("A", "Date filter", "test_a_date_filter.sql"),
    ("B", "Location filter", "test_b_location_filter.sql"),
    ("C", "Date + location", "test_c_date_and_location.sql"),
)

TABLES = (
    (config.CURATED_TABLE, "no", "no"),
    (config.PARTITIONED_TABLE, "yes", "no"),
    (config.OPTIMIZED_TABLE, "yes", "yes"),
)


def table_row_count(bq: bigquery.Client, table_name: str) -> int | None:
    try:
        table = bq.get_table(config.table_id(table_name))
    except NotFound:
        return None
    return int(table.num_rows or 0)


def estimate_cost_usd(bytes_processed: int) -> float:
    tib = bytes_processed / (1024**4)
    return round(tib * config.ON_DEMAND_USD_PER_TIB, 6)


def run_one(bq: bigquery.Client, sql: str) -> tuple[bigquery.QueryJob, int]:
    job_config = bigquery.QueryJobConfig(use_query_cache=False)
    job = bq.query(sql, job_config=job_config)
    rows = list(job.result())
    return job, len(rows)


def elapsed_ms(job: bigquery.QueryJob) -> int:
    if job.started is None or job.ended is None:
        return 0
    return int((job.ended - job.started).total_seconds() * 1000)


def write_csv(results: list[ExperimentResult]) -> None:
    config.RESULTS_DIR.mkdir(exist_ok=True)
    path = config.RESULTS_DIR / "experiment_results.csv"
    fieldnames = list(asdict(results[0]).keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in results:
            writer.writerow(asdict(row))
    print(f"\nWrote {path}")


def write_markdown(results: list[ExperimentResult]) -> None:
    path = config.RESULTS_DIR / "experiment_results.md"
    generated_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# Experiment results",
        "",
        f"Generated: {generated_at}",
        f"Project: `{config.require_project_id()}`",
        f"Dataset: `{config.DATASET}`",
        f"Source: `{config.DATA_SOURCE}` ({config.LOAD_START} to {config.LOAD_END})",
        f"Date filter: `{config.TEST_DATE_START}` to `{config.TEST_DATE_END}`",
        f"Location filter: `pickup_location_id = {config.TEST_LOCATION_ID}`",
        "",
        "Query cache was disabled. Bytes processed and elapsed time come from the completed BigQuery job, not estimates.",
        "",
        "| Test | Table | Partition | Cluster | Bytes processed | Elapsed | Slot-ms | Est. on-demand cost |",
        "| --- | --- | --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for row in results:
        lines.append(
            f"| {row.test_id} {row.test_name} | `{row.table_name}` | {row.partitioned} | "
            f"{row.clustered} | {row.bytes_processed_pretty} | {row.elapsed_ms} ms | "
            f"{row.slot_ms:,} | ${row.estimated_on_demand_usd:.6f} |"
        )
    lines.extend(
        [
            "",
            "## How to read this",
            "",
            "- **Test A** should show partition pruning: the partitioned tables scan June only, while curated scans May–July.",
            "- **Test B** has no date filter, so partitioning does not prune. Clustering on `pickup_location_id` may reduce bytes via block pruning; it is not guaranteed to match every run.",
            "- **Test C** combines both: partition pruning, then block pruning inside the remaining partitions.",
            "- Elapsed time can vary with slot availability. Bytes processed is the more stable cost signal.",
            "",
        ]
    )
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {path}")


def main() -> None:
    bq = client()
    extras = {
        "test_date_start": config.TEST_DATE_START,
        "test_date_end": config.TEST_DATE_END,
        "test_location_id": str(config.TEST_LOCATION_ID),
    }
    results: list[ExperimentResult] = []
    usable_tables: list[tuple[str, str, str]] = []
    for table_name, partitioned, clustered in TABLES:
        rows = table_row_count(bq, table_name)
        if rows is None:
            print(f"Skipping {table_name}: table does not exist.")
            continue
        if rows == 0:
            print(
                f"Skipping {table_name}: 0 rows. "
                "Sandbox partition expiration deletes 2025 date partitions. "
                "This is not partition pruning."
            )
            continue
        usable_tables.append((table_name, partitioned, clustered))

    if not usable_tables:
        raise SystemExit("No usable tables. Build curated_taxi_trips first.")

    for test_id, test_name, filename in TESTS:
        for table_name, partitioned, clustered in usable_tables:
            sql = render_sql(filename, table_name=table_name, **extras)
            print(f"\n>>> Test {test_id} on {table_name}")
            job, row_count = run_one(bq, sql)
            bytes_processed = int(job.total_bytes_processed or 0)
            result = ExperimentResult(
                test_id=test_id,
                test_name=test_name,
                table_name=table_name,
                partitioned=partitioned,
                clustered=clustered,
                bytes_processed=bytes_processed,
                bytes_processed_pretty=format_bytes(bytes_processed),
                elapsed_ms=elapsed_ms(job),
                slot_ms=int(job.slot_millis or 0),
                estimated_on_demand_usd=estimate_cost_usd(bytes_processed),
                job_id=job.job_id,
                row_count=row_count,
            )
            results.append(result)
            print(
                f"    bytes={result.bytes_processed_pretty}  "
                f"elapsed={result.elapsed_ms} ms  slot_ms={result.slot_ms:,}  "
                f"job={result.job_id}"
            )

    write_csv(results)
    write_markdown(results)
    print("\nExperiments complete.")


if __name__ == "__main__":
    main()
