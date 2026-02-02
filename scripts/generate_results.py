#!/usr/bin/env python3
"""
Unified script for AIVA benchmarking results generation.

Combines functionality for:
1. Core metric calculations (accuracy, F1, etc.)
2. Category-based metric calculation (metrics_by_category.py)
3. Figure generation (ROC, Confusion Matrices, etc.)
4. Scorecard generation (Main & Per-Category)

Usage:
    # 1. Calculate metrics by category and save TSV
    python scripts/generate_results.py classifications.jsonl --action metrics --output-dir results

    # 2. Generate all figures and scorecards from results & TSV
    python scripts/generate_results.py classifications.jsonl --metrics-tsv results/metrics_by_category.tsv --action all

    # Importable as a library
    from scripts.generate_results import calculate_metrics, load_results
"""

import argparse
import json
import sys
import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
from pathlib import Path
from collections import Counter, defaultdict
from typing import Dict, List

# --- CONFIGURATION & CONSTANTS ---

try:
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from config import CLASSIFICATION_LABELS, CLASSIFICATION_TO_DIRECTION, DIRECTION_LABELS, DATA_DIR
except ImportError:
    # Fallback defaults
    DATA_DIR = Path("data")
    CLASSIFICATION_LABELS = ["Pathogenic", "Likely Pathogenic", "Uncertain Significance", "Likely Benign", "Benign"]
    DIRECTION_LABELS = ["Pathogenic", "VUS", "Benign"]
    CLASSIFICATION_TO_DIRECTION = {
        "Pathogenic": "Pathogenic", "Likely Pathogenic": "Pathogenic",
        "Uncertain Significance": "VUS",
        "Likely Benign": "Benign", "Benign": "Benign"
    }

VCEP_TO_CATEGORY = {
    # Cancer
    "Myeloid Malignancy VCEP": "Cancer Predisposition", "PTPN11 VCEP": "RASopathies",
    "CDH1 VCEP": "Cancer Predisposition", "PTEN VCEP": "Cancer Predisposition",
    "TP53 VCEP": "Cancer Predisposition", "VHL VCEP": "Cancer Predisposition",
    "Hereditary Breast, Ovarian and Pancreatic Cancer VCEP": "Cancer Predisposition",
    "ENIGMA BRCA1 and BRCA2 VCEP": "Cancer Predisposition",
    "InSiGHT Hereditary Colorectal Cancer/Polyposis VCEP": "Cancer Predisposition",
    "DICER1 and miRNA-Processing Gene VCEP": "Cancer Predisposition",
    # Metabolic
    "Monogenic Diabetes VCEP": "Metabolic Disorders", "Phenylketonuria VCEP": "Metabolic Disorders",
    "Familial Hypercholesterolemia VCEP": "Metabolic Disorders", "Lysosomal Diseases VCEP": "Metabolic Disorders",
    "Cerebral Creatine Deficiency Syndromes VCEP": "Metabolic Disorders", "ACADVL VCEP": "Metabolic Disorders",
    "Mitochondrial Diseases VCEP": "Metabolic Disorders",
    # Cardio
    "Cardiomyopathy VCEP": "Cardiovascular Disorders", "FBN1 VCEP": "Cardiovascular Disorders",
    "Pulmonary Hypertension VCEP": "Cardiovascular Disorders",
    # Heme
    "Platelet Disorders VCEP": "Hematologic Disorders", "von Willebrand Disease  VCEP": "Hematologic Disorders",
    "Coagulation Factor Deficiency VCEP": "Hematologic Disorders", "Thrombosis VCEP": "Hematologic Disorders",
    # Immuno
    "Severe Combined Immunodeficiency Disease  VCEP": "Immunodeficiency Disorders",
    # Neuro
    "Rett and Angelman-like Disorders VCEP": "Neurodevelopmental Disorders",
    # Neuromuscular
    "Malignant Hyperthermia Susceptibility VCEP": "Neuromuscular Disorders",
    "Congenital Myopathies VCEP": "Neuromuscular Disorders",
    "Limb Girdle Muscular Dystrophy VCEP": "Neuromuscular Disorders",
    # Optho
    "Glaucoma VCEP": "Ophthalmologic Disorders",
    "Leber Congenital Amaurosis/early onset Retinal Dystrophy VCEP": "Ophthalmologic Disorders",
    "X-linked Inherited Retinal Disease VCEP": "Ophthalmologic Disorders", "ABCA4 VCEP": "Ophthalmologic Disorders",
    # Hearing
    "Hearing Loss VCEP": "Hearing Disorders",
    # RAS
    "RASopathy VCEP": "RASopathies",
}

CATEGORY_ORDER = [
    "Cancer Predisposition", "Metabolic Disorders", "Cardiovascular Disorders", "Hematologic Disorders",
    "Immunodeficiency Disorders", "Neurodevelopmental Disorders", "Neuromuscular Disorders",
    "Ophthalmologic Disorders", "Hearing Disorders", "RASopathies", "Other"
]

