-- Table 2: cleaned data, still unpartitioned and unclustered.
-- Separates data quality work from storage layout / query-performance work.
-- Source columns are the original TLC parquet names on raw_taxi_trips.
CREATE OR REPLACE TABLE `{{project_id}}.taxi_analytics.curated_taxi_trips` AS
SELECT
  VendorID AS vendor_id,
  tpep_pickup_datetime AS pickup_datetime,
  tpep_dropoff_datetime AS dropoff_datetime,
  DATE(tpep_pickup_datetime) AS pickup_date,
  CAST(passenger_count AS INT64) AS passenger_count,
  CAST(trip_distance AS FLOAT64) AS trip_distance,
  CAST(PULocationID AS INT64) AS pickup_location_id,
  CAST(DOLocationID AS INT64) AS dropoff_location_id,
  CAST(payment_type AS INT64) AS payment_type,
  CAST(fare_amount AS FLOAT64) AS fare_amount,
  CAST(extra AS FLOAT64) AS extra,
  CAST(mta_tax AS FLOAT64) AS mta_tax,
  CAST(tip_amount AS FLOAT64) AS tip_amount,
  CAST(tolls_amount AS FLOAT64) AS tolls_amount,
  CAST(total_amount AS FLOAT64) AS total_amount,
  TIMESTAMP_DIFF(tpep_dropoff_datetime, tpep_pickup_datetime, SECOND) / 60.0 AS trip_duration_minutes,
  SAFE_DIVIDE(
    CAST(trip_distance AS FLOAT64),
    TIMESTAMP_DIFF(tpep_dropoff_datetime, tpep_pickup_datetime, SECOND) / 3600.0
  ) AS trip_speed_mph,
  SAFE_DIVIDE(CAST(tip_amount AS FLOAT64), NULLIF(CAST(fare_amount AS FLOAT64), 0)) AS tip_ratio
FROM `{{project_id}}.taxi_analytics.raw_taxi_trips`
WHERE tpep_pickup_datetime IS NOT NULL
  AND tpep_dropoff_datetime IS NOT NULL
  AND tpep_dropoff_datetime > tpep_pickup_datetime
  AND DATE(tpep_pickup_datetime) BETWEEN '{{load_start}}' AND '{{load_end}}'
  AND passenger_count BETWEEN 1 AND 8
  AND trip_distance > 0
  AND trip_distance < 100
  AND fare_amount >= 0
  AND total_amount > 0
  AND total_amount < 1000
  AND PULocationID IS NOT NULL
  AND DOLocationID IS NOT NULL
  AND PULocationID BETWEEN 1 AND 265
  AND DOLocationID BETWEEN 1 AND 265
  AND payment_type BETWEEN 1 AND 6
  AND TIMESTAMP_DIFF(tpep_dropoff_datetime, tpep_pickup_datetime, SECOND) BETWEEN 60 AND 18000;
