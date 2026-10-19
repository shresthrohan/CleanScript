import pytest

from app.compiler import ast_nodes as ast
from app.compiler.errors import CompileError
from app.compiler.lexer import tokenize
from app.compiler.parser import parse

from conftest import program


def parse_src(src):
    return parse(tokenize(src))


def parse_error(src) -> dict:
    with pytest.raises(CompileError) as exc:
        parse_src(src)
    return exc.value.diagnostic.to_dict()


def test_every_statement_form():
    prog = parse_src(program(
        "REMOVE_NULLS;", "REMOVE_DUPLICATES;", "FILL_NULLS AGE USING MEDIAN;", 'FILL_NULLS "HOME ADDRESS" USING MODE;',
        'DROP_COLUMN "HOME ADDRESS";', 'RENAME "STUDENT NAME" TO NAME;', "FILTER AGE >= 18;",
        'FILTER STATUS == "ACTIVE";', "NORMALIZE MARKS;", "SORT MARKS desc;",
    ))
    t = prog.transforms
    assert [type(s) for s in t] == [
        ast.RemoveNullsStatement, ast.RemoveDuplicatesStatement, ast.FillNullsStatement, ast.FillNullsStatement,
        ast.DropColumnStatement, ast.RenameStatement, ast.FilterStatement, ast.FilterStatement,
        ast.NormalizeStatement, ast.SortStatement]
    assert prog.load.filename == "data.csv" and prog.save.filename == "out.csv"
    assert (t[2].column.name, t[2].column.quoted, t[2].strategy) == ("AGE", False, "MEDIAN")
    assert (t[3].column.name, t[3].column.quoted) == ("HOME ADDRESS", True)
    assert (t[5].column.name, t[5].new_name.name) == ("STUDENT NAME", "NAME")
    assert (t[6].operator, t[6].literal.value, t[6].literal.kind) == (">=", 18, "number")
    assert (t[7].literal.value, t[7].literal.kind) == ("ACTIVE", "string")
    assert t[9].direction == "DESC"


def test_source_locations():
    prog = parse_src('LOAD "data.csv";\n  FILTER AGE >= 18;\nSAVE "o.csv";')
    f = prog.transforms[0]
    assert (f.span.line, f.span.column) == (2, 3)
    assert (f.column.span.line, f.column.span.column) == (2, 10)
    assert (f.literal.span.line, f.literal.span.column) == (2, 17)
    assert prog.save.span.line == 3


def test_ast_serializes():
    d = parse_src(program("SORT AGE ASC;")).to_dict()
    assert d["node"] == "Program"
    sort = d["transforms"][0]
    assert sort["node"] == "SortStatement" and sort["column"]["name"] == "AGE" and sort["span"]["line"] == 2


def test_only_load_and_save():
    prog = parse_src(program())
    assert prog.transforms == []


@pytest.mark.parametrize("src,code", [
    ("", "E_EMPTY_PROGRAM"),
    ('SORT AGE ASC; SAVE "o.csv";', "E_EXPECTED_LOAD"),
    ('LOAD "a.csv"; SORT AGE ASC;', "E_MISSING_SAVE"),
    ('LOAD "a.csv"; SAVE "o.csv"; SAVE "p.csv";', "E_DUPLICATE_SAVE"),
    ('LOAD "a.csv"; SAVE "o.csv"; SORT AGE ASC;', "E_STATEMENT_AFTER_SAVE"),
    ('LOAD "a.csv"; LOAD "a.csv"; SAVE "o.csv";', "E_DUPLICATE_LOAD"),
    ('LOAD data; SAVE "o.csv";', "E_UNEXPECTED_TOKEN"),
    ('LOAD "a.csv" SAVE "o.csv";', "E_MISSING_SEMICOLON"),
    (program("REMOVE_NULLS"), "E_MISSING_SEMICOLON"),
    (program("FILL_NULLS AGE MEDIAN;"), "E_UNEXPECTED_TOKEN"),
    (program("FILL_NULLS AGE USING AVERAGE;"), "E_INVALID_STRATEGY"),
    (program("FILL_NULLS USING MEAN;"), "E_EXPECTED_COLUMN"),
    (program("SORT AGE UP;"), "E_INVALID_DIRECTION"),
    (program("SORT AGE;"), "E_INVALID_DIRECTION"),
    (program("FILTER AGE 18;"), "E_EXPECTED_OPERATOR"),
    (program("FILTER AGE >= ;"), "E_EXPECTED_LITERAL"),
    (program("FILTER STATUS == ACTIVE;"), "E_EXPECTED_LITERAL"),
    (program("RENAME A B;"), "E_UNEXPECTED_TOKEN"),
    (program("DROP AGE;"), "E_UNKNOWN_COMMAND"),
    (program("NORMALIZE MODE;"), "E_EXPECTED_COLUMN"),
    (program("18;"), "E_UNEXPECTED_TOKEN"),
    (program("SORT AGE ASC;;"), "E_UNEXPECTED_TOKEN"),
])
def test_syntax_errors(src, code):
    d = parse_error(src)
    assert d["code"] == code and d["stage"] == "parser" and d["line"] >= 1


def test_missing_semicolon_points_after_previous_token():
    d = parse_error('LOAD "data.csv";\nSORT AGE ASC\nSAVE "o.csv";')
    assert (d["line"], d["column"]) == (2, 13)


def test_unknown_command_suggests_fix():
    d = parse_error(program("NORMALISE MARKS;"))
    assert d["hint"] == "Did you mean NORMALIZE?"


def test_reserved_word_as_column_hint():
    d = parse_error(program("SORT MODE ASC;"))
    assert "quote" in d["hint"]
    # quoting it works
    assert parse_src(program('SORT "MODE" ASC;')).transforms[0].column.name == "MODE"
