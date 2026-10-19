# CleanScript REST API

Base path `/api`. Request/response models: `backend/app/models/schemas.py`. Live OpenAPI docs: `/docs` on the backend.

## Conventions

- Every response carries an `X-Request-ID` header.
- Errors always look like `{"error": {"code": "E_…", "message": "…"}, "request_id": "…"}`. Stack traces and filesystem paths are never returned.
- Values in previews follow one JSON policy: missing (`NA`/`NaN`/`NaT`) → `null`; ±infinity → `"inf"`/`"-inf"`; numpy scalars → JSON numbers; timestamps → ISO 8601.

### Status code policy

| Situation | Status |
|---|---|
| Compile request well-formed (even if the program has errors) | **200**, `status: "failed"` + `diagnostics` |
| Execute a compilation whose status is `failed` | **409** `E_COMPILATION_FAILED` |
| Execution hits a data-dependent error (e.g. all-null column) | **200**, `status: "failed"` + `error` |
| Unknown/expired session, compilation (or one from another session), result | **404** `E_SESSION_NOT_FOUND` / `E_COMPILATION_NOT_FOUND` / `E_RESULT_NOT_FOUND` |
| Bad upload (extension, encoding, empty, malformed CSV) | **400** `E_UNSUPPORTED_FILE` / `E_ENCODING` / `E_EMPTY_CSV` / `E_MALFORMED_CSV` |
| Upload or dataset over limits | **413** `E_FILE_TOO_LARGE` / `E_DATASET_TOO_LARGE` |
| Body/field validation failure (missing file, source too long) | **422** `E_VALIDATION` |
| Unexpected server error | **500** `E_INTERNAL` |

## Endpoints

### `GET /api/health`
`{"status": "ok", "service": "cleanscript", "version": "1.0.0"}`

### `POST /api/sessions/upload`
Multipart form field `file` (`.csv`, UTF-8, ≤ 5 MB by default). The client filename is reduced to a safe basename: path removed, characters outside `A-Za-z0-9 _().-` become `_`. That name is what `LOAD` must use. The file is stored as `input.csv` in a private per-session directory.

```json
{
  "session_id": "opaque",
  "filename": "students.csv",
  "profile": {
    "rows": 6, "columns": 3, "missing_cells": 2, "duplicate_rows": 1,
    "schema": [{"name": "AGE", "type": "integer", "dtype": "Int64", "missing": 1, "missing_pct": 16.67,
                "unique": 4, "stats": {"min": 17, "max": 22, "mean": 19.6, "median": 20.0}}],
    "warnings": [{"code": "W_CONSTANT_COLUMN", "column": "X", "message": "…"}],
    "preview": {"columns": ["…"], "rows": [["…"]], "total_rows": 6, "truncated": false}
  },
  "limits": {"preview_rows": 50, "max_source_chars": 20000}
}
```

### `GET /api/sessions/{session_id}/profile`
Same shape as upload. Profiling is read-only; the profile is identical before and after any execution.

### `DELETE /api/sessions/{session_id}`
204. Removes the session directory. Sessions also expire after 2 hours idle. The oldest sessions are evicted beyond 100.

### `POST /api/sessions/{session_id}/compile`
Request `{"source": "LOAD \"students.csv\"; …"}` (≤ 20 000 chars).

```json
{
  "compilation_id": "opaque",
  "session_id": "…",
  "status": "success | failed",
  "stages": {"lexer": "passed", "parser": "passed", "semantic": "passed | warning | failed", "ir": "passed | skipped", "codegen": "passed | skipped"},
  "tokens": [{"type": "LOAD", "category": "KEYWORD", "lexeme": "LOAD", "value": "LOAD", "line": 1, "column": 1, "end_column": 5}],
  "ast": {"node": "Program", "load": {…}, "transforms": [{"node": "FillNullsStatement", "column": {"node": "ColumnRef", "name": "AGE", "quoted": false, "span": {…}}, "strategy": "MEDIAN", "span": {"line": 2, "column": 1, "end_column": 11}}], "save": {…}},
  "semantic": {"trace": [{"statement": "FILL_NULLS", "line": 2, "status": "ok", "schema": [{"name": "AGE", "type": "integer", "has_nulls": false}]}]},
  "ir": {"version": 1, "input": "students.csv", "output": "cleaned_students.csv",
         "instructions": [{"index": 0, "op": "fill_nulls", "column": "AGE", "strategy": "MEDIAN", "source": {"line": 2, "column": 1}}]},
  "generated_code": "import pandas as pd\n…",
  "diagnostics": [{"severity": "error", "code": "E_UNKNOWN_COLUMN", "message": "…", "stage": "semantic", "line": 3, "column": 6, "end_column": 11, "hint": "…"}]
}
```

Fields for stages that did not run are `null`: `tokens` after a lexer error; `ast` and `semantic` after a parse error; `ir` and `generated_code` after a semantic error. Each compile request is stored, and the last 20 per session are kept.

IR ops: `remove_nulls`, `remove_duplicates`, `fill_nulls{column,strategy}`, `drop_column{column}`, `rename_column{column,new_name}`, `filter_rows{column,operator,value}`, `normalize{column}`, `sort_rows{column,direction}`.

### `POST /api/sessions/{session_id}/execute`
Request `{"compilation_id": "…"}`. The server executes the IR **it stored** for that compilation. Clients cannot submit instructions. The IR is structurally re-validated before running.

```json
{
  "status": "success | failed",
  "session_id": "…", "compilation_id": "…",
  "result_id": "opaque | null",
  "output_filename": "cleaned_students.csv",
  "operations": [{"index": 0, "op": "fill_nulls", "source": {"line": 2, "column": 1}, "status": "ok",
                  "rows_before": 6, "rows_after": 6, "columns_before": 3, "columns_after": 3,
                  "duration_ms": 0.3, "cells_changed": 1, "fill_value": 20.0}],
  "warnings": [{"code": "W_CONSTANT_COLUMN", "message": "…", "index": 4, "source": {…}}],
  "error": null,
  "before": {"rows": 6, "columns": 3},
  "after": {"rows": 4, "columns": 3},
  "result_profile": { "…same shape as profile…" }
}
```

Per-op metrics: `rows_removed` (remove_*, filter), `cells_changed` + `fill_value` (fill), `cells_changed` + `min` + `max` (normalize), `order_changed` (sort). On failure, `error` = `{code, message, index, source}`, the failing op has `status: "failed"`, and `result_id`, `after` and `result_profile` are `null`.

### `GET /api/sessions/{session_id}/result[?result_id=]`
The stored execution response. Defaults to the latest; the last 5 results per session are kept.

### `GET /api/sessions/{session_id}/download[?result_id=]`
`text/csv; charset=utf-8` with `Content-Disposition: attachment; filename="<SAVE name>"`. The bytes are the executed DataFrame written with `to_csv(index=False, lineterminator="\n")`.
