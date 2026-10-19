"""Lexical analysis: CleanScript source text -> list[Token].

Rules (see docs/DSL_SPEC.md):
* whitespace and newlines separate tokens and are otherwise ignored; there are no comments
* keywords are case-insensitive; identifiers match [A-Za-z_][A-Za-z0-9_]*
* strings are double-quoted and single-line; the only escapes are \\" and \\\\
* numbers are integers or decimals with an optional leading '-' (18, 72.5, -3)
* operators use longest match: == != >= <= > <
"""
from __future__ import annotations

from .errors import ERROR, CompileError, Diagnostic
from .tokens import KEYWORDS, Token, TokenType

_TWO_CHAR_OPS = {"==": TokenType.EQ, "!=": TokenType.NEQ, ">=": TokenType.GTE, "<=": TokenType.LTE}
_ONE_CHAR_OPS = {">": TokenType.GT, "<": TokenType.LT, ";": TokenType.SEMICOLON}


def _is_digit(ch: str) -> bool:
    return "0" <= ch <= "9" if ch else False


def _is_ident_start(ch: str) -> bool:
    return ch == "_" or "a" <= ch <= "z" or "A" <= ch <= "Z" if ch else False


def _is_ident_char(ch: str) -> bool:
    return _is_ident_start(ch) or _is_digit(ch)


class Lexer:
    def __init__(self, source: str):
        self.src = source
        self.pos = 0
        self.line = 1
        self.col = 1

    def _peek(self, offset: int = 0) -> str:
        i = self.pos + offset
        return self.src[i] if i < len(self.src) else ""

    def _advance(self) -> str:
        ch = self.src[self.pos]
        self.pos += 1
        if ch == "\n":
            self.line += 1
            self.col = 1
        else:
            self.col += 1
        return ch

    def _error(self, code, message, line, column, end_column=None, hint=None):
        raise CompileError(Diagnostic(ERROR, code, message, "lexer", line, column, end_column or column + 1, hint))

    def tokenize(self) -> list[Token]:
        tokens: list[Token] = []
        while self.pos < len(self.src):
            ch = self._peek()
            if ch in " \t\r\n":
                self._advance()
                continue
            line, col, start = self.line, self.col, self.pos
            if ch == '"':
                tokens.append(self._string())
            elif _is_digit(ch) or (ch == "-" and _is_digit(self._peek(1))):
                tokens.append(self._number())
            elif _is_ident_start(ch):
                while _is_ident_char(self._peek()):
                    self._advance()
                text = self.src[start:self.pos]
                kind = KEYWORDS.get(text.upper(), TokenType.IDENTIFIER)
                value = text if kind is TokenType.IDENTIFIER else kind.value
                tokens.append(Token(kind, text, value, line, col, self.col))
            elif self.src[self.pos:self.pos + 2] in _TWO_CHAR_OPS:
                op = self.src[self.pos:self.pos + 2]
                self._advance()
                self._advance()
                tokens.append(Token(_TWO_CHAR_OPS[op], op, None, line, col, self.col))
            elif ch in _ONE_CHAR_OPS:
                self._advance()
                tokens.append(Token(_ONE_CHAR_OPS[ch], ch, None, line, col, self.col))
            elif ch == "=":
                self._error("E_INVALID_OPERATOR", "Invalid operator '='", line, col,
                            hint="Use '==' to compare for equality.")
            elif ch == "!":
                self._error("E_INVALID_OPERATOR", "Invalid operator '!'", line, col,
                            hint="Use '!=' for 'not equal'.")
            else:
                shown = ch if ch.isprintable() else repr(ch)
                hint = "CleanScript has no comments; '#' and '//' are not allowed." if ch in "#/" else None
                if ch == "'":
                    hint = 'Strings use double quotes, e.g. "ACTIVE".'
                self._error("E_UNEXPECTED_CHAR", f"Unexpected character '{shown}'", line, col, hint=hint)
        tokens.append(Token(TokenType.EOF, "", None, self.line, self.col, self.col))
        return tokens

    def _string(self) -> Token:
        line, col, start = self.line, self.col, self.pos
        self._advance()  # opening quote
        chars: list[str] = []
        while True:
            ch = self._peek()
            if ch in ("", "\n"):
                self._error("E_UNTERMINATED_STRING", "Unterminated string literal", line, col, self.col,
                            hint='Close the string with a double quote (") on the same line.')
            if ch == '"':
                self._advance()
                break
            if ch == "\\":
                nxt = self._peek(1)
                if nxt not in ('"', "\\"):
                    self._error("E_INVALID_ESCAPE", f"Invalid escape sequence '\\{nxt}'", self.line, self.col,
                                self.col + 2, hint='Only \\" and \\\\ are supported inside strings.')
                self._advance()
            chars.append(self._advance())
        return Token(TokenType.STRING, self.src[start:self.pos], "".join(chars), line, col, self.col)

    def _number(self) -> Token:
        line, col, start = self.line, self.col, self.pos
        if self._peek() == "-":
            self._advance()
        while _is_digit(self._peek()):
            self._advance()
        is_decimal = self._peek() == "."
        if is_decimal:
            self._advance()
            if not _is_digit(self._peek()):
                self._bad_number(start, line, col)
            while _is_digit(self._peek()):
                self._advance()
        if _is_ident_char(self._peek()) or self._peek() == ".":
            self._bad_number(start, line, col)
        text = self.src[start:self.pos]
        return Token(TokenType.NUMBER, text, float(text) if is_decimal else int(text), line, col, self.col)

    def _bad_number(self, start: int, line: int, col: int):
        end = self.pos
        while end < len(self.src) and (_is_ident_char(self.src[end]) or self.src[end] == "."):
            end += 1
        text = self.src[start:end]
        self._error("E_MALFORMED_NUMBER", f"Malformed number '{text}'", line, col, col + len(text),
                    hint="Numbers look like 18 or 72.5. Quote column names that start with a digit.")


def tokenize(source: str) -> list[Token]:
    return Lexer(source).tokenize()
