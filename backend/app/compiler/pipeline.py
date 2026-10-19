"""Runs the compiler stages in order and reports exactly which stages completed."""
from __future__ import annotations

from .codegen import generate_code
from .errors import WARNING, CompileError
from .ir import generate_ir
from .lexer import tokenize
from .parser import parse
from .semantic import ColumnInfo, analyze

STAGES = ("lexer", "parser", "semantic", "ir", "codegen")


def compile_source(source: str, schema: list[ColumnInfo], active_filename: str) -> dict:
    """Compile CleanScript source against a dataset schema.

    Returns a JSON-serializable report. Downstream outputs (ast, ir, code) are None when
    an earlier stage failed; `stages` says which ran ("passed", "warning", "failed", "skipped").
    """
    report = {
        "status": "failed",
        "stages": {s: "skipped" for s in STAGES},
        "tokens": None,
        "ast": None,
        "semantic": None,
        "ir": None,
        "generated_code": None,
        "diagnostics": [],
    }
    stages = report["stages"]

    try:
        tokens = tokenize(source)
    except CompileError as e:
        stages["lexer"] = "failed"
        report["diagnostics"].append(e.diagnostic.to_dict())
        return report
    stages["lexer"] = "passed"
    report["tokens"] = [t.to_dict() for t in tokens]

    try:
        program = parse(tokens)
    except CompileError as e:
        stages["parser"] = "failed"
        report["diagnostics"].append(e.diagnostic.to_dict())
        return report
    stages["parser"] = "passed"
    report["ast"] = program.to_dict()

    result = analyze(program, schema, active_filename)
    report["diagnostics"] += [d.to_dict() for d in result.diagnostics]
    report["semantic"] = {"trace": result.trace}
    if not result.ok:
        stages["semantic"] = "failed"
        return report
    stages["semantic"] = "warning" if any(d.severity == WARNING for d in result.diagnostics) else "passed"

    ir = generate_ir(program)
    stages["ir"] = "passed"
    report["ir"] = ir

    report["generated_code"] = generate_code(ir)
    stages["codegen"] = "passed"
    report["status"] = "success"
    return report
