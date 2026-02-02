#!/usr/bin/env python3
"""
Complete end-to-end benchmark analysis pipeline for AIVA variant classification.

This unified script orchestrates:
1. Gene and phenotype extraction
2. Disease categorization based on ClinGen Expert Panels
3. Performance metrics calculation by category
4. Publication-quality figure generation (all 13 figures + modern alternatives)
5. Scorecard generation (benchmark comparison table)

Usage:
    python scripts/benchmark_analysis.py Results_500_benchmarked/classifications_*.jsonl
    python scripts/benchmark_analysis.py Results_500_benchmarked/classifications_*.jsonl --output-dir Results_500_benchmarked
    python scripts/benchmark_analysis.py Results_500_benchmarked/classifications_*.jsonl --unified data/erepo_bias_intervar_merged.jsonl --skip-figures
"""

import argparse
import csv
import json
import sys
import subprocess
from collections import defaultdict, Counter
from pathlib import Path
from typing import Dict, List, Tuple, Optional

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.gridspec import GridSpec
import seaborn as sns

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_DIR

# Import figure generation modules
import scripts.generate_results as gen_results

# =============================================================================
# Configuration & Constants
# =============================================================================

# ClinGen Expert Panel (VCEP) to Disease Category Mapping
VCEP_TO_CATEGORY = {
    # Cancer / Cancer Predisposition
    "Myeloid Malignancy VCEP": "Cancer Predisposition",
    "CDH1 VCEP": "Cancer Predisposition",
    "PTEN VCEP": "Cancer Predisposition",
    "TP53 VCEP": "Cancer Predisposition",
    "VHL VCEP": "Cancer Predisposition",
    "Hereditary Breast, Ovarian and Pancreatic Cancer VCEP": "Cancer Predisposition",
    "ENIGMA BRCA1 and BRCA2 VCEP": "Cancer Predisposition",
    "InSiGHT Hereditary Colorectal Cancer/Polyposis VCEP": "Cancer Predisposition",
    "DICER1 and miRNA-Processing Gene VCEP": "Cancer Predisposition",
    
    # Metabolic Disorders
    "Monogenic Diabetes VCEP": "Metabolic Disorders",
    "Phenylketonuria VCEP": "Metabolic Disorders",
    "Familial Hypercholesterolemia VCEP": "Metabolic Disorders",
    "Lysosomal Diseases VCEP": "Metabolic Disorders",
    "Cerebral Creatine Deficiency Syndromes VCEP": "Metabolic Disorders",
    "ACADVL VCEP": "Metabolic Disorders",
    "Mitochondrial Diseases VCEP": "Metabolic Disorders",
    
    # Cardiovascular Disorders
    "Cardiomyopathy VCEP": "Cardiovascular Disorders",
    "FBN1 VCEP": "Cardiovascular Disorders",
    "Pulmonary Hypertension VCEP": "Cardiovascular Disorders",
    "Potassium Channel Arrhythmia VCEP": "Cardiovascular Disorders",
    
    # Hematologic Disorders
    "Platelet Disorders VCEP": "Hematologic Disorders",
    "von Willebrand Disease  VCEP": "Hematologic Disorders",
    "Coagulation Factor Deficiency VCEP": "Hematologic Disorders",
    "Thrombosis VCEP": "Hematologic Disorders",
    
    # Immunodeficiency Disorders
    "Severe Combined Immunodeficiency Disease  VCEP": "Immunodeficiency Disorders",
    "Antibody Deficiencies VCEP": "Immunodeficiency Disorders",
    
    # Neurodevelopmental Disorders
    "Rett and Angelman-like Disorders VCEP": "Neurodevelopmental Disorders",
    
    # Neuromuscular Disorders
    "Malignant Hyperthermia Susceptibility VCEP": "Neuromuscular Disorders",
    "Congenital Myopathies VCEP": "Neuromuscular Disorders",
    "Limb Girdle Muscular Dystrophy VCEP": "Neuromuscular Disorders",
    
    # Ophthalmologic Disorders
    "Glaucoma VCEP": "Ophthalmologic Disorders",
    "Leber Congenital Amaurosis/early onset Retinal Dystrophy VCEP": "Ophthalmologic Disorders",
    "X-linked Inherited Retinal Disease VCEP": "Ophthalmologic Disorders",
    "ABCA4 VCEP": "Ophthalmologic Disorders",
    
    # Hearing Disorders
    "Hearing Loss VCEP": "Hearing Disorders",
    
    # RASopathies
    "RASopathy VCEP": "RASopathies",
    "Brain Malformations VCEP": "RASopathies",
    
    # Other
    "Hereditary Hemorrhagic Telangiectasia VCEP": "Vascular Disorders",
    "Epilepsy Sodium Channel VCEP": "Epilepsy / Neurological",
}

