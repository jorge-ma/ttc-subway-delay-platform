"""Rider-focused Streamlit dashboard for TTC subway reliability."""

import calendar

import pandas as pd
import streamlit as st

from dashboard.api_client import (
    APIClientError,
    get_causes,
    get_lines,
    get_monthly,
    get_stations,
    get_summary,
)


SUBWAY_LINES = {
    "YU": "Line 1 — Yonge-University",
    "BD": "Line 2 — Bloor-Danforth",
    "SHP": "Line 4 — Sheppard",
}


def categorize_delay_cause(description: str) -> str:
    """Group TTC descriptions into rider-friendly categories."""

    text = description.upper()

    medical_terms = (
        "INJURED",
        "ILL CUSTOMER",
        "MEDICAL",
    )

    customer_security_terms = (
        "PATRON",
        "SECURITY",
        "ASSAULT",
        "UNAUTHORIZED",
        "POLICE",
        "PAA",
    )

    weather_terms = (
        "WEATHER",
        "ICE",
        "SNOW",
        "STORM",
        "FORCE MAJEURE",
    )

    infrastructure_terms = (
        "SIGNAL",
        "TRACK",
        "SWITCH",
        "POWER",
        "ATC",
        "RC&S",
        "ELEVATOR",
        "ESCALATOR",
    )

    mechanical_terms = (
        "BRAKE",
        "DOOR",
        "AIR CONDITIONING",
        "COMPRESSED AIR",
        "COUPLER",
        "PROPULSION",
        "CHOPPER",
        "BODY",
        "HIGH VOLTAGE",
        "LOW VOLTAGE",
    )

    operations_terms = (
        "TRANSPORTATION",
        "NO COLLECTOR",
        "OPTO",
        "CREW",
        "OPERATOR",
    )

    if any(term in text for term in medical_terms):
        return "Medical emergencies"

    if any(term in text for term in customer_security_terms):
        return "Customer & security incidents"

    if any(term in text for term in weather_terms):
        return "Weather"

    if any(term in text for term in infrastructure_terms):
        return "Infrastructure & signals"

    if any(term in text for term in mechanical_terms):
        return "Train / mechanical problems"

    if any(term in text for term in operations_terms):
        return "Operations"

    return "Other / uncategorized"


def calculate_percentage_change(
    current_value: float,
    previous_value: float,
) -> float | None:
    """Return percentage change between two values."""

    if previous_value == 0:
        return None

    return (
        (current_value - previous_value)
        / previous_value
        * 100
    )


st.set_page_config(
    page_title="TTC Reliability Monitor",
    page_icon="🚇",
    layout="wide",
)


# ---------------------------------------------------------------------------
# Data loading
# ---------------------------------------------------------------------------

@st.cache_data(ttl=60)
def load_summary():
    return get_summary()


@st.cache_data(ttl=60)
def load_lines():
    return get_lines(limit=100)


@st.cache_data(ttl=60)
def load_monthly(line=None):
    return get_monthly(line=line)


@st.cache_data(ttl=60)
def load_stations(line=None):
    return get_stations(line=line, limit=10)


@st.cache_data(ttl=60)
def load_causes(line=None):
    return get_causes(line=line, limit=10)


try:
    summary = load_summary()
    all_line_results = load_lines()

except APIClientError as error:
    st.error("TTC reliability data is temporarily unavailable.")
    st.caption(str(error))
    st.stop()


line_results = [
    item
    for item in all_line_results
    if item.get("line") in SUBWAY_LINES
]

available_lines = [
    line
    for line in SUBWAY_LINES
    if any(
        item["line"] == line
        for item in line_results
    )
]


# ---------------------------------------------------------------------------
# Header and filter
# ---------------------------------------------------------------------------

st.title("🚇 TTC Reliability Monitor")

st.write(
    "Explore where subway delays happen, what causes them, "
    "and how reliability changes over time."
)

