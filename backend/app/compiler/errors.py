"""Structured diagnostics shared by every compiler stage."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Optional

ERROR, WARNING, INFO = "error", "warning", "info"


@dataclass
class Diagnostic:
    severity: str          # "error" | "warning" | "info"
    code: str              # stable machine-readable code, e.g. "E_UNKNOWN_COLUMN"
    message: str
    stage: str             # "lexer" | "parser" | "semantic" | "execution"
    line: Optional[int] = None
    column: Optional[int] = None
    end_column: Optional[int] = None
    hint: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)


class CompileError(Exception):
    """Raised by the lexer and parser, which stop at the first error."""

    def __init__(self, diagnostic: Diagnostic):
        super().__init__(diagnostic.message)
        self.diagnostic = diagnostic
