# BigQuery partitioning and clustering experiment

**Objective:** Measure how BigQuery partitioning and clustering change **bytes scanned**, **runtime**, and **on-demand cost** as the same analytical queries run against equivalent tables.

This is a storage-layout experiment, not a data mart and not a machine-learning model.

Code meanings such as `payment_type = 1` (credit card) live in the [TLC yellow-taxi data dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_yellow.pdf). The parquet files store only the codes.

---

## STAR summary (for interviews)

**Situation.** BigQuery bills on-demand queries by **bytes processed**. Scanning a full fact table for a one-month report wastes money. I wanted to prove, with numbers, how table layout changes that.

**Task.** Load NYC yellow-taxi trips, keep the database small (raw / curated / optimized), run the **same SQL** against an unoptimized table, a partitioned table, and a partitioned+clustered table, and record bytes scanned.

**Action.** I loaded May–July 2026 TLC parquet files with the Python BigQuery client (`google-cloud-bigquery`) and Application Default Credentials. I cleaned the data into `curated_taxi_trips` (no layout). I copied those rows into `partitioned_taxi_trips` (`PARTITION BY pickup_date`) and `optimized_taxi_trips` (`PARTITION BY pickup_date CLUSTER BY pickup_location_id, payment_type`). I ran three tests with the query cache off: date filter, location filter, date+location.

**Result.** Partitioning cut a June-only query from **124.54 MiB to 41.24 MiB** (~3× less, May and July skipped). Clustering did not help a date-only query. A location-only query could not use partitions (no date filter); clustering trimmed **62.27 MiB to 56.25 MiB**. The combined query was cheapest on the optimized table: **186.81 → 61.85 → 56.72 MiB**. Lesson: partition on the date almost every query filters; cluster on high-cardinality filter columns, leading with the most common one. Trust **bytes processed**, not elapsed time.

**Why this dataset.** TLC yellow-taxi files are public, large enough for pruning to show up (millions of rows), have a real date column and a real location id, and match how analytics teams actually query trip data.

---

## Partitioning and clustering are not indexes

In a traditional warehouse you might create a B-tree index. **BigQuery does not use indexes** for this. It stores columnar data in files (blocks). Layout tells the engine which files it can skip.

### Partitioning

Partitioning **divides a table into segments**, usually one per day, on a DATE/TIMESTAMP column.

- A query with a filter on that column can use **partition pruning**: only matching partitions are read.
- Example: `WHERE pickup_date BETWEEN '2026-06-01' AND '2026-06-30'` on a table partitioned by `pickup_date` does not read May or July.
- You get a **dry-run cost estimate** that reflects pruning.
- You can expire old partitions. BigQuery allows **one** partition column.

This project: `PARTITION BY pickup_date`.

### Clustering

Clustering **sorts rows inside storage blocks** by up to four columns (order matters; first column is the prefix).

- A filter on those columns can use **block pruning**: skip blocks whose min/max metadata does not match.
- Benefits are **not guaranteed** to be identical every run. Blocks are adaptive. Small tables may show little gain.
- Clustering is not a partition key and not an index.

This project: `CLUSTER BY pickup_location_id, payment_type` (location first, because Tests B and C filter location).

### Together

Partition first, then cluster **inside each partition**.

```
Filter on date        → skip whole partitions     (partition pruning)
Filter on location    → skip some blocks inside   (block pruning)
```

---

## Does this idea exist in Snowflake and other OLAP?

The **idea** (do not scan data you did not ask for) is everywhere. The **feature names** differ.

| System | Closest ideas |
| --- | --- |
| **BigQuery** | Partitioning + clustering (this project) |
| **Snowflake** | Micro-partitions are automatic. You do not pick partition columns the same way. **Clustering keys** can help prune micro-partitions. Search optimization is a different paid feature. |
| **Redshift** | **DISTKEY** / **SORTKEY** (and RA3 distribution). Sort keys are the closest analog to clustering. |
| **Databricks / Spark** | Hive-style **PARTITIONED BY** plus **Z-ORDER** (Delta) for skipping files. |
| **Synapse / BigQuery siblings** | Similar: partition + optional clustered column lists. |

So: learning “filter on the date column so the engine skips files” transfers. Copy-pasting `PARTITION BY pickup_date CLUSTER BY ...` into Snowflake will not work as-is. In Snowflake you would talk about clustering keys and pruning of micro-partitions, not BigQuery partition objects.

---

## Tables we created

Dataset: `taxi_analytics` (US).

