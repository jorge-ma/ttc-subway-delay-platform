"""Queries and response models for ingestion status."""

import datetime as dt
from typing import Literal

from pydantic import BaseModel
from sqlalchemy import Engine, select
from sqlalchemy.orm import Session

from database.models import IngestionRun


class IngestionStatus(BaseModel):
    """Describe the most recent ingestion execution."""

    id: int
    source_file: str
    source_rows: int
    valid_rows: int
    rejected_rows: int
    duplicate_rows: int
    inserted_rows: int
    status: Literal["running", "completed", "failed"]
    error_message: str | None
    started_at: dt.datetime
    completed_at: dt.datetime | None


def fetch_latest_ingestion(engine: Engine) -> IngestionStatus | None:
    """Return the most recent ingestion run."""

    statement = (
        select(IngestionRun)
        .order_by(IngestionRun.id.desc())
        .limit(1)
    )

    with Session(engine) as session:
        run = session.scalar(statement)

    if run is None:
        return None

    return IngestionStatus(
        id=run.id,
        source_file=run.source_file,
        source_rows=run.source_rows,
        valid_rows=run.valid_rows,
        rejected_rows=run.rejected_rows,
        duplicate_rows=run.duplicate_rows,
        inserted_rows=run.inserted_rows,
        status=run.status,
        error_message=run.error_message,
        started_at=run.started_at,
        completed_at=run.completed_at,
    )
