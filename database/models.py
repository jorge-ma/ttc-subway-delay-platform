"""SQLAlchemy models for TTC ingestion history and delay events."""

import datetime as dt

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    """Base class for all TTC database models."""


class IngestionRun(Base):
    """Record the outcome of one ingestion execution."""

    __tablename__ = "ingestion_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source_file: Mapped[str] = mapped_column(String(255), nullable=False)
    source_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    valid_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    rejected_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    duplicate_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    inserted_rows: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        default="running",
        server_default="running",
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now(),
    )
    completed_at: Mapped[dt.datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    events: Mapped[list["DelayEvent"]] = relationship(
        back_populates="ingestion_run"
    )

    __table_args__ = (
        CheckConstraint("source_rows >= 0", name="ck_ingestion_source_rows"),
        CheckConstraint("valid_rows >= 0", name="ck_ingestion_valid_rows"),
        CheckConstraint(
            "rejected_rows >= 0",
            name="ck_ingestion_rejected_rows",
        ),
        CheckConstraint(
            "duplicate_rows >= 0",
            name="ck_ingestion_duplicate_rows",
        ),
        CheckConstraint(
            "inserted_rows >= 0",
            name="ck_ingestion_inserted_rows",
        ),
        CheckConstraint(
            "status IN ('running', 'completed', 'failed')",
            name="ck_ingestion_status",
        ),
    )


class DelayEvent(Base):
    """Represent one normalized, unique TTC delay event."""

    __tablename__ = "delay_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingestion_run_id: Mapped[int] = mapped_column(
        ForeignKey("ingestion_runs.id"),
        nullable=False,
        index=True,
    )
    source_id: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
        index=True,
    )
    date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    time: Mapped[dt.time] = mapped_column(nullable=False)
    day: Mapped[str] = mapped_column(String(9), nullable=False)
    station: Mapped[str] = mapped_column(String(150), nullable=False)
    code: Mapped[str] = mapped_column(String(20), nullable=False)
    min_delay: Mapped[int] = mapped_column(Integer, nullable=False)
    min_gap: Mapped[int] = mapped_column(Integer, nullable=False)
    bound: Mapped[str] = mapped_column(String(20), nullable=False)
    line: Mapped[str] = mapped_column(String(20), nullable=False)
    vehicle: Mapped[int] = mapped_column(Integer, nullable=False)
    event_datetime: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=False),
        nullable=False,
    )
    record_key: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        unique=True,
    )

    ingestion_run: Mapped[IngestionRun] = relationship(
        back_populates="events"
    )

    __table_args__ = (
        CheckConstraint("source_id >= 0", name="ck_delay_source_id"),
        CheckConstraint("min_delay >= 0", name="ck_delay_min_delay"),
        CheckConstraint("min_gap >= 0", name="ck_delay_min_gap"),
        CheckConstraint("vehicle >= 0", name="ck_delay_vehicle"),
        Index("ix_delay_events_event_datetime", "event_datetime"),
        Index("ix_delay_events_station", "station"),
        Index("ix_delay_events_code", "code"),
        Index("ix_delay_events_line", "line"),
    )
