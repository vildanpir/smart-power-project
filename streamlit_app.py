"""Interactive Smart Power prototype built on the validated historical dataset."""

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


DATA_PATH = Path(__file__).parent / "dashboard" / "smart_power_for_tableau.csv"
WINDOW_SIZE = 4
PETROL = "#A9C9EA"
DARK_GREEN = "#C1FF72"
MINT = "#C1FF72"
ORANGE = "#C1FF72"
BURNT_ORANGE = "#DCEBFA"
DEVICE_PRESETS = {
    "Washing machine": 1.0,
    "Dishwasher": 1.2,
    "Tumble dryer": 2.5,
    "EV charging": 20.0,
    "Custom": 2.0,
}


st.set_page_config(
    page_title="Smart Power Netherlands",
    layout="wide",
)

st.markdown(
    """
    <style>
    [data-testid="stHeader"] {height: 0; min-height: 0;}
    [data-testid="stDecoration"], footer {display: none;}
    .block-container {
        max-width: 1500px;
        padding: .6rem 1rem .8rem;
    }
    [data-testid="stVerticalBlock"] {gap: .55rem;}
    [data-testid="stHorizontalBlock"] {gap: .7rem;}
    [data-testid="stSidebar"] {
        min-width: 250px !important;
        max-width: 250px !important;
    }
    [data-testid="stSidebar"] [data-testid="stSidebarContent"] {
        padding: .65rem .8rem;
    }
    [data-testid="stSidebar"] [data-testid="stVerticalBlock"] {gap: .45rem;}
    [data-testid="stSidebar"] h2 {font-size: 1.2rem; margin-bottom: .15rem;}
    [data-testid="stSidebar"] label p {font-size: .82rem;}
.hero {
    padding: .75rem 1rem;
    border-radius: 14px;
    background: linear-gradient(120deg, #244E7D 0%, #173B63 100%);
    border: 1px solid #5F86BA;
    margin-bottom: .35rem;
}
.hero h1 {margin: 0; font-size: 1.65rem; color: #F5F9FD;}
.hero p {margin: .2rem 0 0; color: #DCEBFA; font-size: .85rem;}
.status-card {
    padding: .7rem .85rem;
    border-radius: 14px;
    border-left: 7px solid var(--status-color);
    background: var(--status-bg);
    min-height: 112px;
    color: #F5F9FD;
}
.status-card h3 {margin: 0 0 .2rem; color: var(--status-color); font-size: 1.15rem;}
.status-card p {margin: .12rem 0; color: #F5F9FD; font-size: .84rem;}
.small-note {color: #BFD5EC; font-size: .76rem;}
.chart-top-space {height: .25rem;}
.patterns-heading {
    margin: .15rem 0 .45rem;
    padding-left: .8rem;
    border-left: 6px solid #c1ff72;
    color: #F5F9FD;
    font-size: 1.35rem;
    font-weight: 700;
    line-height: 1.25;
}
div[data-testid="stExpander"] {
    border: 1px solid #4069A7;
    border-top: 4px solid #c1ff72;
    background: linear-gradient(90deg, #244E7D 0%, #173B63 100%);
}
div[data-testid="stExpander"] summary {color: #F5F9FD;}
div[data-testid="stMetric"] {
    background: #244E7D;
    border: 1px solid #4069A7;
    padding: .42rem .55rem;
    border-radius: 12px;
    min-height: 72px;
}
div[data-testid="stMetric"] [data-testid="stMetricLabel"],
div[data-testid="stMetric"] [data-testid="stMetricValue"] {color: #F5F9FD;}
div[data-testid="stMetric"] [data-testid="stMetricLabel"] p {
    font-size: .72rem;
    line-height: 1.1;
    white-space: normal;
}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {
    font-size: 1.35rem;
    line-height: 1.15;
}
div[data-testid="stAlert"] {padding: .45rem .7rem; min-height: auto;}
button[data-baseweb="tab"] {height: 2.15rem; padding: 0 .7rem;}
h1 {font-size: 1.75rem;}
h2 {font-size: 1.35rem;}
h3 {font-size: 1.1rem;}
@media (max-height: 900px) {
    .block-container {padding-top: .35rem; padding-bottom: .5rem;}
    [data-testid="stVerticalBlock"] {gap: .35rem;}
    .hero {padding: .55rem .85rem;}
    .hero h1 {font-size: 1.45rem;}
    .hero p {font-size: .78rem;}
    div[data-testid="stMetric"] {min-height: 62px; padding: .32rem .45rem;}
}
    </style>
    """,
    unsafe_allow_html=True,
)


