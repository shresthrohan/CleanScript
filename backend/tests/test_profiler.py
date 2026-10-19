import json

import pandas as pd
import pytest

from app.services.dataset_profiler import DatasetError, profile, read_csv_bytes, to_json_value

from conftest import df_from


def test_students_profile(students_df):
    original = students_df.copy(deep=True)
    p = profile(students_df)
    assert (p["rows"], p["columns"], p["duplicate_rows"], p["missing_cells"]) == (6, 3, 1, 2)
    by_name = {c["name"]: c for c in p["schema"]}
    assert by_name["AGE"]["missing"] == 1 and by_name["MARKS"]["missing"] == 1
    assert by_name["AGE"]["type"] == "integer" and by_name["STUDENT_NAME"]["type"] == "string"
    assert by_name["MARKS"]["stats"] == {"min": 75, "max": 95, "mean": 86.0, "median": 85.0}
    assert p["preview"]["rows"][2] == ["Rohan", None, 75]
    json.dumps(p)  # fully serializable
    pd.testing.assert_frame_equal(students_df, original)  # read-only


def test_preview_limit():
    df = df_from("A\n" + "\n".join(str(i) for i in range(100)) + "\n")
    pv = profile(df, preview_rows=10)["preview"]
    assert len(pv["rows"]) == 10 and pv["truncated"] and pv["total_rows"] == 100


def test_warnings():
    df = df_from("C,E,M\n1,,1\n1,,2\n1,,x\n")
    codes = {(w["code"], w["column"]) for w in profile(df)["warnings"]}
    assert ("W_CONSTANT_COLUMN", "C") in codes
    assert ("W_ALL_NULL_COLUMN", "E") in codes
    assert ("W_MIXED_TYPES", "M") in codes


@pytest.mark.parametrize("raw,code", [
    (b"", "E_EMPTY_CSV"),
    (b"   \n", "E_EMPTY_CSV"),
    (b"\xff\xfe\x00bad", "E_ENCODING"),
    (b"A,A\n1,2\n", "E_MALFORMED_CSV"),
    (b"A,\n1,2\n", "E_MALFORMED_CSV"),
    (b'A,B\n"unterminated,2\n', "E_MALFORMED_CSV"),
    (b"A,B\n1,2,3,4\n", "E_MALFORMED_CSV"),
])
def test_bad_csv(raw, code):
    with pytest.raises(DatasetError) as exc:
        read_csv_bytes(raw)
    assert exc.value.code == code


def test_utf8_bom_and_unicode():
    df = read_csv_bytes("﻿NAME,CITY\nZoë,München\n".encode("utf-8"))
    assert list(df.columns) == ["NAME", "CITY"] and df["CITY"][0] == "München"


@pytest.mark.parametrize("value,expected", [
    (pd.NA, None), (float("nan"), None), (float("inf"), "inf"), (float("-inf"), "-inf"),
    (pd.Timestamp("2024-01-02"), "2024-01-02T00:00:00"), (True, True),
])
def test_json_policy(value, expected):
    assert to_json_value(value) == expected
