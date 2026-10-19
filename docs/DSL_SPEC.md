# CleanScript language specification (v1)

This is the single reference for the language. The lexer (`backend/app/compiler/lexer.py`), parser (`parser.py`), semantic analyzer (`semantic.py`), code generator (`codegen.py`), executor (`app/services/executor.py`) and the in-app language guide all implement this document.

## 1. Lexical structure

| Token | Rule |
|---|---|
| Whitespace | Spaces, tabs, `\r` and `\n` separate tokens and are otherwise ignored. |
| Keywords | `LOAD SAVE REMOVE_NULLS REMOVE_DUPLICATES FILL_NULLS DROP_COLUMN RENAME FILTER NORMALIZE SORT USING TO MEAN MEDIAN MODE ASC DESC`. Recognised **case-insensitively** (`sort` is `SORT`). |
| IDENTIFIER | `[A-Za-z_][A-Za-z0-9_]*` that is not a keyword. Case is preserved. |
| STRING | `"` … `"` on one line. Escapes: `\"` and `\\` only; any other backslash sequence is an error. |
| NUMBER | `-?[0-9]+(\.[0-9]+)?`, e.g. `18`, `72.5`, `-3`. A number immediately followed by a letter, `_` or `.` is malformed (`12abc`, `1.2.3`, `5.`). |
| Operators | `==` `!=` `>=` `<=` `>` `<` (longest match first). A lone `=` or `!` is an error. |
| Punctuation | `;` |
| EOF | End of input. |

There are no comments. `#`, `//`, single quotes and any other character produce `E_UNEXPECTED_CHAR`.

Every token records `line`, `column` (1-based) and `end_column`.

## 2. Grammar (EBNF)

`{ x }` = zero or more; quoted words are keywords; IDENTIFIER, STRING, NUMBER and EOF are token types.

```ebnf
program             = load_statement, { transform_statement }, save_statement, EOF ;
load_statement      = "LOAD", STRING, ";" ;
save_statement      = "SAVE", STRING, ";" ;
transform_statement = remove_nulls | remove_duplicates | fill_nulls | drop_column
                    | rename_column | filter_rows | normalize_column | sort_rows ;
remove_nulls        = "REMOVE_NULLS", ";" ;
remove_duplicates   = "REMOVE_DUPLICATES", ";" ;
fill_nulls          = "FILL_NULLS", column_ref, "USING", strategy, ";" ;
strategy            = "MEAN" | "MEDIAN" | "MODE" ;
drop_column         = "DROP_COLUMN", column_ref, ";" ;
rename_column       = "RENAME", column_ref, "TO", column_ref, ";" ;
filter_rows         = "FILTER", column_ref, comparator, literal, ";" ;
comparator          = "==" | "!=" | ">" | "<" | ">=" | "<=" ;
normalize_column    = "NORMALIZE", column_ref, ";" ;
sort_rows           = "SORT", column_ref, direction, ";" ;
direction           = "ASC" | "DESC" ;
column_ref          = IDENTIFIER | STRING ;
literal             = NUMBER | STRING ;
```

Consequences: exactly one LOAD, first; exactly one SAVE, last; nothing after SAVE; an empty transform list is valid. Keywords used as column names must be quoted (`SORT "MODE" ASC;`).

The parser is recursive descent, with one method per production (`parse_fill_nulls`, `parse_column_ref`, …). It stops at the first syntax error. Unknown commands get a "did you mean" suggestion.

## 3. Types

Column types are inferred from the uploaded CSV (`pd.read_csv(..., dtype_backend="numpy_nullable")`):

| Type | Meaning |
|---|---|
| `integer` | Int64 column (nulls allowed) |
| `float` | Float64 column |
| `string` | text |
| `boolean` | true/false column (pandas-detected) |
| `datetime` | never inferred from CSV in v1 |
| `empty` | every value is missing |

`integer` and `float` are *numeric*. The profiler warns when a text column is mostly numeric (`W_MIXED_TYPES`).

## 4. Semantic rules

The analyzer walks statements in order with a copy of the schema (name → type, may-contain-nulls). It updates that copy as statements change it and reports **all** errors.

