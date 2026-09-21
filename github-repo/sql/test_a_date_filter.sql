-- Test A: date filter. Teaches partition pruning.
SELECT
  COUNT(*) AS total_trips,
  SUM(total_amount) AS total_revenue
FROM `{{project_id}}.taxi_analytics.{{table_name}}`
WHERE pickup_date BETWEEN '{{test_date_start}}' AND '{{test_date_end}}';
