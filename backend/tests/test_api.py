"""API and end-to-end workflow tests: upload -> profile -> compile -> execute -> result -> download."""
import pytest
from fastapi.testclient import TestClient

from app import config
from app.main import app

from conftest import STUDENTS_CSV, STUDENTS_PROGRAM


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def upload(client, content=STUDENTS_CSV, name="students.csv"):
    return client.post("/api/sessions/upload", files={"file": (name, content, "text/csv")})


@pytest.fixture
def sid(client):
    r = upload(client)
    assert r.status_code == 200, r.text
    return r.json()["session_id"]


def compile_(client, sid, source=STUDENTS_PROGRAM):
    r = client.post(f"/api/sessions/{sid}/compile", json={"source": source})
    assert r.status_code == 200, r.text
    return r.json()


def test_health(client):
    r = client.get("/api/health")
    assert r.json() == {"status": "ok", "service": "cleanscript", "version": "1.0.0"}
    assert r.headers["X-Request-ID"]


def test_full_workflow(client):
    up = upload(client).json()
    sid = up["session_id"]
    assert up["filename"] == "students.csv"
    p = up["profile"]
    assert (p["rows"], p["columns"], p["duplicate_rows"]) == (6, 3, 1)
    assert {c["name"]: c["missing"] for c in p["schema"]} == {"STUDENT_NAME": 0, "AGE": 1, "MARKS": 1}

    assert client.get(f"/api/sessions/{sid}/profile").json()["profile"] == p

    comp = compile_(client, sid)
    assert comp["status"] == "success" and comp["diagnostics"] == []
    assert comp["tokens"][0] == {"type": "LOAD", "category": "KEYWORD", "lexeme": "LOAD", "value": "LOAD",
                                 "line": 1, "column": 1, "end_column": 5}
    assert comp["ast"]["node"] == "Program" and len(comp["ast"]["transforms"]) == 6
    assert len(comp["ir"]["instructions"]) == 6 and "import pandas as pd" in comp["generated_code"]

    ex = client.post(f"/api/sessions/{sid}/execute", json={"compilation_id": comp["compilation_id"]}).json()
    assert ex["status"] == "success" and ex["output_filename"] == "cleaned_students.csv"
    assert ex["before"] == {"rows": 6, "columns": 3} and ex["after"] == {"rows": 4, "columns": 3}
    rows = ex["result_profile"]["preview"]["rows"]
    assert [r[0] for r in rows] == ["Diya", "Kabir", "Aarav", "Rohan"]
    assert rows[1][2] == pytest.approx(0.7333333333)

    res = client.get(f"/api/sessions/{sid}/result").json()
    assert res["result_id"] == ex["result_id"]

    dl = client.get(f"/api/sessions/{sid}/download")
    assert dl.status_code == 200
    assert dl.headers["content-type"].startswith("text/csv")
    assert 'filename="cleaned_students.csv"' in dl.headers["content-disposition"]
    assert dl.content.decode("utf-8") == ("STUDENT_NAME,AGE,MARKS\nDiya,19,1.0\nKabir,22,0.7333333333333333\n"
                                          "Aarav,20,0.6666666666666666\nRohan,20,0.0\n")
    # downloaded CSV matches the preview
    lines = dl.content.decode().splitlines()[1:]
    assert [line.split(",")[0] for line in lines] == [r[0] for r in rows]

    # source dataset unchanged: profile identical after execution
    assert client.get(f"/api/sessions/{sid}/profile").json()["profile"] == p

    assert client.delete(f"/api/sessions/{sid}").status_code == 204
    assert client.get(f"/api/sessions/{sid}/profile").status_code == 404


@pytest.mark.parametrize("source,stage,code", [
    ('LOAD "students.csv"; SORT AGE ASC SAVE "o.csv";', "parser", "E_MISSING_SEMICOLON"),
    ('LOAD "students.csv; SAVE "o.csv";', "lexer", None),
    ('LOAD "students.csv"; SORT GRADE ASC; SAVE "o.csv";', "semantic", "E_UNKNOWN_COLUMN"),
    ('LOAD "students.csv"; NORMALIZE STUDENT_NAME; SAVE "o.csv";', "semantic", "E_TYPE_MISMATCH"),
    ('LOAD "students.csv"; FILTER AGE > "x"; SAVE "o.csv";', "semantic", "E_TYPE_MISMATCH"),
])
def test_compile_failures_are_structured(client, sid, source, stage, code):
    comp = compile_(client, sid, source)
    assert comp["status"] == "failed" and comp["stages"][stage] == "failed"
    assert comp["ir"] is None and comp["generated_code"] is None
    d = comp["diagnostics"][0]
    assert d["severity"] == "error" and d["line"] == 1 and d["column"] >= 1
    if code:
        assert d["code"] == code
    ex = client.post(f"/api/sessions/{sid}/execute", json={"compilation_id": comp["compilation_id"]})
    assert ex.status_code == 409 and ex.json()["error"]["code"] == "E_COMPILATION_FAILED"


def test_compilation_belongs_to_session(client):
    a = upload(client).json()["session_id"]
    b = upload(client).json()["session_id"]
    cid = compile_(client, a)["compilation_id"]
    r = client.post(f"/api/sessions/{b}/execute", json={"compilation_id": cid})
    assert r.status_code == 404 and r.json()["error"]["code"] == "E_COMPILATION_NOT_FOUND"


@pytest.mark.parametrize("method,path,body", [
    ("get", "/api/sessions/nope/profile", None),
    ("post", "/api/sessions/nope/compile", {"source": "x"}),
    ("post", "/api/sessions/nope/execute", {"compilation_id": "x"}),
    ("get", "/api/sessions/nope/result", None),
    ("get", "/api/sessions/nope/download", None),
    ("delete", "/api/sessions/nope", None),
])
def test_invalid_session(client, method, path, body):
    r = getattr(client, method)(path, **({"json": body} if body else {}))
    assert r.status_code == 404 and r.json()["error"]["code"] == "E_SESSION_NOT_FOUND"


