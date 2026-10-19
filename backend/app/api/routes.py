"""HTTP layer only: validate input, call compiler/services, serialize. No parsing or cleaning here."""
from __future__ import annotations

import re
from typing import Optional

from fastapi import APIRouter, File, Request, UploadFile
from fastapi.responses import FileResponse

from app import config
from app.compiler import compile_source
from app.models.schemas import (CompileRequest, CompileResponse, ExecuteRequest, ExecutionResponse,
                                HealthResponse, SessionResponse)
from app.services import dataset_profiler as profiler
from app.services.executor import execute
from app.services.session_store import Session, SessionStore

VERSION = "1.0.0"
router = APIRouter(prefix="/api")


class AppError(Exception):
    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def _store(request: Request) -> SessionStore:
    return request.app.state.store


def _session(request: Request, session_id: str) -> Session:
    session = _store(request).get(session_id)
    if session is None:
        raise AppError(404, "E_SESSION_NOT_FOUND", "Session not found or expired. Upload the CSV again.")
    return session


def safe_upload_name(raw_name: Optional[str]) -> str:
    """Reduce a client-supplied filename to a safe basename ending in .csv."""
    base = re.split(r"[\\/]", raw_name or "")[-1].strip()
    if not base.lower().endswith(".csv") or len(base) <= 4:
        raise AppError(400, "E_UNSUPPORTED_FILE", "Only .csv files are supported")
    stem = re.sub(r"[^A-Za-z0-9 _().-]", "_", base[:-4]).strip(" .") or "dataset"
    return stem[:100] + ".csv"


@router.get("/health", response_model=HealthResponse)
def health():
    return {"status": "ok", "service": "cleanscript", "version": VERSION}


@router.post("/sessions/upload", response_model=SessionResponse)
async def upload(request: Request, file: UploadFile = File(...)):
    filename = safe_upload_name(file.filename)
    raw = await file.read(config.MAX_UPLOAD_BYTES + 1)
    if len(raw) > config.MAX_UPLOAD_BYTES:
        raise AppError(413, "E_FILE_TOO_LARGE", f"File exceeds the {config.MAX_UPLOAD_BYTES // 1024} KB limit")
    try:
        df = profiler.read_csv_bytes(raw)
    except profiler.DatasetError as e:
        raise AppError(400, e.code, str(e))
    if len(df) > config.MAX_ROWS or len(df.columns) > config.MAX_COLUMNS:
        raise AppError(413, "E_DATASET_TOO_LARGE",
                       f"Dataset limits are {config.MAX_ROWS} rows and {config.MAX_COLUMNS} columns")
    profile = profiler.profile(df, config.PREVIEW_ROWS)
    session = _store(request).create(filename, raw, df, profile)
    return _session_payload(session)


def _session_payload(session: Session) -> dict:
    return {
        "session_id": session.id,
        "filename": session.filename,
        "profile": session.profile,
        "limits": {"preview_rows": config.PREVIEW_ROWS, "max_source_chars": config.MAX_SOURCE_CHARS},
    }


@router.get("/sessions/{session_id}/profile", response_model=SessionResponse)
def get_profile(request: Request, session_id: str):
    return _session_payload(_session(request, session_id))


@router.delete("/sessions/{session_id}", status_code=204)
def delete_session(request: Request, session_id: str):
    if not _store(request).delete(session_id):
        raise AppError(404, "E_SESSION_NOT_FOUND", "Session not found or expired")


@router.post("/sessions/{session_id}/compile", response_model=CompileResponse)
def compile_program(request: Request, session_id: str, body: CompileRequest):
    """Always 200 when the request is well-formed; compile errors are reported in `diagnostics`."""
    session = _session(request, session_id)
    report = compile_source(body.source, profiler.schema_of(session.dataframe), session.filename)
    cid = _store(request).add_compilation(session, {"status": report["status"], "ir": report["ir"]})
    return {"compilation_id": cid, "session_id": session.id, **report}


@router.post("/sessions/{session_id}/execute", response_model=ExecutionResponse)
def execute_program(request: Request, session_id: str, body: ExecuteRequest):
    """Runs the stored IR of a successful compilation. Runtime data errors -> 200 with status 'failed'."""
    session = _session(request, session_id)
    compilation = session.compilations.get(body.compilation_id)
    if compilation is None:
        raise AppError(404, "E_COMPILATION_NOT_FOUND", "Compilation not found for this session")
    if compilation["status"] != "success":
        raise AppError(409, "E_COMPILATION_FAILED", "Only a successful compilation can be executed")

    result = execute(session.dataframe, compilation["ir"])
    payload = {
        "status": result.status, "session_id": session.id, "compilation_id": body.compilation_id,
        "result_id": None, "output_filename": None, "operations": result.operations,
        "warnings": result.warnings, "error": result.error, "before": result.before, "after": result.after,
        "result_profile": None,
    }
    if result.status == "success":
        payload["output_filename"] = compilation["ir"]["output"]
        payload["result_profile"] = profiler.profile(result.dataframe, config.PREVIEW_ROWS)
        payload["result_id"] = _store(request).add_result(session, result.dataframe, payload["output_filename"],
                                                         payload)
    return payload


def _result(session: Session, result_id: Optional[str]) -> dict:
    if not session.results:
        raise AppError(404, "E_RESULT_NOT_FOUND", "No result yet. Execute a compiled program first.")
    record = session.results.get(result_id) if result_id else next(reversed(session.results.values()))
    if record is None:
        raise AppError(404, "E_RESULT_NOT_FOUND", "Result not found for this session")
    return record


@router.get("/sessions/{session_id}/result", response_model=ExecutionResponse)
def get_result(request: Request, session_id: str, result_id: Optional[str] = None):
    """Latest result by default; pass ?result_id= for one of the last few retained results."""
    return _result(_session(request, session_id), result_id)["summary"]


@router.get("/sessions/{session_id}/download")
def download(request: Request, session_id: str, result_id: Optional[str] = None):
    record = _result(_session(request, session_id), result_id)
    return FileResponse(record["path"], media_type="text/csv; charset=utf-8", filename=record["output_filename"])
