from pathlib import Path

import pandas as pd
import pytest

from ingestion.explore import (
    REQUIRED_COLUMNS,
    load_csv,
    normalize_column_name,
)


def make_valid_csv(
    tmp_path: Path,
    identifier_column: str = "_id",
) -> Path:
    """Create a small representative TTC CSV file."""

    csv_path = tmp_path / "ttc-delays.csv"

    data = pd.DataFrame(
        [
            {
                identifier_column: 1,
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
            }
        ]
    )

    data.to_csv(csv_path, index=False)

    return csv_path


def test_normalize_column_name():
    assert normalize_column_name("Min Delay") == "min_delay"
    assert normalize_column_name(" Station ") == "station"
    assert normalize_column_name("_id") == "id"


def test_load_current_dataset_columns(tmp_path):
    csv_path = make_valid_csv(tmp_path, identifier_column="_id")

    data = load_csv(csv_path)

    assert "source_id" in data.columns
    assert "id" not in data.columns
    assert REQUIRED_COLUMNS.issubset(data.columns)
    assert len(data) == 1


def test_load_previous_dataset_columns(tmp_path):
    csv_path = make_valid_csv(
        tmp_path,
        identifier_column="lsp_id",
    )

    data = load_csv(csv_path)

    assert "source_id" in data.columns
    assert "lsp_id" not in data.columns
    assert REQUIRED_COLUMNS.issubset(data.columns)


def test_missing_csv_is_rejected(tmp_path):
    missing_path = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError, match="CSV file not found"):
        load_csv(missing_path)


def test_non_csv_file_is_rejected(tmp_path):
    text_path = tmp_path / "delays.txt"
    text_path.write_text("not a CSV", encoding="utf-8")

    with pytest.raises(ValueError, match="Expected a CSV file"):
        load_csv(text_path)


def test_empty_csv_is_rejected(tmp_path):
    csv_path = tmp_path / "empty.csv"
    csv_path.write_text("", encoding="utf-8")

    with pytest.raises(ValueError, match="CSV file is empty"):
        load_csv(csv_path)


def test_csv_without_data_rows_is_rejected(tmp_path):
    csv_path = tmp_path / "headers-only.csv"

    pd.DataFrame(
        columns=[
            "_id",
            "Date",
            "Time",
            "Day",
            "Station",
            "Code",
            "Min Delay",
            "Min Gap",
            "Bound",
            "Line",
            "Vehicle",
        ]
    ).to_csv(csv_path, index=False)

    with pytest.raises(
        ValueError,
        match="CSV file contains no data rows",
    ):
        load_csv(csv_path)


def test_missing_required_column_is_rejected(tmp_path):
    csv_path = make_valid_csv(tmp_path)

    data = pd.read_csv(csv_path)
    data = data.drop(columns=["Station"])
    data.to_csv(csv_path, index=False)

    with pytest.raises(
        ValueError,
        match="missing required columns: station",
    ):
        load_csv(csv_path)
