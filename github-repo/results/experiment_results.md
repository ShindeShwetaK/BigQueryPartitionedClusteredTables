# Experiment results

Generated: 2026-09-21 21:18 UTC
Project: `nyctaxi-509319`
Dataset: `taxi_analytics`
Source: May–July 2026 TLC yellow taxi parquet (3 files)
Tables: 8,161,998 curated rows each (raw started at 11,458,193; 71.2% kept after cleaning)
Date filter: June 2026
Location filter: `pickup_location_id = 237`
Query cache: off

| Test | Table | Partition | Cluster | Bytes processed | Elapsed |
| --- | --- | --- | --- | ---: | ---: |
| A Date filter | `curated_taxi_trips` | no | no | 124.54 MiB | 258 ms |
| A Date filter | `partitioned_taxi_trips` | yes | no | 41.24 MiB | 394 ms |
| A Date filter | `optimized_taxi_trips` | yes | yes | 41.24 MiB | 387 ms |
| B Location filter | `curated_taxi_trips` | no | no | 62.27 MiB | 265 ms |
| B Location filter | `partitioned_taxi_trips` | yes | no | 62.27 MiB | 1113 ms |
| B Location filter | `optimized_taxi_trips` | yes | yes | 56.25 MiB | 766 ms |
| C Date + location | `curated_taxi_trips` | no | no | 186.81 MiB | 266 ms |
| C Date + location | `partitioned_taxi_trips` | yes | no | 61.85 MiB | 338 ms |
| C Date + location | `optimized_taxi_trips` | yes | yes | 56.72 MiB | 216 ms |

## What the numbers mean

- **Test A:** Partitioning cut bytes from 124.54 MiB to 41.24 MiB (about one-third). June is one of three months, so partition pruning skipped May and July. Clustering did not add more because this query has no location filter.
- **Test B:** No date filter, so partitioned = curated (62.27 MiB). Clustering on `pickup_location_id` cut optimized to 56.25 MiB (about 10% less) via block pruning.
- **Test C:** Partitioning first (186.81 → 61.85 MiB), then clustering a bit more (56.72 MiB). Best layout is partitioned + clustered.
- Trust **bytes processed**, not elapsed time.