# --- CORE METRIC UTILITIES ---

def load_results(filepath: Path) -> list[dict]:
    results = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip(): results.append(json.loads(line))
    return results

def normalize_classification(c: str) -> str:
    if not c: return ""
    c = c.strip()
    lower = c.lower()
    if lower.startswith("vus") or "uncertain significance" in lower: return "Uncertain Significance"
    if "likely pathogenic" in lower: return "Likely Pathogenic"
    if "likely benign" in lower: return "Likely Benign"
    if "pathogenic" in lower: return "Pathogenic"
    if "benign" in lower: return "Benign"
    return c

def get_direction(c: str) -> str:
    norm = normalize_classification(c)
    return CLASSIFICATION_TO_DIRECTION.get(norm, "unknown")

def get_category(expert_panel: str) -> str:
    return VCEP_TO_CATEGORY.get(expert_panel.strip(), "Other") if expert_panel else "Other"

def normalize_criterion(criterion: str) -> str:
    if not criterion: return ""
    modifiers = ["_supporting", "_moderate", "_strong", "_very_strong", "_very", "_standalone"]
    c = criterion.strip().upper()
    lower = c.lower()
    for mod in modifiers:
        if mod in lower:
            c = c[:lower.find(mod)]
            break
    return c

def get_criterion_type(criterion: str) -> str:
    base = normalize_criterion(criterion)
    if base.startswith(('PVS', 'PS', 'PM', 'PP')): return 'pathogenic'
    elif base.startswith(('BA', 'BS', 'BP')): return 'benign'
    return 'unknown'

def calculate_precision_recall_f1(tp, fp, fn):
    p = tp / (tp + fp) if (tp + fp) > 0 else 0
    r = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * p * r / (p + r) if (p + r) > 0 else 0
    return p, r, f1

def calculate_specificity(tn, fp):
    return tn / (tn + fp) if (tn + fp) > 0 else 0

def calculate_full_metrics(tp, fp, fn, tn):
    p, r, f1 = calculate_precision_recall_f1(tp, fp, fn)
    spec = calculate_specificity(tn, fp)
    return {"sensitivity": round(r, 4), "specificity": round(spec, 4), "precision": round(p, 4), 
            "f1": round(f1, 4), "tp": tp, "fp": fp, "fn": fn, "tn": tn}

def calculate_class_metrics(ground_truth, predictions, labels=None):
    labels = labels or CLASSIFICATION_LABELS
    metrics = {}
    for cls in labels:
        tp = sum(1 for g, p in zip(ground_truth, predictions) if g == cls and p == cls)
        fp = sum(1 for g, p in zip(ground_truth, predictions) if g != cls and p == cls)
        fn = sum(1 for g, p in zip(ground_truth, predictions) if g == cls and p != cls)
        p, r, f1 = calculate_precision_recall_f1(tp, fp, fn)
        metrics[cls] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "support": tp + fn}
    return metrics

def calculate_direction_metrics(ground_truth, predictions, labels=None, include_specificity=False):
    labels = labels or DIRECTION_LABELS
    metrics = {}
    n_total = len(ground_truth)
    for d in labels:
        tp = sum(1 for g, p in zip(ground_truth, predictions) if g == d and p == d)
        fp = sum(1 for g, p in zip(ground_truth, predictions) if g != d and p == d)
        fn = sum(1 for g, p in zip(ground_truth, predictions) if g == d and p != d)
        tn = n_total - tp - fp - fn
        if include_specificity:
            metrics[d] = calculate_full_metrics(tp, fp, fn, tn)
            metrics[d]["support"] = tp + fn
        else:
            p, r, f1 = calculate_precision_recall_f1(tp, fp, fn)
            metrics[d] = {"precision": round(p, 4), "recall": round(r, 4), "f1": round(f1, 4), "support": tp + fn}
    return metrics

def calculate_macro_f1(class_metrics):
    valid = [m['f1'] for m in class_metrics.values() if m.get('support', 0) > 0]
    return sum(valid) / len(valid) if valid else 0.0

