"""In-memory session registry backed by a private temporary directory.

ponytail: single-process store (dict + lock). Fine for a local/academic deployment; a
multi-worker deployment would need Redis/DB metadata plus shared object storage.
"""
from __future__ import annotations

import secrets
import shutil
import tempfile
import threading
import time
from collections import OrderedDict
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

from app import config

MAX_COMPILATIONS_PER_SESSION = 20
MAX_RESULTS_PER_SESSION = 5


@dataclass
class Session:
    id: str
    filename: str              # sanitized original name; what LOAD must reference
    directory: Path
    dataframe: pd.DataFrame    # the uploaded data; never mutated (executor works on copies)
    profile: dict
    last_access: float = field(default_factory=time.time)
    compilations: OrderedDict = field(default_factory=OrderedDict)  # id -> {"status", "ir", "source"}
    results: OrderedDict = field(default_factory=OrderedDict)       # id -> {"path", "output_filename", "summary"}


class SessionStore:
    def __init__(self):
        self.root = Path(tempfile.mkdtemp(prefix="cleanscript_"))
        self._sessions: dict[str, Session] = {}
        self._lock = threading.Lock()

    def create(self, filename: str, raw: bytes, df: pd.DataFrame, profile: dict) -> Session:
        sid = secrets.token_urlsafe(18)
        directory = self.root / sid
        directory.mkdir()
        (directory / "input.csv").write_bytes(raw)  # server-chosen name; user name is never a path
        session = Session(sid, filename, directory, df, profile)
        with self._lock:
            self._purge_locked()
            while len(self._sessions) >= config.MAX_SESSIONS:
                oldest = min(self._sessions.values(), key=lambda s: s.last_access)
                self._delete_locked(oldest.id)
            self._sessions[sid] = session
        return session

    def get(self, sid: str) -> Session | None:
        with self._lock:
            self._purge_locked()
            session = self._sessions.get(sid)
            if session:
                session.last_access = time.time()
            return session

    def delete(self, sid: str) -> bool:
        with self._lock:
            return self._delete_locked(sid)

    def add_compilation(self, session: Session, record: dict) -> str:
        cid = secrets.token_urlsafe(12)
        with self._lock:
            session.compilations[cid] = record
            while len(session.compilations) > MAX_COMPILATIONS_PER_SESSION:
                session.compilations.popitem(last=False)
        return cid

    def add_result(self, session: Session, df: pd.DataFrame, output_filename: str, summary: dict) -> str:
        rid = secrets.token_urlsafe(12)
        path = session.directory / f"result_{rid}.csv"
        df.to_csv(path, index=False, encoding="utf-8", lineterminator="\n")
        with self._lock:
            session.results[rid] = {"path": path, "output_filename": output_filename, "summary": summary}
            while len(session.results) > MAX_RESULTS_PER_SESSION:
                _, old = session.results.popitem(last=False)
                old["path"].unlink(missing_ok=True)
        return rid

    def close(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def _delete_locked(self, sid: str) -> bool:
        session = self._sessions.pop(sid, None)
        if session:
            shutil.rmtree(session.directory, ignore_errors=True)
        return session is not None

    def _purge_locked(self):
        cutoff = time.time() - config.SESSION_TTL_SECONDS
        for sid in [s.id for s in self._sessions.values() if s.last_access < cutoff]:
            self._delete_locked(sid)
