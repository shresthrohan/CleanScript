"""FastAPI application: wiring, CORS, request IDs and uniform JSON errors."""
from __future__ import annotations

import logging
import secrets
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import config
from app.api.routes import AppError, router
from app.services.session_store import SessionStore

log = logging.getLogger("cleanscript")


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.store = SessionStore()
    yield
    app.state.store.close()


app = FastAPI(title="CleanScript API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=config.CORS_ORIGINS, allow_methods=["GET", "POST", "DELETE"],
                   allow_headers=["Content-Type"], expose_headers=["Content-Disposition", "X-Request-ID"])


def _error(request: Request, status: int, code: str, message: str) -> JSONResponse:
    rid = getattr(request.state, "request_id", None)
    return JSONResponse({"error": {"code": code, "message": message}, "request_id": rid}, status_code=status,
                        headers={"X-Request-ID": rid} if rid else None)


@app.middleware("http")
async def request_id_and_size_guard(request: Request, call_next):
    request.state.request_id = secrets.token_hex(8)
    length = request.headers.get("content-length")
    if length and length.isdigit() and int(length) > config.MAX_UPLOAD_BYTES + 64 * 1024:
        return _error(request, 413, "E_FILE_TOO_LARGE",
                      f"Request exceeds the {config.MAX_UPLOAD_BYTES // 1024} KB limit")
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


@app.exception_handler(AppError)
async def app_error(request: Request, exc: AppError):
    return _error(request, exc.status, exc.code, exc.message)


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError):
    first = exc.errors()[0] if exc.errors() else {}
    where = ".".join(str(p) for p in first.get("loc", []) if p != "body")
    return _error(request, 422, "E_VALIDATION", f"Invalid request: {where or 'body'} {first.get('msg', '')}".strip())


@app.exception_handler(StarletteHTTPException)
async def http_error(request: Request, exc: StarletteHTTPException):
    return _error(request, exc.status_code, "E_HTTP", str(exc.detail))


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):
    log.exception("Unhandled error (request %s)", getattr(request.state, "request_id", "?"))
    return _error(request, 500, "E_INTERNAL", "Internal server error")


app.include_router(router)
