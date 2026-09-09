"""Clean, validate, and deduplicate TTC subway-delay records."""

from dataclasses import dataclass
from hashlib import sha256

import pandas as pd

from ingestion.explore import normalize_columns


INTEGER_COLUMNS = (
    "source_id",
    "min_delay",
    "min_gap",
    "vehicle",
)

OUTPUT_COLUMNS = (
    "source_id",
    "date",
    "time",
    "day",
    "station",
    "code",
    "min_delay",
    "min_gap",
    "bound",
    "line",
    "vehicle",
    "event_datetime",
    "record_key",
)


LINE_ALIASES = {
    "LINE 2 - BLOOR DANFORT": "BD",
    "LINE 2 BLOOR-DANFORTH": "BD",
    "BD/YUS/SHP/FWLRT/ECLRT": "MULTIPLE",
}


@dataclass(frozen=True)
class CleaningResult:
    """Contain the separate outputs from one cleaning operation."""

    source_rows: int
    valid_data: pd.DataFrame
    rejected_data: pd.DataFrame
    duplicate_data: pd.DataFrame


def _normalize_required_text(series: pd.Series) -> pd.Series:
    """Normalize required text while preserving missing values."""

    return series.astype("string").str.strip().str.upper()


def _normalize_optional_text(series: pd.Series) -> pd.Series:
    """Normalize optional text and represent missing values explicitly."""

    normalized = _normalize_required_text(series)
    normalized = normalized.mask(normalized == "")

    return normalized.fillna("UNKNOWN")


def _normalize_line(series: pd.Series) -> pd.Series:
    """Normalize missing values and known TTC line aliases."""

    normalized = _normalize_optional_text(series)

    return normalized.replace(LINE_ALIASES)


def _is_non_integer(series: pd.Series) -> pd.Series:
    """Identify numeric values that are not whole numbers."""

    return series.notna() & series.mod(1).ne(0)


def _build_record_key(row: pd.Series) -> str:
    """Build a stable key from the normalized event content."""

    key_fields = (
        row["event_datetime"].isoformat(),
        row["station"],
        row["code"],
        str(row["min_delay"]),
        str(row["min_gap"]),
        row["bound"],
        row["line"],
        str(row["vehicle"]),
    )

    return sha256("|".join(key_fields).encode("utf-8")).hexdigest()


def clean_data(raw_data: pd.DataFrame) -> CleaningResult:
    """Normalize, validate, and deduplicate TTC delay records."""

    data = normalize_columns(raw_data.copy()).reset_index(drop=True)
    source_rows = len(data)

    data["station"] = _normalize_required_text(data["station"])
    data["code"] = _normalize_required_text(data["code"])
    data["bound"] = _normalize_optional_text(data["bound"])
    data["line"] = _normalize_line(data["line"])

    for column in INTEGER_COLUMNS:
        data[column] = pd.to_numeric(data[column], errors="coerce")

    date_text = data["date"].astype("string").str.strip()
    time_text = data["time"].astype("string").str.strip()
    event_datetime = pd.to_datetime(
        date_text + " " + time_text,
        errors="coerce",
        format="mixed",
    )

    rejection_reasons: list[list[str]] = [
        [] for _ in range(source_rows)
    ]

    def reject(mask: pd.Series, reason: str) -> None:
        """Attach one rejection reason to every matching row."""

        for position in mask.fillna(True).to_numpy().nonzero()[0]:
            rejection_reasons[position].append(reason)

    reject(data["source_id"].isna(), "missing_source_id")
    reject(_is_non_integer(data["source_id"]), "invalid_source_id")
    reject(data["source_id"].lt(0), "negative_source_id")

    reject(
        data["station"].isna() | data["station"].eq(""),
        "missing_station",
    )
    reject(
        data["code"].isna() | data["code"].eq(""),
        "missing_code",
    )
    reject(event_datetime.isna(), "invalid_event_datetime")

    for column in ("min_delay", "min_gap", "vehicle"):
        reject(data[column].isna(), f"missing_{column}")
        reject(_is_non_integer(data[column]), f"invalid_{column}")
        reject(data[column].lt(0), f"negative_{column}")

    invalid_mask = pd.Series(
        [bool(reasons) for reasons in rejection_reasons],
        index=data.index,
    )

    rejected_data = data.loc[invalid_mask].copy()
    rejected_data["rejection_reason"] = [
        ";".join(rejection_reasons[position])
        for position in rejected_data.index
    ]

    valid_data = data.loc[~invalid_mask].copy()
    valid_data["event_datetime"] = event_datetime.loc[~invalid_mask]
    valid_data["date"] = valid_data["event_datetime"].dt.strftime(
        "%Y-%m-%d"
    )
    valid_data["time"] = valid_data["event_datetime"].dt.strftime("%H:%M")
    valid_data["day"] = valid_data["event_datetime"].dt.day_name()

    for column in INTEGER_COLUMNS:
        valid_data[column] = valid_data[column].astype("int64")

    if valid_data.empty:
        valid_data["record_key"] = pd.Series(dtype="string")
    else:
        valid_data["record_key"] = valid_data.apply(
            _build_record_key,
            axis=1,
        )

    duplicate_mask = valid_data.duplicated(
        subset=["record_key"],
        keep="first",
    )

    duplicate_data = valid_data.loc[duplicate_mask].copy()
    duplicate_data["rejection_reason"] = "duplicate_record"

    valid_data = valid_data.loc[~duplicate_mask].copy()
    valid_data = valid_data.loc[:, OUTPUT_COLUMNS].reset_index(drop=True)
    rejected_data = rejected_data.reset_index(drop=True)
    duplicate_data = duplicate_data.reset_index(drop=True)

    return CleaningResult(
        source_rows=source_rows,
        valid_data=valid_data,
        rejected_data=rejected_data,
        duplicate_data=duplicate_data,
    )
