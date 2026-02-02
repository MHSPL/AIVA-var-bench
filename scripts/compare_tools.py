"""
4-way comparison: AIVA vs InterVar vs BIAS-2015 vs eRepo ground truth.

Usage:
    python scripts/compare_tools.py --aiva-results results/classifications_*.jsonl
    python scripts/compare_tools.py --aiva-results results/classifications_*.jsonl --unified data/erepo_bias_intervar_merged.jsonl
"""

import argparse
import json
import sys
from collections import defaultdict, Counter
from pathlib import Path

# Class for diverting stdout to both console and file
class MultiWriter:
    def __init__(self, *files):
        self.files = files

    def write(self, buf):
        for f in self.files:
            f.write(buf)

    def flush(self):
        for f in self.files:
            f.flush()

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RESULTS_DIR, DATA_DIR, CLASSIFICATION_LABELS, DIRECTION_LABELS
from metrics import (
    normalize_classification,
    get_direction,
    calculate_class_metrics,
    calculate_direction_metrics,
    calculate_macro_f1
)
from scripts.generate_results import calculate_full_metrics


def get_consensus_prediction(predictions: list[str]) -> str:
    """Calculate consensus (majority vote) from a list of predictions."""
    # Filter out empty/None predictions
    valid_preds = [normalize_classification(p) for p in predictions if p]
    if not valid_preds:
        return ""
    
    counts = Counter(valid_preds)
    
    # Get max count
    max_count = counts.most_common(1)[0][1]
    
    # Get all candidates with max count (handling ties)
    candidates = [k for k, v in counts.items() if v == max_count]
    
    # Tie-breaking: Sort strings for deterministic result
    # (Ideally this would be severity-weighted, but deterministic is fine for now)
    return sorted(candidates)[0]


def load_jsonl(filepath: Path) -> list[dict]:
    """Load JSONL file."""
    results = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    return results


def load_aiva_results(filepaths: list[Path]) -> dict[str, dict]:
    """
    Load AIVA results and index by variant_id and model.
    Returns: dict[variant_id, dict[model_name, result_dict]]
    """
    aiva_by_id = defaultdict(dict)
    for fp in filepaths:
        for r in load_jsonl(fp):
            vid = r.get("variant_id")
            model = r.get("model_used")
            if not model:
                # Fallback: try to guess from filename or directory? 
                # For now, if model is missing, use "unknown"
                model = "unknown"
                
            if vid and not r.get("error"):
                aiva_by_id[vid][model] = {
                    "classification": r.get("aiva_classification"),
                    "criteria": r.get("aiva_criteria", []),
                    "model": model,
                    "reasoning": r.get("aiva_reasoning", "")
                }
    return aiva_by_id


def calculate_tool_metrics(predictions: list[str], ground_truth: list[str]) -> dict:
    """Calculate comprehensive metrics for a tool."""
    # Normalize predictions
    norm_preds = [normalize_classification(p) for p in predictions]
    norm_gt = [normalize_classification(g) for g in ground_truth]

    # Get directions
    pred_dirs = [get_direction(p) for p in norm_preds]
    gt_dirs = [get_direction(g) for g in norm_gt]

    # Filter valid predictions
    valid_indices = [i for i, (p, g) in enumerate(zip(norm_preds, norm_gt))
                    if p and g]

    valid_preds = [norm_preds[i] for i in valid_indices]
    valid_gt = [norm_gt[i] for i in valid_indices]
    valid_pred_dirs = [pred_dirs[i] for i in valid_indices]
    valid_gt_dirs = [gt_dirs[i] for i in valid_indices]

    n_valid = len(valid_preds)
    if n_valid == 0:
        return {"error": "No valid predictions"}

    # Exact accuracy (5-class)
    exact_matches = sum(1 for p, g in zip(valid_preds, valid_gt) if p == g)
    exact_accuracy = exact_matches / n_valid

    # Directional accuracy (3-class)
    dir_matches = sum(1 for p, g in zip(valid_pred_dirs, valid_gt_dirs) if p == g)
    directional_accuracy = dir_matches / n_valid

    # Per-class metrics
    class_metrics = calculate_class_metrics(valid_gt, valid_preds, CLASSIFICATION_LABELS)
    direction_metrics = calculate_direction_metrics(valid_gt_dirs, valid_pred_dirs, DIRECTION_LABELS)

    # Macro F1
    macro_f1_5class = calculate_macro_f1(class_metrics)
    macro_f1_3class = calculate_macro_f1(direction_metrics)

    return {
        "n_total": len(predictions),
        "n_valid": n_valid,
        "exact_accuracy": round(exact_accuracy, 4),
        "directional_accuracy": round(directional_accuracy, 4),
        "macro_f1_5class": round(macro_f1_5class, 4),
        "macro_f1_3class": round(macro_f1_3class, 4),
        "per_class": class_metrics,
        "per_direction": direction_metrics
    }