selected_option = st.sidebar.selectbox(
    "Choose a subway line",
    ["All subway lines", *available_lines],
    format_func=lambda value: (
        value
        if value == "All subway lines"
        else SUBWAY_LINES[value]
    ),
)

selected_line = (
    None
    if selected_option == "All subway lines"
    else selected_option
)

selected_label = (
    "All subway lines"
    if selected_line is None
    else SUBWAY_LINES[selected_line]
)

st.sidebar.caption(
    "Use this filter to explore delays for a specific subway line."
)


try:
    monthly_results = load_monthly(selected_line)
    station_results = load_stations(selected_line)
    cause_results = load_causes(selected_line)

except APIClientError as error:
    st.error("Unable to load TTC delay information.")
    st.caption(str(error))
    st.stop()


# ---------------------------------------------------------------------------
# Overview
# ---------------------------------------------------------------------------

st.header("TTC delay overview")
st.caption(selected_label)

if selected_line is None:
    overview = {
        "total_events": summary["total_events"],
        "total_delay_minutes": summary["total_delay_minutes"],
        "average_delay_minutes": summary["average_delay_minutes"],
    }

else:
    line_record = next(
        (
            item
            for item in line_results
            if item["line"] == selected_line
        ),
        None,
    )

    if line_record is None:
        overview = {
            "total_events": 0,
            "total_delay_minutes": 0,
            "average_delay_minutes": 0,
        }
    else:
        overview = line_record


total_delay_hours = (
    overview["total_delay_minutes"] / 60
)

latest_date = (
    summary["last_event_at"][:10]
    if summary.get("last_event_at")
    else "Unavailable"
)

metric_columns = st.columns(4)

metric_columns[0].metric(
    "Delay events",
    f"{overview['total_events']:,}",
)

metric_columns[1].metric(
    "Total delay",
    f"{total_delay_hours:,.0f} hours",
)

metric_columns[2].metric(
    "Average delay",
    f"{overview['average_delay_minutes']:.1f} min",
)

metric_columns[3].metric(
    "Data through",
    latest_date,
)


# ---------------------------------------------------------------------------
# Prepare monthly data
# ---------------------------------------------------------------------------

monthly_frame = pd.DataFrame(monthly_results)

if not monthly_frame.empty:
    monthly_frame["month"] = pd.to_datetime(
        monthly_frame["month"],
        format="%Y-%m",
    )

    monthly_frame["delay_hours"] = (
        monthly_frame["total_delay_minutes"] / 60
    )

    monthly_frame = monthly_frame.sort_values(
        "month"
    ).reset_index(drop=True)


# ---------------------------------------------------------------------------
# Latest month comparison
# ---------------------------------------------------------------------------