@st.cache_data
def load_data(path: Path) -> pd.DataFrame:
    """Load and validate the historical Tableau export."""
    if not path.exists():
        raise FileNotFoundError(
            f"Data file not found: {path}. Run the project pipeline first."
        )

    data = pd.read_csv(path)
    required = {
        "timestamp_utc",
        "timestamp_local",
        "date_local",
        "hour_local",
        "electricity_price",
        "renewable_share",
        "carbon_intensity_gco2_kwh",
        "is_cheap",
        "is_low_carbon",
        "is_cheap_and_low_carbon",
    }
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    data["timestamp_utc"] = pd.to_datetime(data["timestamp_utc"], utc=True)
    data["timestamp_local"] = pd.to_datetime(data["timestamp_local"])
    data["date_local"] = pd.to_datetime(data["date_local"]).dt.date
    data["hour_local"] = data["hour_local"].astype(int)
    return data.sort_values("timestamp_local").reset_index(drop=True)


def hourly_profile(data: pd.DataFrame) -> pd.DataFrame:
    """Create the 24-hour historical profile used by the recommendation engine."""
    return (
        data.groupby("hour_local", as_index=False)
        .agg(
            electricity_price=("electricity_price", "mean"),
            carbon_intensity_gco2_kwh=("carbon_intensity_gco2_kwh", "mean"),
            renewable_share=("renewable_share", "mean"),
            cheap_low_carbon_rate=("is_cheap_and_low_carbon", "mean"),
        )
        .sort_values("hour_local")
    )


def find_best_window(
    profile: pd.DataFrame, priority: str, window_size: int = WINDOW_SIZE
) -> tuple[int, int, pd.DataFrame]:
    """Return the best consecutive local-hour window for the selected priority."""
    candidates = []
    for start in range(0, 24 - window_size + 1):
        block = profile[profile["hour_local"].between(start, start + window_size - 1)]
        if len(block) != window_size:
            continue
        candidates.append(
            {
                "start": start,
                "end": start + window_size,
                "price": block["electricity_price"].mean(),
                "carbon": block["carbon_intensity_gco2_kwh"].mean(),
                "good_rate": block["cheap_low_carbon_rate"].mean(),
            }
        )

    scores = pd.DataFrame(candidates)
    if priority == "Lowest cost":
        winner = scores.sort_values(["price", "carbon"]).iloc[0]
    elif priority == "Lowest carbon":
        winner = scores.sort_values(["carbon", "price"]).iloc[0]
    else:
        price_range = scores["price"].max() - scores["price"].min()
        carbon_range = scores["carbon"].max() - scores["carbon"].min()
        scores["price_norm"] = (scores["price"] - scores["price"].min()) / price_range
        scores["carbon_norm"] = (
            scores["carbon"] - scores["carbon"].min()
        ) / carbon_range
        scores["balanced_score"] = (
            0.5 * scores["price_norm"] + 0.5 * scores["carbon_norm"]
        )
        winner = scores.sort_values(
            ["balanced_score", "good_rate"], ascending=[True, False]
        ).iloc[0]

    return int(winner["start"]), int(winner["end"]), scores


def weekday_best_windows(data: pd.DataFrame, priority: str) -> pd.DataFrame:
    """Build one easy-to-read four-hour recommendation for each weekday."""
    weekday_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    rows = []
    local_data = data.assign(weekday=data["timestamp_local"].dt.day_name())
    for weekday in weekday_order:
        day_profile = hourly_profile(local_data[local_data["weekday"] == weekday])
        start, end, _ = find_best_window(day_profile, priority)
        window_rows = day_profile[
            day_profile["hour_local"].between(start, end - 1)
        ]
        rows.append(
            {
                "weekday": weekday,
                "start": start,
                "end": end,
                "midpoint": (start + end) / 2,
                "window": window_label(start, end),
                "average_price": window_rows["electricity_price"].mean(),
                "average_carbon": window_rows[
                    "carbon_intensity_gco2_kwh"
                ].mean(),
            }
        )
    return pd.DataFrame(rows)


