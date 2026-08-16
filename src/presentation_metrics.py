"""Reproduce the stakeholder-deck comparison and impact scenario.

The comparison uses only local dates with one observation for every relevant
hour in both windows. This keeps the 12:00–16:00 and 18:00–22:00 averages
paired on the same dates instead of comparing samples with different gaps.
"""

from pathlib import Path

import pandas as pd


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATA_PATH = PROJECT_ROOT / "dashboard" / "smart_power_for_tableau.csv"
MIDDAY_HOURS = (12, 13, 14, 15)
EVENING_HOURS = (18, 19, 20, 21)
CHARGE_KWH = 20
CHARGES_PER_WEEK = 2
WEEKS_PER_YEAR = 52
HOUSEHOLDS = 10_000


def complete_paired_rows(data: pd.DataFrame) -> pd.DataFrame:
    """Return dates containing exactly one row for every comparison hour."""
    relevant = set(MIDDAY_HOURS + EVENING_HOURS)
    complete_dates = []
    for local_date, group in data.groupby("date_local"):
        counts = group["hour_local"].value_counts()
        if all(counts.get(hour, 0) == 1 for hour in relevant):
            complete_dates.append(local_date)
    return data[
        data["date_local"].isin(complete_dates)
        & data["hour_local"].isin(relevant)
    ].copy()


def window_average(data: pd.DataFrame, hours: tuple[int, ...]) -> pd.Series:
    """Calculate average price and carbon intensity for one local-hour window."""
    return data[data["hour_local"].isin(hours)][
        ["electricity_price", "carbon_intensity_gco2_kwh"]
    ].mean()


def main() -> None:
    data = pd.read_csv(DATA_PATH)
    paired = complete_paired_rows(data)
    midday = window_average(paired, MIDDAY_HOURS)
    evening = window_average(paired, EVENING_HOURS)

    annual_kwh = CHARGE_KWH * CHARGES_PER_WEEK * WEEKS_PER_YEAR
    price_difference = evening["electricity_price"] - midday["electricity_price"]
    carbon_difference = (
        evening["carbon_intensity_gco2_kwh"]
        - midday["carbon_intensity_gco2_kwh"]
    )
    annual_cost = annual_kwh * price_difference
    annual_carbon_kg = annual_kwh * carbon_difference / 1_000

    complete_dates = paired["date_local"].nunique()
    assert complete_dates == 49
    assert len(paired) == complete_dates * 8
    assert round(midday["electricity_price"], 6) == 0.032704
    assert round(evening["electricity_price"], 6) == 0.198163

    print(f"Complete paired dates: {complete_dates}")
    print(
        "Midday 12:00–16:00: "
        f"€{midday['electricity_price']:.6f}/kWh, "
        f"{midday['carbon_intensity_gco2_kwh']:.3f} gCO2/kWh"
    )
    print(
        "Evening 18:00–22:00: "
        f"€{evening['electricity_price']:.6f}/kWh, "
        f"{evening['carbon_intensity_gco2_kwh']:.3f} gCO2/kWh"
    )
    print(f"One household per year: €{annual_cost:.2f}, {annual_carbon_kg:.2f} kg")
    print(
        f"{HOUSEHOLDS:,} households per year: "
        f"€{annual_cost * HOUSEHOLDS:,.0f}, "
        f"{annual_carbon_kg * HOUSEHOLDS / 1_000:,.2f} tonnes"
    )


if __name__ == "__main__":
    main()