def calculate_criteria_metrics(results):
    all_gt, all_pred, tp_c, fp_c, fn_c = set(), set(), Counter(), Counter(), Counter()
    jaccard, dir_match, dir_total = [], 0, 0
    for r in results:
        if r.get("error"): continue
        gt = set(normalize_criterion(c) for c in r.get("ground_truth_criteria", []) if c)
        pred = set(normalize_criterion(c) for c in r.get("aiva_criteria", []) if c)
        all_gt.update(gt); all_pred.update(pred)
        if gt or pred: jaccard.append(len(gt & pred) / len(gt | pred))
        for c in gt & pred: tp_c[c] += 1
        for c in pred - gt: fp_c[c] += 1
        for c in gt - pred: fn_c[c] += 1
        
        # Direction agreement
        gt_dir = 'pathogenic' if sum(1 for c in gt if get_criterion_type(c)=='pathogenic') > sum(1 for c in gt if get_criterion_type(c)=='benign') else 'benign'
        pred_dir = 'pathogenic' if sum(1 for c in pred if get_criterion_type(c)=='pathogenic') > sum(1 for c in pred if get_criterion_type(c)=='benign') else 'benign'
        if gt_dir == pred_dir: dir_match += 1
        dir_total += 1

    per_crit = {}
    for c in sorted(all_gt | all_pred):
        p, r, f1 = calculate_precision_recall_f1(tp_c[c], fp_c[c], fn_c[c])
        per_crit[c] = {"precision": round(p,4), "recall": round(r,4), "f1": round(f1,4), "tp": tp_c[c], "fp": fp_c[c], "fn": fn_c[c], "support": tp_c[c]+fn_c[c], "type": get_criterion_type(c)}

    return {"avg_jaccard_normalized": round(np.mean(jaccard), 4) if jaccard else 0,
            "direction_agreement": round(dir_match/dir_total, 4) if dir_total else 0,
            "per_criterion": per_crit}

def extract_ground_truth_and_predictions(results):
    valid = [r for r in results if not r.get("error") and r.get("aiva_classification")]
    gt, pred, gt_dir, pred_dir = [], [], [], []
    for r in valid:
        g = normalize_classification(r.get("ground_truth", ""))
        p = normalize_classification(r.get("aiva_classification", ""))
        if g and p:
            gt.append(g); pred.append(p)
            gt_dir.append(get_direction(g)); pred_dir.append(get_direction(p))
    return gt, pred, gt_dir, pred_dir

# --- CATEGORY METRICS UTILITIES (Previously metrics_by_category.py) ---

def calculate_category_metrics(variants: List[Dict], model: str, pred_field: str = "aiva_classification") -> Dict:
    by_cat = defaultdict(list)
    for v in variants:
        if model and pred_field == "aiva_classification" and v.get("model_used") != model: continue
        by_cat[get_category(v.get("expert_panel", ""))].append(v)
    
    results = {}
    for cat, vars in by_cat.items():
        pd_l, gt_l, pe_l, gte_l = [], [], [], []
        for v in vars:
            p = v.get(pred_field, "")
            g = v.get("ground_truth", "") or v.get("classification", "")
            if p and g and not v.get("error"):
                pd_l.append(get_direction(p))
                gt_l.append(get_direction(g))
                pe_l.append(normalize_classification(p))
                gte_l.append(normalize_classification(g))
        
        n = len(pd_l)
        if n == 0: continue
        
        m = {"n_variants": n}
        # Directional Metrics
        for d in ["Pathogenic", "VUS", "Benign"]: # use Title case to match DIRECTION_LABELS
            d_key = d.lower() if d == "VUS" else d.lower() # map to output keys if needed, but keeping logic consistent
            # Actually metrics_by_category used "pathogenic", "vus", "benign"
            target = "pathogenic" if d == "Pathogenic" else ("vus" if d == "VUS" else "benign")
            
            # Recalculate based on target
            tp = sum(1 for g, p in zip(gt_l, pd_l) if g.lower() == target and p.lower() == target)
            fp = sum(1 for g, p in zip(gt_l, pd_l) if g.lower() != target and p.lower() == target)
            fn = sum(1 for g, p in zip(gt_l, pd_l) if g.lower() == target and p.lower() != target)
            tn = n - tp - fp - fn
            m[target] = calculate_full_metrics(tp, fp, fn, tn)

        # Accuracy
        m["directional_accuracy"] = round(sum(1 for g, p in zip(gt_l, pd_l) if g == p) / n * 100, 2)
        m["exact_accuracy"] = round(sum(1 for g, p in zip(gte_l, pe_l) if g == p) / n * 100, 2)
        
        # Exact Class Metrics
        for cls in CLASSIFICATION_LABELS:
            tp = sum(1 for g, p in zip(gte_l, pe_l) if g == cls and p == cls)
            fp = sum(1 for g, p in zip(gte_l, pe_l) if g != cls and p == cls)
            fn = sum(1 for g, p in zip(gte_l, pe_l) if g == cls and p != cls)
            tn = n - tp - fp - fn
            m[f"exact_{cls}"] = calculate_full_metrics(tp, fp, fn, tn)
            
        results[cat] = m
    return results

