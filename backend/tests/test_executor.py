import pandas as pd
import pytest

from app.services.executor import execute

from conftest import STUDENTS_PROGRAM, compile_for, df_from, program


def run(df, *stmts):
    report = compile_for(program(*stmts), df)
    assert report["status"] == "success", report["diagnostics"]
    return execute(df, report["ir"])


def test_sample_program_expected_result(students_df):
    original = students_df.copy(deep=True)
    report = compile_for(STUDENTS_PROGRAM, students_df, "students.csv")
    result = execute(students_df, report["ir"])
    assert result.status == "success"
    out = result.dataframe
    assert out["STUDENT_NAME"].tolist() == ["Diya", "Kabir", "Aarav", "Rohan"]
    assert out["AGE"].tolist() == [19, 22, 20, 20]
    assert out["MARKS"].tolist() == pytest.approx([1.0, 11 / 15, 10 / 15, 0.0])
    assert result.before == {"rows": 6, "columns": 3} and result.after == {"rows": 4, "columns": 3}
    ops = {o["index"]: o for o in result.operations}
    assert ops[0]["fill_value"] == 20 and ops[0]["cells_changed"] == 1
    assert ops[1]["fill_value"] == 86 and ops[1]["cells_changed"] == 1
    assert ops[2]["rows_removed"] == 1 and ops[3]["rows_removed"] == 1
    assert (ops[4]["min"], ops[4]["max"]) == (75, 90)
    assert out.to_csv(index=False, lineterminator="\n") == ("STUDENT_NAME,AGE,MARKS\nDiya,19,1.0\nKabir,22,0.7333333333333333\n"
                                       "Aarav,20,0.6666666666666666\nRohan,20,0.0\n")
    pd.testing.assert_frame_equal(students_df, original)  # source untouched


def test_remove_nulls():
    df = df_from("A,B\n1,x\n,y\n3,\n4,z\n")
    r = run(df, "REMOVE_NULLS;")
    assert r.dataframe["A"].tolist() == [1, 4] and r.operations[0]["rows_removed"] == 2


def test_remove_duplicates_keeps_first():
    df = df_from("A,B\n1,x\n2,y\n1,x\n1,z\n")
    r = run(df, "REMOVE_DUPLICATES;")
    assert r.dataframe.values.tolist() == [[1, "x"], [2, "y"], [1, "z"]]


def test_fill_mean_fractional_converts_to_float():
    df = df_from("A,K\n1,a\n2,b\n,c\n")
    r = run(df, "FILL_NULLS A USING MEAN;")
    assert r.dataframe["A"].tolist() == [1.0, 2.0, 1.5]
    assert str(r.dataframe["A"].dtype) == "Float64"


def test_fill_median_integral_keeps_integer():
    df = df_from("A,K\n1,a\n3,b\n,c\n")
    r = run(df, "FILL_NULLS A USING MEDIAN;")
    assert r.dataframe["A"].tolist() == [1, 3, 2] and str(r.dataframe["A"].dtype) == "Int64"


def test_mode_tie_picks_first_in_row_order():
    df = df_from("C,K\nb,1\na,2\n,3\na,4\nb,5\n")
    assert run(df, "FILL_NULLS C USING MODE;").dataframe["C"].tolist() == ["b", "a", "b", "a", "b"]
    df = df_from("N,K\n5,1\n7,2\n7,3\n5,4\n,5\n")
    assert run(df, "FILL_NULLS N USING MODE;").dataframe["N"].tolist()[-1] == 5


def test_mode_clear_winner():
    df = df_from("C,K\nb,1\na,2\na,3\n,4\n")
    assert run(df, "FILL_NULLS C USING MODE;").dataframe["C"].tolist()[-1] == "a"


@pytest.mark.parametrize("stmt", ["FILL_NULLS E USING MEAN;", "FILL_NULLS E USING MEDIAN;",
                                  "FILL_NULLS E USING MODE;", "NORMALIZE E;"])
