"""Semantic analysis: Program AST + dataset schema -> diagnostics and a schema trace.

The analyzer walks statements in source order with a mutable copy of the dataset schema
(a small symbol table: column name -> type, may-contain-nulls). DROP_COLUMN, RENAME,
FILL_NULLS, REMOVE_NULLS and NORMALIZE update that table so later statements are checked
against the schema they will actually see at run time.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import ast_nodes as ast
from .errors import ERROR, INFO, WARNING, Diagnostic

NUMERIC_TYPES = {"integer", "float"}
SAFE_OUTPUT_NAME = re.compile(r"^[A-Za-z0-9_][A-Za-z0-9 _().-]{0,195}\.csv$", re.IGNORECASE)


@dataclass
class ColumnInfo:
    name: str
    type: str          # integer | float | boolean | string | datetime | empty
    has_nulls: bool


@dataclass
class SemanticResult:
    diagnostics: list[Diagnostic]
    trace: list[dict]   # per statement: what was checked and the schema afterwards

    @property
    def ok(self) -> bool:
        return not any(d.severity == ERROR for d in self.diagnostics)


def is_safe_basename(name: str) -> bool:
    return (
        bool(name.strip())
        and len(name) <= 255
        and not any(c in name for c in "/\\:")
        and name not in (".", "..")
        and ".." not in name
        and all(c.isprintable() for c in name)
    )


class SemanticAnalyzer:
    def __init__(self, schema: list[ColumnInfo], active_filename: str):
        # dicts preserve insertion order, which mirrors DataFrame column order
        self.columns: dict[str, ColumnInfo] = {c.name: ColumnInfo(c.name, c.type, c.has_nulls) for c in schema}
        self.active_filename = active_filename
        self.diagnostics: list[Diagnostic] = []
        self.trace: list[dict] = []
        self._last_op: str | None = None
        self._normalized: set[str] = set()

    # -- reporting ---------------------------------------------------------
    def _report(self, severity, code, message, span: ast.Span, hint=None):
        self.diagnostics.append(Diagnostic(severity, code, message, "semantic", span.line, span.column,
                                           span.end_column, hint))

    def _snapshot(self) -> list[dict]:
        return [{"name": c.name, "type": c.type, "has_nulls": c.has_nulls} for c in self.columns.values()]

    def _lookup(self, ref: ast.ColumnRef, command: str) -> ColumnInfo | None:
        info = self.columns.get(ref.name)
        if info is None:
            matches = [n for n in self.columns if n.lower() == ref.name.lower()]
            hint = f"Column names are case-sensitive. Did you mean {matches[0]!r}?" if matches else \
                f"Available columns: {', '.join(self.columns) or '(none)'}"
            self._report(ERROR, "E_UNKNOWN_COLUMN", f"{command}: column {ref.name!r} does not exist at this point",
                         ref.span, hint)
        return info

    def _require_numeric(self, info: ColumnInfo, ref: ast.ColumnRef, command: str) -> bool:
        if info.type in NUMERIC_TYPES:
            return True
        if info.type == "empty":
            self._report(WARNING, "W_ALL_NULL_COLUMN",
                         f"{command}: column {ref.name!r} has no non-null values; execution will fail",
                         ref.span)
            return True
        self._report(ERROR, "E_TYPE_MISMATCH",
                     f"{command} requires a numeric column, but {ref.name!r} is {info.type}", ref.span)
        return False

    # -- entry point --------------------------------------------------------
    def analyze(self, program: ast.Program) -> SemanticResult:
        self._check_load(program.load)
        self.trace.append({"statement": "LOAD", "line": program.load.span.line, "schema": self._snapshot()})
        for stmt in program.transforms:
            before = len(self.diagnostics)
            getattr(self, "_check_" + type(stmt).__name__)(stmt)
            new = self.diagnostics[before:]
            self.trace.append({
                "statement": _statement_name(stmt),
                "line": stmt.span.line,
                "status": "error" if any(d.severity == ERROR for d in new) else
                          "warning" if any(d.severity == WARNING for d in new) else "ok",
                "schema": self._snapshot(),
            })
            self._last_op = type(stmt).__name__
        self._check_save(program.save)
        self.trace.append({"statement": "SAVE", "line": program.save.span.line, "schema": self._snapshot()})
        return SemanticResult(self.diagnostics, self.trace)

    # -- statements ----------------------------------------------------------
    def _check_load(self, stmt: ast.LoadStatement):
        if not is_safe_basename(stmt.filename):
            self._report(ERROR, "E_LOAD_PATH",
                         f"LOAD accepts only the uploaded file's name, not a path: {stmt.filename!r}", stmt.span,
                         f'Use LOAD "{self.active_filename}";')
        elif stmt.filename != self.active_filename:
            self._report(ERROR, "E_LOAD_MISMATCH",
                         f"LOAD {stmt.filename!r} does not match the uploaded file {self.active_filename!r}",
                         stmt.span, f'Use LOAD "{self.active_filename}";')

    def _check_save(self, stmt: ast.SaveStatement):
        if not is_safe_basename(stmt.filename) or not SAFE_OUTPUT_NAME.match(stmt.filename):
            self._report(ERROR, "E_SAVE_FILENAME", f"Invalid output file name {stmt.filename!r}", stmt.span,
                         "Use a plain file name ending in .csv (letters, digits, space, _ - . ( )), no folders.")

    def _check_RemoveNullsStatement(self, stmt):
        if self._last_op == "RemoveNullsStatement":
            self._report(WARNING, "W_REDUNDANT", "REMOVE_NULLS repeated; the second one has no effect", stmt.span)
        for c in self.columns.values():
            c.has_nulls = False

    def _check_RemoveDuplicatesStatement(self, stmt):
        if self._last_op == "RemoveDuplicatesStatement":
            self._report(WARNING, "W_REDUNDANT", "REMOVE_DUPLICATES repeated; the second one has no effect",
                         stmt.span)

    def _check_FillNullsStatement(self, stmt: ast.FillNullsStatement):
        info = self._lookup(stmt.column, "FILL_NULLS")
        if info is None:
            return
        if stmt.strategy in ("MEAN", "MEDIAN"):
            if not self._require_numeric(info, stmt.column, f"FILL_NULLS ... USING {stmt.strategy}"):
                return
        elif info.type == "empty":
            self._report(WARNING, "W_ALL_NULL_COLUMN",
                         f"FILL_NULLS: column {info.name!r} has no non-null values; execution will fail",
                         stmt.column.span)
        if not info.has_nulls:
            self._report(WARNING, "W_NO_NULLS",
                         f"FILL_NULLS: column {info.name!r} has no missing values at this point; no effect",
                         stmt.span)
        info.has_nulls = False

    def _check_DropColumnStatement(self, stmt: ast.DropColumnStatement):
        info = self._lookup(stmt.column, "DROP_COLUMN")
        if info is None:
            return
        if len(self.columns) == 1:
            self._report(ERROR, "E_DROP_LAST_COLUMN",
                         f"DROP_COLUMN would remove {info.name!r}, the only remaining column", stmt.column.span)
            return
        del self.columns[info.name]
        self._normalized.discard(info.name)

    def _check_RenameStatement(self, stmt: ast.RenameStatement):
        info = self._lookup(stmt.column, "RENAME")
        new = stmt.new_name.name
        if not new.strip() or len(new) > 255 or not new.isprintable():
            self._report(ERROR, "E_INVALID_COLUMN_NAME", f"RENAME: {new!r} is not a valid column name",
                         stmt.new_name.span)
            return
        if info is None:
            return
        if new == info.name:
            self._report(ERROR, "E_RENAME_SAME", f"RENAME: column {new!r} is renamed to itself", stmt.new_name.span)
            return
        if new in self.columns:
            self._report(ERROR, "E_RENAME_CONFLICT", f"RENAME: a column named {new!r} already exists",
                         stmt.new_name.span, "Drop or rename the existing column first.")
            return
        # rebuild to keep column order, with the renamed entry in place
        self.columns = {(new if k == info.name else k): v for k, v in self.columns.items()}
        info.name = new
        if stmt.column.name in self._normalized:
            self._normalized.discard(stmt.column.name)
            self._normalized.add(new)

    def _check_FilterStatement(self, stmt: ast.FilterStatement):
        info = self._lookup(stmt.column, "FILTER")
        if info is None:
            return
        lit = stmt.literal
        if info.type in NUMERIC_TYPES and lit.kind != "number":
            self._report(ERROR, "E_TYPE_MISMATCH",
                         f"FILTER: column {info.name!r} is {info.type} but is compared with string {lit.value!r}",
                         lit.span, "Remove the quotes to compare with a number." if _is_number(lit.value) else None)
        elif info.type == "string" and lit.kind != "string":
            self._report(ERROR, "E_TYPE_MISMATCH",
                         f"FILTER: column {info.name!r} is text but is compared with number {lit.value}",
                         lit.span, f'Quote the value to compare text: "{lit.value}".')
        elif info.type in ("boolean", "datetime"):
            self._report(ERROR, "E_UNSUPPORTED_TYPE",
                         f"FILTER on {info.type} columns is not supported in this version ({info.name!r})",
                         stmt.column.span)
        elif info.type == "empty":
            self._report(WARNING, "W_ALL_NULL_COLUMN",
                         f"FILTER: column {info.name!r} has no non-null values; every row will be removed",
                         stmt.column.span)
        elif info.type == "string" and stmt.operator in (">", "<", ">=", "<="):
            self._report(INFO, "I_LEXICOGRAPHIC",
                         f"FILTER: {stmt.operator} on text column {info.name!r} compares alphabetically",
                         stmt.span)

    def _check_NormalizeStatement(self, stmt: ast.NormalizeStatement):
        info = self._lookup(stmt.column, "NORMALIZE")
        if info is None or not self._require_numeric(info, stmt.column, "NORMALIZE"):
            return
        if info.name in self._normalized:
            self._report(WARNING, "W_REDUNDANT", f"NORMALIZE: column {info.name!r} is already normalized",
                         stmt.span)
        self._normalized.add(info.name)
        if info.type != "empty":
            info.type = "float"

    def _check_SortStatement(self, stmt: ast.SortStatement):
        self._lookup(stmt.column, "SORT")


def _is_number(text) -> bool:
    try:
        float(text)
        return True
    except (TypeError, ValueError):
        return False


def _statement_name(stmt) -> str:
    return {
        "RemoveNullsStatement": "REMOVE_NULLS", "RemoveDuplicatesStatement": "REMOVE_DUPLICATES",
        "FillNullsStatement": "FILL_NULLS", "DropColumnStatement": "DROP_COLUMN", "RenameStatement": "RENAME",
        "FilterStatement": "FILTER", "NormalizeStatement": "NORMALIZE", "SortStatement": "SORT",
    }[type(stmt).__name__]


def analyze(program: ast.Program, schema: list[ColumnInfo], active_filename: str) -> SemanticResult:
    return SemanticAnalyzer(schema, active_filename).analyze(program)
