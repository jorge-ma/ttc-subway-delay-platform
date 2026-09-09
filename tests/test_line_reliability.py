"""Tests for TTC line reliability queries and API validation."""

import os
from datetime import date, datetime, time
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.main import app
from api.reliability import fetch_line_reliability
from database.connection import create_database_engine
from database.models import DelayEvent, IngestionRun


TEST_DATABASE_NAME = "ttc_reliability_v2_test"
client = TestClient(app)


@pytest.fixture
def line_engine():
    """Create isolated line data in the migrated test database."""

    database_name = os.getenv("POSTGRES_DB")

    if database_name != TEST_DATABASE_NAME:
        pytest.fail(
            "Line integration tests must use "
            f"POSTGRES_DB={TEST_DATABASE_NAME}; got {database_name!r}"
        )

    engine = create_database_engine()

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM delay_events"))
        connection.execute(text("DELETE FROM ingestion_runs"))

    with Session(engine) as session, session.begin():
        run = IngestionRun(
            source_file="line-test.csv",
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
            (2, "YU", "DUNDAS STATION", 4, "b"),
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


def test_line_query_groups_and_orders_by_total_delay(line_engine):
    results = fetch_line_reliability(line_engine, limit=10)

    assert [result.line for result in results] == ["YU", "BD"]
    assert results[0].total_events == 2
    assert results[0].total_delay_minutes == 12
    assert results[0].average_delay_minutes == 6.0
    assert results[0].maximum_delay_minutes == 8
    assert results[0].affected_stations == 2
    assert results[1].total_delay_minutes == 5


@patch("api.main.fetch_line_reliability")
@patch("api.main.create_database_engine")
def test_line_endpoint_passes_validated_limit(
    create_engine_mock,
    fetch_lines_mock,
):
    engine = Mock()
    create_engine_mock.return_value = engine
    fetch_lines_mock.return_value = []

    response = client.get("/api/v1/reliability/lines?limit=5")

    assert response.status_code == 200
    assert response.json() == []
    fetch_lines_mock.assert_called_once_with(engine, limit=5)
    engine.dispose.assert_called_once_with()


@pytest.mark.parametrize("limit", [0, 101])
def test_line_endpoint_rejects_invalid_limit(limit):
    response = client.get(
        "/api/v1/reliability/lines",
        params={"limit": limit},
    )

    assert response.status_code == 422


@patch("api.main.create_database_engine")
def test_line_endpoint_when_database_is_unavailable(create_engine_mock):
    create_engine_mock.side_effect = RuntimeError("unavailable")

    response = client.get("/api/v1/reliability/lines")

    assert response.status_code == 503