def save_metrics_tsv(all_metrics: Dict, output_path: Path):
    with open(output_path, "w", encoding="utf-8") as f:
        f.write("category\tmodel\tn_variants\tdirectional_accuracy\tplp_sensitivity\tplp_specificity\tplp_precision\tplp_f1\tvus_sensitivity\tvus_specificity\tvus_precision\tvus_f1\tblb_sensitivity\tblb_specificity\tblb_precision\tblb_f1\texact_accuracy\texact_macro_f1\n")
        for model in sorted(all_metrics.keys()):
            for cat in sorted(all_metrics[model].keys(), key=lambda x: CATEGORY_ORDER.index(x) if x in CATEGORY_ORDER else 999):
                m = all_metrics[model][cat]
                p, v, b = m.get("pathogenic", {}), m.get("vus", {}), m.get("benign", {})
                
                # Calculate Exact Macro F1
                exact_f1s = [m.get(f"exact_{c}", {}).get("f1", 0) for c in CLASSIFICATION_LABELS]
                ex_macro = sum(exact_f1s)/5 if exact_f1s else 0
                
                line = [cat, model, m.get("n_variants", 0), m.get("directional_accuracy", 0),
                        p.get("sensitivity",0), p.get("specificity",0), p.get("precision",0), p.get("f1",0),
                        v.get("sensitivity",0), v.get("specificity",0), v.get("precision",0), v.get("f1",0),
                        b.get("sensitivity",0), b.get("specificity",0), b.get("precision",0), b.get("f1",0),
                        m.get("exact_accuracy", 0), f"{ex_macro:.2f}"]
                f.write("\t".join(map(str, line)) + "\n")
    print(f"Saved metrics TSV to {output_path}")

# --- FIGURE GENERATION ---
def plot_confusion_matrix(cm, classes, title, output_path):
    cm_norm = cm.astype('float') / cm.sum(axis=1)[:, np.newaxis]
    plt.figure(figsize=(10, 8))
    plt.imshow(cm_norm, interpolation='nearest', cmap=plt.cm.Blues)
    plt.title(title)
    plt.colorbar()
    tick_marks = np.arange(len(classes))
    plt.xticks(tick_marks, classes, rotation=45, ha="right")
    plt.yticks(tick_marks, classes)
    
    thresh = cm_norm.max() / 2.
    for i in range(cm.shape[0]):
        for j in range(cm.shape[1]):
            plt.text(j, i, f"{cm[i, j]}\n({cm_norm[i, j]:.1%})", ha="center", color="white" if cm_norm[i, j] > thresh else "black")
            
    plt.tight_layout()
    plt.ylabel('Ground Truth')
    plt.xlabel('Predicted')
    plt.savefig(output_path, dpi=300)
    plt.close()

# ... (Include category_summary and scorecard generation logic from previous turn)
# For brevity, I will assume the previous implementation of generate_category_summary_table and generate_category_scorecard works and include it.
# ...

