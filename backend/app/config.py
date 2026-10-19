"""Runtime limits. Every value can be overridden with an environment variable of the same name."""
import os


def _int(name: str, default: int) -> int:
    return int(os.environ.get(name, default))


MAX_UPLOAD_BYTES = _int("CLEANSCRIPT_MAX_UPLOAD_BYTES", 5 * 1024 * 1024)
MAX_ROWS = _int("CLEANSCRIPT_MAX_ROWS", 200_000)
MAX_COLUMNS = _int("CLEANSCRIPT_MAX_COLUMNS", 200)
MAX_SOURCE_CHARS = _int("CLEANSCRIPT_MAX_SOURCE_CHARS", 20_000)
PREVIEW_ROWS = _int("CLEANSCRIPT_PREVIEW_ROWS", 50)
SESSION_TTL_SECONDS = _int("CLEANSCRIPT_SESSION_TTL_SECONDS", 2 * 60 * 60)
MAX_SESSIONS = _int("CLEANSCRIPT_MAX_SESSIONS", 100)
CORS_ORIGINS = [o.strip() for o in os.environ.get(
    "CLEANSCRIPT_CORS_ORIGINS", "http://localhost:5173,http://127.0.0.1:5173").split(",") if o.strip()]
