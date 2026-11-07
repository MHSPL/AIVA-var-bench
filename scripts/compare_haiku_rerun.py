#!/usr/bin/env python3
"""
Compare Haiku from Claude-Code manual prompt classifications vs AIVA Haiku re-run.

Outputs:
1. Detailed metrics JSON
2. Comparison report (Exact & Directional accuracy, Macro F1, Per-class F1)
3. Category-level metrics table
4. Publication-quality comparison figures:
   - Side-by-side 5-class confusion matrices
   - Side-by-side 3-class directional confusion matrices
   - Performance comparison bar chart (Overall, Per-Class, Directional)
   - Category-level F1 comparison (grouped bar chart / slope chart)
   - Combined summary scorecard
"""

import os
os.environ['MPLCONFIGDIR'] = '/tmp/mpl_cache'
import json
import sys
from pathlib import Path
from collections import Counter, defaultdict

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker

# Add repo root to path
REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import CLASSIFICATION_LABELS, DIRECTION_LABELS, CLASSIFICATION_TO_DIRECTION
from scripts.metrics import (
    normalize_classification,
    get_direction,
    calculate_class_metrics,
    calculate_direction_metrics,
    calculate_macro_f1,
)
from scripts.generate_results import VCEP_TO_CATEGORY, CATEGORY_ORDER


