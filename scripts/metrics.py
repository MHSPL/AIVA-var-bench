"""
Shared metrics utilities for AIVA benchmark.

Common functions for classification normalization, metrics calculation,
and result loading used by benchmark.py and compare_models.py.
"""

import json
import warnings
from collections import Counter
from pathlib import Path
from typing import Optional

# Track unmapped classification strings so each distinct value warns only once.
_UNMAPPED_CLASSIFICATIONS = set()

import sys
sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    CLASSIFICATION_LABELS, CLASSIFICATION_TO_DIRECTION, DIRECTION_LABELS
)


def load_results(filepath: Path) -> list[dict]:
    """Load classification results from JSONL file."""
    results = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                results.append(json.loads(line))
    return results


def normalize_classification(classification: str) -> str:
    """
    Normalize classification string for comparison.

    Handles various formats like:
    - "Pathogenic", "pathogenic", "PATHOGENIC"
    - "Likely Pathogenic", "Likely pathogenic"
    - "VUS", "VUS (leaning pathogenic)", "Uncertain Significance"
    """
    if not classification:
        return ""

    c = classification.strip()
    lower = c.lower()

    # Check VUS patterns FIRST (before pathogenic/benign which are substrings)
    # AIVA returns "VUS (leaning pathogenic)" or "VUS (leaning benign)"
    if lower.startswith("vus") or "uncertain" in lower:
        return "Uncertain Significance"

    # Then check compound terms before simple ones
    if "likely pathogenic" in lower:
        return "Likely Pathogenic"
    if "likely benign" in lower:
        return "Likely Benign"

    # Finally check simple terms
    if "pathogenic" in lower:
        return "Pathogenic"
    if "benign" in lower:
        return "Benign"

    # No known pattern matched: surface it instead of silently miscounting it.
    if c not in _UNMAPPED_CLASSIFICATIONS:
        _UNMAPPED_CLASSIFICATIONS.add(c)
        warnings.warn(
            f"Unrecognized classification {c!r} did not match any known label; "
            "returning it unchanged (it will not match any ground-truth label).",
            stacklevel=2,
        )
    return c


def get_direction(classification: str) -> str:
    """Get directional category (pathogenic/vus/benign)."""
    normalized = normalize_classification(classification)
    return CLASSIFICATION_TO_DIRECTION.get(normalized, "unknown")


def normalize_criterion(criterion: str) -> str:
    """
    Normalize ACMG criterion code by stripping strength modifiers.

    Examples:
        PM2_Supporting -> PM2
        PS3_Moderate -> PS3
        PVS1_moderate -> PVS1
        PP4_Moderate -> PP4
    """
    if not criterion:
        return ""

    # Common strength modifiers (case-insensitive)
    modifiers = [
        "_supporting", "_moderate", "_strong", "_very_strong",
        "_very", "_standalone"
    ]

    c = criterion.strip()
    lower = c.lower()

    for mod in modifiers:
        if mod in lower:
            # Find the position and remove the modifier
            idx = lower.find(mod)
            c = c[:idx]
            break

    # Uppercase the base code for consistency
    return c.upper()


def get_criterion_type(criterion: str) -> str:
    """
    Get the evidence direction for an ACMG criterion.

    Returns:
        'pathogenic' for PVS, PS, PM, PP criteria
        'benign' for BA, BS, BP criteria
        'unknown' for unrecognized criteria
    """
    base = normalize_criterion(criterion)

    if base.startswith(('PVS', 'PS', 'PM', 'PP')):
        return 'pathogenic'
    elif base.startswith(('BA', 'BS', 'BP')):
        return 'benign'
    return 'unknown'


def calculate_precision_recall_f1(tp: int, fp: int, fn: int) -> tuple[float, float, float]:
    """Calculate precision, recall, and F1 from TP/FP/FN counts."""
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0
    return precision, recall, f1


