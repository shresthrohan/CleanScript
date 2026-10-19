"""CleanScript compiler: lexer -> parser -> semantic analysis -> IR -> code generation.

Independent of FastAPI; usable directly from Python, tests, and `python -m app.cli`.
"""
from .pipeline import compile_source
from .semantic import ColumnInfo

__all__ = ["compile_source", "ColumnInfo"]
