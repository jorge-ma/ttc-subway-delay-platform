"""Tests for monthly TTC reliability queries and API validation."""

import os
from datetime import date, datetime, time
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.orm import Session

from api.main import app
from api.reliability import fetch_monthly_reliability
from database.connection import create_database_engine
from database.models import DelayEvent, IngestionRun


TEST_DATABASE_NAME = "ttc_reliability_v2_test"
client = TestClient(app)


@pytest.fixture
def monthly_engine():
    """Create isolated monthly data in the migrated test database."""

    if os.getenv("POSTGRES_DB") != TEST_DATABASE_NAME:
        pytest.fail(
            "Monthly integration tests require "
            f"POSTGRES_DB={TEST_DATABASE_NAME}"
        )

    engine = create_database_engine()

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM delay_events"))
        connection.execute(text("DELETE FROM ingestion_runs"))

    with Session(engine) as session, session.begin():
        run = IngestionRun(
            source_file="monthly-test.csv",
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
            (1, datetime(2026, 1, 5, 8, 30), "YU", "BLOOR", 8, "a"),
            (2, datetime(2026, 1, 20, 9, 0), "BD", "KIPLING", 2, "b"),
            (3, datetime(2026, 2, 2, 10, 0), "BD", "ISLINGTON", 5, "c"),
        )

        for source_id, occurred_at, line, station, delay, key in records:
            session.add(
                DelayEvent(
                    ingestion_run_id=run.id,
                    source_id=source_id,
                    date=date(
                        occurred_at.year,
                        occurred_at.month,
                        occurred_at.day,
                    ),
                    time=time(occurred_at.hour, occurred_at.minute),
                    day=occurred_at.strftime("%A"),
                    station=f"{station} STATION",
                    code="MUSAN",
                    min_delay=delay,
                    min_gap=delay + 4,
                    bound="N",
                    line=line,
                    vehicle=5200 + source_id,
                    event_datetime=occurred_at,
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


def test_monthly_query_is_chronological(monthly_engine):
    results = fetch_monthly_reliability(monthly_engine)

    assert [item.month for item in results] == ["2026-01", "2026-02"]
    assert results[0].total_events == 2
    assert results[0].total_delay_minutes == 10
    assert results[0].average_delay_minutes == 5.0
    assert results[0].maximum_delay_minutes == 8
    assert results[0].affected_stations == 2
    assert results[1].total_delay_minutes == 5


def test_monthly_query_filters_by_line(monthly_engine):
    results = fetch_monthly_reliability(monthly_engine, line="BD")

    assert [item.month for item in results] == ["2026-01", "2026-02"]
    assert [item.total_delay_minutes for item in results] == [2, 5]


@patch("api.main.fetch_monthly_reliability")
@patch("api.main.create_database_engine")
def test_monthly_endpoint_normalizes_line_filter(
    create_engine_mock,
    fetch_monthly_mock,
):
    engine = Mock()
    create_engine_mock.return_value = engine
    fetch_monthly_mock.return_value = []

    response = client.get("/api/v1/reliability/monthly?line=bd")

    assert response.status_code == 200
    assert response.json() == []
    fetch_monthly_mock.assert_called_once_with(engine, line="BD")
    engine.dispose.assert_called_once_with()


@pytest.mark.parametrize("line", ("%20%20%20", "X" * 21))
def test_monthly_endpoint_rejects_invalid_line(line):
    response = client.get(f"/api/v1/reliability/monthly?line={line}")

    assert response.status_code == 422


@patch("api.main.create_database_engine")
def test_monthly_endpoint_when_database_is_unavailable(create_engine_mock):
    create_engine_mock.side_effect = RuntimeError("unavailable")

    response = client.get("/api/v1/reliability/monthly")

    assert response.status_code == 503