def test_result_before_execution(client, sid):
    assert client.get(f"/api/sessions/{sid}/result").json()["error"]["code"] == "E_RESULT_NOT_FOUND"
    assert client.get(f"/api/sessions/{sid}/download").status_code == 404


@pytest.mark.parametrize("content,name,status,code", [
    (b"A,B\n1,2\n", "data.txt", 400, "E_UNSUPPORTED_FILE"),
    (b"A,B\n1,2\n", ".csv", 400, "E_UNSUPPORTED_FILE"),
    (b"", "empty.csv", 400, "E_EMPTY_CSV"),
    (b"A,A\n1,2\n", "dup.csv", 400, "E_MALFORMED_CSV"),
    (b'A,B\n"x,2\n', "bad.csv", 400, "E_MALFORMED_CSV"),
    (b"\xff\xfe\x00\x01", "bin.csv", 400, "E_ENCODING"),
])
def test_upload_rejections(client, content, name, status, code):
    r = upload(client, content, name)
    assert r.status_code == status and r.json()["error"]["code"] == code
    assert "Traceback" not in r.text


def test_upload_missing_file(client):
    r = client.post("/api/sessions/upload")
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_VALIDATION"


def test_upload_size_limit(client, monkeypatch):
    monkeypatch.setattr(config, "MAX_UPLOAD_BYTES", 100)
    r = upload(client, b"A,B\n" + b"1,2\n" * 100, "big.csv")
    assert r.status_code == 413 and r.json()["error"]["code"] == "E_FILE_TOO_LARGE"


def test_upload_filename_is_sanitized(client):
    r = upload(client, name="../../etc/my data;rm.csv").json()
    assert r["filename"] == "my data_rm.csv"
    comp = compile_(client, r["session_id"], 'LOAD "my data_rm.csv"; SAVE "o.csv";')
    assert comp["status"] == "success"


@pytest.mark.parametrize("load,save,code", [
    ("../students.csv", "o.csv", "E_LOAD_PATH"),
    ("/tmp/students.csv", "o.csv", "E_LOAD_PATH"),
    ("students.csv", "../../evil.csv", "E_SAVE_FILENAME"),
    ("students.csv", "C:\\\\x.csv", "E_SAVE_FILENAME"),
])
def test_path_traversal_rejected(client, sid, load, save, code):
    comp = compile_(client, sid, f'LOAD "{load}"; SAVE "{save}";')
    assert comp["status"] == "failed" and code in [d["code"] for d in comp["diagnostics"]]


def test_runtime_failure_keeps_source_and_previous_result(client):
    sid = upload(client, b"A,E\n1,\n2,\n", "e.csv").json()["session_id"]
    ok = compile_(client, sid, 'LOAD "e.csv"; SORT A DESC; SAVE "o.csv";')
    first = client.post(f"/api/sessions/{sid}/execute", json={"compilation_id": ok["compilation_id"]}).json()
    bad = compile_(client, sid, 'LOAD "e.csv"; FILL_NULLS E USING MEAN; SAVE "o.csv";')
    assert bad["status"] == "success"  # warning only; the failure is data-dependent
    r = client.post(f"/api/sessions/{sid}/execute", json={"compilation_id": bad["compilation_id"]})
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "failed" and body["error"]["code"] == "E_ALL_NULL_COLUMN" and body["result_id"] is None
    assert client.get(f"/api/sessions/{sid}/result").json()["result_id"] == first["result_id"]
    assert client.get(f"/api/sessions/{sid}/download").text == "A,E\n2,\n1,\n"


def test_empty_filter_result_downloadable(client, sid):
    comp = compile_(client, sid, 'LOAD "students.csv"; FILTER AGE > 100; SAVE "none.csv";')
    ex = client.post(f"/api/sessions/{sid}/execute", json={"compilation_id": comp["compilation_id"]}).json()
    assert ex["status"] == "success" and ex["after"]["rows"] == 0
    assert client.get(f"/api/sessions/{sid}/download").text == "STUDENT_NAME,AGE,MARKS\n"


def test_specific_result_id(client, sid):
    a = compile_(client, sid, 'LOAD "students.csv"; SORT AGE ASC; SAVE "a.csv";')
    b = compile_(client, sid, 'LOAD "students.csv"; REMOVE_NULLS; SAVE "b.csv";')
    ra = client.post(f"/api/sessions/{sid}/execute", json={"compilation_id": a["compilation_id"]}).json()
    client.post(f"/api/sessions/{sid}/execute", json={"compilation_id": b["compilation_id"]})
    dl = client.get(f"/api/sessions/{sid}/download", params={"result_id": ra["result_id"]})
    assert 'filename="a.csv"' in dl.headers["content-disposition"]
    assert client.get(f"/api/sessions/{sid}/result", params={"result_id": "zzz"}).status_code == 404


def test_source_length_limit(client, sid):
    r = client.post(f"/api/sessions/{sid}/compile", json={"source": "x" * (config.MAX_SOURCE_CHARS + 1)})
    assert r.status_code == 422 and r.json()["error"]["code"] == "E_VALIDATION"


def test_cors_allows_dev_origin_only(client):
    ok = client.options("/api/health", headers={"Origin": "http://localhost:5173", "Access-Control-Request-Method": "GET"})
    assert ok.headers.get("access-control-allow-origin") == "http://localhost:5173"
    bad = client.options("/api/health", headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "GET"})
    assert "access-control-allow-origin" not in bad.headers
