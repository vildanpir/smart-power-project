# Smart Power Netherlands ⚡

Smart Power answers one practical question: **when should flexible electricity use be shifted in the Netherlands to reduce both cost and carbon intensity?**

The project combines API ingestion, hourly data engineering, MySQL, exploratory and statistical analysis, machine learning, Tableau, and a Streamlit prototype in one reproducible workflow. The final historical recommendation is **12:00–16:00 Europe/Amsterdam time** for a consecutive four-hour flexible-load window.

## Key results

The validated analysis covers **1,170 unique hourly observations** from **28 May to 3 August 2026**.

| Result | Value |
|---|---:|
| Average electricity price | €0.130/kWh |
| Average carbon intensity | 402.9 gCO₂/kWh |
| Average renewable share | 21.5% |
| Cheap and low-carbon hours | 164 |
| Recommended four-hour window | 12:00–16:00 local time |
| Price–carbon Pearson correlation | 0.495 |
| Renewable share–carbon correlation | -0.710 |
| Gradient Boosting test R² | 0.943 |
| Gradient Boosting test RMSE | €0.0189/kWh |

The 12:00–16:00 and 13:00–17:00 windows have the same historical cheap-and-low-carbon rate. **12:00–16:00 is selected because it has the lower average price.** The recommendation is historical rather than a live forecast.

## Data sources

| Source | Use | Resolution / access |
|---|---|---|
| EnergyZero | Dutch day-ahead electricity prices | Hourly, no key |
| ENTSO-E | Actual generation by source and renewable share | Hourly, free API token |
| Open-Meteo | Wind speed and solar radiation | Hourly, no key |
| Wattnet | Netherlands carbon intensity | 15-minute, global life-cycle gCO₂/kWh; OAuth token or session cookie |

Wattnet records are accepted only when the response metadata reports `valid=true` and `zone_status=complete`. A carbon hour is retained only when all four 15-minute observations are present.

## Methodology

1. `src/ingest.py` downloads the four sources and stores UTC raw CSV files in the git-ignored `data/` directory.
2. The transform layer resamples generation and carbon data to hourly frequency, joins every source on `timestamp_utc`, validates ranges and uniqueness, and loads `smart_power.hourly_data` in MySQL.
3. MySQL views reproduce the analysis thresholds and supply clean daily and hourly summaries.
4. EDA measures distributions, hourly/weekday patterns, price–carbon and renewable–carbon relationships.
5. “Cheap” means price at or below the sample’s first quartile (€0.08/kWh). “Low-carbon” means carbon intensity at or below its first quartile (341.82 gCO₂/kWh). Renewable share is retained as an explanatory variable rather than used as the sustainability label.
6. Consecutive four-hour windows are compared by their cheap-and-low-carbon rate, then by average price and carbon intensity to break ties.
7. A time-aware Gradient Boosting model predicts price using 17 calendar, weather, generation, carbon, and lag features. The held-out test contains 210 observations and the model improves RMSE by about 40% over a persistence baseline.

All source timestamps and database joins use UTC. Local-hour analysis uses `Europe/Amsterdam`, including daylight-saving-time conversion.

### Visual language

Every project visual uses one shared palette: petrol `#36676B` for price and base series, dark green `#215138` for carbon, mint `#81C2A8` for renewable energy, orange `#F09D46` for the recommended window, and burnt orange `#AF5622` for adverse or secondary emphasis. White remains the primary background for readability. Labels and line styles accompany colour so meaning never depends on colour alone.

## Architecture

```text
EnergyZero ─┐
ENTSO-E ────┼─> Python ingestion ─> raw UTC CSV ─> hourly transform + QA
Open-Meteo ─┤                                      │
Wattnet ────┘                                      ├─> MySQL views/checks
                                                   ├─> EDA + statistics + ML
                                                   ├─> Tableau CSV/workbook
                                                   └─> Streamlit prototype
```

## Repository structure

