"""Persist cleaned TTC delay records and ingestion audit information."""

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path

import pandas as pd
from sqlalchemy import insert, select
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from database.models import DelayEvent, IngestionRun
from ingestion.cleaning import CleaningResult


KEY_QUERY_BATCH_SIZE = 1_000


@dataclass(frozen=True)
class PersistenceResult:
    """Summarize one completed database load."""

    ingestion_run_id: int
    inserted_rows: int
    duplicate_rows: int


def _chunks(values: list[str], size: int) -> list[list[str]]:
    """Split values into bounded batches for database queries."""

    return [
        values[position : position + size]
        for position in range(0, len(values), size)
    ]


def _as_date(value: object) -> date:
    """Convert a cleaned date value to a Python date."""

    return pd.Timestamp(value).date()


def _as_time(value: object) -> time:
    """Convert a cleaned time value to a Python time."""

    if isinstance(value, time):
        return value.replace(tzinfo=None)

    return datetime.strptime(str(value), "%H:%M").time()


def _as_datetime(value: object) -> datetime:
    """Convert a cleaned timestamp to a timezone-naive datetime."""

    timestamp = pd.Timestamp(value)

    if timestamp.tzinfo is not None:
        timestamp = timestamp.tz_localize(None)

    return timestamp.to_pydatetime()


def _event_mapping(row: pd.Series, ingestion_run_id: int) -> dict:
    """Convert one cleaned dataframe row into a DelayEvent mapping."""

    return {
        "ingestion_run_id": ingestion_run_id,
        "source_id": int(row["source_id"]),
        "date": _as_date(row["date"]),
        "time": _as_time(row["time"]),
        "day": str(row["day"]),
        "station": str(row["station"]),
        "code": str(row["code"]),
        "min_delay": int(row["min_delay"]),
        "min_gap": int(row["min_gap"]),
        "bound": str(row["bound"]),
        "line": str(row["line"]),
        "vehicle": int(row["vehicle"]),
        "event_datetime": _as_datetime(row["event_datetime"]),
        "record_key": str(row["record_key"]),
    }


def _existing_record_keys(
    session: Session,
    record_keys: list[str],
) -> set[str]:
    """Return keys already stored in the delay-events table."""

    existing_keys: set[str] = set()

    for batch in _chunks(record_keys, KEY_QUERY_BATCH_SIZE):
        existing_keys.update(
            session.scalars(
                select(DelayEvent.record_key).where(
                    DelayEvent.record_key.in_(batch)
                )
            )
        )

    return existing_keys


def _create_ingestion_run(
    engine: Engine,
    source_file: str | Path,
    result: CleaningResult,
) -> int:
    """Create and commit an audit record before loading event rows."""

    with Session(engine) as session, session.begin():
        ingestion_run = IngestionRun(
            source_file=str(source_file),
            source_rows=result.source_rows,
            valid_rows=len(result.valid_data),
            rejected_rows=len(result.rejected_data),
            duplicate_rows=len(result.duplicate_data),
            inserted_rows=0,
            status="running",
        )
        session.add(ingestion_run)
        session.flush()
        ingestion_run_id = ingestion_run.id

    return ingestion_run_id


def _mark_failed(
    engine: Engine,
    ingestion_run_id: int,
    error: Exception,
) -> None:
    """Persist failure information after the event transaction rolls back."""

    with Session(engine) as session, session.begin():
        ingestion_run = session.get(IngestionRun, ingestion_run_id)

        if ingestion_run is None:
            raise RuntimeError(
                f"Ingestion run {ingestion_run_id} no longer exists"
            ) from error

        ingestion_run.status = "failed"
        ingestion_run.error_message = str(error)
        ingestion_run.completed_at = datetime.now(timezone.utc)


def persist_cleaning_result(
    engine: Engine,
    source_file: str | Path,
    result: CleaningResult,
) -> PersistenceResult:
    """Insert new delay events and persist the ingestion outcome."""

    ingestion_run_id = _create_ingestion_run(
        engine=engine,
        source_file=source_file,
        result=result,
    )

    try:
        with Session(engine) as session, session.begin():
            record_keys = result.valid_data["record_key"].astype(str).tolist()
            existing_keys = _existing_record_keys(session, record_keys)
            new_data = result.valid_data.loc[
                ~result.valid_data["record_key"].astype(str).isin(
                    existing_keys
                )
            ]
            event_mappings = [
                _event_mapping(row, ingestion_run_id)
                for _, row in new_data.iterrows()
            ]

            if event_mappings:
                session.execute(insert(DelayEvent), event_mappings)

            inserted_rows = len(event_mappings)
            database_duplicates = len(result.valid_data) - inserted_rows
            duplicate_rows = (
                len(result.duplicate_data) + database_duplicates
            )

            ingestion_run = session.get(IngestionRun, ingestion_run_id)

            if ingestion_run is None:
                raise RuntimeError(
                    f"Ingestion run {ingestion_run_id} no longer exists"
                )

            ingestion_run.inserted_rows = inserted_rows
            ingestion_run.duplicate_rows = duplicate_rows
            ingestion_run.status = "completed"
            ingestion_run.error_message = None
            ingestion_run.completed_at = datetime.now(timezone.utc)
    except Exception as error:
        _mark_failed(engine, ingestion_run_id, error)
        raise

    return PersistenceResult(
        ingestion_run_id=ingestion_run_id,
        inserted_rows=inserted_rows,
        duplicate_rows=duplicate_rows,
    )