def build_confusion_matrix(predictions: list[str], ground_truth: list[str], labels: list[str]) -> dict:
    """Build confusion matrix."""
    matrix = defaultdict(lambda: defaultdict(int))
    for p, g in zip(predictions, ground_truth):
        p_norm = normalize_classification(p)
        g_norm = normalize_classification(g)
        if p_norm and g_norm:
            matrix[g_norm][p_norm] += 1
    return {g: dict(preds) for g, preds in matrix.items()}


def print_confusion_matrices(tool_metrics: dict[str, dict], tool_preds: dict[str, list[str]], ground_truth: list[str]):
    """Print 3-class directional confusion matrices for all tools."""
    print("\n" + "=" * 90)
    print("CONFUSION MATRICES (3-class Directional)")
    print("=" * 90)
    
    # Map 5-class labels to 3-class directions
    directions = DIRECTION_LABELS  # ['Pathogenic', 'VUS', 'Benign']
    
    tools = sorted(tool_metrics.keys())
    
    for tool in tools:
        print(f"\nTool: {tool}")
        preds = tool_preds.get(tool, [])
        if not preds:
            print("  No predictions available.")
            continue
            
        # Build matrix
        matrix = {d1: {d2: 0 for d2 in directions} for d1 in directions}
        
        for p, g in zip(preds, ground_truth):
            p_norm = normalize_classification(p)
            g_norm = normalize_classification(g)
            
            if p_norm and g_norm:
                p_dir = get_direction(p_norm)
                g_dir = get_direction(g_norm)
                
                if p_dir in directions and g_dir in directions:
                    matrix[g_dir][p_dir] += 1
        
        # Print matrix
        # Columns: Predicted
        print(f"  {'':<15} {'Predicted ->':<40}")
        print(f"  {'Actual ↓':<15} {'Pathogenic':>10} {'VUS':>10} {'Benign':>10}")
        print("  " + "-" * 50)
        
        # Display map for cleaner row labels
        display_map = {
            "pathogenic": "Pathogenic",
            "vus": "VUS",
            "benign": "Benign"
        }

        for actual in directions:
            label = display_map.get(actual, actual.title())
            row = matrix[actual]
            # Use lowercase keys matching DIRECTION_LABELS from config.py
            p_val = row.get('pathogenic', 0)
            v_val = row.get('vus', 0)
            b_val = row.get('benign', 0)
            print(f"  {label:<15} {p_val:>10} {v_val:>10} {b_val:>10}")


