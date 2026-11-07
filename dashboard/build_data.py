#!/usr/bin/env python3
"""
Dashboard Data Builder for AIVA Variant Benchmarking.

Scans all model results across AIVA-var-bench, computes comprehensive
metrics, confusion matrices, disease category breakdowns, safety audits,
ACMG criteria frequencies, and pairwise concordance, and outputs a single
JSON dataset consumed by dashboard/generate_html.py.

Dynamic & Extensible: Re-running this script or adding any new result file
instantly refreshes the dashboard.
"""

import glob
import json
import os
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import CLASSIFICATION_LABELS, DIRECTION_LABELS, CLASSIFICATION_TO_DIRECTION
from scripts.metrics import (
    normalize_classification,
    get_direction,
    normalize_criterion,
    calculate_class_metrics,
    calculate_direction_metrics,
    calculate_macro_f1,
)
from scripts.generate_results import VCEP_TO_CATEGORY, CATEGORY_ORDER
from dashboard.registry import PALETTE, read_registry, assign_colors


# Models removed through the dashboard before the registry existed.
LEGACY_EXCLUDED_FILE = REPO_ROOT / "dashboard" / "excluded_models.txt"


def read_legacy_excluded() -> set[str]:
    if not LEGACY_EXCLUDED_FILE.exists():
        return set()
    keys = (line.split("#")[0].strip() for line in LEGACY_EXCLUDED_FILE.read_text(encoding="utf-8").splitlines())
    return {k for k in keys if k}


def macro_f1_directional(gt_3: list[str], pred_3: list[str]) -> float:
    """Macro F1 over the three directions present in the ground truth."""
    m = calculate_direction_metrics(gt_3, pred_3, DIRECTION_LABELS)
    f1s = [m[d.lower()]["f1"] for d in DIRECTION_LABELS if m.get(d.lower(), {}).get("support", 0) > 0]
    return sum(f1s) / len(f1s) if f1s else 0.0


def get_vcep_category(panel: str) -> str:
    if not panel:
        return "Other"
    return VCEP_TO_CATEGORY.get(panel.strip(), "Other")


# The benchmark variant set (scripts/build_variant_set.py). When present, the
# dashboard is built on these variants only; without it, on the whole cohort.
VARIANT_SET_FILE = REPO_ROOT / "data" / "aiva_bench_variants_v1.tsv"


def read_variant_set(path: Path = VARIANT_SET_FILE) -> set[str] | None:
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return {line.split("\t", 1)[0] for line in f
                if line.strip() and not line.startswith(("#", "variant_id"))}


def load_unified_data(path: Path) -> tuple[dict, dict]:
    """Load unified dataset: id -> variant dict, and id -> metadata dict."""
    variants = {}
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                vid = item["id"]
                gt_norm = normalize_classification(item.get("classification", ""))
                panel = item.get("expert_panel", "")
                cat = get_vcep_category(panel)
                variants[vid] = {
                    "id": vid,
                    "gene": item.get("gene_symbol", ""),
                    "variation": item.get("variation", ""),
                    "variant_key": item.get("variant_key", ""),
                    "disease": item.get("disease", ""),
                    "expert_panel": panel,
                    "category": cat,
                    "ground_truth": gt_norm,
                    "ground_truth_direction": get_direction(gt_norm),
                    "criteria_met": [normalize_criterion(c) for c in (item.get("criteria_met") or [])],
                    "criteria_met_raw": list(item.get("criteria_met") or []),
                    "intervar_classification": normalize_classification(item.get("intervar_classification", "")),
                    "intervar_criteria": [normalize_criterion(c) for c in (item.get("intervar_criteria") or [])],
                    "intervar_criteria_raw": list(item.get("intervar_criteria") or []),
                    "bias_classification": normalize_classification(item.get("bias_classification", "")),
                    "bias_criteria": [normalize_criterion(c) for c in (item.get("bias_criteria") or [])],
                    "bias_criteria_raw": list(item.get("bias_criteria") or []),
                }
    return variants


