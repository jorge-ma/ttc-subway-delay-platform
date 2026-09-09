"""Tests for TTC record cleaning, validation, and deduplication."""

import pandas as pd

from ingestion.cleaning import clean_data


def make_raw_data(**overrides: object) -> pd.DataFrame:
    """Return one representative raw TTC record."""

    record: dict[str, object] = {
        "_id": 1,
        "Date": "2026-01-01",
        "Time": "08:30",
        "Day": "Thursday",
        "Station": " Bloor Station ",
        "Code": " musan ",
        "Min Delay": 5,
        "Min Gap": 9,
        "Bound": " n ",
        "Line": " yu ",
        "Vehicle": 5227,
    }
    record.update(overrides)

    return pd.DataFrame([record])


def test_valid_record_is_cleaned():
    result = clean_data(make_raw_data())

    assert result.source_rows == 1
    assert len(result.valid_data) == 1
    assert result.rejected_data.empty
    assert result.duplicate_data.empty

    record = result.valid_data.iloc[0]

    assert record["source_id"] == 1
    assert record["station"] == "BLOOR STATION"
    assert record["code"] == "MUSAN"
    assert record["bound"] == "N"
    assert record["line"] == "YU"
    assert record["date"] == "2026-01-01"
    assert record["time"] == "08:30"
    assert record["day"] == "Thursday"
    assert len(record["record_key"]) == 64


def test_optional_values_become_unknown():
    result = clean_data(make_raw_data(Bound=None, Line=""))
    record = result.valid_data.iloc[0]

    assert record["bound"] == "UNKNOWN"
    assert record["line"] == "UNKNOWN"


def test_missing_station_is_rejected():
    result = clean_data(make_raw_data(Station=None))

    assert result.valid_data.empty
    assert len(result.rejected_data) == 1
    assert "missing_station" in result.rejected_data.loc[
        0, "rejection_reason"
    ]


def test_negative_delay_is_rejected():
    result = clean_data(make_raw_data(**{"Min Delay": -1}))

    assert result.valid_data.empty
    assert "negative_min_delay" in result.rejected_data.loc[
        0, "rejection_reason"
    ]


def test_invalid_datetime_is_rejected():
    result = clean_data(make_raw_data(Date="not-a-date"))

    assert result.valid_data.empty
    assert "invalid_event_datetime" in result.rejected_data.loc[
        0, "rejection_reason"
    ]


def test_duplicate_event_is_separated():
    first = make_raw_data()
    second = make_raw_data(**{"_id": 2})
    raw_data = pd.concat([first, second], ignore_index=True)

    result = clean_data(raw_data)

    assert result.source_rows == 2
    assert len(result.valid_data) == 1
    assert result.rejected_data.empty
    assert len(result.duplicate_data) == 1
    assert result.duplicate_data.loc[0, "rejection_reason"] == (
        "duplicate_record"
    )


def test_record_key_does_not_depend_on_source_id():
    first_result = clean_data(make_raw_data(**{"_id": 1}))
    second_result = clean_data(make_raw_data(**{"_id": 999}))

    first_key = first_result.valid_data.loc[0, "record_key"]
    second_key = second_result.valid_data.loc[0, "record_key"]

    assert first_key == second_key


def test_day_is_derived_from_event_date():
    result = clean_data(make_raw_data(Day="Incorrect"))

    assert result.valid_data.loc[0, "day"] == "Thursday"
