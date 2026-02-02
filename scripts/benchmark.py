"""
Calculate benchmark metrics from classification results.

Usage:
    python scripts/benchmark.py                                    # Use latest results
    python scripts/benchmark.py --input results/classifications_xxx.jsonl
"""

import argparse
import json
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import RESULTS_DIR, CLASSIFICATION_LABELS, DIRECTION_LABELS
from metrics import (
    load_results,
    normalize_classification,
    get_direction,
    calculate_class_metrics,
    calculate_direction_metrics,
    calculate_criteria_metrics,
    calculate_macro_f1,
    extract_ground_truth_and_predictions
)


def calculate_metrics(results: list[dict]) -> dict:
    """Calculate all benchmark metrics."""
    total = len(results)
    errors = sum(1 for r in results if r.get("error"))
    successful = total - errors

    # Extract ground truth and predictions
    ground_truth, predictions, ground_directions, pred_directions = \
        extract_ground_truth_and_predictions(results)

    n_compared = len(ground_truth)
    exact_matches = sum(1 for g, p in zip(ground_truth, predictions) if g == p)
    directional_matches = sum(1 for g, p in zip(ground_directions, pred_directions) if g == p)

    per_class = calculate_class_metrics(ground_truth, predictions, CLASSIFICATION_LABELS)

    # Confusion matrix (5-class)
    confusion_5class = {gt: {pred: 0 for pred in CLASSIFICATION_LABELS} for gt in CLASSIFICATION_LABELS}
    for g, p in zip(ground_truth, predictions):
        if g in confusion_5class and p in CLASSIFICATION_LABELS:
            confusion_5class[g][p] += 1

    # Directional metrics (3-class)
    per_direction = calculate_direction_metrics(ground_directions, pred_directions, DIRECTION_LABELS)

    # Directional confusion matrix (3-class)
    confusion_3class = {g: {p: 0 for p in DIRECTION_LABELS} for g in DIRECTION_LABELS}
    for g, p in zip(ground_directions, pred_directions):
        if g in confusion_3class and p in DIRECTION_LABELS:
            confusion_3class[g][p] += 1

    criteria_metrics = calculate_criteria_metrics(results)

    # Execution time stats
    valid_results = [r for r in results if not r.get("error") and r.get("aiva_classification")]
    exec_times = [r["execution_time_ms"] for r in valid_results if r.get("execution_time_ms")]
    avg_exec_time = sum(exec_times) / len(exec_times) if exec_times else 0
    max_exec_time = max(exec_times) if exec_times else 0
    min_exec_time = min(exec_times) if exec_times else 0

    error_types = Counter(r.get("error", "")[:50] for r in results if r.get("error"))

    return {
        "timestamp": datetime.now().isoformat(),
        "summary": {
            "total_variants": total,
            "successful": successful,
            "errors": errors,
            "compared": n_compared,
            "error_rate": round(errors / total, 4) if total > 0 else 0,
        },
        "accuracy": {
            "exact_match": round(exact_matches / n_compared, 4) if n_compared > 0 else 0,
            "directional": round(directional_matches / n_compared, 4) if n_compared > 0 else 0,
            "exact_matches": exact_matches,
            "directional_matches": directional_matches,
        },
        "per_class_metrics": per_class,
        "per_direction_metrics": per_direction,
        "confusion_matrix_5class": confusion_5class,
        "confusion_matrix_3class": confusion_3class,
        "criteria_analysis": criteria_metrics,
        "execution_time": {
            "avg_ms": round(avg_exec_time, 1),
            "min_ms": min_exec_time,
            "max_ms": max_exec_time
        },
        "error_types": dict(error_types.most_common(10))
    }


def print_report(metrics: dict):
    """Print human-readable benchmark report."""
    print("\n" + "=" * 70)
    print("AIVA VARIANT CLASSIFICATION BENCHMARK RESULTS")
    print("=" * 70)

    s = metrics["summary"]
    print(f"\nDataset: {s['total_variants']} variants")
    print(f"  Successful: {s['successful']} | Errors: {s['errors']} ({s['error_rate']*100:.1f}%)")
    print(f"  Compared: {s['compared']}")

    a = metrics["accuracy"]
    print(f"\n{'='*30} ACCURACY {'='*30}")
    print(f"  EXACT MATCH (5-class):    {a['exact_match']*100:6.2f}%  ({a['exact_matches']}/{s['compared']})")
    print(f"  DIRECTIONAL (3-class):    {a['directional']*100:6.2f}%  ({a['directional_matches']}/{s['compared']})")

    print(f"\n{'='*30} PER-CLASS METRICS {'='*21}")
    print(f"  {'Class':<25} {'Prec':>8} {'Recall':>8} {'F1':>8} {'Support':>8}")
    print(f"  {'-'*60}")
    for cls in CLASSIFICATION_LABELS:
        m = metrics["per_class_metrics"].get(cls, {})
        print(f"  {cls:<25} {m.get('precision', 0):>8.3f} {m.get('recall', 0):>8.3f} {m.get('f1', 0):>8.3f} {m.get('support', 0):>8}")

    # Macro averages
    macro_f1 = calculate_macro_f1(metrics["per_class_metrics"])
    class_metrics = metrics["per_class_metrics"]
    valid_classes = [c for c in CLASSIFICATION_LABELS if class_metrics.get(c, {}).get("support", 0) > 0]
    if valid_classes:
        macro_p = sum(class_metrics[c]["precision"] for c in valid_classes) / len(valid_classes)
        macro_r = sum(class_metrics[c]["recall"] for c in valid_classes) / len(valid_classes)
        print(f"  {'-'*60}")
        print(f"  {'Macro Average':<25} {macro_p:>8.3f} {macro_r:>8.3f} {macro_f1:>8.3f}")

    print(f"\n{'='*30} DIRECTIONAL METRICS {'='*19}")
    print(f"  {'Direction':<15} {'Prec':>8} {'Recall':>8} {'F1':>8} {'Support':>8}")
    print(f"  {'-'*50}")
    for d in DIRECTION_LABELS:
        m = metrics["per_direction_metrics"].get(d, {})
        print(f"  {d:<15} {m.get('precision', 0):>8.3f} {m.get('recall', 0):>8.3f} {m.get('f1', 0):>8.3f} {m.get('support', 0):>8}")

    print("\n" + "=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Calculate benchmark metrics")
    parser.add_argument("--input", help="Input JSONL file with classification results")
    parser.add_argument("--output", help="Output JSON file for metrics")
    parser.add_argument("--quiet", action="store_true", help="Don't print report")

    args = parser.parse_args()

    # Find input file
    if args.input:
        input_path = Path(args.input)
    else:
        result_files = list(RESULTS_DIR.glob("classifications_*.jsonl"))
        if not result_files:
            print("Error: No result files found. Run classify.py first.")
            sys.exit(1)
        input_path = max(result_files, key=lambda p: p.stat().st_mtime)
        print(f"Using most recent results: {input_path}")

    results = load_results(input_path)
    print(f"Loaded {len(results)} results")

    metrics = calculate_metrics(results)

    if not args.quiet:
        print_report(metrics)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = RESULTS_DIR / f"metrics_{timestamp}.json"

    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)
    print(f"\nSaved metrics to {output_path}")


if __name__ == "__main__":
    main()
