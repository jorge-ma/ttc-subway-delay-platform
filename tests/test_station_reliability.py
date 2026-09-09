"""Tests for TTC station reliability queries and API validation."""

import os
from datetime import date, datetime, time
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.main import app
from api.reliability import fetch_station_reliability
from database.connection import create_database_engine
from database.models import DelayEvent, IngestionRun


TEST_DATABASE_NAME = "ttc_reliability_v2_test"
client = TestClient(app)


@pytest.fixture
def station_engine():
    """Create isolated station data in the migrated test database."""

    if os.getenv("POSTGRES_DB") != TEST_DATABASE_NAME:
        pytest.fail(
            "Station integration tests require "
            f"POSTGRES_DB={TEST_DATABASE_NAME}"
        )

    engine = create_database_engine()

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM delay_events"))
        connection.execute(text("DELETE FROM ingestion_runs"))

    with Session(engine) as session, session.begin():
        run = IngestionRun(
            source_file="station-test.csv",
            source_rows=3,
            valid_rows=3,
            rejected_rows=0,
            duplicate_rows=0,
            inserted_rows=3,
            status="completed",
            completed_at=datetime.now(),
        )
        session.add(run)
        session.flush()

        records = (
            (1, "YU", "BLOOR STATION", 8, "a"),
            (2, "YU", "BLOOR STATION", 4, "b"),
            (3, "BD", "KIPLING STATION", 5, "c"),
        )

        for source_id, line, station, delay, key in records:
            session.add(
                DelayEvent(
                    ingestion_run_id=run.id,
                    source_id=source_id,
                    date=date(2026, 1, source_id),
                    time=time(8, 30),
                    day="Thursday",
                    station=station,
                    code="MUSAN",
                    min_delay=delay,
                    min_gap=delay + 4,
                    bound="N",
                    line=line,
                    vehicle=5200 + source_id,
                    event_datetime=datetime(2026, 1, source_id, 8, 30),
                    record_key=key * 64,
                )
            )

    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM delay_events"))
            connection.execute(text("DELETE FROM ingestion_runs"))

        engine.dispose()


def test_station_query_groups_and_orders_by_delay(station_engine):
    results = fetch_station_reliability(station_engine, limit=10)

    assert [(item.station, item.line) for item in results] == [
        ("BLOOR STATION", "YU"),
        ("KIPLING STATION", "BD"),
    ]
    assert results[0].total_events == 2
    assert results[0].total_delay_minutes == 12
    assert results[0].average_delay_minutes == 6.0
    assert results[0].maximum_delay_minutes == 8


def test_station_query_filters_by_line(station_engine):
    results = fetch_station_reliability(
        station_engine,
        limit=10,
        line="BD",
    )

    assert len(results) == 1
    assert results[0].station == "KIPLING STATION"
    assert results[0].line == "BD"


@patch("api.main.fetch_station_reliability")
@patch("api.main.create_database_engine")
def test_station_endpoint_normalizes_line_filter(
    create_engine_mock,
    fetch_station_mock,
):
    engine = Mock()
    create_engine_mock.return_value = engine
    fetch_station_mock.return_value = []

    response = client.get(
        "/api/v1/reliability/stations?line=bd&limit=5"
    )

    assert response.status_code == 200
    assert response.json() == []
    fetch_station_mock.assert_called_once_with(
        engine,
        limit=5,
        line="BD",
    )
    engine.dispose.assert_called_once_with()


@pytest.mark.parametrize(
    "query",
    (
        "limit=0",
        "limit=101",
        f"line={'X' * 21}",
    ),
)
def test_station_endpoint_rejects_invalid_parameters(query):
    response = client.get(f"/api/v1/reliability/stations?{query}")

    assert response.status_code == 422


@patch("api.main.create_database_engine")
def test_station_endpoint_when_database_is_unavailable(create_engine_mock):
    create_engine_mock.side_effect = RuntimeError("unavailable")

    response = client.get("/api/v1/reliability/stations")

    assert response.status_code == 503
