"""Token definitions for CleanScript."""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Union


class TokenType(Enum):
    # command keywords
    LOAD = "LOAD"
    SAVE = "SAVE"
    REMOVE_NULLS = "REMOVE_NULLS"
    REMOVE_DUPLICATES = "REMOVE_DUPLICATES"
    FILL_NULLS = "FILL_NULLS"
    DROP_COLUMN = "DROP_COLUMN"
    RENAME = "RENAME"
    FILTER = "FILTER"
    NORMALIZE = "NORMALIZE"
    SORT = "SORT"
    # secondary keywords
    USING = "USING"
    TO = "TO"
    MEAN = "MEAN"
    MEDIAN = "MEDIAN"
    MODE = "MODE"
    ASC = "ASC"
    DESC = "DESC"
    # names and literals
    IDENTIFIER = "identifier"
    STRING = "string"
    NUMBER = "number"
    # comparison operators
    EQ = "=="
    NEQ = "!="
    GT = ">"
    LT = "<"
    GTE = ">="
    LTE = "<="
    # punctuation / end
    SEMICOLON = ";"
    EOF = "end of input"


# Keywords are recognised case-insensitively; identifiers keep their exact case.
KEYWORDS = {t.value: t for t in TokenType if t.value.replace("_", "").isalpha() and t.value.isupper()}

COMMAND_KEYWORDS = (
    TokenType.LOAD, TokenType.SAVE, TokenType.REMOVE_NULLS, TokenType.REMOVE_DUPLICATES,
    TokenType.FILL_NULLS, TokenType.DROP_COLUMN, TokenType.RENAME, TokenType.FILTER,
    TokenType.NORMALIZE, TokenType.SORT,
)
COMPARATORS = (TokenType.EQ, TokenType.NEQ, TokenType.GT, TokenType.LT, TokenType.GTE, TokenType.LTE)
STRATEGIES = (TokenType.MEAN, TokenType.MEDIAN, TokenType.MODE)
DIRECTIONS = (TokenType.ASC, TokenType.DESC)


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str                           # exact source text
    value: Union[str, int, float, None]   # parsed value: unescaped string, number, or keyword spelling
    line: int
    column: int                           # 1-based start column
    end_column: int                       # 1-based column just past the token

    @property
    def category(self) -> str:
        if self.type.value in KEYWORDS:
            return "KEYWORD"
        if self.type in COMPARATORS:
            return "OPERATOR"
        return self.type.name

    def describe(self) -> str:
        """Human-readable description used in syntax errors."""
        if self.type is TokenType.EOF:
            return "end of input"
        if self.category == "KEYWORD":
            return f"keyword '{self.lexeme}'"
        return f"{self.type.value} '{self.lexeme}'" if self.type.value != self.lexeme else f"'{self.lexeme}'"

    def to_dict(self) -> dict:
        return {
            "type": self.type.name,
            "category": self.category,
            "lexeme": self.lexeme,
            "value": self.value,
            "line": self.line,
            "column": self.column,
            "end_column": self.end_column,
        }
