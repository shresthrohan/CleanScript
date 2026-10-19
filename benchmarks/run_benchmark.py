"""CleanScript benchmark: speed and memory vs. common cleaning approaches, plus a modeled LLM baseline.

Run from the project root with the backend venv (it has pandas):

    backend\\.venv\\Scripts\\python benchmarks\\run_benchmark.py                 # 10, 100, 100k, 1M rows
    backend\\.venv\\Scripts\\python benchmarks\\run_benchmark.py --sizes 10 100  # quick run

Writes benchmarks/logs/benchmark_<timestamp>.log (human readable) and .json (raw numbers).
Generated datasets live in a temp dir and are deleted afterwards; nothing in the app is modified.

What is MEASURED: wall time and OS peak memory of four real engines doing the same cleaning job,
each in a fresh process, and that their outputs are identical.
What is MODELED (not run): an LLM cleaning the rows. Token counts come from the real files; speeds,
limits and model sizes are the stated assumptions in AI_SCENARIOS. Change them and re-run.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import platform
import random
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from datetime import datetime
from pathlib import Path

import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ENGINES = ["cleanscript", "pandas_script", "python_csv", "sqlite"]
ENGINE_LABEL = {
    "cleanscript": "CleanScript (compile + IR interpreter)",
    "pandas_script": "Pandas script (hand-equivalent)",
    "python_csv": "Pure Python (csv module)",
    "sqlite": "SQLite (SQL, in-memory)",
}
REPEATS = {10: 30, 100: 30, 100_000: 5, 1_000_000: 3}

PROGRAM = """LOAD "messy_{n}.csv";
REMOVE_DUPLICATES;
FILL_NULLS AGE USING MEDIAN;
FILL_NULLS MARKS USING MEAN;
FILL_NULLS CITY USING MODE;
DROP_COLUMN "HOME ADDRESS";
FILTER STATUS == "ACTIVE";
FILTER AGE >= 18;
NORMALIZE MARKS;
RENAME MARKS TO SCORE;
SORT SCORE DESC;
SAVE "cleaned_{n}.csv";
"""

# -- LLM model assumptions (edit to taste; every AI number in the log derives from these) --
CHARS_PER_TOKEN = 3.0      # CSV full of digits/commas tokenizes denser than English prose (~4)
PROMPT_OVERHEAD = 400      # instruction tokens repeated in every request (rules + header)
KV_BYTES_PER_TOKEN = 32 * 8 * 128 * 2 * 2   # Llama-3.1-8B: layers x KV heads x head dim x (K,V) x fp16 = 128 KiB
AI_SCENARIOS = {
    "cloud": {
        "label": "Cloud LLM API (frontier model)",
        "context": 200_000, "max_output": 32_000,
        "ttft_s": 1.0, "prefill_tps": 5_000, "decode_tps": 60, "parallel": 10,
        "weights_bytes": None,   # runs on the provider's GPUs; not observable
    },
    "local": {
        "label": "Local 8B model, 4-bit (Llama-3.1-8B class, laptop GPU)",
        "context": 32_768, "max_output": 8_192,
        "ttft_s": 0.5, "prefill_tps": 400, "decode_tps": 20, "parallel": 1,
        "weights_bytes": 4.9e9,  # ~Q4_K_M file size; fp16 would be ~16.1 GB
    },
}

FIRST = ["Aarav", "Diya", "Rohan", "Meera", "Kabir", "Isha", "Vihaan", "Anaya", "Arjun", "Sara"]
LAST = ["Sharma", "Verma", "Iyer", "Khan", "Patel", "Das", "Gupta", "Nair"]
CITIES = ["Delhi", "Mumbai", "Pune", "Chennai", "Kolkata", "Jaipur", "Bengaluru", "Lucknow"]


# -- data ---------------------------------------------------------------------------------

def generate_csv(path: Path, n: int) -> dict:
    """Deterministic messy CSV with n data rows: nulls, exact duplicates, quoted commas."""
    rng = random.Random(42)
    rows, stats = [], {"null_AGE": 0, "null_MARKS": 0, "null_CITY": 0, "null_STATUS": 0, "duplicates": 0}
    for i in range(n):
        if i % 20 == 8 and i >= 5:
            rows.append(rows[i - 5])
            stats["duplicates"] += 1
            continue
        age = "" if i % 13 == 3 else str(rng.randint(15, 30))
        marks = "" if i % 11 == 5 else f"{rng.uniform(0, 100):.1f}"
        status = "" if i % 17 == 6 else ("ACTIVE" if rng.random() < 0.7 else "INACTIVE")
        city = "" if i % 9 == 4 else rng.choice(CITIES)
        for key, v in (("null_AGE", age), ("null_MARKS", marks), ("null_CITY", city), ("null_STATUS", status)):
            stats[key] += v == ""
        rows.append([str(i + 1), f"{rng.choice(FIRST)} {rng.choice(LAST)}", age, marks, status, city,
                     f"{rng.randint(1, 999)} Main Road, Block {rng.choice('ABCDEF')}"])
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(["ID", "NAME", "AGE", "MARKS", "STATUS", "CITY", "HOME ADDRESS"])
        w.writerows(rows)
    return {"rows": n, "columns": 7, "bytes": path.stat().st_size, **stats}


def same_output(a: Path, b: Path) -> tuple[bool, str]:
    x, y = pd.read_csv(a), pd.read_csv(b)
    if list(x.columns) != list(y.columns) or x.shape != y.shape:
        return False, f"shape/columns differ: {x.shape} {list(x.columns)} vs {y.shape} {list(y.columns)}"
    for c in x.columns:
        if pd.api.types.is_numeric_dtype(x[c]) and pd.api.types.is_numeric_dtype(y[c]):
            ok = np.allclose(x[c].to_numpy(float), y[c].to_numpy(float), rtol=1e-9, atol=1e-9, equal_nan=True)
        else:
            ok = x[c].fillna("<NA>").astype(str).equals(y[c].fillna("<NA>").astype(str))
        if not ok:
            return False, f"column {c!r} differs"
    return True, f"identical ({len(x)} rows x {len(x.columns)} cols)"


# -- measurement ----------------------------------------------------------------------------

def run_engine(engine: str, data_dir: Path, n: int, repeats: int) -> dict:
    started = time.perf_counter()
    proc = subprocess.run([sys.executable, str(HERE / "engines.py"), engine, str(data_dir), str(n), str(repeats)],
                          capture_output=True, text=True)
    wall = time.perf_counter() - started
    if proc.returncode != 0:
        raise RuntimeError(f"{engine} @ {n} rows failed:\n{proc.stderr}")
    r = json.loads(proc.stdout.strip().splitlines()[-1])
    totals = sorted(run["total"] for run in r["runs"])
    r.update(
        process_wall_s=wall,
        median_s=float(np.median(totals)),
        min_s=totals[0],
        max_s=totals[-1],
        stage_median_s={k: float(np.median([run[k] for run in r["runs"]])) for k in r["runs"][0]},
        working_memory_bytes=max(0, r["memory_peak_bytes"] - r["memory_after_imports_bytes"]),
    )
    return r


def model_ai(scn: dict, n: int, input_bytes: int, output_bytes: int) -> dict:
    in_tok = math.ceil(input_bytes / CHARS_PER_TOKEN)
    out_tok = math.ceil(output_bytes / CHARS_PER_TOKEN)
    in_row, out_row = in_tok / n, out_tok / n
    # rows per request: both the context window and the output cap must hold
    rows_per_req = max(1, min(n, int((scn["context"] - PROMPT_OVERHEAD) / (in_row + out_row)),
                              int(scn["max_output"] / max(out_row, 1e-9))))
    requests = math.ceil(n / rows_per_req)
    per_req_in = PROMPT_OVERHEAD + rows_per_req * in_row
    per_req_out = rows_per_req * out_row
    per_req_s = scn["ttft_s"] + per_req_in / scn["prefill_tps"] + per_req_out / scn["decode_tps"]
    seq_s = requests * per_req_s
    par_s = math.ceil(requests / scn["parallel"]) * per_req_s
    res = {
        "input_tokens": in_tok, "output_tokens": out_tok,
        "billed_input_tokens": int(requests * PROMPT_OVERHEAD + in_tok),
        "rows_per_request": rows_per_req, "requests": requests,
        "time_sequential_s": seq_s, "time_parallel_s": par_s, "parallel": scn["parallel"],
        "single_context_tokens": PROMPT_OVERHEAD + in_tok + out_tok,
        "fits_one_request": requests == 1,
    }
    if scn["weights_bytes"]:
        per_req_ctx = per_req_in + per_req_out
        res["peak_memory_chunked_bytes"] = scn["weights_bytes"] + per_req_ctx * KV_BYTES_PER_TOKEN
        res["memory_exact_single_context_bytes"] = scn["weights_bytes"] + res["single_context_tokens"] * KV_BYTES_PER_TOKEN
    return res


# -- formatting -------------------------------------------------------------------------------

def t(s: float) -> str:
    if s < 1e-3:
        return f"{s * 1e6:.0f} us"
    if s < 1:
        return f"{s * 1e3:.2f} ms"
    if s < 120:
        return f"{s:.2f} s"
    if s < 7200:
        return f"{s / 60:.1f} min"
    if s < 172800:
        return f"{s / 3600:.1f} h"
    return f"{s / 86400:.1f} days"


def b(x: float) -> str:
    for unit, size in (("TiB", 2**40), ("GiB", 2**30), ("MiB", 2**20), ("KiB", 2**10)):
        if x >= size:
            return f"{x / size:.2f} {unit}"
    return f"{x:.0f} B"


def table(headers: list[str], rows: list[list[str]]) -> list[str]:
    w = [max(len(str(h)), *(len(str(r[i])) for r in rows)) for i, h in enumerate(headers)]
    text_cols = {i for i in range(len(headers)) if any(str(r[i])[:1].isalpha() for r in rows)}
    line = lambda cells: "  ".join(str(c).ljust(w[i]) if i == 0 or i in text_cols else str(c).rjust(w[i])
                                   for i, c in enumerate(cells))
    return [line(headers), "  ".join("-" * x for x in w), *map(line, rows)]


def report(meta: dict, datasets: dict, results: dict, checks: dict, ai: dict) -> str:
    L = ["CleanScript benchmark log", "=" * 72]
    L += [f"{k}: {v}" for k, v in meta.items()]
    L += ["", "Cleaning job (identical for every engine):", *("    " + s for s in PROGRAM.format(n="N").splitlines())]

    L += ["", "1. DATASETS (generated, deterministic seed 42)", "-" * 72]
    L += table(["rows", "file size", "dup rows", "null AGE", "null MARKS", "null CITY", "null STATUS"],
               [[f"{n:,}", b(d["bytes"]), d["duplicates"], d["null_AGE"], d["null_MARKS"], d["null_CITY"], d["null_STATUS"]]
                for n, d in datasets.items()])

    L += ["", "2. SPEED - MEASURED (median of repeated warm runs: read CSV -> clean -> write CSV)", "-" * 72]
    for n in datasets:
        L += ["", f"{n:,} rows  ({REPEATS.get(n, 3)} repeats; cold = new process incl. Python start + imports)"]
        base = results[n]["cleanscript"]["median_s"]
        L += table(["engine", "median", "min", "max", "cold process", "vs CleanScript"],
                   [[ENGINE_LABEL[e], t(r["median_s"]), t(r["min_s"]), t(r["max_s"]), t(r["process_wall_s"]),
                     f"{r['median_s'] / base:.2f}x"] for e, r in results[n].items()])

    L += ["", "3. CLEANSCRIPT STAGE BREAKDOWN - MEASURED (median)", "-" * 72]
    L += table(["rows", "read CSV", "schema inference", "compile (lexer..codegen)", "execute IR", "write CSV", "total"],
               [[f"{n:,}", *(t(results[n]["cleanscript"]["stage_median_s"][k])
                             for k in ("read_csv", "schema", "compile", "execute", "write_csv")),
                 t(results[n]["cleanscript"]["median_s"])] for n in datasets])

    L += ["", "4. MEMORY - MEASURED (OS peak working set of the engine process)", "-" * 72,
          "   'working' = peak minus memory right after imports, i.e. what the cleaning itself needed."]
    L += table(["rows", "engine", "after imports", "peak", "working", "working / file size"],
               [[f"{n:,}", ENGINE_LABEL[e], b(r["memory_after_imports_bytes"]), b(r["memory_peak_bytes"]),
                 b(r["working_memory_bytes"]), f"{r['working_memory_bytes'] / datasets[n]['bytes']:.1f}x"]
                for n in datasets for e, r in results[n].items()])

    L += ["", "5. CORRECTNESS - output of every engine compared to CleanScript's", "-" * 72]
    L += [f"{n:>9,} rows  {e:<14} {'OK  ' if ok else 'FAIL'} {msg}" for n, per in checks.items() for e, (ok, msg) in per.items()]

    L += ["", "6. AI (LLM) CLEANING - MODELED, NOT RUN", "-" * 72,
          f"   Assumptions: {CHARS_PER_TOKEN} chars/token, {PROMPT_OVERHEAD} instruction tokens per request,",
          f"   KV cache {KV_BYTES_PER_TOKEN // 1024} KiB/token (Llama-3.1-8B, fp16). Output size = CleanScript's real output.",
          "   The model must read every input row and write every output row as text; time is dominated by",
          "   output generation speed. No accuracy is claimed for the LLM (it was not run)."]
    for key, scn in AI_SCENARIOS.items():
        L += ["", f"   {scn['label']}: context {scn['context']:,}, max output {scn['max_output']:,}, "
                  f"TTFT {scn['ttft_s']} s, prefill {scn['prefill_tps']:,} tok/s, generate {scn['decode_tps']} tok/s"]
        rows = []
        for n in datasets:
            a = ai[n][key]
            rows.append([f"{n:,}", f"{a['input_tokens']:,}", f"{a['output_tokens']:,}", f"{a['requests']:,}",
                         t(a["time_sequential_s"]), t(a["time_parallel_s"]) if a["parallel"] > 1 else "-",
                         t(results[n]["cleanscript"]["median_s"]),
                         f"{a['time_sequential_s'] / results[n]['cleanscript']['median_s']:,.0f}x"])
        L += table(["rows", "in tokens", "out tokens", "requests", "AI time", f"AI x{scn['parallel']} parallel",
                    "CleanScript", "AI / CleanScript"], rows)

    L += ["", "7. MEMORY: AI vs DSL", "-" * 72,
          "   Local LLM: weights + KV cache of one request (chunked) or of the whole file in one context",
          "   (one context is what exact global median/mean/mode, dedupe, min-max and sort would need).",
          "   Cloud LLM: model memory sits on the provider's GPUs (hundreds of GB for frontier models; not observable)."]
    L += table(["rows", "local LLM, chunked", "local LLM, whole file in context", "CleanScript peak", "CleanScript working"],
               [[f"{n:,}", b(ai[n]["local"]["peak_memory_chunked_bytes"]), b(ai[n]["local"]["memory_exact_single_context_bytes"]),
                 b(results[n]["cleanscript"]["memory_peak_bytes"]), b(results[n]["cleanscript"]["working_memory_bytes"])]
                for n in datasets])

    L += ["", "8. OBSERVATIONS (computed from the numbers above)", "-" * 72]
    small, big = min(datasets), max(datasets)
    cs = results[big]["cleanscript"]["stage_median_s"]
    cs_small = results[small]["cleanscript"]["stage_median_s"]
    L += [f"- Compiler stages (lexer..codegen) took {t(cs_small['compile'])} at {small:,} rows and {t(cs['compile'])} at "
          f"{big:,} rows ({cs['compile'] / cs_small['compile']:.1f}x for {big // small:,}x the data). "
          f"Schema inference, which scans the data, took {t(cs['schema'])} at {big:,} rows.",
          f"- At {big:,} rows CleanScript spent {cs['read_csv'] / results[big]['cleanscript']['median_s']:.0%} of its time "
          f"reading the CSV and {cs['execute'] / results[big]['cleanscript']['median_s']:.0%} executing the IR.",
          f"- CleanScript vs the same job as a plain Pandas script at {big:,} rows: "
          f"{results[big]['cleanscript']['median_s'] / results[big]['pandas_script']['median_s']:.2f}x the time "
          "(the difference is CSV validation + compile + IR checks/metrics; the raw speed comes from Pandas/NumPy).",
          f"- Fastest engine at {small:,} rows: {ENGINE_LABEL[min(results[small], key=lambda e: results[small][e]['median_s'])]}; "
          f"at {big:,} rows: {ENGINE_LABEL[min(results[big], key=lambda e: results[big][e]['median_s'])]}.",
          f"- Modeled cloud LLM at {big:,} rows: {ai[big]['cloud']['requests']:,} requests, "
          f"~{t(ai[big]['cloud']['time_sequential_s'])} sequential vs {t(results[big]['cleanscript']['median_s'])} measured for CleanScript.",
          "- Whenever an LLM needs more than one request, it sees only part of the data per request, so global",
          "  operations (dataset-wide median/mean/mode, cross-chunk duplicates, min-max scaling, sorting) cannot",
          "  be computed correctly inside the model without extra orchestration code.",
          "- Not benchmarked: GUI tools (Excel, OpenRefine, Trifacta/Alteryx) - not installed and not scriptable",
          "  headlessly here. No numbers are claimed for them. (Fact: Excel sheets cap at 1,048,576 rows.)"]
    return "\n".join(L) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", type=int, nargs="+", default=[10, 100, 100_000, 1_000_000])
    args = ap.parse_args()

    meta = {
        "date": datetime.now().isoformat(timespec="seconds"),
        "machine": f"{platform.processor() or platform.machine()} | {platform.system()} {platform.release()}",
        "python": platform.python_version(), "pandas": pd.__version__, "numpy": np.__version__,
        "sqlite": sqlite3.sqlite_version,
    }
    work = Path(tempfile.mkdtemp(prefix="cleanscript_bench_"))
    datasets, results, checks, ai = {}, {}, {}, {}
    try:
        for n in args.sizes:
            print(f"[{n:,} rows] generating data", flush=True)
            datasets[n] = generate_csv(work / f"messy_{n}.csv", n)
            (work / f"program_{n}.clean").write_text(PROGRAM.format(n=n), encoding="utf-8")
            results[n] = {}
            for e in ENGINES:
                print(f"[{n:,} rows] {e}", flush=True)
                results[n][e] = run_engine(e, work, n, REPEATS.get(n, 3))
            outputs = {"cleanscript": work / f"cleanscript_cleaned_{n}.csv", "pandas_script": work / f"cleaned_{n}.csv",
                       "python_csv": work / f"python_csv_cleaned_{n}.csv", "sqlite": work / f"sqlite_cleaned_{n}.csv"}
            checks[n] = {e: same_output(outputs["cleanscript"], p) for e, p in outputs.items() if e != "cleanscript"}
            out_bytes = outputs["cleanscript"].stat().st_size
            ai[n] = {k: model_ai(s, n, datasets[n]["bytes"], out_bytes) for k, s in AI_SCENARIOS.items()}
            for f in work.glob(f"*_{n}.csv"):
                f.unlink()
    finally:
        shutil.rmtree(work, ignore_errors=True)

    text = report(meta, datasets, results, checks, ai)
    logs = HERE / "logs"
    logs.mkdir(exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    (logs / f"benchmark_{stamp}.log").write_text(text, encoding="utf-8")
    (logs / f"benchmark_{stamp}.json").write_text(json.dumps(
        {"meta": meta, "program": PROGRAM, "ai_assumptions": {"chars_per_token": CHARS_PER_TOKEN,
         "prompt_overhead": PROMPT_OVERHEAD, "kv_bytes_per_token": KV_BYTES_PER_TOKEN, "scenarios": AI_SCENARIOS},
         "datasets": datasets, "results": results,
         "checks": {n: {e: {"ok": ok, "detail": m} for e, (ok, m) in c.items()} for n, c in checks.items()},
         "ai_model": ai}, indent=2, default=str), encoding="utf-8")
    print(text)
    print(f"log written to {logs / f'benchmark_{stamp}.log'}")
    if not all(ok for c in checks.values() for ok, _ in c.values()):
        sys.exit("some engine produced a different result - see section 5")


if __name__ == "__main__":
    main()