def window_label(start: int, end: int) -> str:
    return f"{start:02d}:00–{end:02d}:00"


def cost_difference_label(difference: float) -> str:
    if difference > 0:
        return f"€{difference:.2f} estimated saving"
    if difference < 0:
        return f"€{abs(difference):.2f} higher estimated cost"
    return "No estimated cost difference"


def emissions_difference_label(difference: float) -> str:
    if difference > 0:
        return f"{difference:.2f} kg lower associated carbon"
    if difference < 0:
        return f"{abs(difference):.2f} kg higher associated carbon"
    return "No associated carbon difference"


def status_details(row: pd.Series) -> tuple[str, str, str, str]:
    is_cheap = bool(row["is_cheap"])
    is_low_carbon = bool(row["is_low_carbon"])
    if is_cheap and is_low_carbon:
        return (
            "Good time to use electricity",
            "This historical hour had both a relatively low price and low carbon intensity.",
            DARK_GREEN,
            "#244E7D",
        )
    if is_cheap or is_low_carbon:
        advantage = "lower price" if is_cheap else "lower carbon intensity"
        return (
            "Mixed conditions",
            f"This historical hour had {advantage}, but not both advantages.",
            ORANGE,
            "#203F63",
        )
    return (
        "Better to wait if possible",
        "This historical hour was neither low-price nor low-carbon relative to the dataset.",
        BURNT_ORANGE,
        "#1B344F",
    )


try:
    df = load_data(DATA_PATH)
except (FileNotFoundError, ValueError) as error:
    st.error(str(error))
    st.stop()

profile = hourly_profile(df)

st.markdown(
    """
    <div class="hero">
    <h1>Smart Power Netherlands</h1>
      <p>Find historically lower-cost, lower-carbon hours for flexible electricity use.</p>
    </div>
    """,
    unsafe_allow_html=True,
)
st.info(
    "Prototype mode: this app uses validated historical observations, not live electricity data."
)

