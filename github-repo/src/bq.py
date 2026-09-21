"""Small BigQuery helpers used by the build and experiment scripts."""

from __future__ import annotations

from google.cloud import bigquery

from src.config import LOCATION, SQL_DIR, require_project_id


def client() -> bigquery.Client:
    return bigquery.Client(project=require_project_id(), location=LOCATION)


def render_sql(filename: str, **extra: str) -> str:
    text = (SQL_DIR / filename).read_text(encoding="utf-8")
    replacements = {
        "{{project_id}}": require_project_id(),
        **{f"{{{{{key}}}}}": str(value) for key, value in extra.items()},
    }
    for placeholder, value in replacements.items():
        text = text.replace(placeholder, value)
    return text


def run_sql(bq: bigquery.Client, sql: str, label: str) -> bigquery.QueryJob:
    print(f"\n>>> {label}")
    job = bq.query(sql)
    try:
        job.result()
    except Exception:
        errors = getattr(job, "errors", None)
        if errors:
            print(f"    BigQuery error: {errors}")
        raise
    bytes_processed = job.total_bytes_processed or 0
    print(f"    job={job.job_id}  bytes_processed={bytes_processed:,}")
    return job


def format_bytes(num_bytes: int | None) -> str:
    if not num_bytes:
        return "0 B"
    value = float(num_bytes)
    for unit in ("B", "KiB", "MiB", "GiB", "TiB"):
        if value < 1024 or unit == "TiB":
            return f"{value:,.2f} {unit}"
        value /= 1024
    return f"{num_bytes} B"