def print_bias_style_metrics(tool_metrics: dict[str, dict], tool_preds: dict[str, list[str]], ground_truth: list[str]):
    """
    Print metrics in the same format as the BIAS-2015 paper table.
    Shows Sensitivity, Specificity, Precision, F1 for P/LP, B/LB, VUS categories.
    """
    print("\n" + "=" * 100)
    print("BIAS-2015 STYLE METRICS (Sensitivity, Specificity, Precision, F1)")
    print("=" * 100)
    
    # Category mapping: collapse 5-class to 3 directional categories
    # P/LP = Pathogenic + Likely Pathogenic
    # B/LB = Benign + Likely Benign
    # VUS = Uncertain Significance
    
    tools = sorted(tool_metrics.keys())
    categories = ["P/LP", "B/LB", "VUS"]
    
    # Print header
    print(f"\n{'Tool':<35}", end="")
    for cat in categories:
        print(f" | {cat:^36}", end="")
    print()
    
    print(f"{'':<35}", end="")
    for _ in categories:
        print(f" | {'Sens':>8} {'Spec':>8} {'Prec':>8} {'F1':>8}", end="")
    print()
    print("-" * 150)
    
    for tool in tools:
        preds = tool_preds.get(tool, [])
        if not preds:
            continue
        
        # Get directions
        pred_dirs = [get_direction(normalize_classification(p)) for p in preds]
        gt_dirs = [get_direction(normalize_classification(g)) for g in ground_truth]
        
        # Filter valid
        valid_idx = [i for i, (p, g) in enumerate(zip(pred_dirs, gt_dirs)) if p != "unknown" and g != "unknown"]
        valid_preds = [pred_dirs[i] for i in valid_idx]
        valid_gt = [gt_dirs[i] for i in valid_idx]
        n_total = len(valid_gt)
        
        print(f"{tool:<35}", end="")
        
        # Calculate metrics for each category
        cat_map = {"P/LP": "pathogenic", "B/LB": "benign", "VUS": "vus"}
        
        for cat in categories:
            d = cat_map[cat]
            tp = sum(1 for g, p in zip(valid_gt, valid_preds) if g == d and p == d)
            fp = sum(1 for g, p in zip(valid_gt, valid_preds) if g != d and p == d)
            fn = sum(1 for g, p in zip(valid_gt, valid_preds) if g == d and p != d)
            tn = n_total - tp - fp - fn
            
            metrics = calculate_full_metrics(tp, fp, fn, tn)
            sens = metrics["sensitivity"] * 100
            spec = metrics["specificity"] * 100
            prec = metrics["precision"] * 100
            f1 = metrics["f1"] * 100
            
            print(f" | {sens:>7.2f}% {spec:>7.2f}% {prec:>7.2f}% {f1:>7.2f}%", end="")
        
        print()
    
    print("-" * 150)


def print_comparison_table(tool_metrics: dict[str, dict]):
    """Print summary comparison table."""
    print("\n" + "=" * 90)
    print("4-WAY TOOL COMPARISON: AIVA vs InterVar vs BIAS-2015")
    print("=" * 90)

    # Sort by exact accuracy
    sorted_tools = sorted(tool_metrics.keys(),
                         key=lambda t: tool_metrics[t].get("exact_accuracy", 0),
                         reverse=True)

    print(f"\n{'Tool':<20} {'N Valid':>8} {'Exact':>10} {'Direct':>10} {'Macro F1':>10} {'Dir F1':>10}")
    print("-" * 90)

    for tool in sorted_tools:
        m = tool_metrics[tool]
        if "error" in m:
            print(f"{tool:<20} {'ERROR':>8}")
            continue
        print(f"{tool:<20} {m['n_valid']:>8} {m['exact_accuracy']*100:>9.1f}% "
              f"{m['directional_accuracy']*100:>9.1f}% {m['macro_f1_5class']*100:>9.1f}% "
              f"{m['macro_f1_3class']*100:>9.1f}%")

    print("-" * 90)


def print_per_class_comparison(tool_metrics: dict[str, dict]):
    """Print per-class F1 scores for all tools."""
    print("\n" + "=" * 90)
    print("PER-CLASS F1 SCORES (5-class)")
    print("=" * 90)

    tools = list(tool_metrics.keys())

    # Header
    print(f"\n{'Class':<25}", end="")
    for tool in tools:
        short = tool[:12]
        print(f"{short:>14}", end="")
    print()
    print("-" * (25 + 14 * len(tools)))

    for cls in CLASSIFICATION_LABELS:
        print(f"{cls:<25}", end="")
        for tool in tools:
            m = tool_metrics[tool]
            if "error" in m:
                print(f"{'N/A':>14}", end="")
            else:
                f1 = m.get("per_class", {}).get(cls, {}).get("f1", 0)
                print(f"{f1*100:>12.1f}%", end="")
        print()

    print("-" * (25 + 14 * len(tools)))
    print(f"{'Macro F1':<25}", end="")
    for tool in tools:
        m = tool_metrics[tool]
        if "error" in m:
            print(f"{'N/A':>14}", end="")
        else:
            print(f"{m['macro_f1_5class']*100:>12.1f}%", end="")
    print()