if len(monthly_frame) >= 2:

    st.divider()
    st.header("What changed in the latest month?")

    current_month = monthly_frame.iloc[-1]
    previous_month = monthly_frame.iloc[-2]

    current_month_name = current_month["month"].strftime(
        "%B %Y"
    )

    previous_month_name = previous_month["month"].strftime(
        "%B %Y"
    )

    delay_change = calculate_percentage_change(
        current_month["delay_hours"],
        previous_month["delay_hours"],
    )

    event_change = calculate_percentage_change(
        current_month["total_events"],
        previous_month["total_events"],
    )

    average_change = calculate_percentage_change(
        current_month["average_delay_minutes"],
        previous_month["average_delay_minutes"],
    )

    st.write(
        f"Comparing **{current_month_name}** with "
        f"**{previous_month_name}**."
    )

    comparison_columns = st.columns(3)

    comparison_columns[0].metric(
        "Delay hours",
        f"{current_month['delay_hours']:,.1f}",
        (
            f"{delay_change:+.1f}%"
            if delay_change is not None
            else None
        ),
        delta_color="inverse",
    )

    comparison_columns[1].metric(
        "Delay events",
        f"{int(current_month['total_events']):,}",
        (
            f"{event_change:+.1f}%"
            if event_change is not None
            else None
        ),
        delta_color="inverse",
    )

    comparison_columns[2].metric(
        "Average delay",
        f"{current_month['average_delay_minutes']:.1f} min",
        (
            f"{average_change:+.1f}%"
            if average_change is not None
            else None
        ),
        delta_color="inverse",
    )

    if latest_date != "Unavailable":
        latest_timestamp = pd.Timestamp(latest_date)

        last_day_of_month = calendar.monthrange(
            latest_timestamp.year,
            latest_timestamp.month,
        )[1]

        if latest_timestamp.day < last_day_of_month:
            st.info(
                f"{current_month_name} is only partially represented "
                f"because the latest available data is through "
                f"{latest_timestamp.strftime('%B %d, %Y')}."
            )

    if delay_change is not None:
        if delay_change > 0:
            st.write(
                f"Recorded delay time **increased by "
                f"{abs(delay_change):.1f}%** compared with "
                f"{previous_month_name}."
            )

        elif delay_change < 0:
            st.write(
                f"Recorded delay time **decreased by "
                f"{abs(delay_change):.1f}%** compared with "
                f"{previous_month_name}."
            )

        else:
            st.write(
                f"Recorded delay time was unchanged compared with "
                f"{previous_month_name}."
            )


# ---------------------------------------------------------------------------
# Monthly trend
# ---------------------------------------------------------------------------

st.divider()
st.header("How are delays changing?")

st.write(
    "Monthly accumulated delay shows whether riders are experiencing "
    "more or less disruption over time."
)

if monthly_frame.empty:
    st.info(
        "No monthly delay data is available for this selection."
    )

else:
    st.line_chart(
        monthly_frame,
        x="month",
        y="delay_hours",
        x_label="Month",
        y_label="Delay hours",
    )

    with st.expander("View monthly details"):

        detail_frame = monthly_frame[
            [
                "month",
                "total_events",
                "delay_hours",
                "average_delay_minutes",
            ]
        ].copy()

        detail_frame["month"] = (
            detail_frame["month"]
            .dt.strftime("%Y-%m")
        )

        detail_frame["delay_hours"] = (
            detail_frame["delay_hours"]
            .round(1)
        )

        st.dataframe(
            detail_frame.rename(
                columns={
                    "month": "Month",
                    "total_events": "Delay events",
                    "delay_hours": "Delay hours",
                    "average_delay_minutes": "Average delay (min)",
                }
            ),
            hide_index=True,
            width="stretch",
        )


# ---------------------------------------------------------------------------
# Line comparison
# ---------------------------------------------------------------------------

if selected_line is None:

    st.divider()
    st.header("Which subway lines are most affected?")

    line_frame = pd.DataFrame(line_results)

    if line_frame.empty:
        st.info("No subway-line data is available.")

    else:
        line_frame["line_name"] = (
            line_frame["line"].map(
                SUBWAY_LINES
            )
        )

        line_frame["delay_hours"] = (
            line_frame["total_delay_minutes"] / 60
        )

        line_frame = line_frame.sort_values(
            "delay_hours",
            ascending=False,
        )

        st.bar_chart(
            line_frame,
            x="line_name",
            y="delay_hours",
            x_label="Subway line",
            y_label="Delay hours",
        )

        with st.expander("View line details"):

            line_detail = line_frame[
                [
                    "line_name",
                    "total_events",
                    "delay_hours",
                    "average_delay_minutes",
                ]
            ].copy()

            line_detail["delay_hours"] = (
                line_detail["delay_hours"]
                .round(1)
            )

            st.dataframe(
                line_detail.rename(
                    columns={
                        "line_name": "Subway line",
                        "total_events": "Delay events",
                        "delay_hours": "Delay hours",
                        "average_delay_minutes": "Average delay (min)",
                    }
                ),
                hide_index=True,
                width="stretch",
            )


