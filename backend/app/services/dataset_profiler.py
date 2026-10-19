"""Read-only dataset loading, type inference, profiling and JSON-safe previews."""
from __future__ import annotations

import csv
import io
import math
from datetime import date, datetime

import numpy as np
import pandas as pd

from app.compiler.semantic import ColumnInfo

DEFAULT_PREVIEW_ROWS = 50


class DatasetError(ValueError):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


def read_csv_bytes(data: bytes) -> pd.DataFrame:
    """Parse CSV bytes the same way the generated code does (numpy_nullable dtypes)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise DatasetError("E_ENCODING", "The file is not valid UTF-8 text")
    if not text.strip():
        raise DatasetError("E_EMPTY_CSV", "The CSV file is empty")
    header = next(csv.reader(io.StringIO(text)), [])
    if any(not h.strip() for h in header):
        raise DatasetError("E_MALFORMED_CSV", "The CSV header contains empty column names")
    if len(set(header)) != len(header):
        raise DatasetError("E_MALFORMED_CSV", "The CSV header contains duplicate column names")
    try:
        df = pd.read_csv(io.StringIO(text), dtype_backend="numpy_nullable")
    except pd.errors.EmptyDataError:
        raise DatasetError("E_EMPTY_CSV", "The CSV file has no columns")
    except (pd.errors.ParserError, ValueError) as e:
        first_line = str(e).splitlines()[0][:200] if str(e) else "parse error"
        raise DatasetError("E_MALFORMED_CSV", f"The CSV file could not be parsed: {first_line}")
    if not isinstance(df.index, pd.RangeIndex):  # pandas turns surplus leading fields into an index
        raise DatasetError("E_MALFORMED_CSV", "Some rows have more fields than the header")
    df.columns = [str(c) for c in df.columns]
    return df


def infer_type(series: pd.Series) -> str:
    if series.notna().sum() == 0:
        return "empty"
    if pd.api.types.is_bool_dtype(series):
        return "boolean"
    if pd.api.types.is_integer_dtype(series):
        return "integer"
    if pd.api.types.is_float_dtype(series):
        return "float"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    return "string"


def schema_of(df: pd.DataFrame) -> list[ColumnInfo]:
    return [ColumnInfo(c, infer_type(df[c]), bool(df[c].isna().any())) for c in df.columns]


def to_json_value(v):
    """JSON policy: missing -> None, non-finite floats -> 'inf'/'-inf'/None, numpy -> Python."""
    if v is None or v is pd.NA or v is pd.NaT:
        return None
    if isinstance(v, (np.bool_, bool)):
        return bool(v)
    if isinstance(v, (np.integer, int)):
        return int(v)
    if isinstance(v, (np.floating, float)):
        f = float(v)
        if math.isnan(f):
            return None
        if math.isinf(f):
            return "inf" if f > 0 else "-inf"
        return f
    if isinstance(v, (pd.Timestamp, datetime, date)):
        return v.isoformat()
    return str(v)


def preview(df: pd.DataFrame, limit: int = DEFAULT_PREVIEW_ROWS) -> dict:
    head = df.head(limit)
    return {
        "columns": list(df.columns),
        "rows": [[to_json_value(v) for v in row] for row in head.itertuples(index=False, name=None)],
        "total_rows": int(len(df)),
        "truncated": len(df) > limit,
    }


def _numeric_stats(s: pd.Series) -> dict | None:
    s = s.dropna()
    if s.empty:
        return None
    return {k: to_json_value(v) for k, v in
            {"min": s.min(), "max": s.max(), "mean": s.mean(), "median": s.median()}.items()}


def profile(df: pd.DataFrame, preview_rows: int = DEFAULT_PREVIEW_ROWS) -> dict:
    """Describe the dataset without modifying it. Issues are *detected*, never fixed here."""
    rows = len(df)
    columns, warnings = [], []
    for name in df.columns:
        s = df[name]
        ctype = infer_type(s)
        missing = int(s.isna().sum())
        col = {
            "name": name,
            "type": ctype,
            "dtype": str(s.dtype),
            "missing": missing,
            "missing_pct": round(missing / rows * 100, 2) if rows else 0.0,
            "unique": int(s.nunique(dropna=True)),
            "stats": _numeric_stats(s) if ctype in ("integer", "float") else None,
        }
        columns.append(col)
        if ctype == "empty" and rows:
            warnings.append({"code": "W_ALL_NULL_COLUMN", "column": name, "message": f"{name!r} has no values"})
        elif rows > 1 and col["unique"] == 1:
            warnings.append({"code": "W_CONSTANT_COLUMN", "column": name,
                             "message": f"{name!r} has a single distinct value"})
        if ctype == "string":
            non_null = s.dropna()
            numeric_like = pd.to_numeric(non_null, errors="coerce").notna().sum()
            if 0 < numeric_like < len(non_null) and numeric_like / len(non_null) >= 0.5:
                warnings.append({"code": "W_MIXED_TYPES", "column": name,
                                 "message": f"{name!r} is mostly numeric but has {len(non_null) - numeric_like} "
                                            f"non-numeric value(s); it is treated as text"})
    return {
        "rows": int(rows),
        "columns": int(len(df.columns)),
        "schema": columns,
        "missing_cells": int(df.isna().sum().sum()),
        "duplicate_rows": int(df.duplicated().sum()) if len(df.columns) else 0,
        "warnings": warnings,
        "preview": preview(df, preview_rows),
    }