def print_directional_comparison(tool_metrics: dict[str, dict]):
    """Print directional (3-class) metrics for all tools."""
    print("\n" + "=" * 90)
    print("DIRECTIONAL METRICS (3-class: Pathogenic / VUS / Benign)")
    print("=" * 90)

    tools = list(tool_metrics.keys())

    for direction in DIRECTION_LABELS:
        print(f"\n{direction.upper()}:")
        print(f"  {'Tool':<20} {'Precision':>12} {'Recall':>12} {'F1':>12}")
        print("  " + "-" * 60)
        for tool in tools:
            m = tool_metrics[tool]
            if "error" in m:
                print(f"  {tool:<20} {'N/A':>12}")
            else:
                dm = m.get("per_direction", {}).get(direction, {})
                prec = dm.get("precision", 0)
                rec = dm.get("recall", 0)
                f1 = dm.get("f1", 0)
                print(f"  {tool:<20} {prec*100:>11.1f}% {rec*100:>11.1f}% {f1*100:>11.1f}%")


def print_criteria_analysis(unified_data: list[dict], aiva_by_id: dict):
    """Analyze criteria usage across tools."""
    print("\n" + "=" * 90)
    print("CRITERIA ANALYSIS")
    print("=" * 90)

    # Identify models
    all_models = set()
    for v_data in aiva_by_id.values():
        all_models.update(v_data.keys())
    sorted_models = sorted(list(all_models))

    # Collect criteria usage
    gt_criteria = defaultdict(int)
    intervar_criteria = defaultdict(int)
    bias_criteria = defaultdict(int)
    model_criteria = {m: defaultdict(int) for m in sorted_models}

    for v in unified_data:
        for c in v.get("criteria_met", []):
            gt_criteria[c] += 1
        for c in v.get("intervar_criteria", []):
            intervar_criteria[c] += 1
        for c in v.get("bias_criteria", []):
            bias_criteria[c] += 1

        vid = v.get("id")
        if vid in aiva_by_id:
            for m, data in aiva_by_id[vid].items():
                 for c in data.get("criteria", []):
                    model_criteria[m][c] += 1

    # Get all unique criteria
    all_crit_set = set(gt_criteria.keys()) | set(intervar_criteria.keys()) | set(bias_criteria.keys())
    for m_counts in model_criteria.values():
        all_crit_set |= set(m_counts.keys())
    
    all_criteria = sorted(all_crit_set)

    if not all_criteria:
        print("\nNo criteria data available.")
        return

    # Print header
    print(f"\n{'Criterion':<12} {'eRepo GT':>10} {'InterVar':>10} {'BIAS-2015':>10}", end="")
    for m in sorted_models:
        # Shorten model name for display
        m_short = m.split('/')[-1]
        if len(m_short) > 10:
            m_short = m_short[:9] + "."
        print(f" {m_short:>10}", end="")
    print()
    
    print("-" * (46 + 11 * len(sorted_models)))

    for crit in all_criteria[:20]:  # Top 20 criteria
        print(f"{crit:<12} {gt_criteria.get(crit, 0):>10} {intervar_criteria.get(crit, 0):>10} "
              f"{bias_criteria.get(crit, 0):>10}", end="")
        for m in sorted_models:
            print(f" {model_criteria[m].get(crit, 0):>10}", end="")
        print()

    if len(all_criteria) > 20:
        print(f"... and {len(all_criteria) - 20} more criteria")