def test_all_null_column_fails_without_corruption(stmt):
    df = df_from("A,E\n1,\n2,\n")
    original = df.copy(deep=True)
    r = run(df, "SORT A DESC;", stmt)
    assert r.status == "failed" and r.error["code"] == "E_ALL_NULL_COLUMN" and r.error["index"] == 1
    assert r.dataframe is None and r.after is None
    assert [o["status"] for o in r.operations] == ["ok", "failed"]
    pd.testing.assert_frame_equal(df, original)


def test_drop_and_rename():
    df = df_from("A,B,C\n1,2,3\n")
    r = run(df, "DROP_COLUMN B;", "RENAME C TO D;")
    assert list(r.dataframe.columns) == ["A", "D"]
    assert r.operations[0]["columns_after"] == 2


@pytest.mark.parametrize("stmt,expected", [
    ("FILTER A == 2;", [2]), ("FILTER A != 2;", [1, 3]), ("FILTER A > 1;", [2, 3]),
    ("FILTER A < 2;", [1]), ("FILTER A >= 2;", [2, 3]), ("FILTER A <= 2.5;", [1, 2]),
])
def test_numeric_filters_drop_nulls(stmt, expected):
    df = df_from("A,K\n1,a\n2,b\n,c\n3,d\n")
    assert run(df, stmt).dataframe["A"].tolist() == expected


def test_string_filters_and_nulls():
    df = df_from("S\nACTIVE\nINACTIVE\n\nactive\n")
    assert run(df, 'FILTER S == "ACTIVE";').dataframe["S"].tolist() == ["ACTIVE"]
    assert run(df, 'FILTER S != "ACTIVE";').dataframe["S"].tolist() == ["INACTIVE", "active"]
    assert run(df, 'FILTER S < "B";').dataframe["S"].tolist() == ["ACTIVE"]


def test_filter_to_empty_is_valid():
    df = df_from("A,B\n1,x\n2,y\n")
    r = run(df, "FILTER A > 100;")
    assert r.status == "success" and r.after == {"rows": 0, "columns": 2}
    assert r.dataframe.to_csv(index=False, lineterminator="\n") == "A,B\n"
    assert [w["code"] for w in r.warnings] == ["W_EMPTY_RESULT"]


def test_normalize_preserves_nulls():
    df = df_from("A,K\n10,a\n,b\n20,c\n15,d\n")
    out = run(df, "NORMALIZE A;").dataframe["A"]
    assert out.isna().tolist() == [False, True, False, False]
    assert out.dropna().tolist() == [0.0, 1.0, 0.5]


def test_normalize_constant_column():
    df = df_from("A,K\n5,a\n5,b\n,c\n")
    r = run(df, "NORMALIZE A;")
    assert r.dataframe["A"].tolist()[:2] == [0.0, 0.0] and pd.isna(r.dataframe["A"].iloc[2])
    assert [w["code"] for w in r.warnings] == ["W_CONSTANT_COLUMN"]


def test_sort_is_stable_with_nulls_last():
    df = df_from("K,V\n2,a\n,b\n1,c\n2,d\n1,e\n")
    asc = run(df, "SORT K ASC;").dataframe
    assert asc["V"].tolist() == ["c", "e", "a", "d", "b"]
    desc = run(df, "SORT K DESC;").dataframe
    assert desc["V"].tolist() == ["a", "d", "c", "e", "b"]


def test_empty_dataset():
    df = df_from("A,B\n")
    r = run(df, "REMOVE_NULLS;", "REMOVE_DUPLICATES;", "SORT A ASC;")
    assert r.status == "success" and r.after == {"rows": 0, "columns": 2}


def test_tampered_ir_is_rejected(students_df):
    r = execute(students_df, {"version": 1, "input": "x", "output": "y.csv",
                              "instructions": [{"index": 0, "op": "__import__", "column": "os"}]})
    assert r.status == "failed" and r.error["code"] == "E_INVALID_IR"
