"""
Freeze the AIVA Bench variant set: the cohort variants that at most
--max-correct of the reference classifiers called with the exact expert
5-class label. The dashboard and its metrics are built on this set only.

The reference classifiers are every active model in dashboard/models.tsv
plus the BIAS-2015 and InterVar baselines, read with the dashboard's own
loaders so the counts match the dashboard exactly. The set is written once
and stays fixed as models are added; rebuild it only on purpose (new version).

Writes data/aiva_bench_variants_<version>.tsv: one row per selected variant,
with the number of reference classifiers that called it exactly, preceded by
comment lines naming the classifiers used.

Usage:
    python scripts/build_variant_set.py
    python scripts/build_variant_set.py --max-correct 3 --version v1
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from config import DATA_DIR
from dashboard.build_data import discover_model_files, load_model_predictions, load_unified_data

REPO_ROOT = Path(__file__).resolve().parent.parent


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--max-correct", type=int, default=3)
    p.add_argument("--version", default="v1")
    args = p.parse_args()

    unified = load_unified_data(REPO_ROOT / "data" / "erepo_bias_intervar_merged.jsonl")
    models, _, missing = discover_model_files(REPO_ROOT)
    if missing:
        sys.exit(f"Results missing for {sorted(missing)}; the set needs every reference classifier.")

    correct = {vid: 0 for vid in unified}
    used = []
    for key, info in models.items():
        preds = load_model_predictions(info, unified)
        if len(preds) < len(unified):
            sys.exit(f"{info['name']} has calls for {len(preds)} of {len(unified)} variants; complete it first.")
        used.append(info["name"])
        for vid, v in unified.items():
            if preds[vid]["prediction"] == v["ground_truth"]:
                correct[vid] += 1

    keep = [vid for vid in unified if correct[vid] <= args.max_correct]
    out = DATA_DIR / f"aiva_bench_variants_{args.version}.tsv"
    with open(out, "w", encoding="utf-8") as f:
        f.write(f"# AIVA Bench variant set {args.version}: {len(keep)} of {len(unified)} cohort variants\n")
        f.write(f"# Selected where at most {args.max_correct} of {len(used)} reference classifiers called the exact expert class\n")
        f.write("# Reference classifiers: " + "; ".join(used) + "\n")
        f.write("variant_id\tgene\texpert_panel\texpert_classification\tclassifiers_exact\n")
        for vid in keep:
            v = unified[vid]
            f.write(f"{vid}\t{v['gene']}\t{v['expert_panel']}\t{v['ground_truth']}\t{correct[vid]}\n")
    print(f"Variant set {args.version}: {len(keep)} of {len(unified)} variants ({len(used)} reference classifiers)")
    print(f"  {out}")


if __name__ == "__main__":
    main()
