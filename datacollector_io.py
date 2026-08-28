"""
Append Mesa DataCollector frames to a CSV without schema-mismatch parse errors.

The original RAM_cleaning path used ``to_csv(..., mode='a', header=not exists)``.
If a leftover file from a previous run (or from a collector with fewer reporters)
was still on disk, pandas later raised:

    ParserError: Expected 3 fields in line N, saw 5

That is exactly what happens after adding ``wind_speed`` and ``wind_direction``
to the collector while an old 3-column ``Partial_Data_Loading.csv`` remains.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Iterable, Sequence

import pandas as pd

# Current on-disk name.  The development branch originally used
# Partial_Data_Loading.csv; the local run that hit the ParserError used
# Model_Partial_Data_Loading.csv.  We write the latter and delete both on reset.
PARTIAL_DATA_CSV = "Model_Partial_Data_Loading.csv"
LEGACY_PARTIAL_DATA_CSVS: tuple[str, ...] = (
    "Partial_Data_Loading.csv",
    "Model_Partial_Data_Loading.csv",
)


def _as_path(path) -> Path:
    return Path(path) if path is not None else Path(PARTIAL_DATA_CSV)


def reset_partial_data_files(extra: Iterable[str] = ()) -> None:
    """Delete leftover collector CSVs so a new run cannot mix schemas."""
    names = set(LEGACY_PARTIAL_DATA_CSVS)
    names.add(PARTIAL_DATA_CSV)
    names.update(extra)
    for name in names:
        p = Path(name)
        if p.exists():
            p.unlink()
            print(f"[collector] removed leftover {p}")


def _cell_to_csv(value):
    if value is None:
        return value
    try:
        if pd.isna(value):
            return value
    except (TypeError, ValueError):
        pass
    if isinstance(value, (dict, list, tuple, set)):
        return json.dumps(value, default=str)
    return value


def _prepare_frame(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy().reset_index(drop=True)
    unnamed = [c for c in df.columns if str(c).startswith("Unnamed")]
    if unnamed:
        df = df.drop(columns=unnamed)
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].map(_cell_to_csv)
    return df


def _header_columns(path: Path) -> list[str]:
    return list(pd.read_csv(path, nrows=0).columns)


class CollectorSchemaError(ValueError):
    """Partial CSV on disk does not match the current DataCollector reporters."""


def append_datacollector_frame(df: pd.DataFrame, path=None) -> None:
    """
    Append one collector snapshot.

    Writes a header only for a new/empty file.  If a leftover file has a
    different column set (the 3-vs-5 field bug), raise instead of appending.
    """
    if df is None or df.empty:
        return
    df = _prepare_frame(df)
    dest = _as_path(path)
    if dest.exists() and dest.stat().st_size > 0:
        existing = _header_columns(dest)
        new_cols = list(df.columns)
        if existing != new_cols:
            raise CollectorSchemaError(
                f"{dest} has columns {existing} but new collector rows have "
                f"{new_cols}. A leftover partial CSV from a previous reporter "
                "set (for example before wind_speed/wind_direction were added) "
                "cannot be appended to. Delete the file or call "
                "reset_partial_data_files() and re-run."
            )
        df.to_csv(
            dest,
            mode="a",
            header=False,
            index=False,
            quoting=csv.QUOTE_MINIMAL,
        )
    else:
        dest.parent.mkdir(parents=True, exist_ok=True)
        df.to_csv(
            dest,
            mode="w",
            header=True,
            index=False,
            quoting=csv.QUOTE_MINIMAL,
        )


def _read_ragged_csv(path: Path) -> pd.DataFrame:
    """
    Recover a CSV whose later rows gained extra columns.

    Typical case: header + early rows have 3 fields (index, Agents_by_type,
    Drops); from some line onward they have 5 (those plus wind_speed,
    wind_direction).
    """
    with path.open(newline="") as fh:
        rows = list(csv.reader(fh))
    if not rows:
        return pd.DataFrame()

    width = max(len(r) for r in rows)
    header = list(rows[0])
    extras = ["wind_speed", "wind_direction", "Time"]
    i = 0
    while len(header) < width:
        header.append(extras[i] if i < len(extras) else f"extra_{i}")
        i += 1

    body = [r + [""] * (width - len(r)) for r in rows[1:]]
    df = pd.DataFrame(body, columns=header)
    unnamed = [c for c in df.columns if str(c).startswith("Unnamed") or c == ""]
    if unnamed:
        df = df.drop(columns=unnamed)
    return df


def read_partial_data_csv(path=None) -> pd.DataFrame:
    """
    Load the partial collector CSV.

    Tries the current filename, then the legacy name.  If pandas hits a
    ragged-column ParserError (Expected N fields, saw M), recover by padding
    short rows so wind columns added mid-file are not thrown away.
    """
    candidates: Sequence[Path]
    if path is not None:
        candidates = (_as_path(path),)
    else:
        ordered = [Path(PARTIAL_DATA_CSV)]
        for name in LEGACY_PARTIAL_DATA_CSVS:
            p = Path(name)
            if p not in ordered:
                ordered.append(p)
        candidates = tuple(ordered)

    dest = next((p for p in candidates if p.exists() and p.stat().st_size > 0), None)
    if dest is None:
        return pd.DataFrame()

    try:
        df = pd.read_csv(dest)
    except pd.errors.ParserError as err:
        print(f"[collector] {dest} has mixed column counts ({err}); recovering ragged rows")
        df = _read_ragged_csv(dest)

    unnamed = [c for c in df.columns if str(c).startswith("Unnamed")]
    if unnamed:
        df = df.drop(columns=unnamed)
    return df.reset_index(drop=True)


def save_final_collected_results(out_csv, path=None) -> Path | None:
    """Flush-read the partial CSV into ``out_csv`` and delete the partial file."""
    df = read_partial_data_csv(path)
    reset_partial_data_files()
    if df.empty:
        print("[collector] no rows to save")
        return None
    out = Path(out_csv)
    out.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(out, index=False)
    return out
