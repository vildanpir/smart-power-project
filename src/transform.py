"""Build the validated hourly Smart Power dataset and Tableau extract."""

from pathlib import Path

import pandas as pd


CORE_COLUMNS = [
    "timestamp_utc",
    "electricity_price",
    "renewable_share",
    "renewable_generation",
    "total_generation",
    "carbon_intensity_gco2_kwh",
    "wind_speed",
    "solar_radiation",
]


def build_clean_dataset(project_root: Path) -> pd.DataFrame:
    data_dir = project_root / "data"
    prices = pd.read_csv(data_dir / "raw_prices.csv")
    generation = pd.read_csv(data_dir / "raw_generation.csv")
    weather = pd.read_csv(data_dir / "raw_weather.csv")
    carbon = pd.read_csv(data_dir / "raw_carbon_intensity.csv")
    for frame in (prices, generation, weather, carbon):
        frame["timestamp"] = pd.to_datetime(frame["timestamp"], utc=True, errors="raise")

    generation = generation.set_index("timestamp").resample("h").mean()
    production_cols = generation.columns.tolist()
    renewable_cols = [
        col for col in production_cols
        if any(keyword in col for keyword in ("Solar", "Wind", "Hydro", "Biomass"))
    ]
    generation["total_generation"] = generation[production_cols].sum(axis=1)
    generation["renewable_generation"] = generation[renewable_cols].sum(axis=1)
    generation["renewable_share"] = (
        generation["renewable_generation"] / generation["total_generation"]
    )
    generation = generation.reset_index()

    carbon_hourly = (
        carbon.set_index("timestamp")["carbon_intensity_gco2_kwh"]
        .resample("h")
        .agg(["mean", "count"])
    )
    carbon_hourly = carbon_hourly.loc[carbon_hourly["count"] == 4, ["mean"]]
    carbon_hourly = carbon_hourly.rename(columns={"mean": "carbon_intensity_gco2_kwh"}).reset_index()

    clean = (
        prices.merge(generation, on="timestamp", how="inner")
        .merge(weather, on="timestamp", how="inner")
        .merge(carbon_hourly, on="timestamp", how="inner")
        .rename(columns={"timestamp": "timestamp_utc"})
    )[CORE_COLUMNS].dropna().sort_values("timestamp_utc").reset_index(drop=True)

    assert not clean["timestamp_utc"].duplicated().any()
    assert clean["renewable_share"].between(0, 1).all()
    assert clean["carbon_intensity_gco2_kwh"].ge(0).all()
    return clean


def add_sustainability_flags(clean: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    result = clean.copy()
    cheap_threshold = result["electricity_price"].quantile(0.25)
    low_carbon_threshold = result["carbon_intensity_gco2_kwh"].quantile(0.25)
    result["is_cheap"] = (result["electricity_price"] <= cheap_threshold).astype(int)
    result["is_low_carbon"] = (
        result["carbon_intensity_gco2_kwh"] <= low_carbon_threshold
    ).astype(int)
    result["is_cheap_and_low_carbon"] = (
        result["is_cheap"].astype(bool) & result["is_low_carbon"].astype(bool)
    ).astype(int)
    # Backward-compatible aliases keep existing Tableau workbooks refreshable.
    # They now follow the carbon-based definition and should be migrated in Tableau.
    result["is_clean"] = result["is_low_carbon"]
    result["is_cheap_and_clean"] = result["is_cheap_and_low_carbon"]
    result["is_negative_price"] = (result["electricity_price"] < 0).astype(int)
    return result, {
        "cheap_price_threshold": cheap_threshold,
        "low_carbon_threshold_gco2_kwh": low_carbon_threshold,
    }


def build_tableau_extract(clean: pd.DataFrame) -> pd.DataFrame:
    result, _ = add_sustainability_flags(clean)
    local = result["timestamp_utc"].dt.tz_convert("Europe/Amsterdam")
    result.insert(1, "timestamp_local", local.dt.tz_localize(None))
    result.insert(2, "date_local", local.dt.date)
    result.insert(3, "hour_local", local.dt.hour)
    result.insert(4, "weekday_name_local", local.dt.day_name())
    result["timestamp_utc"] = result["timestamp_utc"].dt.tz_localize(None)
    return result


def main() -> None:
    root = Path(__file__).resolve().parents[1]
    clean = build_clean_dataset(root)
    dashboard = build_tableau_extract(clean)
    output = root / "dashboard" / "smart_power_for_tableau.csv"
    dashboard.to_csv(output, index=False)
    print(f"Saved {len(dashboard):,} validated hourly rows to {output}")


if __name__ == "__main__":
    main()
