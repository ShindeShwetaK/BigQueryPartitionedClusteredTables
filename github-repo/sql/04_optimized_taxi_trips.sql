-- Same logical data as curated, with both optimizations.
CREATE OR REPLACE TABLE `{{project_id}}.taxi_analytics.optimized_taxi_trips`
PARTITION BY pickup_date
CLUSTER BY pickup_location_id, payment_type
OPTIONS (partition_expiration_days = NULL)
AS
SELECT * FROM `{{project_id}}.taxi_analytics.curated_taxi_trips`;
