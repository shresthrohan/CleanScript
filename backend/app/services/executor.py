"""Restricted IR interpreter.

Each IR op maps to exactly one allow-listed handler below. Nothing is evaluated as code:
no eval/exec, no dynamic attribute access, no file access. Handlers work on a copy of the
input DataFrame; on any failure the partial copy is discarded and the input is untouched.
The semantics here must stay identical to app/compiler/codegen.py (tests compare both).
"""
from __future__ import annotations

import operator as op_module
import time
from dataclasses import dataclass, field

import pandas as pd

from app.compiler.ir import validate_ir
from app.services.dataset_profiler import to_json_value

_COMPARE = {
    "==": op_module.eq, "!=": op_module.ne, ">": op_module.gt,
    "<": op_module.lt, ">=": op_module.ge, "<=": op_module.le,
}


class ExecutionError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


@dataclass
class ExecutionResult:
    status: str                       # "success" | "failed"
    operations: list[dict]
    warnings: list[dict]
    error: dict | None
    before: dict
    after: dict | None
    dataframe: pd.DataFrame | None = field(default=None, repr=False)


def _is_numeric(s: pd.Series) -> bool:
    return pd.api.types.is_numeric_dtype(s) and not pd.api.types.is_bool_dtype(s)


def _require_column(df: pd.DataFrame, col: str) -> pd.Series:
    if col not in df.columns:
        raise ExecutionError("E_UNKNOWN_COLUMN", f"Column {col!r} does not exist")
    return df[col]


def _require_values(s: pd.Series, command: str):
    if s.isna().all():
        raise ExecutionError("E_ALL_NULL_COLUMN", f"{command}: column {s.name!r} has no non-null values")


# -- handlers: (df, instruction, warn) -> (new_df, metrics) ---------------------------

def _remove_nulls(df, instr, warn):
    out = df.dropna(how="any")
    return out, {"rows_removed": len(df) - len(out)}


def _remove_duplicates(df, instr, warn):
    out = df.drop_duplicates(keep="first")
    return out, {"rows_removed": len(df) - len(out)}


def _fill_nulls(df, instr, warn):
    col, strategy = instr["column"], instr["strategy"]
    s = _require_column(df, col)
    if strategy in ("MEAN", "MEDIAN") and not _is_numeric(s):
        raise ExecutionError("E_TYPE_MISMATCH", f"FILL_NULLS USING {strategy} requires a numeric column ({col!r})")
    _require_values(s, "FILL_NULLS")
    if strategy == "MODE":
        non_null = s.dropna()
        counts = non_null.map(non_null.value_counts())
        fill_value = non_null[counts == counts.max()].iloc[0]  # ties: first in row order
    else:
        fill_value = s.mean() if strategy == "MEAN" else s.median()
        if pd.api.types.is_integer_dtype(s) and not float(fill_value).is_integer():
            s = s.astype("Float64")
    filled = int(s.isna().sum())
    out = df.copy()
    out[col] = s.fillna(fill_value)
    if filled == 0:
        warn("W_NO_NULLS", f"FILL_NULLS: column {col!r} had no missing values")
    return out, {"cells_changed": filled, "fill_value": fill_value}


def _drop_column(df, instr, warn):
    _require_column(df, instr["column"])
    if len(df.columns) == 1:
        raise ExecutionError("E_DROP_LAST_COLUMN", "Cannot drop the only remaining column")
    return df.drop(columns=[instr["column"]]), {}


def _rename_column(df, instr, warn):
    old, new = instr["column"], instr["new_name"]
    _require_column(df, old)
    if new in df.columns:
        raise ExecutionError("E_RENAME_CONFLICT", f"A column named {new!r} already exists")
    return df.rename(columns={old: new}), {}


