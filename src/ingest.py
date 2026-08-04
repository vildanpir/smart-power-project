"""
Smart Power - data ingestion.

Pulls ~90 days of hourly data from three sources and saves raw CSVs (all in UTC):
  1. Weather (Open-Meteo)             -> data/raw_weather.csv
  2. Electricity prices (EnergyZero)  -> data/raw_prices.csv
  3. Generation by source (ENTSO-E)   -> data/raw_generation.csv

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

    print("Done. Raw CSVs saved in data/ (all timestamps in UTC).")


if __name__ == "__main__":
    main()
