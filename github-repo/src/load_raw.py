"""Load local TLC yellow-taxi parquet files into raw_taxi_trips."""

from __future__ import annotations

from pathlib import Path

from google.cloud import bigquery

from src import config


def parquet_files() -> list[Path]:
    if not config.PARQUET_DIR.exists():
        raise SystemExit(f"Missing folder: {config.PARQUET_DIR}")
    files = sorted(config.PARQUET_DIR.glob(config.PARQUET_GLOB))
    if config.LOAD_MONTHS:
        wanted = {f"yellow_tripdata_{month}.parquet" for month in config.LOAD_MONTHS}
        files = [path for path in files if path.name in wanted]
    if not files:
        raise SystemExit(
            f"No files matching {config.PARQUET_GLOB} in {config.PARQUET_DIR}"
        )
    return files


def load_raw(bq: bigquery.Client) -> None:
    table = config.table_id(config.RAW_TABLE)
    files = parquet_files()
    print(f"Loading {len(files)} parquet files into {table}")

    for index, path in enumerate(files):
        disposition = (
            bigquery.WriteDisposition.WRITE_TRUNCATE
            if index == 0
            else bigquery.WriteDisposition.WRITE_APPEND
        )
        job_config = bigquery.LoadJobConfig(
            source_format=bigquery.SourceFormat.PARQUET,
            write_disposition=disposition,
            autodetect=True,
        )
        if index > 0:
            job_config.schema_update_options = [
                bigquery.SchemaUpdateOption.ALLOW_FIELD_ADDITION
            ]
        size_mib = path.stat().st_size / (1024 * 1024)
        print(f"\n>>> {path.name}  {size_mib:.1f} MiB  {disposition}")
        with path.open("rb") as handle:
            job = bq.load_table_from_file(handle, table, job_config=job_config)
        job.result()
        print(f"    job={job.job_id}  rows_loaded={job.output_rows:,}")

    table_obj = bq.get_table(table)
    print(
        f"\nraw_taxi_trips ready: rows={table_obj.num_rows:,}  "
        f"size={table_obj.num_bytes:,} bytes"
    )
