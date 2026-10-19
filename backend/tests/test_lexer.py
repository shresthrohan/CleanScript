import pytest

from app.compiler.errors import CompileError
from app.compiler.lexer import tokenize
from app.compiler.tokens import TokenType as T


def kinds(src):
    return [t.type for t in tokenize(src)]


def lex_error(src) -> dict:
    with pytest.raises(CompileError) as exc:
        tokenize(src)
    return exc.value.diagnostic.to_dict()


@pytest.mark.parametrize("word", [
    "LOAD", "SAVE", "REMOVE_NULLS", "REMOVE_DUPLICATES", "FILL_NULLS", "DROP_COLUMN", "RENAME", "FILTER",
    "NORMALIZE", "SORT", "USING", "TO", "MEAN", "MEDIAN", "MODE", "ASC", "DESC",
])
def test_every_keyword_case_insensitive(word):
    for spelling in (word, word.lower(), word.title()):
        tok = tokenize(spelling)[0]
        assert tok.type is T[word]
        assert tok.value == word and tok.lexeme == spelling


def test_identifier_keeps_case():
    tok = tokenize("Student_Name2")[0]
    assert (tok.type, tok.value) == (T.IDENTIFIER, "Student_Name2")


def test_numbers():
    toks = tokenize("18 72.5 -3 -0.25")
    assert [(t.type, t.value) for t in toks[:-1]] == [
        (T.NUMBER, 18), (T.NUMBER, 72.5), (T.NUMBER, -3), (T.NUMBER, -0.25)]
    assert isinstance(toks[0].value, int) and isinstance(toks[1].value, float)


def test_string_with_escapes():
    tok = tokenize(r'"say \"hi\" \\ there"')[0]
    assert tok.type is T.STRING
    assert tok.value == 'say "hi" \\ there'


def test_operators_longest_match():
    assert kinds("== != >= <= > <")[:-1] == [T.EQ, T.NEQ, T.GTE, T.LTE, T.GT, T.LT]
    assert kinds(">=18")[:2] == [T.GTE, T.NUMBER]


def test_statement_and_semicolon():
    assert kinds('FILTER AGE >= 18;') == [T.FILTER, T.IDENTIFIER, T.GTE, T.NUMBER, T.SEMICOLON, T.EOF]


def test_whitespace_blank_lines_and_positions():
    toks = tokenize('LOAD "a.csv";\n\n   SORT  AGE\tASC;\n')
    sort = toks[3]
    assert (sort.type, sort.line, sort.column, sort.end_column) == (T.SORT, 3, 4, 8)
    asc = toks[5]
    assert (asc.line, asc.column) == (3, 14)
    assert toks[-1].type is T.EOF


def test_empty_source_is_just_eof():
    assert kinds("   \n ") == [T.EOF]


@pytest.mark.parametrize("src,code,line,col", [
    ('LOAD "abc', "E_UNTERMINATED_STRING", 1, 6),
    ('LOAD "abc\n";', "E_UNTERMINATED_STRING", 1, 6),
    ('"bad \\n escape"', "E_INVALID_ESCAPE", 1, 6),
    ("FILTER AGE = 5;", "E_INVALID_OPERATOR", 1, 12),
    ("FILTER AGE ! 5;", "E_INVALID_OPERATOR", 1, 12),
    ("SORT AGE ASC; @", "E_UNEXPECTED_CHAR", 1, 15),
    ("# comment", "E_UNEXPECTED_CHAR", 1, 1),
    ("// comment", "E_UNEXPECTED_CHAR", 1, 1),
    ("FILTER X == 'a';", "E_UNEXPECTED_CHAR", 1, 13),
    ("FILTER X > 1.2.3;", "E_MALFORMED_NUMBER", 1, 12),
    ("FILTER X > 12abc;", "E_MALFORMED_NUMBER", 1, 12),
    ("FILTER X > 5.;", "E_MALFORMED_NUMBER", 1, 12),
    ("\n\n  FILTER X > 1.;", "E_MALFORMED_NUMBER", 3, 14),
])
def test_lexer_errors_have_locations(src, code, line, col):
    d = lex_error(src)
    assert (d["code"], d["line"], d["column"], d["stage"], d["severity"]) == (code, line, col, "lexer", "error")


def test_lone_minus_is_rejected():
    assert lex_error("FILTER X > - 5;")["code"] == "E_UNEXPECTED_CHAR"