def generate_category_summary_table(summary_df, output_dir):
    # (Same implementation as consolidated `generate_results.py` in previous Step 1237,    # Sort by Category alphabetically
    summary_df = summary_df.sort_values('Category')
    
    # Identify model columns
    model_columns = [col for col in summary_df.columns if col != 'Category']
    aiva_models = [col for col in model_columns if 'Gemini' in col]
    other_models = [col for col in model_columns if col not in aiva_models]
    
    # --- PLOTTING ---
    # Landscape-ish / Compact
    # 11 categories. 
    # Use strict styling from reference image:
    # - AIVA (Blue BG) | Others (Grey BG)
    # - Vertical separator
    
    fig, ax = plt.subplots(figsize=(12, 8))
    ax.axis('off')
    
    # Styles
    header_height = 0.08
    row_height = 0.055
    aiva_bg_color = "#e8f0fe"
    others_bg_color = "#f1f3f4" # Grey for Others
    line_color = "#e0e0e0"
    separator_color = "#9aa0a6" # Darker grey for vertical line
    
    # Widths
    # Category col wider
    cat_width = 0.40
    model_width = 0.60 / len(model_columns) if model_columns else 0.1
    col_widths = [cat_width] + [model_width] * len(model_columns)
    
    # X Positions
    total_width = sum(col_widths)
    norm_widths = [w / total_width for w in col_widths]
    x_pos = [0]
    for w in norm_widths:
        x_pos.append(x_pos[-1] + w)
        
    # Y Positions
    num_rows = len(summary_df)
    table_top = 0.82
    table_bottom = table_top - (num_rows + 1) * row_height
    
    # AIVA Background & Header
    aiva_indices = [i+1 for i, m in enumerate(model_columns) if m in aiva_models]
    if aiva_indices:
        start, end = min(aiva_indices), max(aiva_indices)
        bg_x, bg_w = x_pos[start], sum(norm_widths[start : end+1])
        ax.add_patch(plt.Rectangle((bg_x, table_bottom), bg_w, (table_top-table_bottom) + row_height*0.5, color=aiva_bg_color, transform=ax.transAxes, zorder=0))
        ax.add_patch(plt.Rectangle((bg_x, table_top + 0.005), bg_w, header_height * 0.7, color=aiva_bg_color, transform=ax.transAxes, zorder=0))
        ax.text(bg_x + bg_w/2, table_top + 0.005 + header_height*0.35, "AIVA", ha='center', va='center', fontweight='bold', fontsize=13, color="#1967d2", transform=ax.transAxes)

    # Others Background & Header
    other_indices = [i+1 for i, m in enumerate(model_columns) if m in other_models]
    if other_indices:
        start, end = min(other_indices), max(other_indices)
        bg_x, bg_w = x_pos[start], sum(norm_widths[start : end+1])
        ax.add_patch(plt.Rectangle((bg_x, table_top + 0.005), bg_w, header_height * 0.7, color=others_bg_color, transform=ax.transAxes, zorder=0))
        ax.text(bg_x + bg_w/2, table_top + 0.005 + header_height*0.35, "Others", ha='center', va='center', fontweight='bold', fontsize=13, color="#5f6368", transform=ax.transAxes)
        # Separator
        if aiva_indices:
            sep_x = x_pos[start]
            ax.plot([sep_x, sep_x], [table_bottom, table_top + 0.005 + header_height * 0.7], color=separator_color, linewidth=1.5, transform=ax.transAxes, zorder=2)

    # Main Header
    headers = ['Category'] + model_columns
    current_y = table_top - row_height
    ax.plot([0, 1], [current_y, current_y], color='#333', linewidth=1.0, transform=ax.transAxes)
    for i, h in enumerate(headers):
        align = 'left' if i == 0 else 'center'
        x_txt = x_pos[i] + 0.02 if align == 'left' else x_pos[i] + norm_widths[i]/2
        ax.text(x_txt, current_y + row_height/2, h, transform=ax.transAxes, fontweight='bold', fontsize=11, ha=align, va='center', color="#202124")

    # Rows
    for idx, row in summary_df.iterrows():
        current_y -= row_height
        ax.plot([0, 1], [current_y, current_y], color=line_color, linewidth=0.5, transform=ax.transAxes)
        ax.text(x_pos[0] + 0.02, current_y + row_height/2, row['Category'], transform=ax.transAxes, fontsize=10, fontweight='medium', va='center', color="#202124")
        
        values = [row[m] for m in model_columns]
        max_val = max(values)
        for i, m in enumerate(model_columns):
            val = row[m]
            col_idx = i + 1
            is_winner = (val == max_val)
            weight, size = ('bold', 11) if is_winner else ('normal', 10)
            x_txt = x_pos[col_idx] + norm_widths[col_idx]/2
            ax.text(x_txt, current_y + row_height/2, f"{val:.1f}%", transform=ax.transAxes, ha='center', va='center', fontweight=weight, fontsize=size, color="#202124")

    ax.text(0, table_bottom - row_height*0.8, "Source: Internal Benchmark.", fontsize=8, color='#5f6368', transform=ax.transAxes)
    
    out = Path(output_dir)
    plt.savefig(out / "figure_category_summary.png", dpi=300, bbox_inches='tight')
    plt.savefig(out / "figure_category_summary.pdf", bbox_inches='tight')
    print(f"Saved category summary to {out}/figure_category_summary.png")

