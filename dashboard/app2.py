from datetime import datetime

import altair as alt
import streamlit as st

from dashboard.api_client import TTCAPIError, create_api_client
from dashboard.chart_data import (
    get_available_line_filters,
    prepare_cause_chart_data,
    prepare_line_chart_data,
    prepare_monthly_chart_data,
    prepare_station_chart_data,
)


st.set_page_config(
    page_title="TTC Reliability Monitor",
    page_icon="🚇",
    layout="wide",
)


@st.cache_data(ttl=300)
def load_summary() -> dict:
    """Retrieve summary data and cache it for five minutes."""

    return create_api_client().get_summary()


@st.cache_data(ttl=300)
def load_lines() -> list[dict]:
    """Retrieve line statistics for comparison and filtering."""

    return create_api_client().get_lines(limit=100)


@st.cache_data(ttl=300)
def load_monthly(line: str | None) -> list[dict]:
    """Retrieve monthly statistics for all data or one line."""

    return create_api_client().get_monthly(line=line)


@st.cache_data(ttl=300)
def load_stations(limit: int, line: str | None) -> list[dict]:
    """Retrieve the highest-delay station/location records."""

    return create_api_client().get_stations(limit=limit, line=line)


@st.cache_data(ttl=300)
def load_causes(limit: int, line: str | None) -> list[dict]:
    """Retrieve the highest-delay incident-code records."""

    return create_api_client().get_causes(limit=limit, line=line)


def format_timestamp(value: str | None) -> str:
    """Convert an API timestamp into a readable date."""

    if value is None:
        return "Not available"

    return datetime.fromisoformat(value).strftime("%B %d, %Y")


def create_ranking_chart(
    frame,
    category: str,
    category_title: str,
) -> alt.Chart:
    """Create a horizontal total-delay ranking chart."""

    return (
        alt.Chart(frame)
        .mark_bar()
        .encode(
            x=alt.X(
                "total_delay_minutes:Q",
                title="Total delay minutes",
            ),
            y=alt.Y(
                f"{category}:N",
                sort="-x",
                title=category_title,
            ),
            tooltip=[
                alt.Tooltip(f"{category}:N", title=category_title),
                alt.Tooltip(
                    "total_events:Q",
                    title="Events",
                    format=",",
                ),
                alt.Tooltip(
                    "total_delay_minutes:Q",
                    title="Delay minutes",
                    format=",",
                ),
                alt.Tooltip(
                    "average_delay_minutes:Q",
                    title="Average delay",
                    format=".2f",
                ),
                alt.Tooltip(
                    "maximum_delay_minutes:Q",
                    title="Maximum delay",
                    format=",",
                ),
            ],
        )
        .properties(height=max(280, len(frame) * 28))
    )


