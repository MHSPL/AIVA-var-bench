"""
Report what has been classified so far, and what is left.

Coverage is derived from the result files themselves rather than a separate
bookkeeping file, so it cannot drift out of sync with reality. A run that
half-finished still counts for the rows it wrote.

Usage:
    python scripts/ledger.py
    python scripts/ledger.py --results-dir Results_Claude_Sonnet_5_5_Analysis
    python scripts/ledger.py --model anthropic/claude-sonnet-5-5
"""

import argparse
import json
import statistics
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR

DEFAULT_INPUT = DATA_DIR / "erepo_bias_intervar_merged.jsonl"


def scan(result_dirs):
    """One summary row per result file, plus the set of ids done per model."""
    runs = []
    done_by_model = defaultdict(set)
    for d in result_dirs:
        if not d.exists():
            continue
        for path in sorted(d.glob("*.jsonl")):
            ok = err = 0
            times = []
            models = set()
            for line in open(path, encoding="utf-8"):
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if "variant_id" not in rec:
                    break  # not a classification output
                models.add(rec.get("model_used"))
                if rec.get("error") or not rec.get("aiva_classification"):
                    err += 1
                    continue
                ok += 1
                done_by_model[rec.get("model_used")].add(rec["variant_id"])
                if rec.get("execution_time_ms"):
                    times.append(rec["execution_time_ms"])
            if ok or err:
                runs.append({
                    "path": path,
                    "ok": ok,
                    "err": err,
                    "models": sorted(m for m in models if m),
                    "median_s": statistics.median(times) / 1000 if times else None,
                })
    return runs, done_by_model


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--results-dir", action="append", default=None,
                   help="directory to scan (repeatable)")
    p.add_argument("--input", default=str(DEFAULT_INPUT), help="the full cohort")
    p.add_argument("--model", default=None, help="report coverage for this model only")
    args = p.parse_args()

    dirs = [Path(d) for d in (args.results_dir or
                              ["results", "Results_Claude_Sonnet_5_5_Analysis"])]
    runs, done_by_model = scan(dirs)

    total = sum(1 for _ in open(args.input, encoding="utf-8"))

    print(f"cohort: {args.input} ({total} variants)")
    print(f"scanned: {', '.join(str(d) for d in dirs)}\n")

    if not runs:
        print("No classification output found.")
        return

    print(f"{'file':<58} {'ok':>6} {'err':>5} {'med s':>7}  model")
    for r in runs:
        med = f"{r['median_s']:.0f}" if r["median_s"] else "-"
        model = ", ".join(m.split("/")[-1] for m in r["models"]) or "-"
        print(f"{str(r['path']):<58} {r['ok']:>6} {r['err']:>5} {med:>7}  {model}")

    print("\ncoverage by model")
    models = [args.model] if args.model else sorted(done_by_model)
    for m in models:
        n = len(done_by_model.get(m, ()))
        pct = 100 * n / total if total else 0
        left = total - n
        print(f"  {m or '(unknown)'}")
        print(f"    done {n} / {total}  ({pct:.1f}%)   remaining {left}")


if __name__ == "__main__":
    main()