def calculate_class_metrics(
    ground_truth: list[str],
    predictions: list[str],
    labels: Optional[list[str]] = None
) -> dict:
    """
    Calculate per-class precision, recall, and F1 metrics.

    Args:
        ground_truth: List of ground truth labels
        predictions: List of predicted labels
        labels: Optional list of class labels (defaults to CLASSIFICATION_LABELS)

    Returns:
        Dict mapping class name to metrics dict with precision, recall, f1, support
    """
    labels = labels or CLASSIFICATION_LABELS
    metrics = {}

    for cls in labels:
        tp = sum(1 for g, p in zip(ground_truth, predictions) if g == cls and p == cls)
        fp = sum(1 for g, p in zip(ground_truth, predictions) if g != cls and p == cls)
        fn = sum(1 for g, p in zip(ground_truth, predictions) if g == cls and p != cls)

        precision, recall, f1 = calculate_precision_recall_f1(tp, fp, fn)

        metrics[cls] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": tp + fn,
            "predicted": tp + fp,
            "true_positives": tp,
            "false_positives": fp,
            "false_negatives": fn
        }

    return metrics


def calculate_direction_metrics(
    ground_truth: list[str],
    predictions: list[str],
    labels: Optional[list[str]] = None
) -> dict:
    """
    Calculate per-direction precision, recall, and F1 metrics.

    Args:
        ground_truth: List of ground truth direction labels (pathogenic/vus/benign)
        predictions: List of predicted direction labels
        labels: Optional list of direction labels (defaults to DIRECTION_LABELS)

    Returns:
        Dict mapping direction to metrics dict
    """
    labels = labels or DIRECTION_LABELS
    metrics = {}

    for d in labels:
        tp = sum(1 for g, p in zip(ground_truth, predictions) if g == d and p == d)
        fp = sum(1 for g, p in zip(ground_truth, predictions) if g != d and p == d)
        fn = sum(1 for g, p in zip(ground_truth, predictions) if g == d and p != d)

        precision, recall, f1 = calculate_precision_recall_f1(tp, fp, fn)

        metrics[d] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "support": tp + fn
        }

    return metrics


def calculate_macro_f1(class_metrics: dict) -> float:
    """Calculate macro F1 score from per-class metrics."""
    valid_classes = [c for c, m in class_metrics.items() if m.get("support", 0) > 0]
    if not valid_classes:
        return 0.0
    return sum(class_metrics[c]["f1"] for c in valid_classes) / len(valid_classes)


