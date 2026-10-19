"""Intermediate representation: validated AST -> ordered, JSON-serializable instructions.

IR is plain data (dicts of str/int/float), deliberately free of Pandas details, so it can be
stored, inspected, validated again before execution and translated by the code generator.
"""
from __future__ import annotations

from . import ast_nodes as ast

IR_VERSION = 1

# op -> required argument names and their allowed Python types; used by the executor to
# re-validate stored IR before running it.
OP_SCHEMAS: dict[str, dict[str, tuple]] = {
    "remove_nulls": {},
    "remove_duplicates": {},
    "fill_nulls": {"column": (str,), "strategy": (str,)},
    "drop_column": {"column": (str,)},
    "rename_column": {"column": (str,), "new_name": (str,)},
    "filter_rows": {"column": (str,), "operator": (str,), "value": (int, float, str)},
    "normalize": {"column": (str,)},
    "sort_rows": {"column": (str,), "direction": (str,)},
}
STRATEGIES = {"MEAN", "MEDIAN", "MODE"}
OPERATORS = {"==", "!=", ">", "<", ">=", "<="}
DIRECTIONS = {"ASC", "DESC"}


def _source(stmt) -> dict:
    return {"line": stmt.span.line, "column": stmt.span.column}


def _lower(stmt) -> dict:
    match stmt:
        case ast.RemoveNullsStatement():
            return {"op": "remove_nulls"}
        case ast.RemoveDuplicatesStatement():
            return {"op": "remove_duplicates"}
        case ast.FillNullsStatement():
            return {"op": "fill_nulls", "column": stmt.column.name, "strategy": stmt.strategy}
        case ast.DropColumnStatement():
            return {"op": "drop_column", "column": stmt.column.name}
        case ast.RenameStatement():
            return {"op": "rename_column", "column": stmt.column.name, "new_name": stmt.new_name.name}
        case ast.FilterStatement():
            return {"op": "filter_rows", "column": stmt.column.name, "operator": stmt.operator,
                    "value": stmt.literal.value}
        case ast.NormalizeStatement():
            return {"op": "normalize", "column": stmt.column.name}
        case ast.SortStatement():
            return {"op": "sort_rows", "column": stmt.column.name, "direction": stmt.direction}
    raise TypeError(f"No IR lowering for {type(stmt).__name__}")


def generate_ir(program: ast.Program) -> dict:
    """Must only be called on a program that passed semantic analysis."""
    instructions = []
    for i, stmt in enumerate(program.transforms):
        instr = {"index": i, **_lower(stmt), "source": _source(stmt)}
        instructions.append(instr)
    return {
        "version": IR_VERSION,
        "input": program.load.filename,
        "output": program.save.filename,
        "instructions": instructions,
    }


def validate_ir(ir: dict) -> list[str]:
    """Structural validation of an IR document. Returns a list of problems (empty = valid)."""
    problems = []
    if not isinstance(ir, dict) or ir.get("version") != IR_VERSION:
        return ["IR document missing or has an unsupported version"]
    for key in ("input", "output"):
        if not isinstance(ir.get(key), str):
            problems.append(f"IR field {key!r} must be a string")
    instructions = ir.get("instructions")
    if not isinstance(instructions, list):
        return problems + ["IR 'instructions' must be a list"]
    for i, instr in enumerate(instructions):
        op = instr.get("op") if isinstance(instr, dict) else None
        if op not in OP_SCHEMAS:
            problems.append(f"instruction {i}: unknown op {op!r}")
            continue
        for arg, types in OP_SCHEMAS[op].items():
            if not isinstance(instr.get(arg), types) or isinstance(instr.get(arg), bool):
                problems.append(f"instruction {i} ({op}): argument {arg!r} missing or wrong type")
        if op == "fill_nulls" and instr.get("strategy") not in STRATEGIES:
            problems.append(f"instruction {i}: invalid strategy {instr.get('strategy')!r}")
        if op == "filter_rows" and instr.get("operator") not in OPERATORS:
            problems.append(f"instruction {i}: invalid operator {instr.get('operator')!r}")
        if op == "sort_rows" and instr.get("direction") not in DIRECTIONS:
            problems.append(f"instruction {i}: invalid direction {instr.get('direction')!r}")
    return problems
