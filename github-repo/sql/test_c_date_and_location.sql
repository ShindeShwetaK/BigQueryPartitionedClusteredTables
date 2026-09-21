-- Test C: date + location. Partition pruning plus block pruning.
SELECT
  pickup_location_id,
  COUNT(*) AS total_trips,
  SUM(total_amount) AS revenue
FROM `{{project_id}}.taxi_analytics.{{table_name}}`
WHERE pickup_date BETWEEN '{{test_date_start}}' AND '{{test_date_end}}'
  AND pickup_location_id = {{test_location_id}}
GROUP BY pickup_location_id;
