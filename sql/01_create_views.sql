-- Smart Power: MySQL 8 views used by the analysis and Tableau dashboard.
-- Source timestamps are UTC. Convert to Europe/Amsterdam in Tableau so DST
-- is handled correctly in the presentation layer.

USE smart_power;

DROP VIEW IF EXISTS vw_hourly_summary_utc;
DROP VIEW IF EXISTS vw_daily_summary_utc;
DROP VIEW IF EXISTS vw_hourly_dashboard;
DROP VIEW IF EXISTS vw_analysis_thresholds;

-- Match pandas' linearly interpolated quartiles:
-- Bottom 25% of price = cheap; bottom 25% of carbon intensity = low-carbon.
CREATE VIEW vw_analysis_thresholds AS
WITH
stats AS (
    SELECT COUNT(*) AS n
    FROM hourly_data
),
positions AS (
    SELECT
        n,
        (n - 1) * 0.25 AS price_index,
        (n - 1) * 0.25 AS carbon_index
    FROM stats
),
price_ranked AS (
    SELECT
        electricity_price AS value,
        ROW_NUMBER() OVER (ORDER BY electricity_price) AS rn
    FROM hourly_data
),
carbon_ranked AS (
    SELECT
        carbon_intensity_gco2_kwh AS value,
        ROW_NUMBER() OVER (ORDER BY carbon_intensity_gco2_kwh) AS rn
    FROM hourly_data
)
SELECT
    (
        SELECT value
        FROM price_ranked
        WHERE rn = FLOOR(positions.price_index) + 1
    ) +
    (positions.price_index - FLOOR(positions.price_index)) *
    (
        (
            SELECT value
            FROM price_ranked
            WHERE rn = LEAST(FLOOR(positions.price_index) + 2, positions.n)
        ) -
        (
            SELECT value
            FROM price_ranked
            WHERE rn = FLOOR(positions.price_index) + 1
        )
    ) AS cheap_price_threshold,
    (
        SELECT value
        FROM carbon_ranked
        WHERE rn = FLOOR(positions.carbon_index) + 1
    ) +
    (positions.carbon_index - FLOOR(positions.carbon_index)) *
    (
        (
            SELECT value
            FROM carbon_ranked
            WHERE rn = LEAST(FLOOR(positions.carbon_index) + 2, positions.n)
        ) -
        (
            SELECT value
            FROM carbon_ranked
            WHERE rn = FLOOR(positions.carbon_index) + 1
        )
    ) AS low_carbon_threshold_gco2_kwh
FROM positions;

CREATE VIEW vw_hourly_dashboard AS
SELECT
    h.timestamp_utc,
    DATE(h.timestamp_utc) AS date_utc,
    HOUR(h.timestamp_utc) AS hour_utc,
    DAYOFWEEK(h.timestamp_utc) - 1 AS weekday_number_utc,
    DAYNAME(h.timestamp_utc) AS weekday_name_utc,
    h.electricity_price,
    h.renewable_share,
    h.renewable_generation,
    h.total_generation,
    h.carbon_intensity_gco2_kwh,
    h.wind_speed,
    h.solar_radiation,
    CASE WHEN h.electricity_price <= t.cheap_price_threshold THEN 1 ELSE 0 END AS is_cheap,
    CASE WHEN h.carbon_intensity_gco2_kwh <= t.low_carbon_threshold_gco2_kwh THEN 1 ELSE 0 END AS is_low_carbon,
    CASE
        WHEN h.electricity_price <= t.cheap_price_threshold
         AND h.carbon_intensity_gco2_kwh <= t.low_carbon_threshold_gco2_kwh
        THEN 1 ELSE 0
    END AS is_cheap_and_low_carbon
FROM hourly_data AS h
CROSS JOIN vw_analysis_thresholds AS t;

CREATE VIEW vw_daily_summary_utc AS
SELECT
    date_utc,
    COUNT(*) AS observed_hours,
    AVG(electricity_price) AS avg_price,
    MIN(electricity_price) AS min_price,
    MAX(electricity_price) AS max_price,
    AVG(renewable_share) AS avg_renewable_share,
    AVG(carbon_intensity_gco2_kwh) AS avg_carbon_intensity_gco2_kwh,
    AVG(wind_speed) AS avg_wind_speed,
    AVG(solar_radiation) AS avg_solar_radiation,
    SUM(is_cheap_and_low_carbon) AS cheap_low_carbon_hours
FROM vw_hourly_dashboard
GROUP BY date_utc;

CREATE VIEW vw_hourly_summary_utc AS
SELECT
    hour_utc,
    COUNT(*) AS observed_hours,
    AVG(electricity_price) AS avg_price,
    AVG(renewable_share) AS avg_renewable_share,
    AVG(carbon_intensity_gco2_kwh) AS avg_carbon_intensity_gco2_kwh,
    SUM(is_cheap_and_low_carbon) AS cheap_low_carbon_hours,
    1.0 * SUM(is_cheap_and_low_carbon) / COUNT(*) AS cheap_low_carbon_rate
FROM vw_hourly_dashboard
GROUP BY hour_utc;