def save_detailed_results(unified_data: list[dict], aiva_by_id: dict, output_path: Path):
    """Save detailed per-variant comparison."""
    results = []

    # Identify models
    all_models = set()
    for v_data in aiva_by_id.values():
        all_models.update(v_data.keys())
    sorted_models = sorted(list(all_models))

    for v in unified_data:
        vid = v.get("id")
        
        # Only include variants that were processed by AIVA
        if vid not in aiva_by_id:
            continue
            
        aiva_data = aiva_by_id.get(vid, {})

        result = {
            "variant_id": vid,
            "variant": v.get("variation"),
            "gene": v.get("gene_symbol"),
            "ground_truth": v.get("classification"),
            "ground_truth_criteria": v.get("criteria_met", []),
            "intervar": v.get("intervar_classification"),
            "intervar_criteria": v.get("intervar_criteria", []),
            "bias": v.get("bias_classification"),
            "bias_criteria": v.get("bias_criteria", []),
        }

        # Add match indicators
        gt = normalize_classification(result["ground_truth"])
        result["intervar_match"] = normalize_classification(result["intervar"]) == gt
        result["bias_match"] = normalize_classification(result["bias"]) == gt
        
        # Add per-model fields
        model_classifications = []
        for m in sorted_models:
            slug = m.replace("/", "_").replace("-", "_")
            m_res = aiva_data.get(m, {})
            m_cls = m_res.get("classification")
            
            if m_cls:
                model_classifications.append(m_cls)
            
            result[f"aiva_{slug}"] = m_cls
            result[f"aiva_{slug}_criteria"] = m_res.get("criteria", [])
            result[f"aiva_{slug}_match"] = normalize_classification(m_cls) == gt if m_cls else None
            # result[f"aiva_{slug}_model"] = m # Redundant since key has model name

        # Add consensus (Optional - remove if strictly not wanted, but useful for debug)
        # consensus = get_consensus_prediction(model_classifications)
        # result["aiva_consensus"] = consensus
        # result["aiva_consensus_match"] = normalize_classification(consensus) == gt if consensus else None

        results.append(result)

    with open(output_path, "w") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")

    print(f"\nSaved detailed results to {output_path}")


