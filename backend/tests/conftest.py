from pathlib import Path

import pytest

from app.compiler import compile_source
from app.services.dataset_profiler import read_csv_bytes, schema_of

EXAMPLES = Path(__file__).resolve().parents[2] / "examples"
STUDENTS_CSV = (EXAMPLES / "students.csv").read_bytes()
STUDENTS_PROGRAM = (EXAMPLES / "students.clean").read_text()


def df_from(text: str):
    return read_csv_bytes(text.encode())


def compile_for(source: str, df, filename: str = "data.csv") -> dict:
    return compile_source(source, schema_of(df), filename)


def program(*statements: str, load: str = "data.csv", save: str = "out.csv") -> str:
    return "\n".join([f'LOAD "{load}";', *statements, f'SAVE "{save}";'])


def codes(report: dict, severity: str | None = None) -> list[str]:
    return [d["code"] for d in report["diagnostics"] if severity is None or d["severity"] == severity]


@pytest.fixture
def students_df():
    return read_csv_bytes(STUDENTS_CSV)


@pytest.fixture
def mixed_df():
    return df_from(
        "NAME,AGE,MARKS,CITY,STATUS,EMPTY\n"
        "Asha,21,70.5,Pune,ACTIVE,\n"
        "Ben,,88.0,Delhi,INACTIVE,\n"
        "Cara,19,,Pune,ACTIVE,\n"
        "Dev,25,91.5,,ACTIVE,\n"
    )
