-- Smart Power: MySQL 8 database and source table.
-- Run this first in MySQL Workbench while connected to Local instance 3306.

CREATE DATABASE IF NOT EXISTS smart_power
    CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE smart_power;

CREATE TABLE IF NOT EXISTS hourly_data (
    timestamp_utc DATETIME NOT NULL,
    electricity_price DOUBLE NOT NULL,
    renewable_share DOUBLE NOT NULL,
    renewable_generation DOUBLE NOT NULL,
    total_generation DOUBLE NOT NULL,
    carbon_intensity_gco2_kwh DOUBLE NOT NULL,
    wind_speed DOUBLE NOT NULL,
    solar_radiation DOUBLE NOT NULL,
    PRIMARY KEY (timestamp_utc),
    CONSTRAINT chk_renewable_share
        CHECK (renewable_share BETWEEN 0 AND 1),
    CONSTRAINT chk_generation_nonnegative
        CHECK (renewable_generation >= 0 AND total_generation > 0),
    CONSTRAINT chk_carbon_intensity_nonnegative
        CHECK (carbon_intensity_gco2_kwh >= 0)
);

-- Safe migration for databases created before carbon intensity was added.
SET @carbon_column_exists = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE()
      AND table_name = 'hourly_data'
      AND column_name = 'carbon_intensity_gco2_kwh'
);
SET @add_carbon_column = IF(
    @carbon_column_exists = 0,
    'ALTER TABLE hourly_data ADD COLUMN carbon_intensity_gco2_kwh DOUBLE NULL AFTER total_generation',
    'SELECT 1'
);
PREPARE carbon_migration FROM @add_carbon_column;
EXECUTE carbon_migration;
DEALLOCATE PREPARE carbon_migration;
