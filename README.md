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

This tool measures how well AIVA's variant classification aligns with expert panel (VCEP) curations using ACMG/AMP guidelines. It supports two benchmarking workflows:

### Workflow A: Quick AIVA Model Comparison
Compare different LLM models within AIVA using a sample of eRepo variants.

### Workflow B: 4-Way Tool Comparison
Compare AIVA against InterVar and BIAS-2015 using pre-computed predictions from the [BIAS-2015 paper](https://github.com/bitscopic/BIAS-2015).

**Metrics calculated:**
- **Classification accuracy** (5-class and 3-class directional)
- **Per-class precision, recall, and F1 scores**
- **ACMG criteria agreement** (which evidence codes each tool identifies)
- **Confusion matrices** for error analysis

## Quick Start

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Add your AIVA_API_TOKEN

# Workflow A: Quick model comparison (5 min)
python scripts/parse_erepo.py --sample-size 50
python scripts/compare_models.py --models google/gemini-3-flash-preview --limit 10
python scripts/benchmark.py

# Workflow B: 4-way tool comparison (requires BIAS-2015 data)
python scripts/parse_bias_data.py
python scripts/compare_models.py --models google/gemini-3-flash-preview --input data/erepo_bias_intervar_merged.jsonl --limit 100
python scripts/compare_tools.py --aiva-results results/classifications_*.jsonl
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
| `DEFAULT_MODEL` | `google/gemini-3-flash-preview` | LLM model for classification |
| `DEFAULT_ASSEMBLY` | `GRCh38` | Genome assembly |
<<<<<<< HEAD
| `CONCURRENCY_LIMIT` | `5` | Max concurrent API requests |

## Project Structure

```
aiva-var-bench/
├── config.py                    # Configuration settings
├── requirements.txt             # Python dependencies
├── .env.example                 # Environment template
├── data/
│   ├── erepo-tabbed.tsv         # Raw eRepo download
│   ├── erepo_bias_intervar_merged.jsonl  # Merged dataset (8,387 variants) - PRIMARY BASELINE
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
    ├── parse_erepo.py           # Parse & sample eRepo data
    ├── parse_bias_data.py       # Parse BIAS-2015 data
    ├── compare_models.py        # Compare multiple AIVA models
    ├── compare_tools.py         # 4-way tool comparison
    ├── benchmark.py             # Calculate detailed metrics
    ├── benchmark_analysis.py    # End-to-end analysis pipeline
    └── generate_results.py      # Metrics calculation & figure generation
```
=======
| `CONCURRENCY_LIMIT` | `5` | Max concurrent API requests (respects AIVA rate limit) |
>>>>>>> origin/main

## Usage

### Workflow A: Quick AIVA Model Comparison

Use this to compare different LLM models within AIVA on a sample of eRepo variants.

#### Step 1: Parse eRepo Data

Download the eRepo TSV from [ClinGen](https://erepo.clinicalgenome.org/evrepo/) and parse it:

```bash
# Parse and create stratified sample (default: 200 variants)
python scripts/parse_erepo.py

# Custom sample size
python scripts/parse_erepo.py --sample-size 500
```

**Output:**
- `data/parsed_variants.jsonl` - All parsed variants
- `data/sample_200.jsonl` - Stratified sample

#### Step 2: Run Classification & Compare Models

```bash
# Compare multiple models on the sample
python scripts/compare_models.py --models google/gemini-3-flash-preview openai/gpt-4o

# Limit variants for quick testing
python scripts/compare_models.py --models google/gemini-3-flash-preview --limit 20
```

<<<<<<< HEAD
# New Feature: Parallel Execution
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

**New Feature: Custom Output Directory**
You can now specify where to save results using `--output-dir`.

```bash
# Step 1: Download BIAS-2015 data (see below)

# Step 2: Parse and unify data
python scripts/parse_bias_data.py

# Step 3: Run AIVA classification
python scripts/compare_models.py \
  --models openai/gpt-5.2 google/gemini-3-pro-preview \
  --input data/sample_200.jsonl \
  --output-dir results/my_experiment_v1
```

### Full Analysis Pipeline

For comprehensive benchmarking with figures and scorecards:
=======
#### Step 3: Calculate Detailed Metrics
>>>>>>> origin/main

```bash
# Use most recent results
python scripts/benchmark.py

# Specify input file
python scripts/benchmark.py --input results/classifications_*.jsonl
```

---

### Workflow B: 4-Way Tool Comparison (AIVA vs InterVar vs BIAS-2015)

Use this to compare AIVA against InterVar and BIAS-2015 on 7,617 variants from the BIAS-2015 paper.

#### Step 1: Download BIAS-2015 Supplementary Data

Download pre-computed predictions from the BIAS-2015 paper:

**Option A: Direct download (no AWS CLI required)**

Download: https://bias-2015.s3.amazonaws.com/bias_v2.0.0_supplementary_files.zip

**Option B: AWS CLI**

```bash
aws s3 cp s3://bias-2015/bias_v2.0.0_supplementary_files.zip /tmp/
```

Then extract and copy files:
<<<<<<< HEAD
```bash
unzip /tmp/bias_v2.0.0_supplementary_files.zip -d /tmp/bias_supp/
cp /tmp/bias_supp/bias_v2.0.0_supplementary_files/*.{tabbed,intervar,tsv,vcf} data/bias_2015/
```

## Script Reference

| Script | Purpose |
|--------|---------|
| `parse_erepo.py` | Parse ClinGen eRepo TSV, create stratified sample |
| `parse_bias_data.py` | Parse BIAS-2015 files, create unified dataset |
| `compare_models.py` | Run AIVA with multiple models, compare results |
| `compare_tools.py` | Compare AIVA vs InterVar vs BIAS-2015 |
| `benchmark.py` | Calculate detailed metrics |
| `benchmark_analysis.py` | End-to-end analysis pipeline with figures |
| `generate_results.py` | Metrics calculation and figure generation |
=======

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
    --models google/gemini-3-flash-preview \
    --input data/erepo_bias_intervar_merged.jsonl \
    --limit 100

# Full dataset (takes ~21 hours per model at ~9s/variant for 8,387 variants)
python scripts/compare_models.py \
    --models google/gemini-3-flash-preview \
    --input data/erepo_bias_intervar_merged.jsonl
```

#### Step 4: Run 4-Way Comparison

```bash
python scripts/compare_tools.py \
    --aiva-results results/classifications_google_gemini-3-flash-preview_*.jsonl
```

**Output:**
```
=== FAIR COMPARISON (on N AIVA-predicted variants) ===

Tool                  N Valid      Exact     Direct   Macro F1     Dir F1
------------------------------------------------------------------------------------------
AIVA                      100      75.0%      88.0%      68.2%      85.3%
BIAS-2015                 100      58.0%      81.0%      51.4%      81.5%
InterVar                  100      49.0%      65.0%      43.0%      65.9%

REFERENCE: Full dataset metrics (all 7617 variants)
Tool                  N Valid      Exact     Direct
------------------------------------------------------------------------------------------
InterVar (full)          7617      49.6%      65.3%
BIAS-2015 (full)         7617      58.2%      81.2%
```

The comparison is **fair** - all tools are evaluated on the exact same variants that AIVA classified.
>>>>>>> origin/main

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

<<<<<<< HEAD
=======
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

## Project Structure

```
aiva-bench/
├── config.py              # Configuration settings
├── metrics.py             # Shared metrics calculations
├── requirements.txt       # Python dependencies
├── .env.example           # Environment template
├── data/
│   ├── erepo-tabbed.tsv   # Raw eRepo download (Workflow A)
│   ├── parsed_variants.jsonl
│   ├── sample_200.jsonl
│   ├── bias_2015/         # BIAS-2015 supplementary files (Workflow B)
│   │   ├── erepo_feb_2nd.tabbed
│   │   ├── erepo_feb_2nd.hg19_multianno.txt.intervar
│   │   ├── erepo_feb_2nd_bitscopic_classifications.tsv
│   │   └── erepo_feb_2nd_sorted.vcf
│   └── erepo_bias_intervar_merged.jsonl # Unified dataset (8,387 variants) for 4-way comparison
├── results/
│   ├── classifications_*.jsonl
│   ├── comparison_*.json
│   ├── metrics_*.json
│   └── tool_comparison_detailed.jsonl
└── scripts/
    ├── parse_erepo.py     # Parse & sample eRepo data (Workflow A)
    ├── parse_bias_data.py # Parse BIAS-2015 data (Workflow B)
    ├── classify.py        # Call AIVA API (single model)
    ├── compare_models.py  # Compare multiple AIVA models
    ├── compare_tools.py   # 4-way tool comparison
    └── benchmark.py       # Calculate detailed metrics
```

## Script Reference

| Script | Purpose | When to Use |
|--------|---------|-------------|
| `parse_erepo.py` | Parse ClinGen eRepo TSV, create stratified sample | Workflow A, Step 1 |
| `parse_bias_data.py` | Parse BIAS-2015 supplementary files, create unified dataset | Workflow B, Step 2 |
| `classify.py` | Run AIVA classification (single model) | Quick single-model test |
| `compare_models.py` | Run AIVA with multiple models, compare results | Both workflows |
| `compare_tools.py` | Compare AIVA vs InterVar vs BIAS-2015 | Workflow B, Step 4 |
| `benchmark.py` | Calculate detailed metrics, confusion matrices | Detailed analysis |

>>>>>>> origin/main
## Rate Limiting

The classify script handles rate limits automatically:
- Exponential backoff on errors
- Special handling for 429 (rate limit) with longer delays
- Configurable concurrency to avoid overwhelming the API

If you encounter rate limits, reduce concurrency:
```bash
<<<<<<< HEAD
python scripts/compare_models.py --concurrency 1
```

## License

MIT License - see LICENSE file for details.

## Contact

Arun Boddapati, MHSPL Research Team
=======
python scripts/classify.py --concurrency 1
```
>>>>>>> origin/main