| Check | Code |
|---|---|
| LOAD name has `/`, `\`, `:`, `..` or control characters | `E_LOAD_PATH` |
| LOAD name ≠ the uploaded file's (sanitized) name, case-sensitive | `E_LOAD_MISMATCH` |
| SAVE name is not a plain `*.csv` basename (`[A-Za-z0-9_][A-Za-z0-9 _().-]*\.csv`, no `..`) | `E_SAVE_FILENAME` |
| Column does not exist *at that point* (after earlier RENAME/DROP_COLUMN) | `E_UNKNOWN_COLUMN` (+ case hint) |
| MEAN/MEDIAN/NORMALIZE on a non-numeric column | `E_TYPE_MISMATCH` |
| FILTER numeric column with a string literal, or text column with a number | `E_TYPE_MISMATCH` |
| FILTER on boolean/datetime | `E_UNSUPPORTED_TYPE` |
| DROP_COLUMN of the only remaining column | `E_DROP_LAST_COLUMN` |
| RENAME to an existing name | `E_RENAME_CONFLICT` |
| RENAME a column to itself | `E_RENAME_SAME` (rejected, not a no-op) |
| RENAME to an empty/blank/unprintable name | `E_INVALID_COLUMN_NAME` |
| Operation on an all-null column | `W_ALL_NULL_COLUMN` (execution will fail or remove every row) |
| FILL_NULLS on a column with no nulls at that point | `W_NO_NULLS` |
| REMOVE_NULLS / REMOVE_DUPLICATES repeated back to back; NORMALIZE twice | `W_REDUNDANT` |
| `<`, `>`, `<=`, `>=` on text | `I_LEXICOGRAPHIC` |

Warnings and info do not block compilation; errors do. IR is generated only when there are no errors.

## 5. Execution semantics

Statements apply in source order to a **copy** of the uploaded DataFrame. If any operation fails, the copy is discarded. The upload and earlier results are untouched.

| Statement | Behaviour |
|---|---|
| `REMOVE_NULLS` | Drop rows with a missing value in any current column. Reports `rows_removed`. |
| `REMOVE_DUPLICATES` | Drop rows identical (all current columns) to an earlier row; keep the first. |
| `FILL_NULLS c USING MEAN/MEDIAN` | Numeric only; nulls ignored when computing. If `c` is integer and the value is whole, it stays integer; otherwise it becomes float. All-null → `E_ALL_NULL_COLUMN`. Reports `cells_changed`, `fill_value`. |
| `FILL_NULLS c USING MODE` | Any type. Most frequent non-null value; **ties → the tied value that appears first in current row order**. All-null → error. |
| `DROP_COLUMN c` | Remove the column. |
| `RENAME a TO b` | Rename; column order is kept. |
| `FILTER c op v` | Keep rows where the comparison is true. **Rows where `c` is null never match**, including for `!=`. Text comparisons are exact and case-sensitive; ordering is lexicographic. A zero-row result is valid (`W_EMPTY_RESULT`). |
| `NORMALIZE c` | `(x − min) / (max − min)` over non-null values; nulls stay null; result is float. Constant column → non-null values become `0.0` + `W_CONSTANT_COLUMN`. All-null → `E_ALL_NULL_COLUMN`. |
| `SORT c ASC/DESC` | Stable sort; nulls last in both directions. Reports `order_changed`. |
| `SAVE "f.csv"` | Names the download. The server chooses where the file is stored. Output is UTF-8, `\n` line endings, no index. |

## 6. Worked example

`examples/students.csv` + `examples/students.clean`:

1. Median of non-null AGE (20, 19, 20, 17, 22) = 20 → Rohan's AGE = 20 (AGE stays integer).
2. Mean of non-null MARKS (85, 90, 75, 85, 95) = 86 → Kabir's MARKS = 86.
3. The second `Aarav,20,85` row is removed (6 → 5 rows).
4. `FILTER AGE >= 18` removes Meera (17) (5 → 4 rows).
5. MARKS min 75, max 90 → Diya 1.0, Kabir 0.7333…, Aarav 0.6666…, Rohan 0.0.
6. Sorted by MARKS descending.

```csv
STUDENT_NAME,AGE,MARKS
Diya,19,1.0
Kabir,22,0.7333333333333333
Aarav,20,0.6666666666666666
Rohan,20,0.0
```

These values are asserted by `tests/test_executor.py` and `tests/test_api.py`. The application computes them; nothing is hard-coded.
