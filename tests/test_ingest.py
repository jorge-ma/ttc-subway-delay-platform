"""Tests for the repeatable TTC ingestion command."""

from pathlib import Path

import pandas as pd
import pytest

from ingestion.ingest import run_ingestion, validate_paths


def make_source_csv(tmp_path: Path) -> Path:
    """Create valid, invalid, and duplicate representative rows."""

    source_path = tmp_path / "source.csv"
    records = [
        {
            "_id": 1,
            "Date": "2026-01-01",
            "Time": "08:30",
            "Day": "Thursday",
            "Station": "BLOOR STATION",
            "Code": "MUSAN",
            "Min Delay": 5,
            "Min Gap": 9,
            "Bound": "N",
            "Line": "YU",
            "Vehicle": 5227,
        },
        {
            "_id": 2,
            "Date": "2026-01-02",
            "Time": "09:45",
            "Day": "Friday",
            "Station": "KIPLING STATION",
            "Code": "MUIR",
            "Min Delay": 3,
            "Min Gap": 6,
            "Bound": "E",
            "Line": "BD",
            "Vehicle": 5001,
        },
        {
            "_id": 3,
            "Date": "2026-01-01",
            "Time": "08:30",
            "Day": "Thursday",
            "Station": "BLOOR STATION",
            "Code": "MUSAN",
            "Min Delay": 5,
            "Min Gap": 9,
            "Bound": "N",
            "Line": "YU",
            "Vehicle": 5227,
        },
        {
            "_id": 4,
            "Date": "2026-01-03",
            "Time": "10:00",
            "Day": "Saturday",
            "Station": None,
            "Code": "MUSAN",
            "Min Delay": 4,
            "Min Gap": 8,
            "Bound": "S",
            "Line": "YU",
            "Vehicle": 5100,
        },
    ]
    pd.DataFrame(records).to_csv(source_path, index=False)

    return source_path


def test_run_ingestion_writes_separate_outputs(tmp_path):
    source_path = make_source_csv(tmp_path)
    processed_output = tmp_path / "processed" / "clean.csv"
    rejected_output = tmp_path / "rejected" / "rejected.csv"
    duplicate_output = tmp_path / "rejected" / "duplicates.csv"

    result = run_ingestion(
        input_path=source_path,
        processed_output=processed_output,
        rejected_output=rejected_output,
        duplicate_output=duplicate_output,
    )

    assert result.source_rows == 4
    assert len(result.valid_data) == 2
    assert len(result.rejected_data) == 1
    assert len(result.duplicate_data) == 1

    assert processed_output.exists()
    assert rejected_output.exists()
    assert duplicate_output.exists()

    processed_data = pd.read_csv(processed_output)
    rejected_data = pd.read_csv(rejected_output)
    duplicate_data = pd.read_csv(duplicate_output)

    assert len(processed_data) == 2
    assert processed_data["record_key"].is_unique
    assert len(rejected_data) == 1
    assert rejected_data.loc[0, "rejection_reason"] == "missing_station"
    assert len(duplicate_data) == 1
    assert duplicate_data.loc[0, "rejection_reason"] == (
        "duplicate_record"
    )


def test_ingestion_replaces_existing_complete_outputs(tmp_path):
    source_path = make_source_csv(tmp_path)
    processed_output = tmp_path / "clean.csv"
    rejected_output = tmp_path / "rejected.csv"
    duplicate_output = tmp_path / "duplicates.csv"

    processed_output.write_text("old content", encoding="utf-8")

    run_ingestion(
        input_path=source_path,
        processed_output=processed_output,
        rejected_output=rejected_output,
        duplicate_output=duplicate_output,
    )

    processed_data = pd.read_csv(processed_output)

    assert len(processed_data) == 2
    assert "record_key" in processed_data.columns


def test_path_collision_is_rejected(tmp_path):
    shared_path = tmp_path / "shared.csv"

    with pytest.raises(
        ValueError,
        match="Input and output paths must all be different",
    ):
        validate_paths(
            input_path=shared_path,
            processed_output=shared_path,
            rejected_output=tmp_path / "rejected.csv",
            duplicate_output=tmp_path / "duplicates.csv",
        )


def test_missing_source_is_rejected(tmp_path):
    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        run_ingestion(
            input_path=tmp_path / "missing.csv",
            processed_output=tmp_path / "clean.csv",
            rejected_output=tmp_path / "rejected.csv",
            duplicate_output=tmp_path / "duplicates.csv",
        )
