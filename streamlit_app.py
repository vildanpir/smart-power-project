"""Interactive Smart Power prototype built on the validated historical dataset."""

from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st


DATA_PATH = Path(__file__).parent / "dashboard" / "smart_power_for_tableau.csv"
WINDOW_SIZE = 4
DEVICE_PRESETS = {
    "Washing machine": 1.0,
    "Dishwasher": 1.2,
    "Tumble dryer": 2.5,
    "EV charging": 20.0,
    "Custom": 2.0,
}


st.set_page_config(
    page_title="Smart Power Netherlands",
    page_icon="⚡",
    layout="wide",
)

st.markdown(
    """
    <style>
    .block-container {padding-top: 2rem; padding-bottom: 3rem;}
    .hero {
        padding: 1.5rem 1.7rem;
        border-radius: 18px;
        background: linear-gradient(120deg, #f5f3ff 0%, #ecfeff 100%);
        border: 1px solid #ddd6fe;
        margin-bottom: 1rem;
    }
    .hero h1 {margin: 0; font-size: 2.25rem; color: #202124;}
    .hero p {margin: .45rem 0 0; color: #52525b; font-size: 1.05rem;}
    .status-card {
        padding: 1.15rem 1.3rem;
        border-radius: 14px;
        border-left: 7px solid var(--status-color);
        background: var(--status-bg);
        min-height: 150px;
    }
    .status-card h3 {margin: 0 0 .35rem;}
    .status-card p {margin: .2rem 0;}
    .small-note {color: #71717a; font-size: .88rem;}
    div[data-testid="stMetric"] {
        background: #ffffff;
        border: 1px solid #e4e4e7;
        padding: .8rem 1rem;
        border-radius: 12px;
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
        return f"{difference:.2f} kg lower estimated emissions"
    if difference < 0:
        return f"{abs(difference):.2f} kg higher estimated emissions"
    return "No estimated emissions difference"


def status_details(row: pd.Series) -> tuple[str, str, str, str]:
    is_cheap = bool(row["is_cheap"])
    is_low_carbon = bool(row["is_low_carbon"])
    if is_cheap and is_low_carbon:
        return (
            "Good time to use electricity",
            "This historical hour had both a relatively low price and low carbon intensity.",
            "#059669",
            "#ecfdf5",
        )
    if is_cheap or is_low_carbon:
        advantage = "lower price" if is_cheap else "lower carbon intensity"
        return (
            "Mixed conditions",
            f"This historical hour had {advantage}, but not both advantages.",
            "#d97706",
            "#fffbeb",
        )
    return (
        "Better to wait if possible",
        "This historical hour was neither low-price nor low-carbon relative to the dataset.",
        "#dc2626",
        "#fef2f2",
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
      <h1>⚡ Smart Power Netherlands</h1>
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
                alt.value("#14b8a6"),
                alt.value("#c4b5fd"),
            ),
            tooltip=[
                alt.Tooltip("hour_local:O", title="Hour"),
                alt.Tooltip("electricity_price:Q", title="Avg. price", format=".3f"),
            ],
        )
    )
    carbon_line = (
        alt.Chart(chart_data)
        .mark_line(point=True, color="#0f766e", strokeWidth=3)
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
            "Estimated emissions in overall historical best window",
            f"{recommended_emissions:.2f} kg CO₂e",
            delta=emissions_difference_label(carbon_saving),
            delta_color="off",
        )
        if cost_saving > 0 and carbon_saving > 0:
            st.success(
                f"Historical suggestion: run **{device.lower()}** during **{best_label}**. "
                "In this comparison, it reduces both estimated cost and emissions."
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
        "Estimates multiply historical hourly intensity by the entered kWh. They do not include tariffs, taxes, standby use, or appliance efficiency."
    )

with patterns_tab:
    st.subheader("When do low-price and low-carbon conditions overlap?")
    weekday_order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    heatmap_data = (
        df.assign(weekday=df["timestamp_local"].dt.day_name())
        .groupby(["weekday", "hour_local"], as_index=False)[
            "is_cheap_and_low_carbon"
        ]
        .mean()
    )
    heatmap = (
        alt.Chart(heatmap_data)
        .mark_rect(cornerRadius=2)
        .encode(
            x=alt.X("hour_local:O", title="Amsterdam local hour"),
            y=alt.Y("weekday:N", sort=weekday_order, title=None),
            color=alt.Color(
                "is_cheap_and_low_carbon:Q",
                title="Overlap rate",
                scale=alt.Scale(scheme="tealblues"),
                legend=alt.Legend(format=".0%"),
            ),
            tooltip=[
                alt.Tooltip("weekday:N", title="Day"),
                alt.Tooltip("hour_local:O", title="Hour"),
                alt.Tooltip(
                    "is_cheap_and_low_carbon:Q",
                    title="Cheap & low-carbon rate",
                    format=".1%",
                ),
            ],
        )
        .properties(height=300)
    )
    st.altair_chart(heatmap, width="stretch")

    with st.expander("Methodology and limitations", expanded=True):
        st.markdown(
            f"""
            - **Scope:** {len(df):,} validated hourly observations, from
              {df['date_local'].min().strftime('%d %B %Y')} to
              {df['date_local'].max().strftime('%d %B %Y')}.
            - **Price:** Dutch hourly electricity-price observations.
            - **Carbon:** estimated with Wattnet's methodology and global
              life-cycle emission factors, expressed as gCO₂e/kWh.
            - **Low price / low carbon:** bottom quartile of each measure in
              the validated dataset.
            - **Recommendation:** a four-hour historical window. Balanced mode
              gives equal weight to normalized average price and carbon intensity.
            - **Important:** this is an educational prototype, not live advice or
              a forecast. Results mainly represent late spring and summer 2026.
            """
        )