```
taxi_analytics
├── raw_taxi_trips              original parquet load
├── curated_taxi_trips          cleaned; baseline for performance
├── partitioned_taxi_trips      same curated rows; partition only
└── optimized_taxi_trips        same curated rows; partition + cluster
```

| Table | Role | Partition | Cluster |
| --- | --- | --- | --- |
| `raw_taxi_trips` | TLC columns as loaded (`tpep_pickup_datetime`, `PULocationID`, …) | no | no |
| `curated_taxi_trips` | Invalid rows removed; `pickup_date` added | no | no |
| `partitioned_taxi_trips` | Experiment 2 fixture (isolate partition from cluster) | `pickup_date` | no |
| `optimized_taxi_trips` | Production-style layout | `pickup_date` | `pickup_location_id`, `payment_type` |

Core design is **three tables** (raw / curated / optimized). The partitioned-only table exists so Test B can show “partitioning does nothing without a date filter.”

**Counts from the measured run**

| Table | Rows | Size |
| --- | --- | --- |
| raw | 11,458,193 | 1.57 GiB |
| curated / partitioned / optimized | 8,161,998 each | 1.09 GiB each |

About **71%** of raw rows survived cleaning (nulls, 0-mile trips, bad passenger counts, etc.). Curated is the performance baseline, not raw, because raw has a different row count and schema.

Source files (local, not committed):

- `dataset/yellow_tripdata_2026-05.parquet`
- `dataset/yellow_tripdata_2026-06.parquet`
- `dataset/yellow_tripdata_2026-07.parquet`

Three months is enough to prove pruning (June vs May+July) and small enough to stay near BigQuery’s **10 GB free storage** even with several copies.

---

## How Python talks to BigQuery (connector)

There is **no JDBC/ODBC string** in this repo.

| Piece | What we used |
| --- | --- |
| Library | `google-cloud-bigquery` (official Google Cloud client) |
| Auth | **Application Default Credentials** from `gcloud auth application-default login` |
| Project | `.env` → `GCP_PROJECT_ID` |
| Location | `US` (must match the dataset) |

Client construction (`src/bq.py`):

```python
from google.cloud import bigquery
bq = bigquery.Client(project=PROJECT_ID, location="US")
```

That client is the connector. It calls the BigQuery REST API as the signed-in Google user (or a service-account JSON if `GOOGLE_APPLICATION_CREDENTIALS` is set).

### Load path (parquet → raw)

`src/load_raw.py` opens each parquet file and starts a **load job** (load jobs are free; they are not billed as queries):

```python
job_config = bigquery.LoadJobConfig(
    source_format=bigquery.SourceFormat.PARQUET,
    write_disposition=WRITE_TRUNCATE,  # first file
    autodetect=True,
)
with path.open("rb") as handle:
    job = bq.load_table_from_file(handle, table, job_config=job_config)
job.result()
```

Later months use `WRITE_APPEND` and `ALLOW_FIELD_ADDITION` because June 2026 added a `request_source` column that May did not have.

### SQL path (curated / layouts / tests)

Python reads a `.sql` file, replaces `{{project_id}}` and other placeholders, then:

```python
job = bq.query(sql)
job.result()
```

Experiment queries turn the cache **off** so repeated runs are comparable:

```python
job_config = bigquery.QueryJobConfig(use_query_cache=False)
job = bq.query(sql, job_config=job_config)
```

Bytes and time come from the finished job: `job.total_bytes_processed`, `job.started`, `job.ended`, `job.slot_millis`.

End-to-end:

```
parquet files
    → load_table_from_file → raw_taxi_trips
    → bq.query(02_curated_taxi_trips.sql) → curated_taxi_trips
    → bq.query(03_...sql) → partitioned_taxi_trips
    → bq.query(04_...sql) → optimized_taxi_trips
    → bq.query(test_a/b/c.sql) × 3 tables → results/*.csv
```

Commands:

```powershell
python -m src.check_setup
python -m src.build_tables
python -m src.run_experiments
```

---

## The three experiments (tests)

Same SQL, three physical layouts. Cache off.

| Test | Filter | What it isolates |
| --- | --- | --- |
| **A** | `pickup_date` in June 2026 | Partition pruning |
| **B** | `pickup_location_id = 237` only | Clustering (no date, so partitions cannot drop) |
| **C** | June **and** location 237 | Partition pruning, then block pruning |

Test A SQL:

```sql
SELECT COUNT(*) AS total_trips, SUM(total_amount) AS total_revenue
FROM `project.taxi_analytics.<table>`
WHERE pickup_date BETWEEN '2026-06-01' AND '2026-06-30';
```

Optimized DDL:

