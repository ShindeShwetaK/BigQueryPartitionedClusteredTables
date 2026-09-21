CREATE SCHEMA IF NOT EXISTS `{{project_id}}.taxi_analytics`
OPTIONS (
  location = 'US',
  description = 'NYC yellow taxi experiment: raw vs curated vs partitioned vs clustered'
);