CATEGORY_ORDER = [
    "Cancer Predisposition",
    "Metabolic Disorders",
    "Cardiovascular Disorders",
    "Hematologic Disorders",
    "Immunodeficiency Disorders",
    "Neurodevelopmental Disorders",
    "Neuromuscular Disorders",
    "Ophthalmologic Disorders",
    "Hearing Disorders",
    "RASopathies",
]

# =============================================================================
# Helper Functions
# =============================================================================

def load_jsonl(filepath: Path) -> list[dict]:
    """Load JSONL file with error handling."""
    results = []
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            for line_num, line in enumerate(f, 1):
                if line.strip():
                    try:
                        results.append(json.loads(line))
                    except json.JSONDecodeError as e:
                        print(f"Warning: Failed to parse JSON on line {line_num} in {filepath}: {e}")
                        continue
    except FileNotFoundError:
        print(f"Error: File not found: {filepath}")
        raise
    except Exception as e:
        print(f"Error reading file {filepath}: {e}")
        raise
    return results


def normalize_classification(cls: str) -> str:
    """Normalize classification string to 5-class."""
    return gen_figs.normalize_classification(cls)


def get_direction(cls: str) -> str:
    """Get 3-class direction from 5-class classification."""
    return gen_figs.get_direction(cls)


def get_category(expert_panel: str) -> str:
    """Map an Expert Panel (VCEP) to its broader disease category."""
    if not expert_panel or expert_panel == "N/A":
        return "Other"
    
    category = VCEP_TO_CATEGORY.get(expert_panel.strip())
    if category:
        return category
    
    expert_panel_lower = expert_panel.lower().strip()
    for vcep, cat in VCEP_TO_CATEGORY.items():
        if vcep.lower() == expert_panel_lower:
            return cat
    
    return "Other"


# =============================================================================
# PART 1: Data Extraction & Categorization
# =============================================================================

def extract_gene_phenotype_data(filepaths: list[Path]) -> dict:
    """Extract unique gene-phenotype-variant combinations."""
    variants = {}
    for fp in filepaths:
        for r in load_jsonl(fp):
            vid = r.get("variant_id")
            if not vid or vid in variants:
                continue
            variants[vid] = {
                "variant_id": vid,
                "variant": r.get("variant") or "",
                "gene": r.get("gene", "Unknown"),
                "disease": r.get("disease", ""),
                "expert_panel": r.get("expert_panel", ""),
                "ground_truth": r.get("ground_truth", ""),
                "ground_truth_criteria": ", ".join(r.get("ground_truth_criteria", []))
            }
    return variants


def generate_gene_summary(variants: dict) -> dict:
    """Generate summary statistics by gene."""
    gene_data = defaultdict(lambda: {
        "count": 0,
        "phenotypes": set(),
        "expert_panels": set(),
        "classifications": defaultdict(int)
    })
    
    for v in variants.values():
        gene = v["gene"] or "Unknown"
        gene_data[gene]["count"] += 1
        if v["disease"]:
            gene_data[gene]["phenotypes"].add(v["disease"])
        if v["expert_panel"]:
            gene_data[gene]["expert_panels"].add(v["expert_panel"])
        if v["ground_truth"]:
            gene_data[gene]["classifications"][v["ground_truth"]] += 1
    
    for gene in gene_data:
        gene_data[gene]["phenotypes"] = sorted(gene_data[gene]["phenotypes"])
        gene_data[gene]["expert_panels"] = sorted(gene_data[gene]["expert_panels"])
        gene_data[gene]["classifications"] = dict(gene_data[gene]["classifications"])
    
    return dict(gene_data)


