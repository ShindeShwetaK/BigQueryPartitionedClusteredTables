-- Test B: location filter, no date filter. Teaches clustering / block pruning.
-- On partitioned tables this still reads every partition unless clustering helps.
SELECT
  pickup_location_id,
  COUNT(*) AS total_trips
FROM `{{project_id}}.taxi_analytics.{{table_name}}`
WHERE pickup_location_id = {{test_location_id}}
GROUP BY pickup_location_id;
