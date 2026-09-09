"""Integration tests for persistence of cleaned TTC records."""

import os

import pandas as pd
import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import DataError
from sqlalchemy.orm import Session

from database.connection import create_database_engine
from database.loader import persist_cleaning_result
from database.models import DelayEvent, IngestionRun
from ingestion.cleaning import CleaningResult


TEST_DATABASE_NAME = "ttc_reliability_v2_test"


def make_result(code: str = "MUSAN") -> CleaningResult:
    """Return one representative cleaned TTC record."""

    valid_data = pd.DataFrame(
        [
            {
                "source_id": 1,
                "date": "2025-01-01",
                "time": "02:10",
                "day": "Wednesday",
                "station": "BATHURST STATION",
                "code": code,
                "min_delay": 5,
                "min_gap": 9,
                "bound": "E",
                "line": "BD",
                "vehicle": 5227,
                "event_datetime": pd.Timestamp("2025-01-01 02:10"),
                "record_key": "a" * 64,
            }
        ]
    )

    return CleaningResult(
        source_rows=1,
        valid_data=valid_data,
        rejected_data=pd.DataFrame(),
        duplicate_data=pd.DataFrame(),
    )


@pytest.fixture
def database_engine():
    """Provide the isolated V2 test database and clean it afterward."""

    database_name = os.getenv("POSTGRES_DB")

    if database_name != TEST_DATABASE_NAME:
        pytest.fail(
            "Database integration tests must use "
            f"POSTGRES_DB={TEST_DATABASE_NAME}; got {database_name!r}"
        )

    engine = create_database_engine()

    with engine.connect() as connection:
        migrated_revision = connection.scalar(
            text("SELECT version_num FROM alembic_version")
        )

    if migrated_revision is None:
        pytest.fail("The V2 test database has not been migrated")

    with engine.begin() as connection:
        connection.execute(text("DELETE FROM delay_events"))
        connection.execute(text("DELETE FROM ingestion_runs"))

    try:
        yield engine
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM delay_events"))
            connection.execute(text("DELETE FROM ingestion_runs"))

        engine.dispose()


def test_first_load_inserts_event_and_completes_run(database_engine):
    result = persist_cleaning_result(
        engine=database_engine,
        source_file="sample.csv",
        result=make_result(),
    )

    assert result.inserted_rows == 1
    assert result.duplicate_rows == 0

    with Session(database_engine) as session:
        event = session.scalar(
            select(DelayEvent).where(
                DelayEvent.ingestion_run_id
                == result.ingestion_run_id
            )
        )
        run = session.get(IngestionRun, result.ingestion_run_id)

    assert event is not None
    assert event.station == "BATHURST STATION"
    assert event.ingestion_run_id == result.ingestion_run_id
    assert run is not None
    assert run.status == "completed"
    assert run.inserted_rows == 1
    assert run.completed_at is not None


def test_repeated_load_is_idempotent(database_engine):
    cleaning_result = make_result()

    first_result = persist_cleaning_result(
        engine=database_engine,
        source_file="sample.csv",
        result=cleaning_result,
    )
    second_result = persist_cleaning_result(
        engine=database_engine,
        source_file="sample.csv",
        result=cleaning_result,
    )

    assert first_result.inserted_rows == 1
    assert first_result.duplicate_rows == 0
    assert second_result.inserted_rows == 0
    assert second_result.duplicate_rows == 1

    with Session(database_engine) as session:
        event_count = session.scalar(
            select(func.count()).select_from(DelayEvent)
        )
        runs = session.scalars(
            select(IngestionRun).order_by(IngestionRun.id)
        ).all()

    assert event_count == 1
    assert len(runs) == 2
    assert all(run.status == "completed" for run in runs)


def test_failed_load_is_recorded(database_engine):
    invalid_result = make_result(code="X" * 21)

    with pytest.raises(DataError):
        persist_cleaning_result(
            engine=database_engine,
            source_file="invalid.csv",
            result=invalid_result,
        )

    with Session(database_engine) as session:
        failed_run = session.scalar(
            select(IngestionRun)
            .where(IngestionRun.status == "failed")
            .order_by(IngestionRun.id.desc())
        )
        event_count = session.scalar(
            select(func.count()).select_from(DelayEvent)
        )

    assert failed_run is not None
    assert failed_run.error_message
    assert failed_run.completed_at is not None
    assert event_count == 0