```sql
CREATE OR REPLACE TABLE `project.taxi_analytics.optimized_taxi_trips`
PARTITION BY pickup_date
CLUSTER BY pickup_location_id, payment_type
AS SELECT * FROM `project.taxi_analytics.curated_taxi_trips`;
```

---

## Results (measured 2026-09-21, cache off)

| Test | Curated (no layout) | Partitioned | Partition + cluster |
| --- | ---: | ---: | ---: |
| A Date | 124.54 MiB | **41.24 MiB** | **41.24 MiB** |
| B Location | 62.27 MiB | 62.27 MiB | **56.25 MiB** |
| C Date + location | 186.81 MiB | 61.85 MiB | **56.72 MiB** |

### Did we see improvement?

**Yes, where the layout matches the filter.**

- **Test A:** ~**3× less data** with partitioning (June is one of three months). Clustering added **zero** because the query does not filter clustered columns.
- **Test B:** Partitioning **did not help** (no date predicate). Clustering saved ~**10%** (62.27 → 56.25 MiB). Modest because clustering is block-level, not an index.
- **Test C:** Partitioning did the big cut (186.81 → 61.85). Clustering took a little more (56.72). Best table: **optimized**.

Elapsed time is **not** the score. Partitioned Test B was slower (1113 ms) while scanning the same 62.27 MiB as curated. Cost follows **bytes processed**.

On-demand cost for these nine queries is far under a cent (`$6.25 / TiB`).

Full job ids: `results/experiment_results.csv`.

---

## Suggestion: what to partition and cluster in BigQuery tomorrow

**Partition**

- Prefer a **DATE** (or TIMESTAMP truncated to day) that **almost every dashboard query** puts in `WHERE`.
- Typical: `order_date`, `event_date`, `pickup_date`, `_PARTITIONTIME` only if ingestion time is the grain you filter.
- One partition column only. Daily is the default. Use monthly if each day is tiny.
- Do not partition on a column nobody filters (e.g. `vendor_id`).

**Cluster** (up to 4 columns, **most selective / most filtered first**)

- Columns that appear in `WHERE` or `JOIN` **after** the date filter: customer id, location id, status, product id.
- This project: `pickup_location_id` then `payment_type`.
- Avoid clustering on a column with almost one value, or on the partition column alone if you already partition by it (sometimes people still cluster the date for intra-day sort; we did not need that).

**Do not**

- Treat clustering as a unique index.
- Expect Test-B-style queries (no date) to get partition pruning.
- Copy a full year three times on the sandbox 10 GB cap.

**Snowflake tomorrow:** you would not create `PARTITION BY pickup_date`. You would define a **clustering key** on `(pickup_date, pickup_location_id)` and look at partition-scan stats in query profiles. The habit is the same: put the date and the common filters in the skip metadata.

---

## How we analyzed

1. Load three months → raw.  
2. Clean → curated (types, `pickup_date`, drop bad rows).  
3. CTAS copies with different `PARTITION` / `CLUSTER` options.  
4. Run Tests A–C on all three layouts with cache disabled.  
5. Compare `total_bytes_processed` (primary) and elapsed ms / slot-ms (secondary).  
6. Write `results/experiment_results.csv`.

That is the whole analysis loop.

---

## Setup (reproduce)

1. GCP project, BigQuery API, billing linked (sandbox 60-day **partition expiration** will empty old date partitions).  
2. `gcloud init` and `gcloud auth application-default login`.  
3. Put May–July 2026 parquet files in `dataset/` (see `dataset/README.md`).  
4. `python -m venv .venv` then `pip install -r requirements.txt`.  
5. Copy `.env.example` to `.env` and set `GCP_PROJECT_ID`.  
6. `python -m src.check_setup`  
7. `python -m src.build_tables`  
8. `python -m src.run_experiments`  

---

## What to push to GitHub

Push **this folder** (`github-repo`), not the parent OneDrive project (that contains `.venv`, parquet, and `.env`).

**Commit**

- `README.md` (this file)
- `src/`
- `sql/`
- `requirements.txt`
- `.env.example`
- `.gitignore`
- `results/experiment_results.csv` and `results/experiment_results.md`
- `dataset/README.md`

**Do not commit**

- `.env`
- `dataset/*.parquet`
- `.venv/`
- service-account JSON keys
- personal CSV extracts of trip rows

```powershell
cd "C:\Users\shwet\OneDrive\Desktop\Bigquery project\github-repo"
git init
git add .
git commit -m "Add BigQuery partitioning and clustering experiment."
git branch -M main
git remote add origin https://github.com/<your-user>/<your-repo>.git
git push -u origin main
```
