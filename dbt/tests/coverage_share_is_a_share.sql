-- A share outside 0..1 means a broken join.
select * from {{ ref('mart_coverage_summary') }}
where coverage_share < 0 or coverage_share > 1
