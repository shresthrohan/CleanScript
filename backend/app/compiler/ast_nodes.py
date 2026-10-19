"""Typed AST for CleanScript. Every node keeps the source location of its first token."""
from __future__ import annotations

from dataclasses import dataclass, field, fields
from typing import Union


@dataclass(frozen=True)
class Span:
    line: int
    column: int
    end_column: int

    def to_dict(self) -> dict:
        return {"line": self.line, "column": self.column, "end_column": self.end_column}


class Node:
    """Base class: generic, field-driven serialization for the compiler inspector."""

    def to_dict(self) -> dict:
        out: dict = {"node": type(self).__name__}
        for f in fields(self):
            out[f.name] = _serialize(getattr(self, f.name))
        return out


def _serialize(value):
    if isinstance(value, (Node, Span)):
        return value.to_dict()
    if isinstance(value, list):
        return [_serialize(v) for v in value]
    return value


@dataclass
class ColumnRef(Node):
    name: str
    quoted: bool
    span: Span


@dataclass
class Literal(Node):
    value: Union[int, float, str]
    kind: str  # "number" | "string"
    span: Span


@dataclass
class LoadStatement(Node):
    filename: str
    span: Span


@dataclass
class SaveStatement(Node):
    filename: str
    span: Span


@dataclass
class RemoveNullsStatement(Node):
    span: Span


@dataclass
class RemoveDuplicatesStatement(Node):
    span: Span


@dataclass
class FillNullsStatement(Node):
    column: ColumnRef
    strategy: str  # MEAN | MEDIAN | MODE
    span: Span


@dataclass
class DropColumnStatement(Node):
    column: ColumnRef
    span: Span


@dataclass
class RenameStatement(Node):
    column: ColumnRef
    new_name: ColumnRef
    span: Span


@dataclass
class FilterStatement(Node):
    column: ColumnRef
    operator: str  # == != > < >= <=
    literal: Literal
    span: Span


@dataclass
class NormalizeStatement(Node):
    column: ColumnRef
    span: Span


@dataclass
class SortStatement(Node):
    column: ColumnRef
    direction: str  # ASC | DESC
    span: Span


TransformStatement = Union[
    RemoveNullsStatement, RemoveDuplicatesStatement, FillNullsStatement, DropColumnStatement,
    RenameStatement, FilterStatement, NormalizeStatement, SortStatement,
]


@dataclass
class Program(Node):
    load: LoadStatement
    transforms: list = field(default_factory=list)
    save: SaveStatement = None
