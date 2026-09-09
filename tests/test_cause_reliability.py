"""Tests for TTC incident-cause reliability queries and API validation."""

import os
from datetime import date, datetime, time
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.main import app
from api.reliability import fetch_cause_reliability
from database.connection import create_database_engine
from database.models import DelayEvent, IngestionRun


TEST_DATABASE_NAME = "ttc_reliability_v2_test"
client = TestClient(app)


@pytest.fixture
def cause_engine():
    """Create isolated incident-code data in the test database."""

    if os.getenv("POSTGRES_DB") != TEST_DATABASE_NAME:
        pytest.fail(
            "Cause integration tests require "
            f"POSTGRES_DB={TEST_DATABASE_NAME}"
        )

    engine = create_database_engine()

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM delay_events"))
        connection.execute(text("DELETE FROM ingestion_runs"))

    with Session(engine) as session, session.begin():
        run = IngestionRun(
            source_file="cause-test.csv",
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
            (1, "YU", "BLOOR STATION", "SUDP", 10, "a"),
            (2, "BD", "KIPLING STATION", "SUDP", 2, "b"),
            (3, "BD", "ISLINGTON STATION", "MUIR", 5, "c"),
        )

        for source_id, line, station, code, delay, key in records:
            session.add(
                DelayEvent(
                    ingestion_run_id=run.id,
                    source_id=source_id,
                    date=date(2026, 1, source_id),
                    time=time(8, 30),
                    day="Thursday",
                    station=station,
                    code=code,
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


def test_cause_query_groups_and_orders_by_delay(cause_engine):
    results = fetch_cause_reliability(cause_engine, limit=10)

    assert [item.code for item in results] == ["SUDP", "MUIR"]
    assert results[0].total_events == 2
    assert results[0].total_delay_minutes == 12
    assert results[0].average_delay_minutes == 6.0
    assert results[0].maximum_delay_minutes == 10
    assert results[0].affected_stations == 2


def test_cause_query_filters_by_line(cause_engine):
    results = fetch_cause_reliability(
        cause_engine,
        limit=10,
        line="BD",
    )

    assert [item.code for item in results] == ["MUIR", "SUDP"]
    assert [item.total_delay_minutes for item in results] == [5, 2]


@patch("api.main.fetch_cause_reliability")
@patch("api.main.create_database_engine")
def test_cause_endpoint_normalizes_line_filter(
    create_engine_mock,
    fetch_cause_mock,
):
    engine = Mock()
    create_engine_mock.return_value = engine
    fetch_cause_mock.return_value = []

    response = client.get(
        "/api/v1/reliability/causes?line=bd&limit=5"
    )

    assert response.status_code == 200
    assert response.json() == []
    fetch_cause_mock.assert_called_once_with(
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
def test_cause_endpoint_rejects_invalid_parameters(query):
    response = client.get(f"/api/v1/reliability/causes?{query}")

    assert response.status_code == 422


@patch("api.main.create_database_engine")
def test_cause_endpoint_when_database_is_unavailable(create_engine_mock):
    create_engine_mock.side_effect = RuntimeError("unavailable")

    response = client.get("/api/v1/reliability/causes")

    assert response.status_code == 503