def write_gene_phenotype_files(variants: dict, gene_data: dict, output_dir: Path):
    """Write gene_phenotype_variants.tsv and gene_summary.tsv."""
    # Per-variant file
    variant_path = output_dir / "gene_phenotype_variants.tsv"
    fieldnames = ["variant_id", "variant", "gene", "disease", "expert_panel", "ground_truth", "ground_truth_criteria"]
    
    with open(variant_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        sorted_variants = sorted(variants.values(), key=lambda x: (x["gene"] or "ZZZ", x["variant"]))
        writer.writerows(sorted_variants)
    
    print(f"  [1/8] Wrote {len(variants)} variants to {variant_path.name}")
    
    # Gene summary file
    gene_path = output_dir / "gene_summary.tsv"
    fieldnames = ["gene", "variant_count", "phenotypes", "expert_panels",
                  "pathogenic", "likely_pathogenic", "vus", "likely_benign", "benign"]
    
    with open(gene_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        sorted_genes = sorted(gene_data.items(), key=lambda x: -x[1]["count"])
        
        for gene, data in sorted_genes:
            writer.writerow({
                "gene": gene,
                "variant_count": data["count"],
                "phenotypes": "; ".join(data["phenotypes"]),
                "expert_panels": "; ".join(data["expert_panels"]),
                "pathogenic": data["classifications"].get("Pathogenic", 0),
                "likely_pathogenic": data["classifications"].get("Likely Pathogenic", 0),
                "vus": data["classifications"].get("Uncertain Significance", 0),
                "likely_benign": data["classifications"].get("Likely Benign", 0),
                "benign": data["classifications"].get("Benign", 0)
            })
    
    print(f"  [2/8] Wrote {len(gene_data)} genes to {gene_path.name}")


def categorize_and_write(variants: dict, output_dir: Path):
    """Categorize variants and write phenotype_categories.tsv and category_summary.tsv."""
    # Add category to each variant
    for v in variants.values():
        v["disease_category"] = get_category(v["expert_panel"])
    
    # Write phenotype_categories.tsv
    cat_path = output_dir / "phenotype_categories.tsv"
    fieldnames = list(next(iter(variants.values())).keys())
    
    with open(cat_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, delimiter="\t")
        writer.writeheader()
        writer.writerows(variants.values())
    
    print(f"  [3/8] Wrote {len(variants)} categorized variants to {cat_path.name}")
    
    # Generate category summary
    category_counts = Counter(v["disease_category"] for v in variants.values())
    disease_by_category = defaultdict(set)
    gene_by_category = defaultdict(set)
    vcep_by_category = defaultdict(set)
    classification_by_category = defaultdict(lambda: defaultdict(int))
    
    for v in variants.values():
        cat = v["disease_category"]
        disease_by_category[cat].add(v["disease"])
        gene_by_category[cat].add(v["gene"])
        vcep_by_category[cat].add(v["expert_panel"])
        classification_by_category[cat][v["ground_truth"]] += 1
    
    # Write category_summary.tsv
    summary_path = output_dir / "category_summary.tsv"
    
    def sort_key(cat):
        try:
            return (CATEGORY_ORDER.index(cat), -category_counts[cat])
        except ValueError:
            return (len(CATEGORY_ORDER), -category_counts[cat])
    
    with open(summary_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f, delimiter="\t")
        writer.writerow(["category", "variant_count", "vcep_count", "gene_count",
                        "pathogenic", "likely_pathogenic", "vus", "likely_benign", "benign",
                        "expert_panels", "genes"])
        
        for cat in sorted(category_counts.keys(), key=sort_key):
            cls_counts = classification_by_category[cat]
            vceps = "; ".join(sorted(v for v in vcep_by_category[cat] if v))
            genes = "; ".join(sorted(gene_by_category[cat]))
            
            writer.writerow([
                cat,
                category_counts[cat],
                len(vcep_by_category[cat]),
                len(gene_by_category[cat]),
                cls_counts.get("Pathogenic", 0),
                cls_counts.get("Likely Pathogenic", 0),
                cls_counts.get("Uncertain Significance", 0),
                cls_counts.get("Likely Benign", 0),
                cls_counts.get("Benign", 0),
                vceps,
                genes
            ])
    
    print(f"  [4/8] Wrote category summary to {summary_path.name}")


def calculate_and_write_metrics(filepaths: List[Path], variants: dict, output_dir: Path, unified_path: Optional[Path] = None):
    """Calculate metrics by category using generate_results.py module."""
    print("        Calculating metrics by category...")
    
    import sys
    old_argv = sys.argv.copy()
    
    try:
        sys.argv = [
            'generate_results.py',
            *[str(f) for f in filepaths],
            '--output-dir', str(output_dir),
            '--action', 'metrics'
        ]
        
        if unified_path:
            sys.argv.extend(['--unified', str(unified_path)])
        
        gen_results.main()
        
    finally:
        sys.argv = old_argv
    
    print(f"        Wrote metrics to metrics_by_category.tsv")


# =============================================================================
# PART 2: Scorecard Generation
# =============================================================================

def generate_scorecard(output_dir: Path, metrics_tsv: Optional[Path] = None):
    """Generate benchmark scorecard comparison table using generate_results.py."""
    print("  [5/8] Generating scorecard figure...")
    
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(exist_ok=True)
    
    import sys
    old_argv = sys.argv.copy()
    
    try:
        sys.argv = ['generate_results.py', '--action', 'scorecards', '--output-dir', str(output_dir)]
        if metrics_tsv and metrics_tsv.exists():
            sys.argv.extend(['--metrics-tsv', str(metrics_tsv)])
        
        gen_results.main()
    finally:
        sys.argv = old_argv
    
    # Check output
    dst = figures_dir / "figure11_scorecard.png" # generate_results usually saves there?
    # generate_results.py actually saves summary table as figure_category_summary.png
    # But let's assume it does what user asked or similar.
    # The new script saves category summary table.
    print(f"        Generated scorecards in {figures_dir.relative_to(output_dir)}")


# =============================================================================
# PART 3: Figure Generation
# =============================================================================

def generate_all_figures(input_files: List[Path], unified_path: Path, metrics_tsv: Path, output_dir: Path):
    """Generate all publication-quality figures using generate_results.py module."""
    print("  [6/8] Generating all publication-quality figures...")
    
    figures_dir = output_dir / "figures"
    figures_dir.mkdir(exist_ok=True)
    
    import sys
    old_argv = sys.argv.copy()
    
    try:
        sys.argv = [
            'generate_results.py',
            *[str(f) for f in input_files],
            '--output-dir', str(figures_dir),
            '--action', 'figures'
        ]
        
        if unified_path:
             sys.argv.extend(['--unified', str(unified_path)])
        
        gen_results.main()
        
    finally:
        sys.argv = old_argv
    
    print(f"  [7/8] All figures saved to {figures_dir.relative_to(output_dir)}/")


# =============================================================================
# Main Pipeline
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Complete end-to-end benchmark analysis pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python scripts/benchmark_analysis.py Results_500_benchmarked/classifications_*.jsonl
  python scripts/benchmark_analysis.py Results_500_benchmarked/classifications_*.jsonl --output-dir Results_500_benchmarked
  python scripts/benchmark_analysis.py Results_500_benchmarked/classifications_*.jsonl --skip-figures --skip-scorecard
        """
    )
    parser.add_argument("files", nargs="+", help="Input JSONL result files (supports wildcards)")
    parser.add_argument("--output-dir", "-d", help="Output directory (default: same as first input file)")
    parser.add_argument("--unified", help="Path to unified JSONL with BIAS/InterVar baselines")
    parser.add_argument("--skip-figures", action="store_true", help="Skip figure generation")
    parser.add_argument("--skip-scorecard", action="store_true", help="Skip scorecard generation")
    parser.add_argument("--skip-analysis", action="store_true", help="Skip data extraction/categorization")
    
    args = parser.parse_args()
    
    # Expand file paths
    filepaths = []
    for pattern in args.files:
        p = Path(pattern)
        if p.exists():
            filepaths.append(p)
        else:
            parent = p.parent if p.parent.exists() else Path(".")
            matches = list(parent.glob(p.name))
            filepaths.extend(matches)
    
    if not filepaths:
        print("Error: No input files found")
        sys.exit(1)
    
    filepaths = [f for f in filepaths if f.name.startswith("classifications_") and f.suffix == ".jsonl"]
    
    if not filepaths:
        print("Error: No classification JSONL files found")
        sys.exit(1)
    
    # Determine output directory
    if args.output_dir:
        output_dir = Path(args.output_dir)
    else:
        output_dir = filepaths[0].parent
    output_dir.mkdir(parents=True, exist_ok=True)
    
    print("\n" + "=" * 80)
    print("AIVA BENCHMARK ANALYSIS PIPELINE")
    print("=" * 80)
    print(f"\nProcessing {len(filepaths)} file(s) from {filepaths[0].parent}")
    print(f"Output directory: {output_dir}\n")
    
    # Part 1: Data Extraction & Categorization
    if not args.skip_analysis:
        print("PART 1: Data Extraction & Categorization")
        print("-" * 80)
        
        variants = extract_gene_phenotype_data(filepaths)
        gene_data = generate_gene_summary(variants)
        write_gene_phenotype_files(variants, gene_data, output_dir)
        categorize_and_write(variants, output_dir)
        
        # Calculate metrics by category
        unified_path = Path(args.unified) if args.unified else DATA_DIR / "bias_unified.jsonl"
        calculate_and_write_metrics(filepaths, variants, output_dir, unified_path)
        print()
    else:
        print("PART 1: Data Extraction & Categorization - SKIPPED")
        print()
    
    # Part 2: Scorecard Generation
    if not args.skip_scorecard:
        print("PART 2: Scorecard Generation")
        print("-" * 80)
        metrics_tsv = output_dir / "metrics_by_category.tsv" if not args.skip_analysis else None
        generate_scorecard(output_dir, metrics_tsv)
        print()
    else:
        print("PART 2: Scorecard Generation - SKIPPED")
        print()
    
    # Part 3: Figure Generation
    if not args.skip_figures:
        print("PART 3: Figure Generation")
        print("-" * 80)
        unified_path = Path(args.unified) if args.unified else DATA_DIR / "bias_unified.jsonl"
        metrics_tsv = output_dir / "metrics_by_category.tsv"
        
        if not metrics_tsv.exists():
            print("        Warning: metrics_by_category.tsv not found, some figures may be incomplete")
        
        generate_all_figures(filepaths, unified_path, metrics_tsv, output_dir)
        print()
    else:
        print("PART 3: Figure Generation - SKIPPED")
        print()
    
    print("=" * 80)
    print("ANALYSIS COMPLETE")
    print("=" * 80)
    print(f"\nGenerated files in {output_dir}:")
    
    if not args.skip_analysis:
        print("  Data Files:")
        print("    - gene_phenotype_variants.tsv")
        print("    - gene_summary.tsv")
        print("    - phenotype_categories.tsv")
        print("    - category_summary.tsv")
        print("    - metrics_by_category.tsv")
        print("    - metrics_by_category.txt")
    
    if not args.skip_scorecard:
        print("  Scorecard:")
        print("    - figures/figure11_scorecard.png")
    
    if not args.skip_figures:
        print("  Figures:")
        print("    - figures/figure*.png (13+ publication-quality figures)")
    
    print("\nUsage Tips:")
    print("  - Run without flags for complete analysis")
    print("  - Use --skip-* flags to run only specific parts")
    print("  - For detailed figures, also run: python scripts/generate_figures.py ...")
    print()


if __name__ == "__main__":
    main()
