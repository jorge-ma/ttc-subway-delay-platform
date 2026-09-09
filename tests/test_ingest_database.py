"""Tests for the database-enabled ingestion command."""

from pathlib import Path
from unittest.mock import Mock, patch

from database.loader import PersistenceResult
from ingestion.cleaning import CleaningResult
from ingestion.ingest import parse_arguments, persist_result


def test_database_loading_is_disabled_by_default():
    arguments = parse_arguments(["--input", "sample.csv"])

    assert arguments.load_database is False


def test_database_loading_can_be_requested_explicitly():
    arguments = parse_arguments(
        ["--input", "sample.csv", "--load-database"]
    )

    assert arguments.load_database is True


@patch("ingestion.ingest.persist_cleaning_result")
@patch("ingestion.ingest.create_database_engine")
def test_persist_result_disposes_database_engine(
    create_engine_mock,
    persist_mock,
):
    engine = Mock()
    create_engine_mock.return_value = engine
    persistence_result = PersistenceResult(
        ingestion_run_id=7,
        inserted_rows=1,
        duplicate_rows=0,
    )
    persist_mock.return_value = persistence_result
    cleaning_result = CleaningResult(
        source_rows=0,
        valid_data=Mock(),
        rejected_data=Mock(),
        duplicate_data=Mock(),
    )

    result = persist_result(Path("sample.csv"), cleaning_result)

    assert result == persistence_result
    persist_mock.assert_called_once_with(
        engine=engine,
        source_file=Path("sample.csv"),
        result=cleaning_result,
    )
    engine.dispose.assert_called_once_with()