```text
smart-power-project/
├── dashboard/
│   ├── smart_power_dashboard.twb
│   └── smart_power_for_tableau.csv
├── notebooks/
│   ├── smart-power-transform.ipynb
│   ├── smart-power-sql.ipynb
│   ├── smart-power-eda.ipynb
│   └── smart-power-ml.ipynb
├── presentation/
│   └── Smart_Power_Final_Presentation.pptx
├── sql/
│   ├── 00_create_database.sql
│   ├── 01_create_views.sql
│   └── 02_quality_checks.sql
├── src/
│   ├── ingest.py
│   ├── transform.py
│   └── database.py
├── streamlit_app.py
├── .streamlit/
│   └── config.toml
├── .env.example
└── requirements.txt
```

## Reproduce the project

### 1. Install dependencies

Python 3.11 or 3.12 and MySQL 8 are recommended.

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
```

Open `.env` and add the local MySQL credentials, an ENTSO-E token, and—only when needed—a temporary Wattnet token or cookie. `.env` and raw API data are git-ignored and must never be committed.

### 2. Create the database

Start MySQL, then run [`sql/00_create_database.sql`](sql/00_create_database.sql) in MySQL Workbench or with the MySQL CLI.

### 3. Download raw data

```bash
python src/ingest.py
```

This writes `raw_prices.csv`, `raw_generation.csv`, `raw_weather.csv`, and `raw_carbon_intensity.csv` under `data/`.

### 4. Transform and load MySQL

Run [`notebooks/smart-power-transform.ipynb`](notebooks/smart-power-transform.ipynb) from top to bottom. It creates the hourly clean table, applies the idempotent carbon-column migration when needed, and loads MySQL.

To rebuild only the Tableau-ready CSV from existing raw files:

```bash
python src/transform.py
```

### 5. Run SQL and analysis notebooks

Run these notebooks in order:

1. [`notebooks/smart-power-sql.ipynb`](notebooks/smart-power-sql.ipynb)
2. [`notebooks/smart-power-eda.ipynb`](notebooks/smart-power-eda.ipynb)
3. [`notebooks/smart-power-ml.ipynb`](notebooks/smart-power-ml.ipynb)

The reusable SQL is also available in [`sql/01_create_views.sql`](sql/01_create_views.sql) and [`sql/02_quality_checks.sql`](sql/02_quality_checks.sql).

## Dashboards and presentation

- [Tableau workbook](dashboard/smart_power_dashboard.twb) — open it with [the Tableau-ready CSV](dashboard/smart_power_for_tableau.csv) next to the workbook. If Tableau prompts for a missing file on another computer, reconnect the text source to that CSV.
- [Streamlit prototype](streamlit_app.py) — launch with `streamlit run streamlit_app.py`.
- [Final presentation](presentation/Smart_Power_Final_Presentation.pptx) — designed for a presentation of no more than 10 minutes.

## Data-quality checks

The pipeline verifies:

- unique hourly UTC timestamps;
- no nulls in the final analysis columns;
- renewable share between 0 and 1;
- non-negative carbon intensity and generation;
- four complete 15-minute Wattnet observations per retained carbon hour;
- MySQL row counts, duplicate timestamps, analysis thresholds, and flag totals;
- time-ordered rather than random train/test splitting for machine learning.

## Limitations

- The dataset spans roughly 68 calendar days in late spring and summer, so the result is not a full-year seasonal recommendation.
- There are 460 missing clock hours in the requested period after enforcing valid and complete Wattnet coverage; gaps are preserved rather than imputed into the analysis or lag features.
- Wattnet uses global life-cycle methodology; results depend on that definition and source coverage.
- Correlations describe association, not causation.
- The Tableau and Streamlit outputs are historical planning tools, not real-time dispatch or guaranteed savings products.
- The household savings example in the EDA notebook is an illustrative scenario based on stated flexible-load assumptions.

## Conclusion

In this sample, flexible use around midday offers the strongest combination of low prices and low measured carbon intensity. The central portfolio takeaway is not only the 12:00–16:00 window: the project demonstrates a traceable end-to-end workflow from external APIs to validated SQL, statistical evidence, a time-aware model, and user-facing dashboards.
