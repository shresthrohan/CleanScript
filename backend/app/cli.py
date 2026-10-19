"""Command-line compiler driver (no web server needed).

    python -m app.cli ../examples/students.clean ../examples/students.csv            # compile, print code
    python -m app.cli ../examples/students.clean ../examples/students.csv --stage tokens
    python -m app.cli ../examples/students.clean ../examples/students.csv --run out.csv
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from app.compiler import compile_source
from app.services.dataset_profiler import DatasetError, read_csv_bytes, schema_of
from app.services.executor import execute


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(prog="cleanscript", description="Compile a CleanScript program against a CSV.")
    ap.add_argument("program", type=Path)
    ap.add_argument("csv", type=Path)
    ap.add_argument("--stage", choices=["tokens", "ast", "semantic", "ir", "code"], default="code")
    ap.add_argument("--run", metavar="OUTPUT_CSV", type=Path, help="execute the IR and write the result here")
    args = ap.parse_args(argv)

    try:
        df = read_csv_bytes(args.csv.read_bytes())
    except DatasetError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    report = compile_source(args.program.read_text(encoding="utf-8"), schema_of(df), args.csv.name)
    for d in report["diagnostics"]:
        loc = f"{args.program.name}:{d['line']}:{d['column']}" if d["line"] else args.program.name
        print(f"{loc}: {d['severity']} [{d['code']}] {d['message']}", file=sys.stderr)
        if d.get("hint"):
            print(f"    hint: {d['hint']}", file=sys.stderr)
    if report["status"] != "success":
        return 1

    key = {"code": "generated_code", "semantic": "semantic"}.get(args.stage, args.stage)
    out = report[key]
    print(out if isinstance(out, str) else json.dumps(out, indent=2))

    if args.run:
        result = execute(df, report["ir"])
        if result.status != "success":
            print(f"execution error: {result.error['message']}", file=sys.stderr)
            return 1
        result.dataframe.to_csv(args.run, index=False, lineterminator="\n")
        print(f"wrote {result.after['rows']} rows x {result.after['columns']} columns to {args.run}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