def discover_model_files(repo_root: Path) -> tuple[dict[str, dict], list[dict], set[str]]:
    """
    Read dashboard/models.tsv. Returns (active models with results present,
    removed models, keys of active models whose results file is missing).
    """
    rows = read_registry()
    assign_colors(rows)
    legacy_excluded = read_legacy_excluded()
    discovered, removed, missing = {}, [], set()
    for row in rows:
        key = row["key"]
        if row["status"] != "active" or key in legacy_excluded:
            removed.append({"key": key, "name": row["name"]})
            continue
        fmt = row["format"] or "auto"
        if fmt == "unified" or row["path"].startswith("data:"):
            fmt, path = "unified_field", "unified:" + row["path"].split(":", 1)[1]
        else:
            file = repo_root / row["path"]
            if not file.exists():
                missing.add(key)
                print(f"  ! {row['name']}: results file not found ({row['path']})")
                continue
            if fmt == "auto":
                fmt = "json_array" if file.suffix == ".json" else "jsonl"
            path = str(file)
        discovered[key] = {
            "name": row["name"],
            "short_name": row["name"],
            "family": row["provider"],
            "is_anthropic": row["provider"] == "Anthropic",
            "type": row["method"] or "Unspecified",
            "path": path,
            "format": fmt,
            "color": row["color"],
            "color_dark": row["color_dark"] or row["color"],
            "description": row["method"],
            "section": row["section"],
        }

    registered = {r["path"].split("/")[0] for r in rows}
    unregistered = sorted(d.name for d in repo_root.glob("Results_*") if d.is_dir() and d.name not in registered and any(d.glob("*.jsonl")))
    if unregistered:
        print("  Result folders not in dashboard/models.tsv (not shown): " + ", ".join(unregistered))
    return discovered, removed, missing


STRENGTH_WORDS = ("supporting", "moderate", "strong", "very strong", "very_strong", "stand-alone", "standalone")


def with_strength(code: str, strength: str) -> str:
    s = strength.strip().lower()
    if "_" in code or s not in STRENGTH_WORDS:
        return code
    return f"{code}_{strength.strip().replace(' ', '_')}"


def criterion_points(criterion: str) -> int:
    """
    Points for one ACMG criterion on the ClinGen/Tavtigian (2020) scale:
    supporting 1, moderate 2, strong 4, very strong 8 (BA1 stand-alone 8),
    negative for benign evidence. An explicit strength modifier
    (e.g. PM2_Supporting) overrides the criterion's default strength.
    """
    low = criterion.strip().lower().replace(" ", "_").replace("-", "_")
    base = normalize_criterion(criterion).upper()
    if not base:
        return 0
    if "very" in low or "stand" in low:
        pts = 8
    elif "_strong" in low:
        pts = 4
    elif "_moderate" in low:
        pts = 2
    elif "_supporting" in low:
        pts = 1
    elif base.startswith(("PVS", "BA")):
        pts = 8
    elif base.startswith(("PS", "BS")):
        pts = 4
    elif base.startswith("PM"):
        pts = 2
    else:
        pts = 1
    return -pts if base.startswith("B") else pts


