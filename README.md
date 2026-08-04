# Smart Power ⚡

When is electricity in the Netherlands cheapest **and** cleanest during the day,
and how much of that is driven by renewable generation? This project builds an
end-to-end data pipeline and a machine-learning model to answer that, and turns it
into a simple recommendation: the best hours to use electricity to save money and CO₂.

## Data sources (all free, hourly)
- **EnergyZero** — Dutch day-ahead electricity prices (no key)
- **ENTSO-E** — actual electricity generation by source, to compute the renewable share (needs a free token)
- **Open-Meteo** — weather: wind + solar radiation (no key)

## Project structure
```
smart-power-project/
├── README.md
├── requirements.txt
├── .env.example        # copy to .env and add your ENTSO-E token
├── .gitignore
├── src/
│   └── ingest.py       # pulls ~90 days from the 3 APIs -> data/ (all UTC)
├── notebooks/          # EDA + machine learning
├── dashboard/          # Tableau / dashboard files
└── data/               # raw + clean data (git-ignored)
```

## Setup
```bash
pip install -r requirements.txt
cp .env.example .env      # then open .env and paste your ENTSO-E token
```

## Run the ingestion
```bash
python src/ingest.py
```
This saves `data/raw_weather.csv`, `data/raw_prices.csv`, `data/raw_generation.csv` (all in UTC).

## Workflow
Ingest (APIs) → transform (clean, resample, join on timestamp, renewable share) →
store (SQLite) → EDA + stats → machine learning (predict price / best hours) →
Tableau dashboard.
