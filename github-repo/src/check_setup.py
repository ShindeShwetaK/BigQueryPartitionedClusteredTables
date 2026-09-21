"""Verify local config before talking to BigQuery."""

from __future__ import annotations

from src import config
from src.load_raw import parquet_files


def main() -> None:
    files = parquet_files()
    print(f"GCP_PROJECT_ID = {config.PROJECT_ID or '(missing)'}")
    print(f"BQ_LOCATION    = {config.LOCATION}")
    print(f"DATASET        = {config.DATASET}")
    print(f"PARQUET FILES  = {len(files)} in {config.PARQUET_DIR}")
    print(f"LOAD MONTHS    = {', '.join(config.LOAD_MONTHS) if config.LOAD_MONTHS else 'all files in dataset/'}")
    print(f"DATE WINDOW    = {config.LOAD_START} to {config.LOAD_END}")
    print(f"TEST DATES     = {config.TEST_DATE_START} to {config.TEST_DATE_END}")
    print(f"TEST LOCATION  = {config.TEST_LOCATION_ID}")
    if not config.PROJECT_ID or config.PROJECT_ID == "your-gcp-project-id":
        print("Missing GCP_PROJECT_ID. Copy .env.example to .env and set your project id.")
        raise SystemExit(1)
    print("Config looks set. Next: python -m src.build_tables")


if __name__ == "__main__":
    main()
