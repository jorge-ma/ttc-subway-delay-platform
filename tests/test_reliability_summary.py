"""Tests for the TTC reliability summary query and API endpoint."""

import os
from datetime import date, datetime, time
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.main import app
from api.reliability import fetch_reliability_summary
from database.connection import create_database_engine
from database.models import DelayEvent, IngestionRun


TEST_DATABASE_NAME = "ttc_reliability_v2_test"
client = TestClient(app)


@pytest.fixture
def summary_engine():
    """Create isolated TTC events in the migrated test database."""

    database_name = os.getenv("POSTGRES_DB")

    if database_name != TEST_DATABASE_NAME:
        pytest.fail(
            "Summary integration tests must use "
            f"POSTGRES_DB={TEST_DATABASE_NAME}; got {database_name!r}"
        )

    engine = create_database_engine()

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM delay_events"))
        connection.execute(text("DELETE FROM ingestion_runs"))

    with Session(engine) as session, session.begin():
        ingestion_run = IngestionRun(
            source_file="summary-test.csv",
            source_rows=2,
            valid_rows=2,
            rejected_rows=0,
            duplicate_rows=0,
            inserted_rows=2,
            status="completed",
            completed_at=datetime.now(),
        )
        session.add(ingestion_run)
        session.flush()

        session.add_all(
            [
                DelayEvent(
                    ingestion_run_id=ingestion_run.id,
                    source_id=1,
                    date=date(2026, 1, 1),
                    time=time(8, 30),
                    day="Thursday",
                    station="BLOOR STATION",
                    code="MUSAN",
                    min_delay=5,
                    min_gap=9,
                    bound="N",
                    line="YU",
                    vehicle=5227,
                    event_datetime=datetime(2026, 1, 1, 8, 30),
                    record_key="a" * 64,
                ),
                DelayEvent(
                    ingestion_run_id=ingestion_run.id,
                    source_id=2,
                    date=date(2026, 1, 2),
                    time=time(9, 45),
                    day="Friday",
                    station="KIPLING STATION",
                    code="MUIR",
                    min_delay=3,
                    min_gap=6,
                    bound="E",
                    line="BD",
                    vehicle=5001,
                    event_datetime=datetime(2026, 1, 2, 9, 45),
                    record_key="b" * 64,
                ),
            ]
        )

    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM delay_events"))
            connection.execute(text("DELETE FROM ingestion_runs"))

        engine.dispose()


def test_summary_query_calculates_expected_metrics(summary_engine):
    summary = fetch_reliability_summary(summary_engine)

    assert summary.total_events == 2
    assert summary.total_delay_minutes == 8
    assert summary.average_delay_minutes == 4.0
    assert summary.maximum_delay_minutes == 5
    assert summary.affected_stations == 2
    assert summary.first_event_at == datetime(2026, 1, 1, 8, 30)
    assert summary.last_event_at == datetime(2026, 1, 2, 9, 45)


@patch("api.main.fetch_reliability_summary")
@patch("api.main.create_database_engine")
def test_summary_endpoint(create_engine_mock, fetch_summary_mock):
    engine = Mock()
    create_engine_mock.return_value = engine
    fetch_summary_mock.return_value = {
        "total_events": 2,
        "total_delay_minutes": 8,
        "average_delay_minutes": 4.0,
        "maximum_delay_minutes": 5,
        "affected_stations": 2,
        "first_event_at": "2026-01-01T08:30:00",
        "last_event_at": "2026-01-02T09:45:00",
    }

    response = client.get("/api/v1/reliability/summary")

    assert response.status_code == 200
    assert response.json()["total_events"] == 2
    assert response.json()["total_delay_minutes"] == 8
    engine.dispose.assert_called_once_with()


@patch("api.main.create_database_engine")
def test_summary_endpoint_when_database_is_unavailable(create_engine_mock):
    create_engine_mock.side_effect = RuntimeError("unavailable")

    response = client.get("/api/v1/reliability/summary")

    assert response.status_code == 503
    assert response.json() == {
        "detail": "Reliability data is temporarily unavailable"
    }