def load_claude_code_results(json_path: Path) -> dict:
    """Load Claude-Code manual Haiku JSON and index by variant id."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return {item["id"]: item for item in data}


def load_aiva_rerun_results(jsonl_path: Path) -> dict:
    """Load AIVA Haiku rerun JSONL and index by variant_id."""
    results = {}
    with open(jsonl_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                vid = item.get("variant_id")
                if vid:
                    results[vid] = item
    return results


def load_ground_truth(unified_path: Path) -> dict:
    """Load ground truth from unified dataset."""
    gt = {}
    with open(unified_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                gt[item["id"]] = item
    return gt


def get_vcep_category(panel: str) -> str:
    if not panel:
        return "Other"
    panel_clean = panel.strip()
    return VCEP_TO_CATEGORY.get(panel_clean, "Other")


def compute_metrics():
    cc_path = REPO_ROOT / "Claude_code_results" / "acmg_classifications_manual_Haiku.json"
    rerun_path = REPO_ROOT / "Results_Claude_Haiku_5_5_Analysis_rerun" / "haiku_full.jsonl"
    unified_path = REPO_ROOT / "data" / "erepo_bias_intervar_merged.jsonl"
    output_dir = REPO_ROOT / "Claude_code_results" / "comparison_figures"
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"Loading Claude-Code Haiku results: {cc_path}")
    cc_data = load_claude_code_results(cc_path)
    print(f"  Loaded {len(cc_data)} records.")

    print(f"Loading AIVA Haiku Rerun results: {rerun_path}")
    rerun_data = load_aiva_rerun_results(rerun_path)
    print(f"  Loaded {len(rerun_data)} records.")

    print(f"Loading Unified Ground Truth: {unified_path}")
    gt_data = load_ground_truth(unified_path)
    print(f"  Loaded {len(gt_data)} ground truth records.")

    # Match common variants
    common_ids = sorted(set(cc_data.keys()) & set(rerun_data.keys()))
    print(f"\nCommon variants evaluated: {len(common_ids)}")

    rows = []
    for vid in common_ids:
        cc_item = cc_data[vid]
        rerun_item = rerun_data[vid]
        gt_item = gt_data.get(vid, {})

        gt_raw = rerun_item.get("ground_truth") or gt_item.get("classification", "")
        gt_norm = normalize_classification(gt_raw)
        gt_dir = get_direction(gt_norm)

        cc_raw = cc_item.get("classification", "")
        cc_norm = normalize_classification(cc_raw)
        cc_dir = get_direction(cc_norm)

        rerun_raw = rerun_item.get("aiva_classification", "")
        rerun_norm = normalize_classification(rerun_raw)
        rerun_dir = get_direction(rerun_norm)

        vcep = rerun_item.get("expert_panel") or gt_item.get("expert_panel", "")
        category = get_vcep_category(vcep)

        rows.append({
            "variant_id": vid,
            "gene": rerun_item.get("gene", ""),
            "variant": rerun_item.get("variant", ""),
            "expert_panel": vcep,
            "category": category,
            "ground_truth": gt_norm,
            "ground_truth_direction": gt_dir,
            "claude_code_prediction": cc_norm,
            "claude_code_direction": cc_dir,
            "aiva_rerun_prediction": rerun_norm,
            "aiva_rerun_direction": rerun_dir,
            "cc_exact_correct": (cc_norm == gt_norm) and (gt_norm != ""),
            "cc_dir_correct": (cc_dir == gt_dir) and (gt_dir in DIRECTION_LABELS),
            "rerun_exact_correct": (rerun_norm == gt_norm) and (gt_norm != ""),
            "rerun_dir_correct": (rerun_dir == gt_dir) and (gt_dir in DIRECTION_LABELS),
            "models_agree_exact": (cc_norm == rerun_norm),
            "models_agree_dir": (cc_dir == rerun_dir),
        })

    df = pd.DataFrame(rows)
    df.to_csv(output_dir / "haiku_comparison_per_variant.tsv", sep="\t", index=False)
    print(f"Saved per-variant comparison to {output_dir / 'haiku_comparison_per_variant.tsv'}")

    # Summary Metrics
    total = len(df)
    cc_exact_acc = df["cc_exact_correct"].mean()
    rerun_exact_acc = df["rerun_exact_correct"].mean()
    cc_dir_acc = df["cc_dir_correct"].mean()
    rerun_dir_acc = df["rerun_dir_correct"].mean()

    # Per class metrics
    gt_list = df["ground_truth"].tolist()
    cc_pred_list = df["claude_code_prediction"].tolist()
    rerun_pred_list = df["aiva_rerun_prediction"].tolist()

    cc_per_class = calculate_class_metrics(gt_list, cc_pred_list, CLASSIFICATION_LABELS)
    rerun_per_class = calculate_class_metrics(gt_list, rerun_pred_list, CLASSIFICATION_LABELS)

    cc_macro_f1 = calculate_macro_f1(cc_per_class)
    rerun_macro_f1 = calculate_macro_f1(rerun_per_class)

    # Directional metrics
    gt_dir_list = df["ground_truth_direction"].tolist()
    cc_dir_pred_list = df["claude_code_direction"].tolist()
    rerun_dir_pred_list = df["aiva_rerun_direction"].tolist()

    cc_per_dir = calculate_direction_metrics(gt_dir_list, cc_dir_pred_list, DIRECTION_LABELS)
    rerun_per_dir = calculate_direction_metrics(gt_dir_list, rerun_dir_pred_list, DIRECTION_LABELS)

    print("\n" + "=" * 75)
    print("HAIKU BENCHMARK COMPARISON: Claude-Code Prompt vs AIVA Re-run")
    print("=" * 75)
    print(f"Total Variants Evaluated: {total}")
    print(f"{'Metric':<35} {'Claude-Code Haiku':>18} {'AIVA Haiku Rerun':>18} {'Delta (AIVA-CC)':>16}")
    print("-" * 75)
    print(f"{'5-Class Exact Accuracy':<35} {cc_exact_acc*100:>17.2f}% {rerun_exact_acc*100:>17.2f}% {(rerun_exact_acc - cc_exact_acc)*100:>+15.2f}%")
    print(f"{'3-Class Directional Accuracy':<35} {cc_dir_acc*100:>17.2f}% {rerun_dir_acc*100:>17.2f}% {(rerun_dir_acc - cc_dir_acc)*100:>+15.2f}%")
    print(f"{'5-Class Macro F1':<35} {cc_macro_f1*100:>17.2f}% {rerun_macro_f1*100:>17.2f}% {(rerun_macro_f1 - cc_macro_f1)*100:>+15.2f}%")
    print("-" * 75)
    print("Per-Class F1 Scores:")
    for cls in CLASSIFICATION_LABELS:
        cc_f1 = cc_per_class.get(cls, {}).get("f1", 0) * 100
        rr_f1 = rerun_per_class.get(cls, {}).get("f1", 0) * 100
        print(f"  {cls:<33} {cc_f1:>17.2f}% {rr_f1:>17.2f}% {rr_f1 - cc_f1:>+15.2f}%")
    print("-" * 75)
    print("Directional F1 Scores:")
    for d in DIRECTION_LABELS:
        cc_f1 = cc_per_dir.get(d, {}).get("f1", 0) * 100
        rr_f1 = rerun_per_dir.get(d, {}).get("f1", 0) * 100
        print(f"  {d:<33} {cc_f1:>17.2f}% {rr_f1:>17.2f}% {rr_f1 - cc_f1:>+15.2f}%")
    print("=" * 75)

    # Category Breakdown
    cat_metrics = []
    for cat in CATEGORY_ORDER:
        sub_df = df[df["category"] == cat]
        if sub_df.empty:
            continue
        n_cat = len(sub_df)
        cat_gt = sub_df["ground_truth"].tolist()
        cat_cc = sub_df["claude_code_prediction"].tolist()
        cat_rr = sub_df["aiva_rerun_prediction"].tolist()

        cc_m = calculate_class_metrics(cat_gt, cat_cc, CLASSIFICATION_LABELS)
        rr_m = calculate_class_metrics(cat_gt, cat_rr, CLASSIFICATION_LABELS)

        cc_f1 = calculate_macro_f1(cc_m) * 100
        rr_f1 = calculate_macro_f1(rr_m) * 100

        cc_acc = sub_df["cc_exact_correct"].mean() * 100
        rr_acc = sub_df["rerun_exact_correct"].mean() * 100

        cc_dir = sub_df["cc_dir_correct"].mean() * 100
        rr_dir = sub_df["rerun_dir_correct"].mean() * 100

        cat_metrics.append({
            "category": cat,
            "count": n_cat,
            "cc_macro_f1": round(cc_f1, 2),
            "rerun_macro_f1": round(rr_f1, 2),
            "delta_f1": round(rr_f1 - cc_f1, 2),
            "cc_exact_acc": round(cc_acc, 2),
            "rerun_exact_acc": round(rr_acc, 2),
            "delta_exact_acc": round(rr_acc - cc_acc, 2),
            "cc_dir_acc": round(cc_dir, 2),
            "rerun_dir_acc": round(rr_dir, 2),
            "delta_dir_acc": round(rr_dir - cc_dir, 2),
        })

    cat_df = pd.DataFrame(cat_metrics)
    cat_df.to_csv(output_dir / "category_comparison_summary.tsv", sep="\t", index=False)
    print(f"Saved category summary to {output_dir / 'category_comparison_summary.tsv'}")

    # Save summary metrics JSON
    summary_dict = {
        "total": total,
        "cc_exact_acc": cc_exact_acc,
        "rerun_exact_acc": rerun_exact_acc,
        "cc_dir_acc": cc_dir_acc,
        "rerun_dir_acc": rerun_dir_acc,
        "cc_macro_f1": cc_macro_f1,
        "rerun_macro_f1": rerun_macro_f1,
        "cc_per_class": cc_per_class,
        "rerun_per_class": rerun_per_class,
        "cc_per_dir": cc_per_dir,
        "rerun_per_dir": rerun_per_dir,
    }
    with open(output_dir / "summary_metrics.json", "w") as f:
        json.dump(summary_dict, f, indent=2)

    return df, cat_df, summary_dict, output_dir


def plot_all_figures(df, cat_df, summary, output_dir: Path):
    plt.rcParams.update({
        'font.sans-serif': 'Helvetica, Arial, sans-serif',
        'font.family': 'sans-serif',
        'figure.dpi': 300,
        'savefig.dpi': 300,
        'axes.edgecolor': '#cccccc',
        'axes.linewidth': 0.8,
    })

    # Color palette
    CC_COLOR = "#D97706"     # Amber / Warm Claude orange
    RERUN_COLOR = "#2563EB"  # Blue / AIVA Navy-blue
    DELTA_POS = "#16A34A"    # Green
    DELTA_NEG = "#DC2626"    # Red

    # -------------------------------------------------------------------------
    # 1. SIDE-BY-SIDE 5-CLASS CONFUSION MATRICES
    # -------------------------------------------------------------------------
    labels = CLASSIFICATION_LABELS
    short_labels = ["Path", "Likely Path", "VUS", "Likely Ben", "Benign"]

    cm_cc = np.zeros((5, 5), dtype=int)
    cm_rr = np.zeros((5, 5), dtype=int)

    for _, r in df.iterrows():
        g = r["ground_truth"]
        p_cc = r["claude_code_prediction"]
        p_rr = r["aiva_rerun_prediction"]
        if g in labels:
            gi = labels.index(g)
            if p_cc in labels:
                cm_cc[gi, labels.index(p_cc)] += 1
            if p_rr in labels:
                cm_rr[gi, labels.index(p_rr)] += 1

    fig, axes = plt.subplots(1, 2, figsize=(14, 6.2))
    for ax, cm, title, color_map in [
        (axes[0], cm_cc, "Claude-Code Haiku (Manual Prompt)", plt.cm.Oranges),
        (axes[1], cm_rr, "AIVA Haiku 5.5 Re-run", plt.cm.Blues),
    ]:
        im = ax.imshow(cm, interpolation='nearest', cmap=color_map)
        ax.set_title(title, fontsize=12, fontweight='bold', pad=12)
        tick_marks = np.arange(len(short_labels))
        ax.set_xticks(tick_marks)
        ax.set_xticklabels(short_labels, rotation=35, ha='right', fontsize=9)
        ax.set_yticks(tick_marks)
        ax.set_yticklabels(short_labels, fontsize=9)
        ax.set_xlabel("Predicted Classification", fontsize=10, fontweight='bold', labelpad=8)
        ax.set_ylabel("Ground Truth (ClinGen eRepo)", fontsize=10, fontweight='bold', labelpad=8)

        thresh = cm.max() / 2.0
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                val = cm[i, j]
                ax.text(j, i, f"{val:,}",
                        ha="center", va="center",
                        fontsize=8.5,
                        color="white" if val > thresh else "#202124",
                        fontweight="bold" if i == j else "normal")

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=8)

    plt.suptitle("5-Class Variant Classification Confusion Matrices: Claude-Code vs AIVA Re-run",
                 fontsize=14, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_dir / "figure1_confusion_matrices_5class_comparison.png", bbox_inches='tight')
    plt.savefig(output_dir / "figure1_confusion_matrices_5class_comparison.pdf", bbox_inches='tight')
    plt.close()
    print("Saved 5-Class Confusion Matrices Comparison.")

    # -------------------------------------------------------------------------
    # 2. SIDE-BY-SIDE 3-CLASS DIRECTIONAL CONFUSION MATRICES
    # -------------------------------------------------------------------------
    d_labels = [d for d in DIRECTION_LABELS]
    cm_cc_d = np.zeros((len(d_labels), len(d_labels)), dtype=int)
    cm_rr_d = np.zeros((len(d_labels), len(d_labels)), dtype=int)

    for _, r in df.iterrows():
        g = r["ground_truth_direction"]
        p_cc = r["claude_code_direction"]
        p_rr = r["aiva_rerun_direction"]
        if g in d_labels:
            gi = d_labels.index(g)
            if p_cc in d_labels:
                cm_cc_d[gi, d_labels.index(p_cc)] += 1
            if p_rr in d_labels:
                cm_rr_d[gi, d_labels.index(p_rr)] += 1

    fig, axes = plt.subplots(1, 2, figsize=(12, 5.2))
    for ax, cm, title, color_map in [
        (axes[0], cm_cc_d, f"Claude-Code Haiku (Acc: {summary['cc_dir_acc']*100:.1f}%)", plt.cm.Oranges),
        (axes[1], cm_rr_d, f"AIVA Haiku Re-run (Acc: {summary['rerun_dir_acc']*100:.1f}%)", plt.cm.Blues),
    ]:
        im = ax.imshow(cm, interpolation='nearest', cmap=color_map)
        ax.set_title(title, fontsize=11, fontweight='bold', pad=10)
        tick_marks = np.arange(len(d_labels))
        ax.set_xticks(tick_marks)
        ax.set_xticklabels([d.capitalize() for d in d_labels], fontsize=9.5)
        ax.set_yticks(tick_marks)
        ax.set_yticklabels([d.capitalize() for d in d_labels], fontsize=9.5)
        ax.set_xlabel("Predicted Direction", fontsize=10, fontweight='bold', labelpad=6)
        ax.set_ylabel("Ground Truth Direction", fontsize=10, fontweight='bold', labelpad=6)

        thresh = cm.max() / 2.0
        for i in range(cm.shape[0]):
            for j in range(cm.shape[1]):
                val = cm[i, j]
                ax.text(j, i, f"{val:,}",
                        ha="center", va="center",
                        fontsize=9.5,
                        color="white" if val > thresh else "#202124",
                        fontweight="bold" if i == j else "normal")

        cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
        cbar.ax.tick_params(labelsize=8)

    plt.suptitle("3-Class Directional Classification Confusion Matrices: Claude-Code vs AIVA Re-run",
                 fontsize=13, fontweight='bold', y=0.98)
    plt.tight_layout(rect=[0, 0, 1, 0.95])
    plt.savefig(output_dir / "figure2_directional_confusion_matrices_comparison.png", bbox_inches='tight')
    plt.savefig(output_dir / "figure2_directional_confusion_matrices_comparison.pdf", bbox_inches='tight')
    plt.close()
    print("Saved Directional Confusion Matrices Comparison.")

    # -------------------------------------------------------------------------
    # 3. METRIC COMPARISON BAR CHART (Overall + Per-Class + Directional)
    # -------------------------------------------------------------------------
    metrics_names = [
        "Exact Match\n(5-Class)", "Directional\n(3-Class)", "Macro F1\n(5-Class)",
        "Pathogenic\nF1", "Likely Path\nF1", "VUS\nF1", "Likely Ben\nF1", "Benign\nF1"
    ]
    cc_vals = [
        summary["cc_exact_acc"] * 100,
        summary["cc_dir_acc"] * 100,
        summary["cc_macro_f1"] * 100,
        summary["cc_per_class"]["Pathogenic"]["f1"] * 100,
        summary["cc_per_class"]["Likely Pathogenic"]["f1"] * 100,
        summary["cc_per_class"]["Uncertain Significance"]["f1"] * 100,
        summary["cc_per_class"]["Likely Benign"]["f1"] * 100,
        summary["cc_per_class"]["Benign"]["f1"] * 100,
    ]
    rr_vals = [
        summary["rerun_exact_acc"] * 100,
        summary["rerun_dir_acc"] * 100,
        summary["rerun_macro_f1"] * 100,
        summary["rerun_per_class"]["Pathogenic"]["f1"] * 100,
        summary["rerun_per_class"]["Likely Pathogenic"]["f1"] * 100,
        summary["rerun_per_class"]["Uncertain Significance"]["f1"] * 100,
        summary["rerun_per_class"]["Likely Benign"]["f1"] * 100,
        summary["rerun_per_class"]["Benign"]["f1"] * 100,
    ]

    fig, ax = plt.subplots(figsize=(12, 5.5))
    x = np.arange(len(metrics_names))
    width = 0.35

    rects1 = ax.bar(x - width/2, cc_vals, width, label='Claude-Code Haiku (Manual)', color=CC_COLOR, alpha=0.9, edgecolor='none')
    rects2 = ax.bar(x + width/2, rr_vals, width, label='AIVA Haiku Re-run', color=RERUN_COLOR, alpha=0.9, edgecolor='none')

    ax.set_ylabel('Performance (%)', fontsize=11, fontweight='bold')
    ax.set_title('Overall & Per-Class Performance Comparison: Claude-Code vs AIVA Re-run', fontsize=13, fontweight='bold', pad=14)
    ax.set_xticks(x)
    ax.set_xticklabels(metrics_names, fontsize=9.5)
    ax.set_ylim(0, max(max(cc_vals), max(rr_vals)) * 1.18)
    ax.legend(frameon=True, fontsize=10, loc='upper left')
    ax.grid(axis='y', linestyle='--', alpha=0.3)

    for rect in rects1:
        h = rect.get_height()
        ax.annotate(f'{h:.1f}%',
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=8.5, fontweight='bold', color='#444')
    for rect in rects2:
        h = rect.get_height()
        ax.annotate(f'{h:.1f}%',
                    xy=(rect.get_x() + rect.get_width() / 2, h),
                    xytext=(0, 3), textcoords="offset points",
                    ha='center', va='bottom', fontsize=8.5, fontweight='bold', color='#1d4ed8')

    plt.tight_layout()
    plt.savefig(output_dir / "figure3_overall_metrics_comparison.png", bbox_inches='tight')
    plt.savefig(output_dir / "figure3_overall_metrics_comparison.pdf", bbox_inches='tight')
    plt.close()
    print("Saved Overall Metrics Comparison Bar Chart.")

    # -------------------------------------------------------------------------
    # 4. CATEGORY MACRO F1 COMPARISON (Horizontal Grouped Bar Chart)
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(11, 7.5))
    cats_plot = cat_df.iloc[::-1]

    y = np.arange(len(cats_plot))
    h = 0.36

    ax.barh(y + h/2, cats_plot['cc_macro_f1'], h, label='Claude-Code Haiku', color=CC_COLOR, alpha=0.9)
    ax.barh(y - h/2, cats_plot['rerun_macro_f1'], h, label='AIVA Haiku Re-run', color=RERUN_COLOR, alpha=0.9)

    for i, (_, row) in enumerate(cats_plot.iterrows()):
        d = row['delta_f1']
        color = DELTA_POS if d >= 0 else DELTA_NEG
        sym = "+" if d >= 0 else ""
        max_val = max(row['cc_macro_f1'], row['rerun_macro_f1'])
        ax.text(max_val + 1.2, y[i], f"{sym}{d:.1f}%", va='center', ha='left',
                fontsize=8.5, fontweight='bold', color=color)

    ax.set_yticks(y)
    ax.set_yticklabels([f"{c} (n={n})" for c, n in zip(cats_plot['category'], cats_plot['count'])], fontsize=9.5)
    ax.set_xlabel('Macro F1 (%)', fontsize=11, fontweight='bold')
    ax.set_title('Disease Category Performance (Macro F1): Claude-Code vs AIVA Re-run', fontsize=12.5, fontweight='bold', pad=12)
    ax.set_xlim(0, max(cat_df['rerun_macro_f1'].max(), cat_df['cc_macro_f1'].max()) + 12)
    ax.legend(loc='lower right', fontsize=10, frameon=True)
    ax.grid(axis='x', linestyle='--', alpha=0.3)

    plt.tight_layout()
    plt.savefig(output_dir / "figure4_category_f1_comparison.png", bbox_inches='tight')
    plt.savefig(output_dir / "figure4_category_f1_comparison.pdf", bbox_inches='tight')
    plt.close()
    print("Saved Category F1 Comparison Bar Chart.")

    # -------------------------------------------------------------------------
    # 5. DISCORDANCE & MIGRATION MATRIX
    # -------------------------------------------------------------------------
    fig, ax = plt.subplots(figsize=(8, 6.5))
    mig_matrix = np.zeros((5, 5), dtype=int)
    for _, r in df.iterrows():
        c_cc = r["claude_code_prediction"]
        c_rr = r["aiva_rerun_prediction"]
        if c_cc in labels and c_rr in labels:
            mig_matrix[labels.index(c_cc), labels.index(c_rr)] += 1

    im = ax.imshow(mig_matrix, cmap=plt.cm.Purples)
    ax.set_title("Classification Migration Matrix: Claude-Code vs AIVA Re-run\n(Where do the two systems disagree?)",
                 fontsize=11.5, fontweight='bold', pad=12)
    tick_marks = np.arange(len(short_labels))
    ax.set_xticks(tick_marks)
    ax.set_xticklabels(short_labels, rotation=30, ha='right', fontsize=9)
    ax.set_yticks(tick_marks)
    ax.set_yticklabels(short_labels, fontsize=9)
    ax.set_xlabel("AIVA Haiku Re-run Classification", fontsize=10, fontweight='bold', labelpad=8)
    ax.set_ylabel("Claude-Code Haiku Classification", fontsize=10, fontweight='bold', labelpad=8)

    thresh = mig_matrix.max() / 2.0
    for i in range(5):
        for j in range(5):
            val = mig_matrix[i, j]
            ax.text(j, i, f"{val:,}", ha="center", va="center",
                    fontsize=8.5,
                    color="white" if val > thresh else "#202124",
                    fontweight="bold" if i == j else "normal")

    cbar = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cbar.ax.tick_params(labelsize=8)

    plt.tight_layout()
    plt.savefig(output_dir / "figure5_migration_discordance.png", bbox_inches='tight')
    plt.savefig(output_dir / "figure5_migration_discordance.pdf", bbox_inches='tight')
    plt.close()
    print("Saved Migration Discordance Matrix.")

    # -------------------------------------------------------------------------
    # 6. COMBINED SUMMARY SCORECARD (Clean Table Figure)
    # -------------------------------------------------------------------------
    fig = plt.figure(figsize=(10, 8.5), dpi=300)
    ax = fig.add_subplot(111)
    ax.axis('off')

    # Direction keys
    def get_dir_f1(d_dict, key):
        return (d_dict.get(key) or d_dict.get(key.lower()) or d_dict.get(key.capitalize()) or {}).get("f1", 0) * 100

    cc_p_f1 = get_dir_f1(summary['cc_per_dir'], 'Pathogenic')
    rr_p_f1 = get_dir_f1(summary['rerun_per_dir'], 'Pathogenic')
    cc_v_f1 = get_dir_f1(summary['cc_per_dir'], 'VUS')
    rr_v_f1 = get_dir_f1(summary['rerun_per_dir'], 'VUS')
    cc_b_f1 = get_dir_f1(summary['cc_per_dir'], 'Benign')
    rr_b_f1 = get_dir_f1(summary['rerun_per_dir'], 'Benign')

    table_data = [
        ["Benchmark Cohort", "8,387 ClinGen curated variants across 13 disease categories", ""],
        ["Metric", "Claude-Code Haiku", "AIVA Haiku Re-run", "Delta (AIVA - CC)"],
        ["5-Class Exact Match Accuracy", f"{summary['cc_exact_acc']*100:.2f}%", f"{summary['rerun_exact_acc']*100:.2f}%", f"{(summary['rerun_exact_acc'] - summary['cc_exact_acc'])*100:+.2f}%"],
        ["3-Class Directional Accuracy", f"{summary['cc_dir_acc']*100:.2f}%", f"{summary['rerun_dir_acc']*100:.2f}%", f"{(summary['rerun_dir_acc'] - summary['cc_dir_acc'])*100:+.2f}%"],
        ["5-Class Macro F1", f"{summary['cc_macro_f1']*100:.2f}%", f"{summary['rerun_macro_f1']*100:.2f}%", f"{(summary['rerun_macro_f1'] - summary['cc_macro_f1'])*100:+.2f}%"],
        ["Pathogenic F1", f"{summary['cc_per_class']['Pathogenic']['f1']*100:.2f}%", f"{summary['rerun_per_class']['Pathogenic']['f1']*100:.2f}%", f"{(summary['rerun_per_class']['Pathogenic']['f1'] - summary['cc_per_class']['Pathogenic']['f1'])*100:+.2f}%"],
        ["Likely Pathogenic F1", f"{summary['cc_per_class']['Likely Pathogenic']['f1']*100:.2f}%", f"{summary['rerun_per_class']['Likely Pathogenic']['f1']*100:.2f}%", f"{(summary['rerun_per_class']['Likely Pathogenic']['f1'] - summary['cc_per_class']['Likely Pathogenic']['f1'])*100:+.2f}%"],
        ["Uncertain Significance (VUS) F1", f"{summary['cc_per_class']['Uncertain Significance']['f1']*100:.2f}%", f"{summary['rerun_per_class']['Uncertain Significance']['f1']*100:.2f}%", f"{(summary['rerun_per_class']['Uncertain Significance']['f1'] - summary['cc_per_class']['Uncertain Significance']['f1'])*100:+.2f}%"],
        ["Likely Benign F1", f"{summary['cc_per_class']['Likely Benign']['f1']*100:.2f}%", f"{summary['rerun_per_class']['Likely Benign']['f1']*100:.2f}%", f"{(summary['rerun_per_class']['Likely Benign']['f1'] - summary['cc_per_class']['Likely Benign']['f1'])*100:+.2f}%"],
        ["Benign F1", f"{summary['cc_per_class']['Benign']['f1']*100:.2f}%", f"{summary['rerun_per_class']['Benign']['f1']*100:.2f}%", f"{(summary['rerun_per_class']['Benign']['f1'] - summary['cc_per_class']['Benign']['f1'])*100:+.2f}%"],
        ["Directional: Pathogenic F1", f"{cc_p_f1:.2f}%", f"{rr_p_f1:.2f}%", f"{rr_p_f1 - cc_p_f1:+.2f}%"],
        ["Directional: VUS F1", f"{cc_v_f1:.2f}%", f"{rr_v_f1:.2f}%", f"{rr_v_f1 - cc_v_f1:+.2f}%"],
        ["Directional: Benign F1", f"{cc_b_f1:.2f}%", f"{rr_b_f1:.2f}%", f"{rr_b_f1 - cc_b_f1:+.2f}%"],
    ]

    header_y = 0.94
    ax.text(0.02, header_y, "Claude Haiku 5.5 Benchmark Comparison Scorecard", fontsize=15, fontweight='bold', color='#111827')
    ax.text(0.02, header_y - 0.04, "AIVA API Automated Reasoning Pipeline vs Claude-Code Manual Prompts (n=8,387 variants)",
            fontsize=10, color='#6B7280')

    cols = [0.02, 0.46, 0.66, 0.84]
    y_start = 0.83
    row_h = 0.052

    ax.fill_between([0.01, 0.99], y_start, y_start + row_h, color="#F3F4F6")
    ax.text(cols[0], y_start + 0.018, "Evaluation Dimension", fontweight='bold', fontsize=10.5, color='#1F2937')
    ax.text(cols[1], y_start + 0.018, "Claude-Code Haiku", fontweight='bold', fontsize=10.5, color='#D97706')
    ax.text(cols[2], y_start + 0.018, "AIVA Haiku Re-run", fontweight='bold', fontsize=10.5, color='#2563EB')
    ax.text(cols[3], y_start + 0.018, "Delta", fontweight='bold', fontsize=10.5, color='#1F2937')

    cur_y = y_start
    for i, r in enumerate(table_data[2:]):
        cur_y -= row_h
        bg_col = "#FAFAFA" if i % 2 == 1 else "#FFFFFF"
        ax.fill_between([0.01, 0.99], cur_y, cur_y + row_h, color=bg_col)
        ax.text(cols[0], cur_y + 0.016, r[0], fontsize=9.5, fontweight='bold' if "Accuracy" in r[0] or "Macro" in r[0] else 'normal', color='#111827')
        ax.text(cols[1], cur_y + 0.016, r[1], fontsize=9.5, color='#374151')
        ax.text(cols[2], cur_y + 0.016, r[2], fontsize=9.5, fontweight='bold', color='#1D4ED8')

        delta_val = float(r[3].replace("%", "").replace("+", ""))
        d_color = DELTA_POS if delta_val >= 0 else DELTA_NEG
        ax.text(cols[3], cur_y + 0.016, r[3], fontsize=9.5, fontweight='bold', color=d_color)

    ax.text(0.02, cur_y - 0.04,
            "Evaluation source: ClinGen Expert Panel Curated Benchmark (eRepo) dataset, n=8,387 variants.\n"
            "Claude-Code Haiku: direct prompt classification via Claude code CLI.\n"
            "AIVA Haiku Re-run: automated multi-step ACMG guideline reasoning and criteria evaluation pipeline.",
            fontsize=8, color='#6B7280', fontstyle='italic')

    plt.tight_layout()
    plt.savefig(output_dir / "figure6_haiku_scorecard_comparison.png", bbox_inches='tight')
    plt.savefig(output_dir / "figure6_haiku_scorecard_comparison.pdf", bbox_inches='tight')
    plt.close()
    print("Saved Haiku Comparison Scorecard.")


if __name__ == "__main__":
    df, cat_df, summary, output_dir = compute_metrics()
    plot_all_figures(df, cat_df, summary, output_dir)
    print("\nAll figures generated successfully in:", output_dir)