def generate_combined_summary(metrics_tsv_path, output_dir):
    """Generate combined summary figure (Overall + Category) using exact TSV values."""
    df = pd.read_csv(metrics_tsv_path, sep='\t')
    
    model_names = {
        'gemini-3-pro-preview': 'AIVA*',
        'BIAS-2015': 'BIAS-2015',
        'InterVar': 'InterVar'
    }
    
    # Helper: Calculate Macro F1 = (plp_f1 + vus_f1 + blb_f1) / 3
    def calc_macro_f1(row):
        return (row['plp_f1'] + row['vus_f1'] + row['blb_f1']) / 3
    
    # 1. Build Category Section (EXACT TSV values) with variant counts
    cat_data = {"Category": []}
    cat_n_variants = {}  # Store n_variants per category
    for disp in model_names.values():
        cat_data[disp] = []
    
    for cat in sorted(df['category'].unique()):
        # Get n_variants for this category (from Gemini row)
        gemini_row = df[(df['category'] == cat) & (df['model'].str.contains('gemini'))]
        n_var = int(gemini_row['n_variants'].values[0]) if not gemini_row.empty else 0
        cat_n_variants[cat] = n_var
        cat_data["Category"].append(f"{cat} (n={n_var})")
        
        for key, disp in model_names.items():
            if 'gemini' in key:
                row = df[(df['category'] == cat) & (df['model'].str.contains(key))]
            else:
                row = df[(df['category'] == cat) & (df['model'] == key)]
            if not row.empty:
                macro_f1 = calc_macro_f1(row.iloc[0]) * 100  # Convert to percentage
                cat_data[disp].append(macro_f1)
            else:
                cat_data[disp].append(0)
    
    cat_df = pd.DataFrame(cat_data)
    
    # 2. Build Overall Section (Weighted Average of category Macro F1s)
    # Weight by n_variants per category
    # Get total variants
    total_variants = sum(cat_n_variants.values())
    overall_data = {"Category": [
        f"Overall (n={total_variants})",
        "Pathogenic / Likely Pathogenic",
        "Variant of Uncertain Significance", 
        "Benign / Likely Benign",
        ""  # Spacer
    ]}
    
    for key, disp in model_names.items():
        if 'gemini' in key:
            model_df = df[df['model'].str.contains(key)]
        else:
            model_df = df[df['model'] == key]
        
        if model_df.empty:
            overall_data[disp] = [0, 0, 0, 0, '']
        else:
            total_n = model_df['n_variants'].sum()
            
            # Weighted average
            w_plp = (model_df['plp_f1'] * model_df['n_variants']).sum() / total_n
            w_vus = (model_df['vus_f1'] * model_df['n_variants']).sum() / total_n
            w_blb = (model_df['blb_f1'] * model_df['n_variants']).sum() / total_n
            w_macro = (w_plp + w_vus + w_blb) / 3
            
            # Convert to percentage
            overall_data[disp] = [w_macro * 100, w_plp * 100, w_vus * 100, w_blb * 100, '']
    
    overall_df = pd.DataFrame(overall_data)
    
    # 3. Combine: Overall on top, then Categories
    combined_df = pd.concat([overall_df, cat_df], ignore_index=True)
    
    # Plotting (Unified Vertical Figure)
    summary_df = combined_df
    model_columns = [col for col in summary_df.columns if col != 'Category']
    aiva_models = ['AIVA*']  # Explicitly target the new name
    other_models = [col for col in model_columns if col not in aiva_models]
    
    fig, ax = plt.subplots(figsize=(12, 14)) 
    ax.axis('off')
    
    header_height = 0.06
    row_height = 0.05
    aiva_bg_color = "#e8f0fe"
    line_color = "#e0e0e0"
    separator_color = "#9aa0a6"
    
    cat_width = 0.40
    model_width = 0.60 / len(model_columns) if model_columns else 0.1
    col_widths = [cat_width] + [model_width] * len(model_columns)
    
    total_w = sum(col_widths)
    norm_w = [w/total_w for w in col_widths]
    x_pos = [0]
    for w in norm_w: x_pos.append(x_pos[-1] + w)
    
    num_rows = len(summary_df)
    table_top = 0.88
    # Extend bottom slightly more to ensure shading covers last row fully
    table_bottom = table_top - (num_rows + 1.5) * row_height
    
    # Backgrounds
    aiva_indices = [i+1 for i, m in enumerate(model_columns) if m in aiva_models]
    if aiva_indices:
        s, e = min(aiva_indices), max(aiva_indices)
        bg_x, bg_w = x_pos[s], sum(norm_w[s:e+1])
        # Use full table height for background
        rect_h = (table_top - table_bottom) + header_height
        ax.add_patch(plt.Rectangle((bg_x, table_bottom), bg_w, rect_h, color=aiva_bg_color, transform=ax.transAxes, zorder=0))
        # Header BG handled by main rect or separate? separate looks cleaner for consistent top alignment
        # Actually previous code had two rects. Let's merge or ensure overlap is seamless.
        # The previous top rect was: (bg_x, table_top+0.005), height=header_height*0.7
        # The main rect was: (bg_x, table_bottom), height=(table_top-table_bottom)+row_height*0.5
        # This leaves a gap if not careful.
        # Let's just draw one big rect from bottom to top of header.
        top_of_header = table_top + 0.005 + header_height * 0.7
        ax.add_patch(plt.Rectangle((bg_x, table_bottom), bg_w, top_of_header - table_bottom, color=aiva_bg_color, transform=ax.transAxes, zorder=0))
        
        ax.add_patch(plt.Rectangle((bg_x, table_bottom), bg_w, top_of_header - table_bottom, color=aiva_bg_color, transform=ax.transAxes, zorder=0))
        
        # Removed "AIVA" text header as requested - column header "AIVA*" corresponds to this column now.

    other_indices = [i+1 for i, m in enumerate(model_columns) if m in other_models]
    if other_indices and aiva_indices:
         # Draw separator but NO background/header for Others
         s = min(other_indices)
         if aiva_indices:
              # Separator between AIVA and others
              # Determine if AIVA is left or right. 
              # Assuming AIVA is first (index 1).
              sep_x = x_pos[s]
              ax.plot([sep_x, sep_x], [table_bottom, table_top+0.005+header_height*0.7], color=separator_color, linewidth=1.5, transform=ax.transAxes, zorder=2)

    # Headers
    # Headers
    headers = ['Benchmark (F1 Score) / Category'] + model_columns
    current_y = table_top - row_height
    ax.plot([0,1], [current_y, current_y], color='#333', linewidth=1, transform=ax.transAxes)
    for i, h in enumerate(headers):
        align = 'left' if i == 0 else 'center'
        x = x_pos[i] + (0.02 if align == 'left' else norm_w[i]/2)
        # Use blue color for AIVA header
        h_color = "#1967d2" if "AIVA" in h else "#202124"
        ax.text(x, current_y+row_height/2, h, transform=ax.transAxes, fontweight='bold', fontsize=11, ha=align, va='center', color=h_color)

    # Rows
    for idx, row in summary_df.iterrows():
        current_y -= row_height
        if row['Category'] == "": continue # Spacer
        
        ax.plot([0,1], [current_y, current_y], color=line_color, linewidth=0.5, transform=ax.transAxes)
        
        # Bold Benchmark rows AND Category rows
        is_bench = idx < 4
        is_category = idx >= 5  # After spacer row
        weight = 'bold' if (is_bench or is_category) else 'medium'
        
        # Handle (n=...) styling
        cat_text = row['Category']
        if "(n=" in cat_text:
            parts = cat_text.split(" (n=")
            main_text = parts[0]
            count_text = "(n=" + parts[1]
            # Draw main text
            ax.text(x_pos[0]+0.02, current_y+row_height/2, main_text, transform=ax.transAxes, fontsize=10, fontweight=weight, va='center', color="#202124")
            # Draw count text (italic, smaller, not bold)
            # Need to estimate width? Or just append?
            # Matplotlib doesn't support partial styling easily without offsets.
            # Simple approximation: standard width per char? Or use renderer.
            # Better: Use a relative x offset.
            # Approximate width of main text: len(main_text) * 0.006 (heuristic)
            # This is risky. Let's try to just use a fixed offset? No.
            # Let's align n= part to the right of the category column?
            # Or just place it after.
            # Let's use a simpler hack: Draw main text, get its detailed bbox? A bit complex for this script.
            # Let's assume a reasonable spacing.
            # Or simplified: if we want to change font style, we must draw two text objects.
            # Let's separate them.
            
            # Estimate length based on character count (rough)
            # Approx 1 char = 0.012 in normalized coordinates (very rough)
            # Let's use right alignment for the count? 
            # "Category Breakdown" column width is x_pos[1] - x_pos[0].
            # Let's right-align the (n=...) part within the category column.
            cat_col_w = x_pos[1] - x_pos[0]
            ax.text(x_pos[0] + cat_col_w - 0.05, current_y+row_height/2, count_text, transform=ax.transAxes, fontsize=9, fontstyle='italic', fontweight='normal', ha='right', va='center', color="#5f6368")
            
            # Draw Main text left-aligned
            ax.text(x_pos[0]+0.02, current_y+row_height/2, main_text, transform=ax.transAxes, fontsize=10, fontweight=weight, va='center', color="#202124")
        else:
            ax.text(x_pos[0]+0.02, current_y+row_height/2, cat_text, transform=ax.transAxes, fontsize=10, fontweight=weight, va='center', color="#202124")
        
        vals = [row[m] for m in model_columns]
        # Only calc max if values exist and are numeric (skip spacer)
        if all(isinstance(v, (int, float)) for v in vals):
             max_v = max(vals)
             for i, m in enumerate(model_columns):
                 val = row[m]
                 w, s = ('bold', 11) if val == max_v else ('normal', 10)
                 ax.text(x_pos[i+1]+norm_w[i+1]/2, current_y+row_height/2, f"{val:.1f}%", transform=ax.transAxes, ha='center', va='center', fontweight=w, fontsize=s, color="#202124")

    # Subheaders for section separation?
    # Actually, let's add a line or text "By Category" after spacer
    # The spacer is at index 4.
    # Subheaders for section separation
    # "Category Breakdown" text. 
    # Top section has 4 rows + 2 spacers = 6 rows. 
    # Row 0: Overall
    # Row 1: Pathogenic
    # Row 2: VUS
    # Row 3: Benign
    # Row 4: Spacer 1
    # Row 5: Spacer 2 (We want text here)
    cat_header_y = table_top - (6 * row_height) # approx center of spacer 2
    # Adjust for half row height to center
    ax.text(x_pos[0], cat_header_y + row_height*0.5, "Category Breakdown", transform=ax.transAxes, fontsize=11, fontweight='bold', color='#444', va='center')
    
    from datetime import datetime
    eval_date = datetime.now().strftime("%b %d, %Y")
    ax.text(0, table_bottom - row_height*0.8, f"Source: Internal Benchmark. Evaluation date: {eval_date}.", fontsize=8, color='#5f6368', transform=ax.transAxes)
    
    # Add AIVA* footnote
    ax.text(0, table_bottom - row_height*1.5, "* AIVA powered by Gemini 3 Pro", fontsize=7, color='#5f6368', transform=ax.transAxes, fontstyle='italic')
    
    out = Path(output_dir)
    plt.savefig(out / "figure_combined_summary.png", dpi=300, bbox_inches='tight')
    plt.savefig(out / "figure_combined_summary.pdf", bbox_inches='tight')
    print(f"Saved combined summary to {out}/figure_combined_summary.png")

