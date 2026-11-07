# AIVA Variant Classification Benchmark

Benchmark suite for evaluating AIVA's AI-powered variant classification against expert-curated classifications from the [ClinGen Evidence Repository (eRepo)](https://erepo.clinicalgenome.org/evrepo/).

## Key Results

AIVA (powered by Gemini 3 Pro) achieves **80.5% macro F1** on 8,387 expert-curated variants across 11 disease categories:

| Metric | Score |
|--------|-------|
| Overall Macro F1 | 80.5% |
| Pathogenic/Likely Pathogenic F1 | 87.4% |
| VUS F1 | 73.3% |
| Benign/Likely Benign F1 | 80.9% |

**AIVA outperforms BIAS-2015 and InterVar in 9 of 11 disease categories.**

See [BENCHMARK_FINDINGS.md](Results_Gemini_Pro_Analysis/BENCHMARK_FINDINGS.md) for detailed analysis.

## Overview

This tool measures how well AIVA's variant classification aligns with expert panel (VCEP) curations using ACMG/AMP guidelines. It supports two primary modes of operation:

### Option 1: Standard Evaluation (Recommended)
Directly use the expert-consolidated benchmark dataset (`data/erepo_bias_intervar_merged.jsonl`) containing 8,387 variants to compare AIVA models and external tools.

### Option 2: Full Reproduction
Re-generate the entire consolidated dataset from raw BIAS-2015 supplementary files and eRepo source data using the reproduction engine.

**Metrics calculated:**
- **Classification accuracy** (5-class and 3-class directional)
- **Per-class precision, recall, and F1 scores**
- **ACMG criteria agreement** (which evidence codes each tool identifies)
- **Confusion matrices** for error analysis

## Quick Start

**Requirements:** Python 3.10+ and (for the classification step only) an AIVA API token.

```bash
# 1. Setup (always)
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
```

#### Path A — Reproduce the analysis (no API token needed)

Regenerate all metrics and figures from the classification results bundled in
this repo. This is the fastest way to verify the pipeline works end-to-end:

```bash
python scripts/benchmark_analysis.py \
  Results_Gemini_Pro_Analysis/classifications_google_gemini-3-pro-preview_combined.jsonl \
  --output-dir results/my_run
```

Outputs metrics TSVs, scorecards, and figures under `results/my_run/`. The
BIAS-2015 / InterVar baselines are read from the bundled
`data/erepo_bias_intervar_merged.jsonl`.

#### Path B — Run AIVA classification yourself (requires your API token)

```bash
cp .env.example .env        # then edit .env and set AIVA_API_TOKEN

# Quick test on 100 variants of the 8,387-variant benchmark
python scripts/compare_models.py \
  --models google/gemini-3-pro-preview \
  --input data/erepo_bias_intervar_merged.jsonl \
  --limit 100 \
  --output-dir results/my_run

# Then analyze your own results (no API needed for this step)
python scripts/benchmark_analysis.py results/my_run/classifications_*.jsonl --output-dir results/my_run
```

#### Path C — Rebuild the benchmark dataset from source

```bash
# Regenerates data/erepo_bias_intervar_merged.jsonl from the raw
# eRepo / BIAS-2015 / InterVar files in data/bias_2015/
python scripts/parse_bias_data.py
```

## Setup

```bash
# Clone and enter directory
cd aiva-bench

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Configure API access
cp .env.example .env
# Edit .env with your AIVA API token
```

## Configuration

Edit `config.py` or set environment variables:

| Setting | Default | Description |
|---------|---------|-------------|
| `AIVA_API_URL` | `http://localhost:8000` | AIVA API endpoint |
| `AIVA_API_TOKEN` | - | AIVA API token for authentication |
| `DEFAULT_MODEL` | `google/gemini-3-pro-preview` | LLM model for classification |
| `DEFAULT_ASSEMBLY` | `GRCh37` | Genome assembly (eRepo baseline is GRCh37/hg19) |
| `CONCURRENCY_LIMIT` | `5` | Max concurrent API requests (respects AIVA rate limit) |

## Project Structure