# ---------------------------------------------------------------------------
# Stations
# ---------------------------------------------------------------------------

st.divider()
st.header("Where are delays concentrated?")

st.write(
    "Stations are ranked by the total amount of recorded delay."
)

station_frame = pd.DataFrame(station_results)

if station_frame.empty:
    st.info(
        "No station delay data is available for this selection."
    )

else:
    station_frame["delay_hours"] = (
        station_frame["total_delay_minutes"] / 60
    )

    station_frame = station_frame.sort_values(
        "delay_hours",
        ascending=False,
    )

    st.bar_chart(
        station_frame,
        x="station",
        y="delay_hours",
        x_label="Station",
        y_label="Delay hours",
    )

    with st.expander("View station details"):

        station_detail = station_frame[
            [
                "station",
                "total_events",
                "delay_hours",
                "average_delay_minutes",
            ]
        ].copy()

        station_detail["delay_hours"] = (
            station_detail["delay_hours"]
            .round(1)
        )

        st.dataframe(
            station_detail.rename(
                columns={
                    "station": "Station",
                    "total_events": "Delay events",
                    "delay_hours": "Delay hours",
                    "average_delay_minutes": "Average delay (min)",
                }
            ),
            hide_index=True,
            width="stretch",
        )


# ---------------------------------------------------------------------------
# Rider-friendly cause categories
# ---------------------------------------------------------------------------

st.divider()
st.header("Why are trains delayed?")

st.write(
    "TTC incident descriptions are grouped into simpler categories "
    "to make the major causes of delays easier to understand."
)

cause_frame = pd.DataFrame(cause_results)

if cause_frame.empty:
    st.info(
        "No delay-cause data is available for this selection."
    )

else:
    cause_frame["description"] = (
        cause_frame["description"]
        .fillna("Undocumented TTC code")
    )

    cause_frame["delay_hours"] = (
        cause_frame["total_delay_minutes"] / 60
    )

    cause_frame["category"] = (
        cause_frame["description"]
        .apply(categorize_delay_cause)
    )

    category_frame = (
        cause_frame
        .groupby(
            "category",
            as_index=False,
        )
        .agg(
            delay_hours=("delay_hours", "sum"),
            delay_events=("total_events", "sum"),
        )
        .sort_values(
            "delay_hours",
            ascending=False,
        )
    )

    category_frame["delay_hours"] = (
        category_frame["delay_hours"]
        .round(1)
    )

    st.bar_chart(
        category_frame,
        x="category",
        y="delay_hours",
        x_label="Cause category",
        y_label="Delay hours",
    )

    with st.expander(
        "View official TTC cause details"
    ):

        cause_detail = cause_frame[
            [
                "description",
                "category",
                "code",
                "total_events",
                "delay_hours",
                "average_delay_minutes",
            ]
        ].copy()

        cause_detail["delay_hours"] = (
            cause_detail["delay_hours"]
            .round(1)
        )

        cause_detail = cause_detail.sort_values(
            "delay_hours",
            ascending=False,
        )

        st.dataframe(
            cause_detail.rename(
                columns={
                    "description": "Official TTC description",
                    "category": "Rider-friendly category",
                    "code": "TTC code",
                    "total_events": "Delay events",
                    "delay_hours": "Delay hours",
                    "average_delay_minutes": "Average delay (min)",
                }
            ),
            hide_index=True,
            width="stretch",
        )

    st.caption(
        "Cause categories are simplified for this dashboard and are "
        "not official TTC classifications. Official TTC descriptions "
        "and codes are available in the details table."
    )


# ---------------------------------------------------------------------------
# About
# ---------------------------------------------------------------------------

st.divider()
st.subheader("About the data")

st.caption(
    f"Data through {latest_date}. "
    "Source: City of Toronto Open Data — TTC Subway Delay Data. "
    "Delay totals represent accumulated recorded delay and should "
    "not be interpreted as the delay experienced by a single rider."
)

