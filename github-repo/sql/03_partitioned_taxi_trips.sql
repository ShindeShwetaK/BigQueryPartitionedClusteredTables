-- Experiment fixture only: same curated rows, partitioned, not clustered.
CREATE OR REPLACE TABLE `{{project_id}}.taxi_analytics.partitioned_taxi_trips`
PARTITION BY pickup_date
OPTIONS (partition_expiration_days = NULL)
AS
SELECT * FROM `{{project_id}}.taxi_analytics.curated_taxi_trips`;