```
aiva-var-bench/
├── config.py                    # Configuration settings
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
├── data/
│   ├── erepo-tabbed.tsv         # Raw eRepo download
│   ├── erepo_bias_intervar_merged.jsonl  # Merged dataset (8,387 variants) - PRIMARY BASELINE
│   ├── aiva_bench_variants_v1.tsv        # AIVA Bench variant set (2,894 variants)
│   ├── aiva_bench_variants_v1_input.jsonl # Classifier input for that set (no expert labels)
│   └── bias_unified.jsonl       # Legacy BIAS-2015 dataset (7,617 variants, deprecated)
├── Results_Gemini_Pro_Analysis/ # Main benchmark results
│   ├── BENCHMARK_FINDINGS.md    # Comprehensive benchmark report
│   ├── classifications_*.jsonl  # Raw classification results
│   ├── metrics_by_category.tsv  # Performance metrics by disease category
│   ├── category_summary.tsv     # Dataset composition summary
│   └── figures/                 # Publication-quality visualizations
│       └── png/
│           ├── figure11_scorecard.png
│           ├── figure_sankey_flow_matplotlib.png
│           ├── figure_combined_summary.png
│           └── variant_distribution_by_category.png
└── scripts/
    ├── parse_bias_data.py       # Rebuild the merged dataset from raw source
    ├── classify.py              # AIVA API client (single variant)
    ├── compare_models.py        # Run/compare multiple AIVA models
    ├── compare_tools.py         # 4-way tool comparison (AIVA/BIAS/InterVar)
    ├── benchmark.py             # Calculate detailed metrics
    ├── benchmark_analysis.py    # End-to-end analysis pipeline (metrics + figures)
    ├── generate_results.py      # Metrics calculation & figure generation
    ├── metrics.py               # Shared metric utilities
    └── retry_errors.py          # Re-run failed classifications
```

## Usage

### Workflow A: Quick AIVA Model Comparison

Use this to compare different LLM models within AIVA on a subset of the
benchmark. Requires an AIVA API token in `.env`.

#### Step 1: Run Classification & Compare Models

The bundled `data/erepo_bias_intervar_merged.jsonl` (8,387 variants) is the
input; use `--limit` to take a quick subset for testing.

```bash
# Compare multiple models on the first 20 variants (quick test)
python scripts/compare_models.py \
  --models google/gemini-3-pro-preview openai/gpt-4o \
  --input data/erepo_bias_intervar_merged.jsonl \
  --limit 20
```

#### New Feature: Parallel Execution
You can use the `--parallel` flag to run multiple models concurrently, significantly speeding up the benchmarking process.

```bash
python scripts/compare_models.py \
  --models openai/gpt-5.2 google/gemini-3-pro-preview anthropic/claude-opus-4-5-20251101 \
  --input data/erepo_bias_intervar_merged.jsonl \
  --parallel \
  --concurrency 5
```

When using `--parallel`:
- Progress bars are replaced with periodic status updates to avoid console conflicts.
- Each model runs in its own concurrent task.

#### New Feature: Custom Output Directory
You can now specify where to save results using `--output-dir`.

```bash
python scripts/compare_models.py \
  --models openai/gpt-5.2 google/gemini-3-pro-preview \
  --input data/erepo_bias_intervar_merged.jsonl \
  --limit 100 \
  --output-dir results/my_experiment_v1
```

#### Step 2: Calculate Detailed Metrics

```bash
# Use most recent results
python scripts/benchmark.py

# Specify input file
python scripts/benchmark.py --input results/classifications_*.jsonl
```

---

### Workflow B: 4-Way Tool Comparison (AIVA vs InterVar vs BIAS-2015)

Use this to compare AIVA against InterVar and BIAS-2015 on 8,387 variants from the unified baseline.

#### Step 1: Download BIAS-2015 Supplementary Data

Download pre-computed predictions from the BIAS-2015 paper:

**Option A: Direct download (no AWS CLI required)**

Download: https://bias-2015.s3.amazonaws.com/bias_v2.0.0_supplementary_files.zip

**Option B: AWS CLI**

```bash
aws s3 cp s3://bias-2015/bias_v2.0.0_supplementary_files.zip /tmp/
```

Then extract and copy files:

```bash
unzip /tmp/bias_v2.0.0_supplementary_files.zip -d /tmp/bias_supp/

# Copy required files to project
cp /tmp/bias_supp/bias_v2.0.0_supplementary_files/erepo_feb_2nd.tabbed data/bias_2015/
cp /tmp/bias_supp/bias_v2.0.0_supplementary_files/erepo_feb_2nd.hg19_multianno.txt.intervar data/bias_2015/
cp /tmp/bias_supp/bias_v2.0.0_supplementary_files/erepo_feb_2nd_bitscopic_classifications.tsv data/bias_2015/
cp /tmp/bias_supp/bias_v2.0.0_supplementary_files/erepo_feb_2nd_sorted.vcf data/bias_2015/
```

**Files needed:**
| File | Description |
|------|-------------|
| `erepo_feb_2nd.tabbed` | eRepo ground truth (expert classifications) |
| `erepo_feb_2nd.hg19_multianno.txt.intervar` | InterVar predictions |
| `erepo_feb_2nd_bitscopic_classifications.tsv` | BIAS-2015 predictions |
| `erepo_feb_2nd_sorted.vcf` | Authoritative variant list (VCF format) |

#### Step 2: Parse and Unify Data

```bash
python scripts/parse_bias_data.py
```

This creates `data/erepo_bias_intervar_merged.jsonl` containing 8,387 variants with:
- Ground truth classifications from eRepo
- InterVar predictions
- BIAS-2015 predictions
- All in AIVA-compatible format (hg19/GRCh37)

