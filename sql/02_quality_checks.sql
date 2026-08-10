-- Smart Power: repeatable MySQL 8 data-quality and result checks.

USE smart_power;

-- Expected: total_rows = unique_hours and incomplete_rows = 0.
SELECT
    COUNT(*) AS total_rows,
    COUNT(DISTINCT timestamp_utc) AS unique_hours,
    SUM(
        CASE
            WHEN electricity_price IS NULL
              OR renewable_share IS NULL
              OR renewable_generation IS NULL
              OR total_generation IS NULL
              OR carbon_intensity_gco2_kwh IS NULL
              OR wind_speed IS NULL
              OR solar_radiation IS NULL
            THEN 1 ELSE 0
        END
    ) AS incomplete_rows,
    MIN(timestamp_utc) AS first_hour_utc,
    MAX(timestamp_utc) AS last_hour_utc
FROM hourly_data;

-- Expected: no rows.
SELECT timestamp_utc, COUNT(*) AS duplicate_count
FROM hourly_data
GROUP BY timestamp_utc
HAVING COUNT(*) > 1;

-- Expected: one row matching the EDA thresholds.
SELECT *
FROM vw_analysis_thresholds;

-- Counts depend on the current valid/complete Wattnet coverage.
SELECT
    COUNT(*) AS dashboard_rows,
    SUM(is_cheap) AS cheap_hours,
    SUM(is_low_carbon) AS low_carbon_hours,
    SUM(is_cheap_and_low_carbon) AS cheap_and_low_carbon_hours
FROM vw_hourly_dashboard;

SELECT *
FROM vw_hourly_summary_utc
ORDER BY hour_utc;