def main():
    parser = argparse.ArgumentParser(description="4-way tool comparison")
    parser.add_argument("--aiva-results", nargs="+", required=True,
                       help="AIVA classification result files (JSONL)")
    parser.add_argument("--unified", default=str(DATA_DIR / "bias_unified.jsonl"),
                       help="Unified data file with InterVar/BIAS predictions")
    parser.add_argument("--output", help="Output file for detailed results")

    args = parser.parse_args()
    
    # Determine output paths early so we can start logging
    aiva_paths = [Path(p) for p in args.aiva_results]
    
    if args.output:
        output_path = Path(args.output)
    else:
        # Determine default output directory based on first input file
        if aiva_paths:
            base_dir = aiva_paths[0].parent
            output_path = base_dir / "tool_comparison_detailed.jsonl"
        else:
            output_path = RESULTS_DIR / "tool_comparison_detailed.jsonl"
            
    # Report file path (same dir, same name, but .txt extension)
    report_path = output_path.with_suffix(".txt")
    
    # Start capturing output
    original_stdout = sys.stdout
    with open(report_path, "w", encoding="utf-8") as log_file:
        sys.stdout = MultiWriter(original_stdout, log_file)
        
        try:
            print(f"Report will be saved to: {report_path}")
            
            # Load unified data (contains ground truth, InterVar, BIAS-2015)
            unified_path = Path(args.unified)
            print(f"Loading unified data from {unified_path}")
            unified_data = load_jsonl(unified_path)
            print(f"  Loaded {len(unified_data)} variants")

            # Load AIVA results
            print(f"Loading AIVA results from {len(aiva_paths)} file(s)")
            aiva_by_id = load_aiva_results(aiva_paths)
            print(f"  Loaded {len(aiva_by_id)} AIVA predictions")

            # Build unified data index
            unified_by_id = {v.get("id"): v for v in unified_data}

            # Identify models
            all_models = set()
            for v_data in aiva_by_id.values():
                all_models.update(v_data.keys())
            sorted_models = sorted(list(all_models))
            print(f"  Found results for models: {', '.join(sorted_models)}")

            # FAIR COMPARISON: Only compare on variants where AIVA has predictions
            aiva_variant_ids = set(aiva_by_id.keys())
            print(f"\n=== FAIR COMPARISON (on {len(aiva_variant_ids)} AIVA-predicted variants) ===")

            # Extract predictions for variants AIVA predicted
            ground_truth_fair = []
            intervar_preds_fair = []
            bias_preds_fair = []
            aiva_model_preds = {m: [] for m in sorted_models}
            
            # Sort IDs for deterministic ordering
            sorted_vids = sorted(list(aiva_variant_ids))

            for vid in sorted_vids:
                v = unified_by_id.get(vid)
                if not v:
                    continue

                ground_truth_fair.append(v.get("classification"))
                intervar_preds_fair.append(v.get("intervar_classification", ""))
                bias_preds_fair.append(v.get("bias_classification", ""))
                
                variant_models = aiva_by_id[vid]
                for m in sorted_models:
                    aiva_model_preds[m].append(variant_models.get(m, {}).get("classification", ""))

            # Calculate metrics for fair comparison
            tool_metrics_fair = {
                "InterVar": calculate_tool_metrics(intervar_preds_fair, ground_truth_fair),
                "BIAS-2015": calculate_tool_metrics(bias_preds_fair, ground_truth_fair)
            }
            
            # Calculate Individual Model Metrics
            for m in sorted_models:
                m_name = f"AIVA ({m.split('/')[-1]})"
                tool_metrics_fair[m_name] = calculate_tool_metrics(aiva_model_preds[m], ground_truth_fair)
            
            # Print fair comparison
            print_comparison_table(tool_metrics_fair)
            print_per_class_comparison(tool_metrics_fair)
            print_directional_comparison(tool_metrics_fair)

            # Collect predictions for confusion matrix
            all_tool_preds = {
                "InterVar": intervar_preds_fair,
                "BIAS-2015": bias_preds_fair
            }
            for m in sorted_models:
                m_name = f"AIVA ({m.split('/')[-1]})"
                all_tool_preds[m_name] = aiva_model_preds[m]

            # Print confusion matrices
            print_confusion_matrices(tool_metrics_fair, all_tool_preds, ground_truth_fair)
            
            # Print BIAS-2015 style metrics table (Sensitivity, Specificity, Precision, F1)
            print_bias_style_metrics(tool_metrics_fair, all_tool_preds, ground_truth_fair)

            # FULL DATASET comparison for reference
            print("\n\n" + "=" * 90)
            print(f"REFERENCE: Full dataset metrics (all {len(unified_data)} variants)")
            print("=" * 90)

            ground_truth_all = []
            intervar_preds_all = []
            bias_preds_all = []

            for v in unified_data:
                ground_truth_all.append(v.get("classification"))
                intervar_preds_all.append(v.get("intervar_classification", ""))
                bias_preds_all.append(v.get("bias_classification", ""))

            tool_metrics_full = {
                "InterVar (full)": calculate_tool_metrics(intervar_preds_all, ground_truth_all),
                "BIAS-2015 (full)": calculate_tool_metrics(bias_preds_all, ground_truth_all)
            }

            print(f"\n{'Tool':<20} {'N Valid':>8} {'Exact':>10} {'Direct':>10} {'Macro F1':>10} {'Dir F1':>10}")
            print("-" * 90)
            for tool, m in tool_metrics_full.items():
                print(f"{tool:<20} {m['n_valid']:>8} {m['exact_accuracy']*100:>9.1f}% "
                      f"{m['directional_accuracy']*100:>9.1f}% {m['macro_f1_5class']*100:>9.1f}% "
                      f"{m['macro_f1_3class']*100:>9.1f}%")

            # Criteria analysis (on AIVA subset)
            print_criteria_analysis(
                [unified_by_id[vid] for vid in aiva_variant_ids if vid in unified_by_id],
                aiva_by_id
            )

            # Save detailed results
            save_detailed_results(unified_data, aiva_by_id, output_path)

            # Summary
            print("\n" + "=" * 90)
            print("SUMMARY")
            print("=" * 90)

            print(f"\nFair comparison on {len(aiva_variant_ids)} variants:")

            print(f"\nBest exact accuracy: ", end="")
            best = max(tool_metrics_fair.items(), key=lambda x: x[1].get("exact_accuracy", 0))
            print(f"{best[0]} ({best[1]['exact_accuracy']*100:.1f}%)")

            print(f"Best directional accuracy: ", end="")
            best = max(tool_metrics_fair.items(), key=lambda x: x[1].get("directional_accuracy", 0))
            print(f"{best[0]} ({best[1]['directional_accuracy']*100:.1f}%)")
            
        finally:
            sys.stdout = original_stdout


if __name__ == "__main__":
    main()