def _filter_rows(df, instr, warn):
    col, value = instr["column"], instr["value"]
    s = _require_column(df, col)
    numeric_literal = isinstance(value, (int, float))
    if numeric_literal != _is_numeric(s) and not s.isna().all():
        raise ExecutionError("E_TYPE_MISMATCH", f"FILTER: cannot compare column {col!r} ({s.dtype}) with {value!r}")
    mask = s.notna() & _COMPARE[instr["operator"]](s, value)  # nulls never match
    out = df[mask]
    if out.empty and len(df):
        warn("W_EMPTY_RESULT", f"FILTER removed every row ({col!r} {instr['operator']} {value!r})")
    return out, {"rows_removed": len(df) - len(out)}


def _normalize(df, instr, warn):
    col = instr["column"]
    s = _require_column(df, col)
    if not _is_numeric(s):
        raise ExecutionError("E_TYPE_MISMATCH", f"NORMALIZE requires a numeric column ({col!r})")
    _require_values(s, "NORMALIZE")
    values = s.astype("Float64")
    col_min, col_max = values.min(), values.max()
    if col_max == col_min:
        normalized = values.where(values.isna(), 0.0)  # constant column -> 0.0
        warn("W_CONSTANT_COLUMN", f"NORMALIZE: column {col!r} is constant ({col_min}); values set to 0.0")
    else:
        normalized = (values - col_min) / (col_max - col_min)
    out = df.copy()
    out[col] = normalized
    changed = int((values.notna() & (values != normalized)).sum())
    return out, {"cells_changed": changed, "min": col_min, "max": col_max}


def _sort_rows(df, instr, warn):
    col = instr["column"]
    _require_column(df, col)
    out = df.sort_values(col, ascending=instr["direction"] == "ASC", kind="stable", na_position="last")
    return out, {"order_changed": not out.index.equals(df.index)}


HANDLERS = {
    "remove_nulls": _remove_nulls,
    "remove_duplicates": _remove_duplicates,
    "fill_nulls": _fill_nulls,
    "drop_column": _drop_column,
    "rename_column": _rename_column,
    "filter_rows": _filter_rows,
    "normalize": _normalize,
    "sort_rows": _sort_rows,
}


def _shape(df: pd.DataFrame) -> dict:
    return {"rows": int(len(df)), "columns": int(len(df.columns))}


def execute(source_df: pd.DataFrame, ir: dict) -> ExecutionResult:
    before = _shape(source_df)
    problems = validate_ir(ir)
    if problems:
        return ExecutionResult("failed", [], [], {"code": "E_INVALID_IR", "message": "; ".join(problems)},
                               before, None)

    df = source_df.copy(deep=True)
    operations, warnings = [], []
    for instr in ir["instructions"]:
        op = instr["op"]
        record = {"index": instr["index"], "op": op, "source": instr.get("source"),
                  "rows_before": int(len(df)), "columns_before": int(len(df.columns))}

        def warn(code, message, _instr=instr):
            warnings.append({"code": code, "message": message, "index": _instr["index"],
                             "source": _instr.get("source")})

        started = time.perf_counter()
        try:
            df, metrics = HANDLERS[op](df, instr, warn)
        except ExecutionError as e:
            record.update(status="failed", message=str(e))
            operations.append(record)
            error = {"code": e.code, "message": str(e), "index": instr["index"], "source": instr.get("source")}
            return ExecutionResult("failed", operations, warnings, error, before, None)
        except (TypeError, ValueError) as e:  # defensive: unexpected data problem inside Pandas
            record.update(status="failed", message=f"{op} failed: {e}")
            operations.append(record)
            error = {"code": "E_EXECUTION", "message": f"{op} failed on this data",
                     "index": instr["index"], "source": instr.get("source")}
            return ExecutionResult("failed", operations, warnings, error, before, None)
        record.update(
            status="ok",
            rows_after=int(len(df)),
            columns_after=int(len(df.columns)),
            duration_ms=round((time.perf_counter() - started) * 1000, 3),
            **{k: to_json_value(v) for k, v in metrics.items()},
        )
        operations.append(record)

    df = df.reset_index(drop=True)
    return ExecutionResult("success", operations, warnings, None, before, _shape(df), df)