#### Step 3: Run AIVA Classification

```bash
# Test with small sample first
python scripts/compare_models.py \
    --models google/gemini-3-pro-preview \
    --input data/erepo_bias_intervar_merged.jsonl \
    --limit 100

# Full dataset (takes ~21 hours per model at ~9s/variant for 8,387 variants)
python scripts/compare_models.py \
    --models google/gemini-3-pro-preview \
    --input data/erepo_bias_intervar_merged.jsonl
```

#### Step 4: Run 4-Way Comparison

```bash
python scripts/compare_tools.py \
    --aiva-results Results_Gemini_Pro_Analysis/classifications_google_gemini-3-pro-preview_*.jsonl
```

**Output:**
```
=== FAIR COMPARISON (on N AIVA-predicted variants) ===

Tool                  N Valid      Exact     Direct   Macro F1     Dir F1
------------------------------------------------------------------------------------------
AIVA                      100      75.0%      88.0%      68.2%      85.3%
BIAS-2015                 100      58.0%      81.0%      51.4%      81.5%
InterVar                  100      49.0%      65.0%      43.0%      65.9%

REFERENCE: Full dataset metrics (all 8387 variants)
Tool                  N Valid      Exact     Direct
------------------------------------------------------------------------------------------
InterVar (full)          8387      49.6%      65.3%
BIAS-2015 (full)         8387      58.2%      81.2%
```

The comparison is **fair** - all tools are evaluated on the exact same variants that AIVA classified.

## Script Reference

| Script | Purpose |
|--------|---------|
| `parse_bias_data.py` | Parse raw eRepo/BIAS-2015/InterVar files, create the unified dataset |
| `classify.py` | AIVA API client (classify a single variant) |
| `compare_models.py` | Run AIVA with multiple models, compare results |
| `compare_tools.py` | Compare AIVA vs InterVar vs BIAS-2015 |
| `benchmark.py` | Calculate detailed metrics |
| `benchmark_analysis.py` | End-to-end analysis pipeline with figures |
| `generate_results.py` | Metrics calculation and figure generation |
| `metrics.py` | Shared metric utilities |
| `retry_errors.py` | Re-run failed classifications in a results file |
| `build_variant_input.py` | Write the classifier input JSONL for the AIVA Bench variant set |

## Metrics Explained

### Classification Accuracy

| Metric | Description |
|--------|-------------|
| **Exact Match (5-class)** | % where AIVA matches expert classification exactly |
| **Directional (3-class)** | % correct when collapsed to Pathogenic/VUS/Benign |

### Per-Class Metrics

For each of the 5 ACMG classifications:
- **Precision**: When AIVA predicts this class, how often is it correct?
- **Recall**: Of all variants in this class, how many does AIVA identify?
- **F1**: Harmonic mean of precision and recall

### Criteria Analysis

| Metric | Description |
|--------|-------------|
| **Avg Jaccard (normalized)** | Overlap of ACMG criteria (after normalizing modifiers like `_Supporting`) |
| **Direction Agreement** | % where AIVA's evidence leans the same direction (pathogenic vs benign) |
| **Per-Criterion P/R/F1** | How well AIVA identifies each specific criterion (PM2, PP3, etc.) |

### Evidence Direction

Criteria are grouped by evidence direction:
- **Pathogenic**: PVS1, PS1-4, PM1-6, PP1-5
- **Benign**: BA1, BS1-4, BP1-7

## Example Output

```
======================================================================
AIVA VARIANT CLASSIFICATION BENCHMARK RESULTS
======================================================================

Dataset: 200 variants
  Successful: 195 | Errors: 5 (2.5%)
  Compared: 195

============================== ACCURACY ==============================
  EXACT MATCH (5-class):     72.31%  (141/195)
  DIRECTIONAL (3-class):     89.74%  (175/195)

============================== CRITERIA ANALYSIS =====================
  Avg Jaccard (normalized): 0.312
  Evidence Direction Agreement: 85.6%

  Aggregate by Evidence Type:
    Pathogenic (PVS/PS/PM/PP): P=0.542 R=0.478 F1=0.508
    Benign (BA/BS/BP):         P=0.234 R=0.189 F1=0.209

  Per-Criterion Metrics (top 15 by support):
  Criterion  Type     Prec Recall     F1   TP   FP   FN Supp
  --------------------------------------------------------------
  PM2        PATH    0.892  0.943  0.917  150   18    9  159
  PP3        PATH    0.654  0.567  0.607   72   38   55  127
  ...
```

## Rate Limiting

The classify script handles rate limits automatically:
- Exponential backoff on errors
- Special handling for 429 (rate limit) with longer delays
- Configurable concurrency to avoid overwhelming the API

If you encounter rate limits, reduce concurrency:
```bash
python scripts/compare_models.py --concurrency 1
```

## License

MIT License - see LICENSE file for details.

## Contact

Arun Boddapati, MHSPL Research Team