def load_model_predictions(model_info: dict, unified_dict: dict) -> dict[str, dict]:
    """
    Load variant_id -> {prediction, criteria, time_ms, raw} for a given model.
    """
    fmt = model_info["format"]
    path_str = model_info["path"]
    preds = {}

    if fmt == "unified_field":
        field = path_str.split(":")[1]
        crit_field = "bias_criteria" if "bias" in field else "intervar_criteria"
        for vid, v in unified_dict.items():
            p_raw = v.get(field, "")
            preds[vid] = {
                "prediction": p_raw,
                "criteria": v.get(crit_field, []),
                "criteria_raw": v.get(crit_field + "_raw", []),
                "score": None,
                "execution_time_ms": 0,
                "error": None,
            }
        return preds

    if fmt == "json_array":
        with open(path_str, "r", encoding="utf-8") as f:
            data = json.load(f)
        for item in data:
            vid = item.get("id")
            if not vid:
                continue
            met = item.get("criteria", {}).get("met", {}) or {}
            crit = list(met.keys())
            preds[vid] = {
                # Strength is the prefix of each criterion's note, e.g. "Supporting: ..."
                "criteria_raw": [with_strength(k, str(v).split(":")[0]) for k, v in met.items()],
                "score": item.get("acmg_points"),
                "prediction": normalize_classification(item.get("classification", "")),
                "criteria": [normalize_criterion(c) for c in crit],
                "execution_time_ms": item.get("execution_time_ms", 0),
                "error": None,
                "confidence": item.get("confidence", ""),
                "rationale": item.get("disease_context", ""),
            }
        return preds

    if fmt == "jsonl":
        with open(path_str, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    item = json.loads(line)
                except json.JSONDecodeError:
                    continue
                vid = item.get("variant_id") or item.get("id")
                if not vid:
                    continue
                cls_raw = item.get("aiva_classification") or item.get("classification", "")
                err = item.get("error")
                if err or not cls_raw or cls_raw == "Not classified":
                    continue
                preds[vid] = {
                    "prediction": normalize_classification(cls_raw),
                    "criteria": [normalize_criterion(c) for c in (item.get("aiva_criteria") or item.get("criteria") or [])],
                    "execution_time_ms": item.get("execution_time_ms", 0),
                    "error": err,
                    "confidence": item.get("aiva_confidence", ""),
                    "evidence": item.get("aiva_evidence", {}),
                    "criteria_raw": list(item.get("aiva_criteria") or item.get("criteria") or []),
                    "score": item.get("aiva_acmg_score"),
                }
        return preds

    return preds


VARIANT_COLUMNS = ["id", "gene", "variation", "variant_key", "disease", "category", "expert_panel",
                   "ground_truth", "expert_criteria", "expert_points"]
NO_CALL = "-"


def base36(n: int) -> str:
    """Same digits as JavaScript's n.toString(36)."""
    digits = "0123456789abcdefghijklmnopqrstuvwxyz"
    out = ""
    while True:
        n, r = divmod(n, 36)
        out = digits[r] + out
        if not n:
            return out


def model_criteria(p: dict) -> list[str]:
    """The criteria a model cited for one variant, as it wrote them (strength modifiers kept)."""
    return list(p.get("criteria_raw") or p.get("criteria") or [])


def build_variant_table(unified_dict: dict, model_predictions: dict, model_keys: list[str]) -> dict:
    """
    Every benchmark variant with the expert classification and each model's call
    and ACMG criteria, kept compact for embedding in the page:

    rows            one row per variant (VARIANT_COLUMNS)
    calls[model]    one character per row: the index of the call in
                    CLASSIFICATION_LABELS, or NO_CALL
    criteria[model] per row, the criteria the model cited as base-36 indices
                    into criteria_vocab separated by spaces; rows separated by "|"
    """
    ids = sorted(unified_dict, key=lambda v: (unified_dict[v]["gene"], unified_dict[v]["variation"], v))
    rows = []
    for vid in ids:
        u = unified_dict[vid]
        rows.append([vid, u["gene"], u["variation"], u["variant_key"], u["disease"], u["category"], u["expert_panel"],
                     u["ground_truth"], " ".join(u["criteria_met_raw"]),
                     sum(criterion_points(c) for c in u["criteria_met_raw"])])
    code = {label: str(i) for i, label in enumerate(CLASSIFICATION_LABELS)}
    counts = Counter(c for k in model_keys for vid in ids if vid in model_predictions[k]
                     for c in model_criteria(model_predictions[k][vid]))
    vocab = [c for c, _ in counts.most_common()]
    index = {c: base36(i) for i, c in enumerate(vocab)}
    calls, criteria = {}, {}
    for k in model_keys:
        preds = model_predictions[k]
        calls[k] = "".join(code.get(preds[vid]["prediction"], NO_CALL) if vid in preds else NO_CALL for vid in ids)
        criteria[k] = "|".join(" ".join(index[c] for c in model_criteria(preds[vid])) if vid in preds else "" for vid in ids)
    return {"columns": VARIANT_COLUMNS, "labels": CLASSIFICATION_LABELS, "rows": rows, "calls": calls,
            "criteria_vocab": vocab, "criteria": criteria}


def build_dashboard_dataset():
    print(f"[{datetime.now().strftime('%T')}] Initializing Dashboard Data Builder...")
    unified_path = REPO_ROOT / "data" / "erepo_bias_intervar_merged.jsonl"
    print(f"Loading Ground Truth & Baselines from {unified_path}...")
    unified_dict = load_unified_data(unified_path)
    variant_set = read_variant_set()
    if variant_set is not None:
        unified_dict = {vid: v for vid, v in unified_dict.items() if vid in variant_set}
        print(f"Restricted to the benchmark variant set ({VARIANT_SET_FILE.name}).")
    total_cohort = len(unified_dict)
    print(f"Loaded {total_cohort} ClinGen expert curated variants.")

    models_info, excluded_models, missing = discover_model_files(REPO_ROOT)
    print(f"Discovered {len(models_info)} models and baselines:")
    for k, m in models_info.items():
        print(f"  • [{m['family']}] {m['name']} ({m['format']})")

    # Load predictions for all models
    model_predictions = {}
    for m_key, m_info in models_info.items():
        print(f"Loading predictions for {m_key}...")
        preds = load_model_predictions(m_info, unified_dict)
        model_predictions[m_key] = preds
        print(f"  -> {len(preds)} valid predictions loaded.")

    # -------------------------------------------------------------------------
    # COMPUTE COMPREHENSIVE METRICS FOR EACH MODEL
    # -------------------------------------------------------------------------
    models_summary = []
    models_confusion = {}
    models_categories = {}
    models_criteria = {}
    models_safety = {}
    models_cross = {}
    models_latency = {}

    all_criteria_set = set([
        "PVS1", "PS1", "PS2", "PS3", "PS4",
        "PM1", "PM2", "PM3", "PM4", "PM5", "PM6",
        "PP1", "PP2", "PP3", "PP4", "PP5",
        "BA1", "BS1", "BS2", "BS3", "BS4",
        "BP1", "BP2", "BP3", "BP4", "BP5", "BP7"
    ])

    for m_key, m_info in models_info.items():
        preds = model_predictions[m_key]
        if not preds:
            continue

        evaluated_ids = [vid for vid in unified_dict if vid in preds]
        n_eval = len(evaluated_ids)
        if n_eval == 0:
            continue

        gt_5 = [unified_dict[vid]["ground_truth"] for vid in evaluated_ids]
        pred_5 = [preds[vid]["prediction"] for vid in evaluated_ids]

        gt_3 = [unified_dict[vid]["ground_truth_direction"] for vid in evaluated_ids]
        pred_3 = [get_direction(p) for p in pred_5]

        # Overall exact and directional matches
        exact_matches = sum(1 for g, p in zip(gt_5, pred_5) if g == p and g != "")
        directional_matches = sum(1 for g, p in zip(gt_3, pred_3) if g == p and g in DIRECTION_LABELS)

        exact_acc = round(exact_matches / n_eval * 100, 2)
        dir_acc = round(directional_matches / n_eval * 100, 2)

        # Per-class 5-class metrics
        per_class_5 = calculate_class_metrics(gt_5, pred_5, CLASSIFICATION_LABELS)
        macro_f1_5 = round(calculate_macro_f1(per_class_5) * 100, 2)

        # Per-direction 3-class metrics
        per_class_3 = calculate_direction_metrics(gt_3, pred_3, DIRECTION_LABELS)
        valid_3_f1s = [per_class_3[d.lower()]["f1"] for d in DIRECTION_LABELS if per_class_3.get(d.lower(), {}).get("support", 0) > 0]
        macro_f1_3 = round((sum(valid_3_f1s) / len(valid_3_f1s) * 100) if valid_3_f1s else 0, 2)

        # Safety / Critical Clinical Errors:
        # 1. False Pathogenic (Type I): Ground truth is Benign/Likely Benign, but model called Pathogenic/Likely Pathogenic
        # 2. False Benign (Type II): Ground truth is Pathogenic/Likely Pathogenic, but model called Benign/Likely Benign
        false_pathogenic_ids = []
        false_benign_ids = []

        for vid in evaluated_ids:
            g_dir = (unified_dict[vid]["ground_truth_direction"] or "").lower()
            p_dir = (get_direction(preds[vid]["prediction"]) or "").lower()
            if g_dir == "benign" and p_dir == "pathogenic":
                false_pathogenic_ids.append(vid)
            elif g_dir == "pathogenic" and p_dir == "benign":
                false_benign_ids.append(vid)

        type1_err_count = len(false_pathogenic_ids)
        type2_err_count = len(false_benign_ids)
        total_critical = type1_err_count + type2_err_count
        critical_error_rate = round(total_critical / n_eval * 100, 2)

        # Criteria frequencies
        crit_counter = Counter()
        for vid in evaluated_ids:
            for c in preds[vid]["criteria"]:
                if c:
                    crit_counter[c] += 1

        # Execution latency
        times = [preds[vid]["execution_time_ms"] for vid in evaluated_ids if preds[vid].get("execution_time_ms", 0) > 0]
        avg_time = round(sum(times) / len(times) / 1000, 1) if times else 0.0

        # Model Summary Object
        summary_obj = {
            "key": m_key,
            "name": m_info["name"],
            "short_name": m_info["short_name"],
            "family": m_info["family"],
            "is_anthropic": m_info["is_anthropic"],
            "type": m_info["type"],
            "color": m_info["color"],
            "color_dark": m_info.get("color_dark", m_info["color"]),
            "description": m_info["description"],
            "section": m_info["section"],
            "evaluated_count": n_eval,
            "total_cohort": total_cohort,
            "coverage_pct": round(n_eval / total_cohort * 100, 1),
            "exact_accuracy": exact_acc,
            "directional_accuracy": dir_acc,
            "macro_f1_5": macro_f1_5,
            "macro_f1_3": macro_f1_3,
            "critical_error_count": total_critical,
            "critical_error_rate": critical_error_rate,
            "false_pathogenic_count": type1_err_count,
            "false_benign_count": type2_err_count,
            "avg_latency_sec": avg_time,
            "per_class_5": {
                c: {
                    "precision": round(per_class_5[c]["precision"] * 100, 2),
                    "recall": round(per_class_5[c]["recall"] * 100, 2),
                    "f1": round(per_class_5[c]["f1"] * 100, 2),
                    "support": per_class_5[c]["support"],
                    "tp": per_class_5[c]["true_positives"],
                    "fp": per_class_5[c]["false_positives"],
                    "fn": per_class_5[c]["false_negatives"],
                }
                for c in CLASSIFICATION_LABELS
            },
            "per_class_3": {
                d: {
                    "precision": round(per_class_3.get(d.lower(), {}).get("precision", 0) * 100, 2),
                    "recall": round(per_class_3.get(d.lower(), {}).get("recall", 0) * 100, 2),
                    "f1": round(per_class_3.get(d.lower(), {}).get("f1", 0) * 100, 2),
                    "support": per_class_3.get(d.lower(), {}).get("support", 0),
                }
                for d in DIRECTION_LABELS
            },
        }
        models_summary.append(summary_obj)

        # 5x5 Confusion Matrix
        cm5 = [[0 for _ in range(5)] for _ in range(5)]
        for g, p in zip(gt_5, pred_5):
            if g in CLASSIFICATION_LABELS and p in CLASSIFICATION_LABELS:
                cm5[CLASSIFICATION_LABELS.index(g)][CLASSIFICATION_LABELS.index(p)] += 1

        # 3x3 Confusion Matrix
        cm3 = [[0 for _ in range(3)] for _ in range(3)]
        d_lower_labels = [d.lower() for d in DIRECTION_LABELS]
        for g, p in zip(gt_3, pred_3):
            g_low = (g or "").lower()
            p_low = (p or "").lower()
            if g_low in d_lower_labels and p_low in d_lower_labels:
                cm3[d_lower_labels.index(g_low)][d_lower_labels.index(p_low)] += 1

        models_confusion[m_key] = {
            "matrix_5": cm5,
            "matrix_3": cm3,
            "labels_5": CLASSIFICATION_LABELS,
            "labels_3": DIRECTION_LABELS,
        }

        # Category Breakdown
        cat_metrics = {}
        for cat in CATEGORY_ORDER:
            c_vids = [vid for vid in evaluated_ids if unified_dict[vid]["category"] == cat]
            if not c_vids:
                continue
            c_gt = [unified_dict[vid]["ground_truth"] for vid in c_vids]
            c_pred = [preds[vid]["prediction"] for vid in c_vids]
            c_gt3 = [unified_dict[vid]["ground_truth_direction"] for vid in c_vids]
            c_pred3 = [get_direction(p) for p in c_pred]

            c_exact = sum(1 for g, p in zip(c_gt, c_pred) if g == p)
            c_dir = sum(1 for g, p in zip(c_gt3, c_pred3) if g == p)
            c_m = calculate_class_metrics(c_gt, c_pred, CLASSIFICATION_LABELS)

            c_cm = [[0] * 5 for _ in range(5)]
            for g, p in zip(c_gt, c_pred):
                if g in CLASSIFICATION_LABELS and p in CLASSIFICATION_LABELS:
                    c_cm[CLASSIFICATION_LABELS.index(g)][CLASSIFICATION_LABELS.index(p)] += 1

            cat_metrics[cat] = {
                "count": len(c_vids),
                "exact_correct": c_exact,
                "directional_correct": c_dir,
                "matrix_5": c_cm,
                "exact_accuracy": round(c_exact / len(c_vids) * 100, 2),
                "directional_accuracy": round(c_dir / len(c_vids) * 100, 2),
                "macro_f1": round(calculate_macro_f1(c_m) * 100, 2),
                "macro_f1_3": round(macro_f1_directional(c_gt3, c_pred3) * 100, 2),
                "plp_f1": round((c_m["Pathogenic"]["f1"] + c_m["Likely Pathogenic"]["f1"]) / 2 * 100, 2),
                "vus_f1": round(c_m["Uncertain Significance"]["f1"] * 100, 2),
                "blb_f1": round((c_m["Benign"]["f1"] + c_m["Likely Benign"]["f1"]) / 2 * 100, 2),
            }
        models_categories[m_key] = cat_metrics

        # Every cross-direction error, with expert and model evidence
        def cross_record(vid, direction):
            u = unified_dict[vid]
            p = preds[vid]
            return {
                "id": vid,
                "direction": direction,
                "gene": u["gene"],
                "variant": u["variation"],
                "disease": u["disease"],
                "category": u["category"],
                "expert_panel": u["expert_panel"],
                "ground_truth": u["ground_truth"],
                "expert_criteria": u["criteria_met_raw"],
                "expert_points": sum(criterion_points(c) for c in u["criteria_met_raw"]),
                "predicted": p["prediction"],
                "model_criteria": p.get("criteria_raw") or p.get("criteria") or [],
                "model_points": p.get("score"),
                "confidence": p.get("confidence") or "",
            }
        models_cross[m_key] = [cross_record(v, "B→P") for v in false_pathogenic_ids] + [cross_record(v, "P→B") for v in false_benign_ids]

        # Criteria frequencies
        models_criteria[m_key] = {
            c: crit_counter.get(c, 0) for c in sorted(all_criteria_set)
        }

        # Safety samples
        models_safety[m_key] = {
            "false_pathogenic_count": type1_err_count,
            "false_benign_count": type2_err_count,
            "top_false_pathogenic": [
                {
                    "id": vid,
                    "gene": unified_dict[vid]["gene"],
                    "variant": unified_dict[vid]["variation"],
                    "disease": unified_dict[vid]["disease"],
                    "ground_truth": unified_dict[vid]["ground_truth"],
                    "predicted": preds[vid]["prediction"],
                    "criteria": preds[vid]["criteria"][:5],
                }
                for vid in false_pathogenic_ids[:10]
            ],
            "top_false_benign": [
                {
                    "id": vid,
                    "gene": unified_dict[vid]["gene"],
                    "variant": unified_dict[vid]["variation"],
                    "disease": unified_dict[vid]["disease"],
                    "ground_truth": unified_dict[vid]["ground_truth"],
                    "predicted": preds[vid]["prediction"],
                    "criteria": preds[vid]["criteria"][:5],
                }
                for vid in false_benign_ids[:10]
            ],
        }

    # -------------------------------------------------------------------------
    # PAIRWISE MODEL CONCORDANCE
    # -------------------------------------------------------------------------
    model_keys = [m["key"] for m in models_summary]
    concordance_matrix = {k1: {} for k1 in model_keys}

    for k1 in model_keys:
        for k2 in model_keys:
            if k1 == k2:
                concordance_matrix[k1][k2] = {"exact_pct": 100.0, "dir_pct": 100.0, "overlap": len(model_predictions[k1])}
                continue
            common = set(model_predictions[k1].keys()) & set(model_predictions[k2].keys())
            if not common:
                concordance_matrix[k1][k2] = {"exact_pct": 0.0, "dir_pct": 0.0, "overlap": 0}
                continue
            exact_agrees = sum(1 for vid in common if model_predictions[k1][vid]["prediction"] == model_predictions[k2][vid]["prediction"])
            dir_agrees = sum(1 for vid in common if get_direction(model_predictions[k1][vid]["prediction"]) == get_direction(model_predictions[k2][vid]["prediction"]))
            concordance_matrix[k1][k2] = {
                "exact_pct": round(exact_agrees / len(common) * 100, 1),
                "dir_pct": round(dir_agrees / len(common) * 100, 1),
                "overlap": len(common),
            }

    # -------------------------------------------------------------------------
    # EVERY BENCHMARK VARIANT WITH EACH MODEL'S CALL (the page's CSV download)
    # -------------------------------------------------------------------------
    variant_table = build_variant_table(unified_dict, model_predictions, model_keys)

    # -------------------------------------------------------------------------
    # LIVE RE-RUN BACKGROUND JOB MONITORING
    # -------------------------------------------------------------------------
    live_jobs = {}
    for job_name, pid_file, log_file, target_total in [
        ("Sonnet 5.5 Re-Run", "run_overnight_sonnet.pid", "run_overnight_sonnet_*.log", 5760),
        ("Opus 5.5 Re-Run", "run_overnight_opus.pid", "run_overnight_opus_*.log", 8387),
    ]:
        p_path = REPO_ROOT / pid_file
        pid = None
        status = "Inactive"
        if p_path.exists():
            try:
                pid = int(p_path.read_text().strip())
                status = "Running"
            except Exception:
                pass

        # Find latest log
        logs = sorted(glob.glob(str(REPO_ROOT / log_file)))
        latest_log = logs[-1] if logs else ""
        current_progress = 0
        latest_line = ""
        if latest_log and os.path.exists(latest_log):
            try:
                with open(latest_log, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        if "Progress:" in line:
                            match = re.search(r"Progress:\s*(\d+)/(\d+)", line)
                            if match:
                                current_progress = int(match.group(1))
                                latest_line = line.strip()
            except Exception:
                pass

        live_jobs[job_name] = {
            "pid": pid,
            "status": status,
            "log_path": str(latest_log),
            "progress_count": current_progress,
            "target_total": target_total,
            "progress_pct": round(current_progress / target_total * 100, 1) if target_total else 0,
            "latest_log_snippet": latest_line,
        }

    # -------------------------------------------------------------------------
    # FINAL ASSEMBLED DASHBOARD PAYLOAD
    # -------------------------------------------------------------------------
    payload = {
        "metadata": {
            "title": "AIVA Variant Benchmark",
            "subtitle": "Anthropic Claude vs Frontiers & Classical Baselines on ClinGen Curated Variant Classification",
            "evaluation_date": datetime.now().strftime("%B %d, %Y"),
            "total_variants": total_cohort,
            "categories": CATEGORY_ORDER,
            "classification_labels": CLASSIFICATION_LABELS,
            "direction_labels": DIRECTION_LABELS,
            "excluded_models": excluded_models,
            "palette": [[light, dark] for light, dark, _ in PALETTE],
        },
        "models": models_summary,
        "confusion_matrices": models_confusion,
        "categories_data": models_categories,
        "criteria_data": models_criteria,
        "safety_data": models_safety,
        "cross_direction": models_cross,
        "concordance": concordance_matrix,
        "variant_table": variant_table,
        "live_jobs": live_jobs,
    }

    carry_over_archived_models(payload, missing)

    out_file = REPO_ROOT / "dashboard" / "data" / "benchmark_data.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    with open(out_file, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2)

    print(f"[{datetime.now().strftime('%T')}] Wrote dashboard data to {out_file}")
    print(f"Data file size: {out_file.stat().st_size / 1024:.1f} KB")

    return payload


def load_previous_dataset() -> dict:
    """Dataset embedded in the current dashboard/index.html, if any."""
    html_path = REPO_ROOT / "dashboard" / "index.html"
    if not html_path.exists():
        return {}
    html = html_path.read_text(encoding="utf-8")
    marker = "window.BENCHMARK_DATA = "
    start = html.find(marker)
    if start == -1:
        return {}
    try:
        data, _ = json.JSONDecoder().raw_decode(html, start + len(marker))
    except json.JSONDecodeError:
        return {}
    return data


def carry_over_archived_models(payload: dict, missing: set[str]) -> None:
    """
    Keep registered models whose results file is not in this checkout (for
    example a run excluded by .gitignore) by copying their computed results
    from the previous build. They are flagged "archived" and lack
    variant-level comparisons against models that were added later.
    """
    previous = load_previous_dataset()
    current = {m["key"] for m in payload["models"]}
    archived = [m for m in previous.get("models", [])
                if m["key"] in missing and m["key"] not in current
                and m["key"] in previous.get("confusion_matrices", {})]

    for m in archived:
        k = m["key"]
        m = dict(m, archived=True)
        payload["models"].append(m)
        payload["confusion_matrices"][k] = previous["confusion_matrices"][k]
        for section in ("categories_data", "criteria_data", "safety_data", "cross_direction"):
            if k in previous.get(section, {}):
                payload[section][k] = previous[section][k]
        cats = payload["categories_data"].get(k, {})
        for r in cats.values():
            r.setdefault("exact_correct", round(r["exact_accuracy"] * r["count"] / 100))
            r.setdefault("directional_correct", round(r["directional_accuracy"] * r["count"] / 100))

        old_conc = previous.get("concordance", {}).get(k, {})
        payload["concordance"][k] = {o: v for o, v in old_conc.items() if o in payload["concordance"] or o == k}
        for o, v in old_conc.items():
            if o in payload["concordance"] and o != k:
                payload["concordance"][o][k] = v

        old_table = previous.get("variant_table") or {}
        old_calls = dict(zip((r[0] for r in old_table.get("rows", [])), old_table.get("calls", {}).get(k, "")))
        table = payload["variant_table"]
        table["calls"][k] = "".join(old_calls.get(r[0], NO_CALL) for r in table["rows"])
        # Criteria: decode with the previous vocabulary, re-encode with this one
        old_vocab = old_table.get("criteria_vocab", [])
        old_crit = old_table.get("criteria", {}).get(k, "")
        old_lists = dict(zip((r[0] for r in old_table.get("rows", [])), old_crit.split("|") if old_crit else []))
        vocab = table["criteria_vocab"]

        def encode(c: str) -> str:
            if c not in vocab:
                vocab.append(c)
            return base36(vocab.index(c))

        table["criteria"][k] = "|".join(
            " ".join(encode(old_vocab[int(t, 36)]) for t in old_lists.get(r[0], "").split())
            for r in table["rows"])
        print(f"  Carried over {m['name']} from the previous build (raw results not found).")


if __name__ == "__main__":
    build_dashboard_dataset()
