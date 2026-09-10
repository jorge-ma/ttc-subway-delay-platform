"""Streamlit dashboard for TTC reliability statistics."""

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
    "SRT": "Line 3 — Scarborough",
    "SHP": "Line 4 — Sheppard",
}


st.set_page_config(
    page_title="TTC Reliability Monitor",
    page_icon="🚇",
    layout="wide",
)

st.title("TTC Reliability Monitor")
st.caption(
    "Reliability statistics generated from TTC subway delay data"
)


@st.cache_data(ttl=60)
def load_summary():
    """Load system-wide summary statistics."""

    return get_summary()


@st.cache_data(ttl=60)
def load_lines():
    """Load reliability statistics for all lines."""

    return get_lines(limit=100)


@st.cache_data(ttl=60)
def load_monthly(line=None):
    """Load monthly statistics."""

    return get_monthly(line=line)


@st.cache_data(ttl=60)
def load_stations(line=None):
    """Load the highest-impact stations."""

    return get_stations(line=line, limit=10)


@st.cache_data(ttl=60)
def load_causes(line=None):
    """Load the highest-impact incident causes."""

    return get_causes(line=line, limit=10)


try:
    summary = load_summary()
    all_line_results = load_lines()

except APIClientError as error:
    st.error("The TTC reliability API is currently unavailable.")
    st.code(str(error))
    st.stop()


# Keep non-subway and network-wide values out of the selector and chart.
line_results = [
    item
    for item in all_line_results
    if item.get("line") in SUBWAY_LINES
]

line_names = [
    line
    for line in SUBWAY_LINES
    if any(item["line"] == line for item in line_results)
]

selected_option = st.sidebar.selectbox(
    "TTC subway line",
    ["All subway lines", *line_names],
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

st.sidebar.caption(
    "Dashboard data is retrieved from the FastAPI service."
)


try:
    monthly_results = load_monthly(selected_line)
    station_results = load_stations(selected_line)
    cause_results = load_causes(selected_line)

except APIClientError as error:
    st.error("Unable to load filtered dashboard data.")
    st.code(str(error))
    st.stop()


st.subheader("System overview")

first_row = st.columns(4)

first_row[0].metric(
    "Delay events",
    f"{summary['total_events']:,}",
)
first_row[1].metric(
    "Delay minutes",
    f"{summary['total_delay_minutes']:,}",
)
first_row[2].metric(
    "Average delay",
    f"{summary['average_delay_minutes']:.2f} min",
)
first_row[3].metric(
    "Maximum delay",
    f"{summary['maximum_delay_minutes']:,} min",
)

second_row = st.columns(3)

second_row[0].metric(
    "Affected stations",
    f"{summary['affected_stations']:,}",
)
second_row[1].metric(
    "First event",
    summary["first_event_at"][:10],
)
second_row[2].metric(
    "Last event",
    summary["last_event_at"][:10],
)


st.divider()
st.subheader("Monthly delay trend")

monthly_frame = pd.DataFrame(monthly_results)

if monthly_frame.empty:
    st.info("No monthly data is available for this selection.")
else:
    monthly_frame["month"] = pd.to_datetime(
        monthly_frame["month"],
        format="%Y-%m",
    )
    monthly_frame = monthly_frame.sort_values("month")

    st.line_chart(
        monthly_frame,
        x="month",
        y="total_delay_minutes",
    )

    st.dataframe(
        monthly_frame[
            [
                "month",
                "total_events",
                "total_delay_minutes",
                "average_delay_minutes",
                "maximum_delay_minutes",
            ]
        ],
        hide_index=True,
        use_container_width=True,
    )


st.divider()
st.subheader("Subway line comparison")

line_frame = pd.DataFrame(line_results)

if line_frame.empty:
    st.info("No subway-line statistics are available.")
else:
    line_frame = line_frame.sort_values(
        "total_delay_minutes",
        ascending=False,
    )
    line_frame["line_name"] = line_frame["line"].map(
        SUBWAY_LINES
    )

    st.bar_chart(
        line_frame,
        x="line_name",
        y="total_delay_minutes",
    )

    st.dataframe(
        line_frame[
            [
                "line_name",
                "total_events",
                "total_delay_minutes",
                "average_delay_minutes",
                "maximum_delay_minutes",
            ]
        ].rename(columns={"line_name": "line"}),
        hide_index=True,
        use_container_width=True,
    )


st.divider()
ranking_columns = st.columns(2)

with ranking_columns[0]:
    st.subheader("Top affected stations")

    station_frame = pd.DataFrame(station_results)

    if station_frame.empty:
        st.info("No station data is available.")
    else:
        st.bar_chart(
            station_frame,
            x="station",
            y="total_delay_minutes",
        )
        st.dataframe(
            station_frame[
                [
                    "station",
                    "total_events",
                    "total_delay_minutes",
                    "average_delay_minutes",
                ]
            ],
            hide_index=True,
            use_container_width=True,
        )


with ranking_columns[1]:
    st.subheader("Top incident causes")

    cause_frame = pd.DataFrame(cause_results)

    if cause_frame.empty:
        st.info("No incident-cause data is available.")
    else:
        st.bar_chart(
            cause_frame,
            x="code",
            y="total_delay_minutes",
        )
        st.dataframe(
            cause_frame[
                [
                    "code",
                    "total_events",
                    "total_delay_minutes",
                    "average_delay_minutes",
                ]
            ],
            hide_index=True,
            use_container_width=True,
        )