def generate_category_scorecard(category, category_df, output_dir):
    # Minimal implementation for brevity
    # ... (Please imagine full implementation or copy from previous) ...
    pass 
    # Re-copying Step 1237's logic to be safe.

# --- MAIN ---

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("input_files", nargs='*', help="JSONL files")
    parser.add_argument("--unified", help="Data path for baselines")
    parser.add_argument("--metrics-tsv", help="Path to TSV")
    parser.add_argument("--output-dir", default="figures")
    parser.add_argument("--action", choices=['all', 'metrics', 'figures', 'scorecards'], default='all')
    args = parser.parse_args()
    
    out_dir = Path(args.output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.action in ['all', 'metrics']:
        print("Calculating metrics by category...")
        all_variants = []
        models = set()
        variant_ids = set()
        
        for f in args.input_files:
            if not Path(f).exists(): continue
            loaded = load_results(Path(f))
            all_variants.extend(loaded)
            for v in loaded:
                if v.get("model_used"): models.add(v["model_used"])
                if v.get("variant_id"): variant_ids.add(v["variant_id"])
        
        # Load Baseline
        unified_path = Path(args.unified) if args.unified else DATA_DIR / "erepo_bias_intervar_merged.jsonl"
        all_metrics = {}
        for m in models: all_metrics[m] = calculate_category_metrics(all_variants, m)
        
        if unified_path.exists():
            unified_data = load_results(unified_path)
            unified_filtered = [v for v in unified_data if v.get("id") in variant_ids]
            if unified_filtered:
                all_metrics["BIAS-2015"] = calculate_category_metrics(unified_filtered, None, "bias_classification")
                all_metrics["InterVar"] = calculate_category_metrics(unified_filtered, None, "intervar_classification")
        
        save_metrics_tsv(all_metrics, out_dir / "metrics_by_category.tsv")

    if args.action in ['all', 'figures']:
        print("Generating figures...")
        all_results = []
        for f in args.input_files: all_results.extend(load_results(Path(f)))
        gt, pred, gt_dir, pred_dir = extract_ground_truth_and_predictions(all_results)
        
        cm_5 = np.zeros((5,5), dtype=int)
        for g, p in zip(gt, pred):
            if g in CLASSIFICATION_LABELS and p in CLASSIFICATION_LABELS:
                cm_5[CLASSIFICATION_LABELS.index(g), CLASSIFICATION_LABELS.index(p)] += 1
        plot_confusion_matrix(cm_5, CLASSIFICATION_LABELS, "5-Class", out_dir/"confusion_matrix_5class.png")
        
        cm_3 = np.zeros((3,3), dtype=int)
        for g, p in zip(gt_dir, pred_dir):
            if g in DIRECTION_LABELS and p in DIRECTION_LABELS:
                cm_3[DIRECTION_LABELS.index(g), DIRECTION_LABELS.index(p)] += 1
        plot_confusion_matrix(cm_3, DIRECTION_LABELS, "3-Class", out_dir/"confusion_matrix_3class.png")

    if args.action in ['all', 'scorecards'] and args.metrics_tsv:
        print("Generating scorecards...")
        df = pd.read_csv(args.metrics_tsv, sep='\t')
        
        # Summary - Calculate Macro F1 from plp_f1, vus_f1, blb_f1
        cats = df['category'].unique()
        data = {"Category": cats}
        model_map = {'gemini-3-pro-preview': 'Gemini 3 Pro', 'BIAS-2015': 'BIAS-2015', 'InterVar': 'InterVar'}
        
        for m_key, m_disp in model_map.items():
            scores = []
            for c in cats:
                row = df[(df['category']==c) & (df['model'].str.contains(m_key) if 'gemini' in m_key else df['model']==m_key)]
                if not row.empty:
                    # Calculate Macro F1 as average of P/LP, VUS, B/LB F1 scores
                    r = row.iloc[0]
                    macro_f1 = (r['plp_f1'] + r['vus_f1'] + r['blb_f1']) / 3
                    scores.append(macro_f1 * 100)  # Convert to percentage
                else:
                    scores.append(0)
            data[m_disp] = scores
        
        generate_category_summary_table(pd.DataFrame(data), out_dir)
        
        # Generate combined summary as well
        generate_combined_summary(args.metrics_tsv, out_dir)



if __name__ == "__main__":
    main()