def calculate_criteria_metrics(results: list[dict]) -> dict:
    """
    Calculate detailed ACMG criteria metrics.

    Returns metrics including:
    - Per-criterion precision/recall/F1
    - Normalized Jaccard similarity
    - Evidence direction agreement
    """
    # Collect all criteria
    all_gt_criteria = set()
    all_pred_criteria = set()

    # For per-criterion metrics
    criterion_tp = Counter()  # True positives per criterion
    criterion_fp = Counter()  # False positives per criterion
    criterion_fn = Counter()  # False negatives per criterion

    # For Jaccard with normalized criteria
    jaccard_scores = []

    # For direction agreement
    direction_matches = 0
    direction_total = 0

    for r in results:
        if r.get("error"):
            continue

        gt_raw = r.get("ground_truth_criteria", [])
        pred_raw = r.get("aiva_criteria", [])

        # Normalize criteria
        gt_normalized = set(normalize_criterion(c) for c in gt_raw if c)
        pred_normalized = set(normalize_criterion(c) for c in pred_raw if c)

        all_gt_criteria.update(gt_normalized)
        all_pred_criteria.update(pred_normalized)

        # Calculate Jaccard for this sample
        if gt_normalized or pred_normalized:
            intersection = len(gt_normalized & pred_normalized)
            union = len(gt_normalized | pred_normalized)
            jaccard = intersection / union if union > 0 else 0
            jaccard_scores.append(jaccard)

        # Per-criterion TP/FP/FN
        for c in gt_normalized & pred_normalized:
            criterion_tp[c] += 1
        for c in pred_normalized - gt_normalized:
            criterion_fp[c] += 1
        for c in gt_normalized - pred_normalized:
            criterion_fn[c] += 1

        # Direction agreement: compare pathogenic vs benign evidence counts
        gt_path = sum(1 for c in gt_normalized if get_criterion_type(c) == 'pathogenic')
        gt_benign = sum(1 for c in gt_normalized if get_criterion_type(c) == 'benign')
        pred_path = sum(1 for c in pred_normalized if get_criterion_type(c) == 'pathogenic')
        pred_benign = sum(1 for c in pred_normalized if get_criterion_type(c) == 'benign')

        # Direction matches if both lean the same way (or both neutral)
        gt_direction = 'pathogenic' if gt_path > gt_benign else ('benign' if gt_benign > gt_path else 'neutral')
        pred_direction = 'pathogenic' if pred_path > pred_benign else ('benign' if pred_benign > pred_path else 'neutral')

        if gt_direction == pred_direction:
            direction_matches += 1
        direction_total += 1

    # Calculate per-criterion precision/recall/F1
    all_criteria = sorted(all_gt_criteria | all_pred_criteria)
    per_criterion = {}

    for c in all_criteria:
        tp = criterion_tp[c]
        fp = criterion_fp[c]
        fn = criterion_fn[c]

        precision, recall, f1 = calculate_precision_recall_f1(tp, fp, fn)

        per_criterion[c] = {
            "precision": round(precision, 4),
            "recall": round(recall, 4),
            "f1": round(f1, 4),
            "tp": tp,
            "fp": fp,
            "fn": fn,
            "support": tp + fn,  # Times it appeared in ground truth
            "predicted": tp + fp,  # Times AIVA predicted it
            "type": get_criterion_type(c)
        }

    # Aggregate by criterion type (pathogenic vs benign)
    path_criteria = [c for c in all_criteria if get_criterion_type(c) == 'pathogenic']
    benign_criteria = [c for c in all_criteria if get_criterion_type(c) == 'benign']

    def aggregate_metrics(criteria_list):
        if not criteria_list:
            return {"precision": 0, "recall": 0, "f1": 0}
        total_tp = sum(criterion_tp[c] for c in criteria_list)
        total_fp = sum(criterion_fp[c] for c in criteria_list)
        total_fn = sum(criterion_fn[c] for c in criteria_list)
        p, r, f = calculate_precision_recall_f1(total_tp, total_fp, total_fn)
        return {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f, 4)}

    return {
        "avg_jaccard_normalized": round(sum(jaccard_scores) / len(jaccard_scores), 4) if jaccard_scores else 0,
        "direction_agreement": round(direction_matches / direction_total, 4) if direction_total > 0 else 0,
        "samples_evaluated": len(jaccard_scores),
        "unique_criteria_in_ground_truth": len(all_gt_criteria),
        "unique_criteria_in_predictions": len(all_pred_criteria),
        "pathogenic_evidence_metrics": aggregate_metrics(path_criteria),
        "benign_evidence_metrics": aggregate_metrics(benign_criteria),
        "per_criterion": per_criterion
    }


def extract_ground_truth_and_predictions(results: list[dict]) -> tuple[list[str], list[str], list[str], list[str]]:
    """
    Extract normalized ground truth and predictions from results.

    Returns:
        Tuple of (ground_truth, predictions, ground_directions, pred_directions)
    """
    valid_results = [r for r in results if not r.get("error") and r.get("aiva_classification")]

    ground_truth = []
    predictions = []
    ground_directions = []
    pred_directions = []

    for r in valid_results:
        gt = normalize_classification(r.get("ground_truth", ""))
        pred = normalize_classification(r.get("aiva_classification", ""))

        if gt and pred:
            ground_truth.append(gt)
            predictions.append(pred)
            ground_directions.append(get_direction(gt))
            pred_directions.append(get_direction(pred))

    return ground_truth, predictions, ground_directions, pred_directions