def render_dashboard() -> None:
    """Render the TTC reliability summary page."""

    st.title("TTC Reliability Monitor")
    st.caption(
        "Reliability insights calculated from City of Toronto "
        "TTC subway-delay records."
    )

    if st.button("Refresh data"):
        st.cache_data.clear()

    try:
        summary = load_summary()
        line_records = load_lines()
    except TTCAPIError as error:
        st.error(
            "The dashboard cannot reach the TTC Reliability API. "
            "Confirm that FastAPI is running and try again."
        )
        st.code(str(error))
        st.stop()

    line_names = get_available_line_filters(line_records)
    selected_line = st.sidebar.selectbox(
        "Monthly trend line",
        options=["All lines", *line_names],
    )
    line_filter = None if selected_line == "All lines" else selected_line
    result_limit = st.sidebar.slider(
        "Ranking results",
        min_value=5,
        max_value=25,
        value=10,
        step=5,
    )

    try:
        monthly_records = load_monthly(line_filter)
        station_records = load_stations(result_limit, line_filter)
        cause_records = load_causes(result_limit, line_filter)
    except TTCAPIError as error:
        st.error("Dashboard analytics data is currently unavailable.")
        st.code(str(error))
        st.stop()

    columns = st.columns(5)

    columns[0].metric(
        "Delay events",
        f"{summary['total_events']:,}",
    )
    columns[1].metric(
        "Delay minutes",
        f"{summary['total_delay_minutes']:,}",
    )
    columns[2].metric(
        "Average delay",
        f"{summary['average_delay_minutes']:.2f} min",
    )
    columns[3].metric(
        "Maximum delay",
        f"{summary['maximum_delay_minutes']:,} min",
    )
    columns[4].metric(
        "Affected locations",
        f"{summary['affected_stations']:,}",
    )

    first_event = format_timestamp(summary.get("first_event_at"))
    last_event = format_timestamp(summary.get("last_event_at"))

    st.info(f"Dataset coverage: {first_event} to {last_event}")

    st.header("Delay by TTC line")
    st.caption(
        "Recognized subway line codes are ranked by accumulated "
        "delay minutes. Other raw source labels remain in the database."
    )

    line_frame = prepare_line_chart_data(line_records).head(10)

    if line_frame.empty:
        st.warning("No line reliability data is available.")
    else:
        st.bar_chart(
            line_frame,
            x="line",
            y="total_delay_minutes",
            x_label="TTC line",
            y_label="Total delay minutes",
        )

    st.header("Monthly reliability trend")
    st.caption(
        "Use the sidebar to display the network-wide trend or filter "
        "the chart to one source line label."
    )

    monthly_frame = prepare_monthly_chart_data(monthly_records)

    if monthly_frame.empty:
        st.warning("No monthly reliability data is available.")
    else:
        delay_tab, events_tab, average_tab = st.tabs(
            ["Delay minutes", "Event count", "Average delay"]
        )

        with delay_tab:
            st.line_chart(
                monthly_frame,
                x="month",
                y="total_delay_minutes",
                x_label="Month",
                y_label="Total delay minutes",
            )

        with events_tab:
            st.line_chart(
                monthly_frame,
                x="month",
                y="total_events",
                x_label="Month",
                y_label="Delay events",
            )

        with average_tab:
            st.line_chart(
                monthly_frame,
                x="month",
                y="average_delay_minutes",
                x_label="Month",
                y_label="Average delay minutes",
            )

    st.header("Station and incident rankings")
    st.caption(
        "Rankings follow the selected line and result limit in the "
        "sidebar. Incident codes are shown exactly as published."
    )

    station_frame = prepare_station_chart_data(station_records)
    cause_frame = prepare_cause_chart_data(cause_records)
    station_tab, cause_tab = st.tabs(
        ["Delayed stations", "Incident causes"]
    )

    with station_tab:
        if station_frame.empty:
            st.warning("No station reliability data is available.")
        else:
            st.altair_chart(
                create_ranking_chart(
                    station_frame,
                    category="station",
                    category_title="Station or location",
                ),
                use_container_width=True,
            )
            st.dataframe(
                station_frame.rename(
                    columns={
                        "station": "Station or location",
                        "total_events": "Events",
                        "total_delay_minutes": "Delay minutes",
                        "average_delay_minutes": "Average delay",
                        "maximum_delay_minutes": "Maximum delay",
                    }
                ),
                hide_index=True,
            )

    with cause_tab:
        if cause_frame.empty:
            st.warning("No incident-code data is available.")
        else:
            st.altair_chart(
                create_ranking_chart(
                    cause_frame,
                    category="code",
                    category_title="Incident code",
                ),
                use_container_width=True,
            )
            st.dataframe(
                cause_frame.rename(
                    columns={
                        "code": "Incident code",
                        "total_events": "Events",
                        "total_delay_minutes": "Delay minutes",
                        "average_delay_minutes": "Average delay",
                        "maximum_delay_minutes": "Maximum delay",
                        "affected_stations": "Affected locations",
                    }
                ),
                hide_index=True,
            )


if __name__ == "__main__":
    render_dashboard()

