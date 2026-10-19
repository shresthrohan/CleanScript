"""Recursive-descent parser: list[Token] -> Program AST.

Each method maps to one grammar production in docs/DSL_SPEC.md. The parser stops at the
first syntax error and raises CompileError with the offending source location.
"""
from __future__ import annotations

import difflib

from . import ast_nodes as ast
from .errors import ERROR, CompileError, Diagnostic
from .tokens import COMMAND_KEYWORDS, COMPARATORS, DIRECTIONS, STRATEGIES, Token, TokenType

_COMMAND_NAMES = [t.value for t in COMMAND_KEYWORDS]


def _span(tok: Token) -> ast.Span:
    return ast.Span(tok.line, tok.column, tok.end_column)


class Parser:
    def __init__(self, tokens: list[Token]):
        self.tokens = tokens
        self.pos = 0

    # -- token helpers ----------------------------------------------------
    @property
    def current(self) -> Token:
        return self.tokens[self.pos]

    @property
    def previous(self) -> Token:
        return self.tokens[self.pos - 1]

    def _check(self, *types: TokenType) -> bool:
        return self.current.type in types

    def _advance(self) -> Token:
        tok = self.current
        if tok.type is not TokenType.EOF:
            self.pos += 1
        return tok

    def _error(self, code: str, message: str, tok: Token, hint: str | None = None):
        raise CompileError(Diagnostic(ERROR, code, message, "parser", tok.line, tok.column,
                                      max(tok.end_column, tok.column + 1), hint))

    def _expect(self, ttype: TokenType, what: str, code: str = "E_UNEXPECTED_TOKEN", hint: str | None = None) -> Token:
        if self._check(ttype):
            return self._advance()
        self._error(code, f"Expected {what} but found {self.current.describe()}", self.current, hint)

    def _expect_semicolon(self, command: str) -> None:
        if self._check(TokenType.SEMICOLON):
            self._advance()
            return
        # Report at the end of the previous token: that is where the ';' is missing.
        prev = self.previous
        raise CompileError(Diagnostic(
            ERROR, "E_MISSING_SEMICOLON",
            f"Expected ';' after {command} statement but found {self.current.describe()}",
            "parser", prev.line, prev.end_column, prev.end_column + 1,
            "Every statement must end with a semicolon."))

    # -- grammar ------------------------------------------------------------
    # program = load_statement, { transform_statement }, save_statement, EOF ;
    def parse_program(self) -> ast.Program:
        if not self._check(TokenType.LOAD):
            if self._check(TokenType.EOF):
                self._error("E_EMPTY_PROGRAM", "Program is empty", self.current,
                            'A program starts with LOAD "<file>.csv"; and ends with SAVE "<file>.csv";')
            self._error("E_EXPECTED_LOAD", f"Program must begin with LOAD but found {self.current.describe()}",
                        self.current, 'Start the program with LOAD "<uploaded file>.csv";')
        load = self.parse_load()
        transforms = []
        while not self._check(TokenType.SAVE, TokenType.EOF):
            transforms.append(self.parse_transform())
        if self._check(TokenType.EOF):
            self._error("E_MISSING_SAVE", "Program must end with a SAVE statement", self.current,
                        'Add SAVE "<output>.csv"; as the last statement.')
        save = self.parse_save()
        if not self._check(TokenType.EOF):
            if self._check(TokenType.SAVE):
                self._error("E_DUPLICATE_SAVE", "Only one SAVE statement is allowed", self.current)
            self._error("E_STATEMENT_AFTER_SAVE",
                        f"SAVE must be the last statement, but found {self.current.describe()} after it",
                        self.current)
        return ast.Program(load, transforms, save)

    # load_statement = "LOAD", STRING, ";" ;
    def parse_load(self) -> ast.LoadStatement:
        kw = self._advance()
        name = self._expect(TokenType.STRING, 'a quoted file name after LOAD',
                            hint='Example: LOAD "students.csv";')
        self._expect_semicolon("LOAD")
        return ast.LoadStatement(name.value, _span(kw))

    # save_statement = "SAVE", STRING, ";" ;
    def parse_save(self) -> ast.SaveStatement:
        kw = self._advance()
        name = self._expect(TokenType.STRING, 'a quoted file name after SAVE',
                            hint='Example: SAVE "cleaned.csv";')
        self._expect_semicolon("SAVE")
        return ast.SaveStatement(name.value, _span(kw))

    def parse_transform(self):
        tok = self.current
        dispatch = {
            TokenType.REMOVE_NULLS: self.parse_remove_nulls,
            TokenType.REMOVE_DUPLICATES: self.parse_remove_duplicates,
            TokenType.FILL_NULLS: self.parse_fill_nulls,
            TokenType.DROP_COLUMN: self.parse_drop_column,
            TokenType.RENAME: self.parse_rename,
            TokenType.FILTER: self.parse_filter,
            TokenType.NORMALIZE: self.parse_normalize,
            TokenType.SORT: self.parse_sort,
        }
        if tok.type in dispatch:
            return dispatch[tok.type]()
        if tok.type is TokenType.LOAD:
            self._error("E_DUPLICATE_LOAD", "LOAD may only appear once, as the first statement", tok)
        if tok.type is TokenType.IDENTIFIER:
            close = difflib.get_close_matches(tok.lexeme.upper(), _COMMAND_NAMES, n=1)
            self._error("E_UNKNOWN_COMMAND", f"Unknown command '{tok.lexeme}'", tok,
                        f"Did you mean {close[0]}?" if close else "See the documentation for supported commands.")
        self._error("E_UNEXPECTED_TOKEN", f"Expected a command but found {tok.describe()}", tok)

    # remove_nulls = "REMOVE_NULLS", ";" ;
    def parse_remove_nulls(self):
        kw = self._advance()
        self._expect_semicolon("REMOVE_NULLS")
        return ast.RemoveNullsStatement(_span(kw))

    # remove_duplicates = "REMOVE_DUPLICATES", ";" ;
    def parse_remove_duplicates(self):
        kw = self._advance()
        self._expect_semicolon("REMOVE_DUPLICATES")
        return ast.RemoveDuplicatesStatement(_span(kw))

    # fill_nulls = "FILL_NULLS", column_ref, "USING", strategy, ";" ;
    def parse_fill_nulls(self):
        kw = self._advance()
        column = self.parse_column_ref("FILL_NULLS")
        self._expect(TokenType.USING, "USING after the column name", hint="Example: FILL_NULLS AGE USING MEDIAN;")
        if not self._check(*STRATEGIES):
            self._error("E_INVALID_STRATEGY",
                        f"Expected fill strategy MEAN, MEDIAN or MODE but found {self.current.describe()}",
                        self.current)
        strategy = self._advance().type.value
        self._expect_semicolon("FILL_NULLS")
        return ast.FillNullsStatement(column, strategy, _span(kw))

    # drop_column = "DROP_COLUMN", column_ref, ";" ;
    def parse_drop_column(self):
        kw = self._advance()
        column = self.parse_column_ref("DROP_COLUMN")
        self._expect_semicolon("DROP_COLUMN")
        return ast.DropColumnStatement(column, _span(kw))

    # rename_column = "RENAME", column_ref, "TO", column_ref, ";" ;
    def parse_rename(self):
        kw = self._advance()
        old = self.parse_column_ref("RENAME")
        self._expect(TokenType.TO, "TO after the column name", hint='Example: RENAME "STUDENT NAME" TO NAME;')
        new = self.parse_column_ref("RENAME ... TO")
        self._expect_semicolon("RENAME")
        return ast.RenameStatement(old, new, _span(kw))

    # filter_rows = "FILTER", column_ref, comparator, literal, ";" ;
    def parse_filter(self):
        kw = self._advance()
        column = self.parse_column_ref("FILTER")
        if not self._check(*COMPARATORS):
            self._error("E_EXPECTED_OPERATOR",
                        f"Expected a comparison operator (==, !=, >, <, >=, <=) but found {self.current.describe()}",
                        self.current)
        op = self._advance().type.value
        literal = self.parse_literal()
        self._expect_semicolon("FILTER")
        return ast.FilterStatement(column, op, literal, _span(kw))

    # normalize_column = "NORMALIZE", column_ref, ";" ;
    def parse_normalize(self):
        kw = self._advance()
        column = self.parse_column_ref("NORMALIZE")
        self._expect_semicolon("NORMALIZE")
        return ast.NormalizeStatement(column, _span(kw))

    # sort_rows = "SORT", column_ref, direction, ";" ;
    def parse_sort(self):
        kw = self._advance()
        column = self.parse_column_ref("SORT")
        if not self._check(*DIRECTIONS):
            self._error("E_INVALID_DIRECTION",
                        f"Expected sort direction ASC or DESC but found {self.current.describe()}", self.current)
        direction = self._advance().type.value
        self._expect_semicolon("SORT")
        return ast.SortStatement(column, direction, _span(kw))

    # column_ref = IDENTIFIER | STRING ;
    def parse_column_ref(self, context: str) -> ast.ColumnRef:
        tok = self.current
        if tok.type in (TokenType.IDENTIFIER, TokenType.STRING):
            self._advance()
            return ast.ColumnRef(tok.value, tok.type is TokenType.STRING, _span(tok))
        hint = None
        if tok.category == "KEYWORD":
            hint = f'{tok.lexeme} is a reserved word; quote it to use it as a column name: "{tok.lexeme}".'
        self._error("E_EXPECTED_COLUMN", f"Expected a column name after {context} but found {tok.describe()}",
                    tok, hint)

    # literal = NUMBER | STRING ;
    def parse_literal(self) -> ast.Literal:
        tok = self.current
        if tok.type is TokenType.NUMBER:
            self._advance()
            return ast.Literal(tok.value, "number", _span(tok))
        if tok.type is TokenType.STRING:
            self._advance()
            return ast.Literal(tok.value, "string", _span(tok))
        hint = 'Quote text values, e.g. FILTER STATUS == "ACTIVE";' if tok.type is TokenType.IDENTIFIER else None
        self._error("E_EXPECTED_LITERAL", f"Expected a number or quoted string but found {tok.describe()}", tok, hint)


def parse(tokens: list[Token]) -> ast.Program:
    return Parser(tokens).parse_program()
