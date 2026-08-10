"""
Smart Power - data ingestion.

Pulls ~90 days of data from four sources and saves raw CSVs (all in UTC):
  1. Weather (Open-Meteo)             -> data/raw_weather.csv
  2. Electricity prices (EnergyZero)  -> data/raw_prices.csv
  3. Generation by source (ENTSO-E)   -> data/raw_generation.csv
  4. Carbon intensity (Wattnet)       -> data/raw_carbon_intensity.csv

Setup:
  pip install -r requirements.txt
  cp .env.example .env   # then paste your ENTSO-E token into .env
Run:
  python src/ingest.py
"""

import os
from datetime import datetime, timedelta, timezone

import requests
import pandas as pd
from dotenv import load_dotenv

load_dotenv()

# Netherlands (Amsterdam)
LAT, LON = 52.37, 4.90
DAYS = 90
DATA_DIR = "data"
WATTNET_URL = "https://api.wattnet.eu/v1/footprints"


def fetch_weather():
    """Open-Meteo: wind speed + solar radiation (renewable-energy proxy). Returns UTC."""
    url = "https://api.open-meteo.com/v1/forecast"
    params = {
        "latitude": LAT,
        "longitude": LON,
        "hourly": "wind_speed_10m,shortwave_radiation",
        "past_days": DAYS,   # up to 92
        "forecast_days": 1,
        "timezone": "UTC",
    }
    data = requests.get(url, params=params).json()
    return pd.DataFrame({
        "timestamp": pd.to_datetime(data["hourly"]["time"], utc=True),
        "wind_speed": data["hourly"]["wind_speed_10m"],
        "solar_radiation": data["hourly"]["shortwave_radiation"],
    })


def fetch_prices():
    """EnergyZero: hourly Dutch day-ahead prices. Loops per day. Returns UTC."""
    end = datetime.now(timezone.utc).date()
    start = end - timedelta(days=DAYS)
    frames, day = [], start
    while day <= end:
        params = {
            "fromDate": f"{day}T00:00:00.000Z",
            "tillDate": f"{day}T23:59:59.999Z",
            "interval": 4,      # hourly
            "usageType": 1,     # electricity
            "inclBtw": "true",  # include VAT
        }
        r = requests.get("https://api.energyzero.nl/v1/energyprices", params=params)
        prices = r.json().get("Prices", [])
        if prices:
            frames.append(pd.DataFrame(prices))
        day += timedelta(days=1)
    df = pd.concat(frames, ignore_index=True)
    df = df.rename(columns={"readingDate": "timestamp", "price": "electricity_price"})
    df["timestamp"] = pd.to_datetime(df["timestamp"], utc=True)
    return df[["timestamp", "electricity_price"]]


def fetch_generation():
    """ENTSO-E: actual generation per production type. Needs token. Returns UTC."""
    from entsoe import EntsoePandasClient

    token = os.getenv("ENTSOE_API_TOKEN")
    if not token or token == "your_token_here":
        raise RuntimeError("Put your ENTSO-E token in the .env file (ENTSOE_API_TOKEN=...)")

    client = EntsoePandasClient(api_key=token)
    end = pd.Timestamp.now(tz="Europe/Amsterdam").normalize()
    start = end - pd.Timedelta(days=DAYS)

    gen = client.query_generation("NL", start=start, end=end)
    # When consumption is also returned, columns are a MultiIndex -> keep "Actual Aggregated"
    if isinstance(gen.columns, pd.MultiIndex):
        gen = gen.xs("Actual Aggregated", axis=1, level=-1)
    gen.index = gen.index.tz_convert("UTC")
    gen.index.name = "timestamp"
    return gen.reset_index()


def fetch_carbon_intensity(start=None, end=None):
    """Wattnet: validated 15-minute global life-cycle carbon intensity for NL."""
    end = end or datetime.now(timezone.utc)
    start = start or end - timedelta(days=DAYS)
    if start.tzinfo is None or end.tzinfo is None:
        raise ValueError("Wattnet start/end must be timezone-aware")

    headers = {"Accept": "application/json"}
    token = os.getenv("WATTNET_API_TOKEN")
    cookie = os.getenv("WATTNET_COOKIE")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if cookie:
        headers["Cookie"] = cookie

    response = requests.get(
        WATTNET_URL,
        params={
            "zone": "NL",
            "footprint_type": "carbon",
            "scope": "life-cycle",
            "start": start.astimezone(timezone.utc).isoformat(),
            "end": end.astimezone(timezone.utc).isoformat(),
            "aggregate": "false",
            "use_global": "true",
        },
        headers=headers,
        timeout=120,
    )
    response.raise_for_status()
    content_type = response.headers.get("content-type", "").lower()
    if "application/json" not in content_type:
        raise RuntimeError(
            "Wattnet returned a login page instead of JSON. Authenticate via "
            "WATTNET_API_TOKEN or a temporary WATTNET_COOKIE in .env; never commit it."
        )

    payload = response.json()
    if not isinstance(payload, list) or not payload:
        raise ValueError("Unexpected Wattnet response: expected a non-empty list")
    matching = [
        item for item in payload
        if item.get("footprint_type") == "carbon"
        and item.get("scope") == "life-cycle"
        and item.get("zone") == "NL"
        and item.get("unit") == "gCO2/kWh"
        and item.get("coverage") == "global"
    ]
    if len(matching) != 1:
        raise ValueError(f"Expected one matching Wattnet footprint, found {len(matching)}")

    series = matching[0].get("series")
    if not isinstance(series, list):
        raise ValueError("Unexpected Wattnet response: missing series list")
    complete = [s for s in series if s.get("valid") is True and s.get("zone_status") == "complete"]
    if not complete:
        raise ValueError("Wattnet returned no valid, complete carbon series")

    values = [value for item in complete for value in item.get("values", [])]
    carbon = pd.DataFrame(values, columns=["timestamp", "carbon_intensity_gco2_kwh"])
    carbon["timestamp"] = pd.to_datetime(carbon["timestamp"], utc=True)
    carbon["carbon_intensity_gco2_kwh"] = pd.to_numeric(
        carbon["carbon_intensity_gco2_kwh"], errors="raise"
    )
    carbon = carbon.sort_values("timestamp").drop_duplicates("timestamp", keep="last")
    if carbon.empty or carbon["carbon_intensity_gco2_kwh"].lt(0).any():
        raise ValueError("Wattnet carbon intensity is empty or contains negative values")
    return carbon.reset_index(drop=True)


def main():
    os.makedirs(DATA_DIR, exist_ok=True)

    print("Fetching weather (Open-Meteo)...")
    weather = fetch_weather()
    weather.to_csv(f"{DATA_DIR}/raw_weather.csv", index=False)
    print("  weather:", weather.shape)

    print("Fetching prices (EnergyZero)...")
    prices = fetch_prices()
    prices.to_csv(f"{DATA_DIR}/raw_prices.csv", index=False)
    print("  prices:", prices.shape)

    print("Fetching generation (ENTSO-E)...")
    generation = fetch_generation()
    generation.to_csv(f"{DATA_DIR}/raw_generation.csv", index=False)
    print("  generation:", generation.shape)

    print("Fetching carbon intensity (Wattnet)...")
    carbon = fetch_carbon_intensity()
    carbon.to_csv(f"{DATA_DIR}/raw_carbon_intensity.csv", index=False)
    print("  carbon intensity:", carbon.shape)

    print("Done. Raw CSVs saved in data/ (all timestamps in UTC).")


if __name__ == "__main__":
    main()
