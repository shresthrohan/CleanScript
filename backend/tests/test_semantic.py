import pytest

from conftest import STUDENTS_PROGRAM, codes, compile_for, program


def test_sample_program_is_clean(students_df):
    r = compile_for(STUDENTS_PROGRAM, students_df, "students.csv")
    assert r["status"] == "success" and r["diagnostics"] == []
    assert r["stages"] == {s: "passed" for s in ("lexer", "parser", "semantic", "ir", "codegen")}


@pytest.mark.parametrize("stmt", [
    "FILL_NULLS age USING MEAN;", "DROP_COLUMN NOPE;", "SORT NOPE ASC;", "NORMALIZE NOPE;",
    "FILTER NOPE > 1;", "RENAME NOPE TO X;",
])
def test_unknown_column(mixed_df, stmt):
    r = compile_for(program(stmt), mixed_df)
    assert r["status"] == "failed" and codes(r, "error") == ["E_UNKNOWN_COLUMN"]
    assert r["stages"]["semantic"] == "failed" and r["ir"] is None and r["generated_code"] is None
    d = r["diagnostics"][0]
    assert d["line"] == 2 and d["stage"] == "semantic"


def test_unknown_column_case_hint(mixed_df):
    r = compile_for(program("SORT age ASC;"), mixed_df)
    assert "AGE" in r["diagnostics"][0]["hint"]


@pytest.mark.parametrize("stmt", ["FILL_NULLS CITY USING MEAN;", "FILL_NULLS CITY USING MEDIAN;", "NORMALIZE NAME;"])
def test_numeric_required(mixed_df, stmt):
    assert codes(compile_for(program(stmt), mixed_df), "error") == ["E_TYPE_MISMATCH"]


def test_mode_allowed_on_text(mixed_df):
    assert compile_for(program("FILL_NULLS CITY USING MODE;"), mixed_df)["status"] == "success"


@pytest.mark.parametrize("stmt,ok", [
    ("FILTER AGE >= 18;", True),
    ("FILTER MARKS < 72.5;", True),
    ('FILTER STATUS == "ACTIVE";', True),
    ('FILTER AGE >= "18";', False),
    ("FILTER STATUS == 1;", False),
])
def test_filter_type_compatibility(mixed_df, stmt, ok):
    r = compile_for(program(stmt), mixed_df)
    assert (r["status"] == "success") is ok
    if not ok:
        assert codes(r, "error") == ["E_TYPE_MISMATCH"]


def test_filter_string_ordering_is_info(mixed_df):
    r = compile_for(program('FILTER CITY > "M";'), mixed_df)
    assert r["status"] == "success" and codes(r) == ["I_LEXICOGRAPHIC"]


def test_schema_tracks_rename_and_drop(mixed_df):
    ok = compile_for(program("RENAME NAME TO STUDENT;", "SORT STUDENT ASC;", "DROP_COLUMN CITY;"), mixed_df)
    assert ok["status"] == "success"
    trace_cols = [c["name"] for c in ok["semantic"]["trace"][-1]["schema"]]
    assert trace_cols == ["STUDENT", "AGE", "MARKS", "STATUS", "EMPTY"]

    old_name = compile_for(program("RENAME NAME TO STUDENT;", "SORT NAME ASC;"), mixed_df)
    assert codes(old_name, "error") == ["E_UNKNOWN_COLUMN"]
    assert old_name["diagnostics"][0]["line"] == 3

    dropped = compile_for(program("DROP_COLUMN AGE;", "FILTER AGE > 1;"), mixed_df)
    assert codes(dropped, "error") == ["E_UNKNOWN_COLUMN"]


def test_rename_conflicts(mixed_df):
    assert codes(compile_for(program("RENAME NAME TO AGE;"), mixed_df), "error") == ["E_RENAME_CONFLICT"]
    assert codes(compile_for(program("RENAME NAME TO NAME;"), mixed_df), "error") == ["E_RENAME_SAME"]
    assert codes(compile_for(program('RENAME NAME TO "  ";'), mixed_df), "error") == ["E_INVALID_COLUMN_NAME"]


def test_drop_last_column():
    from conftest import df_from
    df = df_from("A,B\n1,2\n")
    r = compile_for(program("DROP_COLUMN A;", "DROP_COLUMN B;"), df)
    assert codes(r, "error") == ["E_DROP_LAST_COLUMN"]


def test_multiple_errors_are_all_reported(mixed_df):
    r = compile_for(program("SORT X ASC;", "NORMALIZE CITY;", "FILTER Y > 1;"), mixed_df)
    assert codes(r, "error") == ["E_UNKNOWN_COLUMN", "E_TYPE_MISMATCH", "E_UNKNOWN_COLUMN"]
    assert [d["line"] for d in r["diagnostics"]] == [2, 3, 4]


@pytest.mark.parametrize("load,code", [
    ("other.csv", "E_LOAD_MISMATCH"),
    ("../data.csv", "E_LOAD_PATH"),
    ("/etc/passwd", "E_LOAD_PATH"),
    ("C:\\\\data.csv", "E_LOAD_PATH"),
    ("sub/data.csv", "E_LOAD_PATH"),
    ("DATA.csv", "E_LOAD_MISMATCH"),
])
def test_load_must_be_active_upload(mixed_df, load, code):
    assert codes(compile_for(program(load=load), mixed_df), "error") == [code]


@pytest.mark.parametrize("save", ["../out.csv", "out.txt", "dir/out.csv", "C:\\\\out.csv", ".csv", "a..b.csv", ""])
def test_save_name_rejected(mixed_df, save):
    assert codes(compile_for(program(save=save), mixed_df), "error") == ["E_SAVE_FILENAME"]


@pytest.mark.parametrize("save", ["out.csv", "cleaned students (v2).csv", "a_b-c.CSV"])
def test_save_name_accepted(mixed_df, save):
    assert compile_for(program(save=save), mixed_df)["status"] == "success"


def test_warnings_do_not_block(mixed_df):
    r = compile_for(program("REMOVE_DUPLICATES;", "REMOVE_DUPLICATES;", "FILL_NULLS NAME USING MODE;"), mixed_df)
    assert r["status"] == "success" and r["stages"]["semantic"] == "warning"
    assert codes(r, "warning") == ["W_REDUNDANT", "W_NO_NULLS"]


def test_null_tracking(mixed_df):
    r = compile_for(program("REMOVE_NULLS;", "FILL_NULLS AGE USING MEAN;"), mixed_df)
    assert codes(r, "warning") == ["W_NO_NULLS"]
    r = compile_for(program("FILL_NULLS AGE USING MEAN;", "FILL_NULLS AGE USING MEDIAN;"), mixed_df)
    assert codes(r, "warning") == ["W_NO_NULLS"]


def test_all_null_column_warns(mixed_df):
    r = compile_for(program("FILL_NULLS EMPTY USING MEAN;"), mixed_df)
    assert r["status"] == "success" and "W_ALL_NULL_COLUMN" in codes(r, "warning")


def test_double_normalize_warns(mixed_df):
    assert codes(compile_for(program("NORMALIZE AGE;", "NORMALIZE AGE;"), mixed_df)) == ["W_REDUNDANT"]
