"""IR shape, code generation, and equivalence between generated Pandas code and the executor.

Executing the generated code here is test-only: it is our compiler's output run in a temp
directory to prove it matches the interpreter. The application never executes generated code.
"""
import ast as pyast
import os

import pandas as pd
import pytest

from app.compiler.ir import validate_ir
from app.services.executor import execute

from conftest import EXAMPLES, STUDENTS_CSV, STUDENTS_PROGRAM, compile_for, df_from, program


def test_ir_shape(students_df):
    ir = compile_for(STUDENTS_PROGRAM, students_df, "students.csv")["ir"]
    assert ir["version"] == 1 and ir["input"] == "students.csv" and ir["output"] == "cleaned_students.csv"
    assert [i["op"] for i in ir["instructions"]] == [
        "fill_nulls", "fill_nulls", "remove_duplicates", "filter_rows", "normalize", "sort_rows"]
    assert ir["instructions"][0] == {"index": 0, "op": "fill_nulls", "column": "AGE", "strategy": "MEDIAN",
                                     "source": {"line": 2, "column": 1}}
    assert ir["instructions"][3]["value"] == 18 and ir["instructions"][3]["operator"] == ">="
    assert validate_ir(ir) == []


def test_validate_ir_rejects_tampering():
    assert validate_ir({"version": 1, "input": "a.csv", "output": "b.csv",
                        "instructions": [{"op": "exec", "code": "x"}]}) == ["instruction 0: unknown op 'exec'"]
    bad = {"version": 1, "input": "a.csv", "output": "b.csv",
           "instructions": [{"op": "filter_rows", "column": "A", "operator": "in", "value": 1}]}
    assert validate_ir(bad) == ["instruction 0: invalid operator 'in'"]
    assert validate_ir({"version": 2}) != []


def test_codegen_is_deterministic_and_valid_python(students_df):
    a = compile_for(STUDENTS_PROGRAM, students_df, "students.csv")["generated_code"]
    b = compile_for(STUDENTS_PROGRAM, students_df, "students.csv")["generated_code"]
    assert a == b
    pyast.parse(a)
    assert "pd.read_csv('students.csv', dtype_backend='numpy_nullable')" in a
    assert "df.to_csv('cleaned_students.csv', index=False, lineterminator='\\n')" in a


def test_codegen_escapes_hostile_names():
    df = df_from('"we\'ird""; import os",B\nx,1\n')
    col = df.columns[0]
    src = program('RENAME "we\'ird\\"; import os" TO "x\\\\y";', "SORT B ASC;")
    r = compile_for(src, df)
    assert r["status"] == "success", r["diagnostics"]
    code = r["generated_code"]
    tree = pyast.parse(code)
    # the only import in the generated module is pandas
    imports = [n for n in pyast.walk(tree) if isinstance(n, (pyast.Import, pyast.ImportFrom))]
    assert len(imports) == 1 and imports[0].names[0].name == "pandas"
    assert repr(col) in code


def _run_generated(code: str, csv_bytes: bytes, input_name: str, output_name: str, tmp_path) -> pd.DataFrame:
    (tmp_path / input_name).write_bytes(csv_bytes)
    cwd = os.getcwd()
    os.chdir(tmp_path)
    try:
        exec(compile(code, "<generated>", "exec"), {})  # test-only, see module docstring
    finally:
        os.chdir(cwd)
    return pd.read_csv(tmp_path / output_name, dtype_backend="numpy_nullable")


EQUIVALENCE_CASES = [
    (STUDENTS_CSV, STUDENTS_PROGRAM, "students.csv"),
    ((EXAMPLES / "students_extended.csv").read_bytes(), (EXAMPLES / "students_extended.clean").read_text(),
     "students_extended.csv"),
    (b"N,A,C\nx,1,p\ny,,q\nz,3,\nx,1,p\nw,2,q\n",
     program("FILL_NULLS C USING MODE;", "FILL_NULLS A USING MEAN;", "REMOVE_DUPLICATES;",
             'FILTER C != "p";', "SORT A DESC;", "RENAME N TO NAME;", "DROP_COLUMN C;"), "data.csv"),
    (b"A,B\n1,5\n2,5\n,5\n4,\n",
     program("NORMALIZE B;", "NORMALIZE A;", "SORT A ASC;", "REMOVE_NULLS;"), "data.csv"),
    (b"A,B\n1.5,x\n2.5,y\n,z\n", program("FILL_NULLS A USING MEDIAN;", "FILTER A < 2.1;"), "data.csv"),
    (b"A,B\n1,x\n2,y\n", program("FILTER A > 100;"), "data.csv"),
]


@pytest.mark.parametrize("csv_bytes,src,name", EQUIVALENCE_CASES)
def test_generated_code_matches_executor(csv_bytes, src, name, tmp_path):
    df = df_from(csv_bytes.decode())
    report = compile_for(src, df, name)
    assert report["status"] == "success", report["diagnostics"]
    result = execute(df, report["ir"])
    assert result.status == "success", result.error
    generated = _run_generated(report["generated_code"], csv_bytes, name, report["ir"]["output"], tmp_path)
    interpreted_csv = result.dataframe.to_csv(index=False)
    assert generated.to_csv(index=False) == pd.read_csv(
        __import__("io").StringIO(interpreted_csv), dtype_backend="numpy_nullable").to_csv(index=False)