with st.sidebar:
    st.header("Plan an electricity task")
    priority = st.radio(
        "What matters most?",
        ["Balanced", "Lowest cost", "Lowest carbon"],
        help="Balanced gives equal weight to average price and carbon intensity.",
    )
    selected_date = st.selectbox(
        "Historical date",
        sorted(df["date_local"].unique(), reverse=True),
        format_func=lambda value: value.strftime("%d %B %Y"),
    )
    selected_day = df[df["date_local"] == selected_date]
    available_hours = sorted(selected_day["hour_local"].unique().tolist())
    default_hour = 14 if 14 in available_hours else available_hours[len(available_hours) // 2]
    selected_hour = st.select_slider(
        "Historical local hour",
        options=available_hours,
        value=default_hour,
        format_func=lambda hour: f"{hour:02d}:00",
    )
    st.caption("Times are shown in Europe/Amsterdam local time.")

best_start, best_end, _ = find_best_window(profile, priority)
best_label = window_label(best_start, best_end)
selected_row = selected_day[selected_day["hour_local"] == selected_hour].iloc[0]

metric_columns = st.columns(4)
metric_columns[0].metric("Historical observations", f"{len(df):,}")
metric_columns[1].metric("Average price", f"€{df['electricity_price'].mean():.3f}/kWh")
metric_columns[2].metric(
    "Average carbon intensity",
    f"{df['carbon_intensity_gco2_kwh'].mean():.1f} gCO₂/kWh",
)
metric_columns[3].metric(f"Overall historical best 4-hour window · {priority}", best_label)

overview_tab, planner_tab, patterns_tab = st.tabs(
    ["Historical view", "Device planner", "Patterns & method"]
)

with overview_tab:
    st.subheader("Would this have been a good time to use electricity?")
    left, right = st.columns([1, 1.45])
    title, description, status_color, status_background = status_details(selected_row)
    with left:
        st.markdown(
            f"""
            <div class="status-card" style="--status-color:{status_color}; --status-bg:{status_background};">
              <h3>{title}</h3>
              <p>{selected_date.strftime('%d %B %Y')} at {selected_hour:02d}:00</p>
              <p>{description}</p>
              <p class="small-note">Historical classification based on dataset quartiles.</p>
            </div>
            """,
            unsafe_allow_html=True,
        )
    with right:
        detail_columns = st.columns(3)
        detail_columns[0].metric(
            "Price", f"€{selected_row['electricity_price']:.3f}/kWh"
        )
        detail_columns[1].metric(
            "Carbon intensity",
            f"{selected_row['carbon_intensity_gco2_kwh']:.0f} gCO₂/kWh",
        )
        detail_columns[2].metric(
            "Renewable share", f"{selected_row['renewable_share']:.1%}"
        )

    chart_data = profile.copy()
    chart_data["recommended"] = chart_data["hour_local"].between(
        best_start, best_end - 1
    )
    price_bars = (
        alt.Chart(chart_data)
        .mark_bar(cornerRadiusTopLeft=3, cornerRadiusTopRight=3)
        .encode(
            x=alt.X("hour_local:O", title="Amsterdam local hour"),
            y=alt.Y("electricity_price:Q", title="Average price (€/kWh)"),
            color=alt.condition(
                "datum.recommended",
                alt.value(ORANGE),
                alt.value(PETROL),
            ),
            tooltip=[
                alt.Tooltip("hour_local:O", title="Hour"),
                alt.Tooltip("electricity_price:Q", title="Avg. price", format=".3f"),
            ],
        )
    )
    carbon_line = (
        alt.Chart(chart_data)
        .mark_line(point=True, color=DARK_GREEN, strokeWidth=3)
        .encode(
            x=alt.X("hour_local:O", title="Amsterdam local hour"),
            y=alt.Y(
                "carbon_intensity_gco2_kwh:Q",
                title="Average carbon intensity (gCO₂/kWh)",
                axis=alt.Axis(orient="right"),
            ),
            tooltip=[
                alt.Tooltip("hour_local:O", title="Hour"),
                alt.Tooltip(
                    "carbon_intensity_gco2_kwh:Q",
                    title="Avg. carbon intensity",
                    format=".1f",
                ),
            ],
        )
    )
    st.markdown('<div class="chart-top-space"></div>', unsafe_allow_html=True)
    st.altair_chart(
        alt.layer(price_bars, carbon_line)
        .resolve_scale(y="independent")
        .properties(
            height=390,
            title=f"Historical hourly pattern · highlighted window: {best_label}",
        ),
        width="stretch",
    )

with planner_tab:
    st.subheader("Compare the selected hour with the overall historical best window")
    control_col, result_col = st.columns([1, 1.4])
    with control_col:
        device = st.selectbox("Device or task", list(DEVICE_PRESETS))
        default_energy = DEVICE_PRESETS[device]
        energy_kwh = st.number_input(
            "Energy needed (kWh)",
            min_value=0.1,
            max_value=100.0,
            value=float(default_energy),
            step=0.1,
        )
        st.caption(
            "Preset values are simple examples. Enter the value from your appliance label or charging plan for a better estimate."
        )

    recommended_rows = profile[profile["hour_local"].between(best_start, best_end - 1)]
    recommended_price = recommended_rows["electricity_price"].mean()
    recommended_carbon = recommended_rows["carbon_intensity_gco2_kwh"].mean()
    selected_cost = float(selected_row["electricity_price"]) * energy_kwh
    recommended_cost = recommended_price * energy_kwh
    selected_emissions = (
        float(selected_row["carbon_intensity_gco2_kwh"]) * energy_kwh / 1000
    )
    recommended_emissions = recommended_carbon * energy_kwh / 1000
    cost_saving = selected_cost - recommended_cost
    carbon_saving = selected_emissions - recommended_emissions

    with result_col:
        result_metrics = st.columns(2)
        result_metrics[0].metric(
            "Estimated cost in overall historical best window",
            f"€{recommended_cost:.2f}",
            delta=cost_difference_label(cost_saving),
            delta_color="off",
        )
        result_metrics[1].metric(
            "Associated carbon in overall historical best window",
            f"{recommended_emissions:.2f} kg CO₂",
            delta=emissions_difference_label(carbon_saving),
            delta_color="off",
        )
        if cost_saving > 0 and carbon_saving > 0:
            st.success(
                f"Historical suggestion: run **{device.lower()}** during **{best_label}**. "
                "In this comparison, it reduces both estimated cost and associated carbon."
            )
        elif cost_saving > 0 or carbon_saving > 0:
            st.warning(
            "The overall historical best window improves one goal in this comparison, but not both. "
                "Try changing the priority in the sidebar."
            )
        else:
            st.info(
                "The selected historical hour already performs as well as, or better than, "
            "the overall historical best window for this comparison."
            )
    st.caption(
        "Estimates multiply historical hourly intensity by the entered kWh. The price data includes VAT, but not network or fixed charges, contract differences, standby use, or appliance efficiency."
    )

with patterns_tab:
    st.markdown(
        '<div class="patterns-heading">Best time to use electricity by day</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        f"Recommended four-hour windows based on historical {priority.lower()} conditions."
    )
    weekday_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    weekday_windows = weekday_best_windows(df, priority)
    schedule_bars = (
        alt.Chart(weekday_windows)
        .mark_bar(cornerRadius=7, height=22, color=ORANGE)
        .encode(
            x=alt.X(
                "start:Q",
                title="Amsterdam local hour",
                scale=alt.Scale(domain=[0, 24]),
                axis=alt.Axis(values=list(range(0, 25, 2)), format="02d"),
            ),
            x2="end:Q",
            y=alt.Y("weekday:N", sort=weekday_order, title=None),
            tooltip=[
                alt.Tooltip("weekday:N", title="Day"),
                alt.Tooltip("window:N", title="Best window"),
                alt.Tooltip("average_price:Q", title="Avg. price", format=".3f"),
                alt.Tooltip("average_carbon:Q", title="Avg. carbon", format=".0f"),
            ],
        )
        .properties(height=245)
    )
    schedule_labels = (
        alt.Chart(weekday_windows)
        .mark_text(color="#244E7D", fontWeight="bold", fontSize=12)
        .encode(
            x="midpoint:Q",
            y=alt.Y("weekday:N", sort=weekday_order),
            text="window:N",
        )
    )
    chart_column, table_column = st.columns([1.35, 1])
    with chart_column:
        st.altair_chart(schedule_bars + schedule_labels, width="stretch")
    with table_column:
        display_windows = weekday_windows[
            ["weekday", "window", "average_price", "average_carbon"]
        ].rename(
            columns={
                "weekday": "Day",
                "window": "Recommended window",
                "average_price": "Avg. price",
                "average_carbon": "Avg. carbon",
            }
        )
        st.dataframe(
            display_windows,
            hide_index=True,
            width="stretch",
            column_config={
                "Avg. price": st.column_config.NumberColumn(format="€%.3f/kWh"),
                "Avg. carbon": st.column_config.NumberColumn(format="%.0f gCO₂/kWh"),
            },
        )

    with st.expander("How these recommendations are calculated", expanded=False):
        st.markdown(
            f"""
            - **Scope:** {len(df):,} validated hourly observations, from
              {df['date_local'].min().strftime('%d %B %Y')} to
              {df['date_local'].max().strftime('%d %B %Y')}.
            - **Price:** Dutch hourly electricity-price observations.
            - **Carbon:** estimated with Wattnet's methodology and global
              life-cycle emission factors, expressed as gCO₂/kWh as reported by Wattnet.
            - **Low price / low carbon:** bottom quartile of each measure in
              the validated dataset.
            - **Recommendation:** a four-hour historical window. Balanced mode
              gives equal weight to normalized average price and carbon intensity.
            - **Important:** this is an educational prototype, not live advice or
              a forecast. Results mainly represent late spring and summer 2026.
            """
        )
