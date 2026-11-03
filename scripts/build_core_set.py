"""
Build the frozen AIVA Bench core set: a fixed subset of the cohort that future
models run instead of all 8,387 variants.

Variants are drawn proportionally across every (VCEP x expert classification)
cell, so the core keeps the cohort's mix of panels and classes (cohort-
weighted: a panel with 17% of the cohort has ~17% of the core). Cell quotas
use the largest-remainder method so they sum exactly to --n; cells too small
for a whole variant get none. The draw is seeded, so the same inputs always
give the same set.

Writes:
    data/aiva_bench_core_v1.jsonl         cohort records, ready for classify.py --input
    data/aiva_bench_core_v1_manifest.tsv  one row per variant with its stratum and
                                          weight (cell size / cell sample)

Usage:
    python scripts/build_core_set.py
    python scripts/build_core_set.py --n 1000 --seed 42 --version v1
"""

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from config import DATA_DIR, RANDOM_SEED
from scripts.metrics import normalize_classification

DEFAULT_INPUT = DATA_DIR / "erepo_bias_intervar_merged.jsonl"


def allocate(sizes: dict, n: int) -> dict:
    """Largest-remainder quotas proportional to cell size, summing to n."""
    total = sum(sizes.values())
    exact = {c: n * s / total for c, s in sizes.items()}
    quota = {c: int(x) for c, x in exact.items()}
    # Ties broken by cell key so the allocation is deterministic
    order = sorted(sizes, key=lambda c: (-(exact[c] - quota[c]), c))
    for c in order[: n - sum(quota.values())]:
        quota[c] += 1
    return quota


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--n", type=int, default=1000, help="core size")
    p.add_argument("--seed", type=int, default=RANDOM_SEED)
    p.add_argument("--version", default="v1")
    p.add_argument("--input", default=str(DEFAULT_INPUT))
    args = p.parse_args()

    lines, records = [], []
    with open(args.input, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                lines.append(line.rstrip("\n"))
                records.append(json.loads(line))

    cells = defaultdict(list)
    for i, r in enumerate(records):
        cells[(r["expert_panel"], normalize_classification(r["classification"]))].append(i)

    quota = allocate({c: len(ix) for c, ix in cells.items()}, args.n)
    rng = random.Random(args.seed)
    chosen, weight = set(), {}
    for c in sorted(cells):
        k = quota[c]
        if not k:
            continue
        pick = rng.sample(sorted(cells[c], key=lambda i: records[i]["id"]), k)
        chosen.update(pick)
        for i in pick:
            weight[i] = len(cells[c]) / k

    out = DATA_DIR / f"aiva_bench_core_{args.version}.jsonl"
    manifest = DATA_DIR / f"aiva_bench_core_{args.version}_manifest.tsv"
    keep = sorted(chosen)
    with open(out, "w", encoding="utf-8") as f:
        for i in keep:
            f.write(lines[i] + "\n")
    with open(manifest, "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, delimiter="\t")
        w.writerow(["variant_id", "gene", "expert_panel", "expert_classification", "cell_size", "cell_sample", "weight"])
        for i in keep:
            r = records[i]
            c = (r["expert_panel"], normalize_classification(r["classification"]))
            w.writerow([r["id"], r["gene_symbol"], c[0], c[1], len(cells[c]), quota[c], f"{weight[i]:.4f}"])

    empty = sum(1 for c in cells if not quota[c])
    print(f"Core {args.version}: {len(keep)} of {len(records)} variants, seed {args.seed}")
    print(f"  {len(cells)} VCEP x class cells; {empty} too small for a variant at this size")
    print(f"  {out}\n  {manifest}")


if __name__ == "__main__":
    main()
