"""Tests for the TTC SQLAlchemy table definitions."""

from sqlalchemy import CheckConstraint

from database.models import Base, DelayEvent, IngestionRun


def test_expected_tables_are_registered():
    assert set(Base.metadata.tables) == {
        "ingestion_runs",
        "delay_events",
    }


def test_record_key_is_unique_and_required():
    record_key = DelayEvent.__table__.columns["record_key"]

    assert record_key.unique is True
    assert record_key.nullable is False
    assert record_key.type.length == 64


def test_delay_event_references_ingestion_run():
    foreign_keys = DelayEvent.__table__.foreign_keys

    assert len(foreign_keys) == 1
    assert next(iter(foreign_keys)).target_fullname == (
        "ingestion_runs.id"
    )


def test_database_models_include_nonnegative_checks():
    delay_checks = {
        constraint.name
        for constraint in DelayEvent.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert {
        "ck_delay_source_id",
        "ck_delay_min_delay",
        "ck_delay_min_gap",
        "ck_delay_vehicle",
    }.issubset(delay_checks)


def test_ingestion_status_is_constrained():
    ingestion_checks = {
        constraint.name
        for constraint in IngestionRun.__table__.constraints
        if isinstance(constraint, CheckConstraint)
    }

    assert "ck_ingestion_status" in ingestion_checks
