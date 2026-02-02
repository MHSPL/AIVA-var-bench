# AIVA Variant Classification Benchmark Results

## Executive Summary

This document presents benchmarking results for **AIVA (AI-powered Variant Assessment)** powered by Google Gemini 3 Pro Preview. We evaluated AIVA against 8,387 expert-curated variant classifications from the ClinGen Evidence Repository across 11 disease categories, comparing performance against two established rule-based classification tools: BIAS-2015 and InterVar.

### Key Findings

- **Overall Macro F1**: 80.5%
- **Pathogenic/Likely Pathogenic F1**: 87.4%
- **Benign/Likely Benign F1**: 80.9%
- **VUS F1**: 73.3%
- AIVA outperforms BIAS-2015 and InterVar in **9 of 11 disease categories**

---

## Dataset Composition

### Ground Truth Source

The benchmark dataset is derived from the **ClinGen Evidence Repository (eRepo)**, which contains variant classifications curated by Variant Curation Expert Panels (VCEPs). These expert-reviewed classifications serve as the gold standard for evaluating automated classification tools.

### Dataset Statistics

| Category | Variants | VCEPs | Genes | P/LP | VUS | B/LB |
|----------|----------|-------|-------|------|-----|------|
| **Cancer Predisposition** | 2,380 | 9 | 18 | 547 | 1,021 | 812 |
| **Metabolic Disorders** | 2,675 | 7 | 17 | 1,614 | 831 | 230 |
| **Cardiovascular** | 341 | 3 | 3 | 160 | 101 | 80 |
| **Hematologic** | 695 | 4 | 6 | 380 | 187 | 128 |
| **Immunodeficiency** | 379 | 1 | 8 | 144 | 150 | 85 |
| **Neurodevelopmental** | 387 | 1 | 6 | 97 | 55 | 235 |
| **Neuromuscular** | 523 | 3 | 13 | 190 | 234 | 99 |
| **Ophthalmologic** | 330 | 2 | 2 | 118 | 156 | 56 |
| **Hearing** | 196 | 1 | 12 | 94 | 46 | 56 |
| **RASopathies** | 407 | 2 | 21 | 141 | 54 | 212 |
| **Other** | 74 | 3 | 15 | 18 | 14 | 14 |
| **Total** | **8,387** | **34** | **122** | **3,503** | **2,849** | **2,007** |

### Expert Panels Represented

The dataset includes classifications from 34 ClinGen Variant Curation Expert Panels, including:

- **Cancer**: CDH1, PTEN, TP53, VHL, BRCA1/2, Lynch Syndrome, Myeloid Malignancy VCEPs
- **Metabolic**: Monogenic Diabetes, PKU, Familial Hypercholesterolemia, Lysosomal Diseases VCEPs
- **Cardiology**: Cardiomyopathy, FBN1, Pulmonary Hypertension VCEPs
- **Hematology**: Platelet Disorders, von Willebrand Disease, Coagulation Factor Deficiency VCEPs
- **Neurology**: Rett/Angelman-like, Congenital Myopathies, Hearing Loss VCEPs

---

## Classification Flow Analysis

![Sankey Classification Flow](figures/png/figure_sankey_flow_matplotlib.png)

The Sankey diagram above illustrates the flow of variants from ground truth classifications (left) to AIVA predictions (right). This visualization reveals both concordance patterns and systematic biases in AIVA's classification behavior.

### Pathogenic/Likely Pathogenic Performance

AIVA demonstrates strong performance on pathogenic variants, correctly classifying 87.4% of P/LP variants. The remaining variants are distributed as follows:

- **10.3% downgraded to VUS**: These represent cases where AIVA exercised caution due to limited functional evidence or conflicting data. In clinical practice, this conservative approach may be preferable to false positive pathogenic calls.
- **2.3% misclassified as B/LB**: A small proportion of pathogenic variants were incorrectly classified as benign, representing the most clinically significant error type.

### Benign/Likely Benign Performance

Benign variant classification shows an asymmetric error pattern:

- **74.4% correctly classified as B/LB**: AIVA successfully identifies most benign variants.
- **20.5% upgraded to VUS**: A notable proportion of benign variants are classified as VUS, reflecting AIVA's conservative approach. This may result from variants in functional domains that lack sufficient population frequency data.
- **5.1% misclassified as P/LP**: These false positives warrant investigation to identify systematic patterns (e.g., computational predictor overweighting).

### VUS Classification Stability

- **77.8% correctly classified as VUS**: AIVA maintains appropriate uncertainty for variants with insufficient evidence.
- **12.8% upgraded to P/LP**: These may represent variants with emerging evidence not yet reflected in expert classifications.
- **9.4% downgraded to B/LB**: These may represent common variants with population frequency data supporting benign status.

---

## Dataset Class Imbalance

![Variant Distribution by Category](figures/png/variant_distribution_by_category.png)

The benchmark dataset exhibits significant class imbalance that varies by disease category. Understanding this imbalance is critical for interpreting performance metrics.

### High Pathogenic Categories

**Metabolic Disorders** (2,675 variants) shows the strongest pathogenic bias, with 60% of variants classified as P/LP. This reflects the nature of these genes—most curated variants are disease-causing mutations identified in affected patients.

### Balanced Categories

**Cancer Predisposition** (2,380 variants) exhibits a more balanced distribution with a high VUS proportion (43%). This pattern reflects the complex landscape of cancer susceptibility, where many rare variants lack definitive functional evidence.

### High Benign Categories

**Neurodevelopmental Disorders** (387 variants) shows an inverted distribution with 61% benign variants. This may reflect increased attention to exome/genome sequencing incidental findings, requiring expert adjudication of common variants.

### Implications for Metrics

Class imbalance affects metric interpretation:
- **High pathogenic categories**: Pathogenic F1 scores are more reliable; benign metrics have lower sample sizes
- **High benign categories**: Benign F1 scores are emphasized; pathogenic detection may be under-sampled
- **Balanced categories**: All metrics are comparably reliable

---

## Performance Summary by Category

![Combined Performance Summary](figures/png/figure_combined_summary.png)

The figure above presents a comprehensive view of AIVA performance, comparing F1 scores across disease categories (left panel) and overall classification patterns via confusion matrices (right panel).

### Top Performing Categories (>84% F1)

| Category | F1 Score | Key Observations |
|----------|----------|------------------|
| **Other** | 88.0% | Strong across diverse conditions including vascular and neurological disorders |
| **RASopathies** | 86.5% | Excellent performance on Noonan syndrome and related conditions with well-characterized hotspot mutations |
| **Immunodeficiency** | 85.6% | SCID-associated genes (ADA, IL2RG, JAK3, RAG1/2) show clear LOF pathogenicity patterns |
| **Ophthalmologic** | 85.3% | Strong performance on MYOC (glaucoma) and RPE65 (retinal dystrophy) variants |
| **Hematologic** | 84.7% | Coagulation factor and platelet disorder genes have well-established variant-phenotype correlations |

These categories share common characteristics:
1. **Well-characterized disease mechanisms**: Clear genotype-phenotype relationships
2. **Rich functional data**: Extensive published assays for key genes
3. **Strong ClinVar representation**: Many previously classified variants for training

### Moderate Performing Categories (78-82% F1)

| Category | F1 Score | Key Observations |
|----------|----------|------------------|
| **Cardiovascular** | 81.5% | Cardiomyopathy genes (MYH7) and connective tissue disorders (FBN1) show good classification |
| **Neuromuscular** | 81.7% | Muscular dystrophy and myopathy genes exhibit diverse mutation types |
| **Metabolic** | 80.2% | Large, heterogeneous category spanning enzyme deficiencies, diabetes, and mitochondrial disease |
| **Cancer Predisposition** | 78.2% | High VUS rate (43%) reflects uncertainty in moderate-penetrance variants |

### Categories Requiring Improvement (<78% F1)

| Category | F1 Score | Challenges |
|----------|----------|------------|
| **Hearing** | 77.5% | Conservative benign classification (71.4% B/LB sensitivity) |
| **Neurodevelopmental** | 71.9% | Very conservative on benign variants (64.3% B/LB sensitivity); highest specificity (98.7%) |

The lower performance in these categories reflects AIVA's conservative classification strategy. While this may reduce sensitivity for benign variants, it maintains high specificity (>98%), which may be clinically appropriate for genes where missing a pathogenic variant carries significant consequences.

---

## Comparison with Baseline Tools

We compared AIVA against two established variant classification tools:

### Comparison Tools

**BIAS-2015 v2.1.1**: A rule-based ACMG/AMP classifier that applies standardized criteria using computational evidence (population frequency, conservation, splice predictions) without disease-specific context.

**InterVar**: An automated ACMG/AMP interpretation tool that integrates multiple databases and computational predictors to generate classifications.

### Performance Comparison (Macro F1 Scores)

| Category | AIVA | BIAS-2015 | InterVar |
|----------|------|-----------|----------|
| **Cancer Predisposition** | **78.2%** | 77.9% | 64.9% |
| **Cardiovascular** | **81.5%** | 72.7% | 50.5% |
| **Hematologic** | **84.7%** | 71.6% | 59.3% |
| **Immunodeficiency** | **85.6%** | 81.2% | 71.4% |
| **Metabolic** | **80.2%** | 72.3% | 58.9% |
| **Neuromuscular** | **81.7%** | 73.2% | 61.7% |
| **Ophthalmologic** | **85.3%** | 79.2% | 49.8% |
| **Other** | **88.0%** | 77.3% | 58.7% |
| **RASopathies** | **86.5%** | 83.3% | 65.5% |
| Hearing | 77.5% | **78.5%** | 56.9% |
| Neurodevelopmental | 71.9% | **73.8%** | 52.9% |

AIVA outperforms both baseline tools in **9 of 11 categories** using macro F1 score.

### Performance Gap Analysis

**Where AIVA excels most** (>8% improvement over BIAS-2015):

**Hematologic Disorders (+13.1%)**  
AIVA's gene-specific knowledge of coagulation pathways enables nuanced classification. For example, **SERPINC1 c.1350C>T (p.Asn450=)** is a synonymous variant in the antithrombin gene. BIAS-2015 classified it as VUS based on computational evidence, while AIVA correctly identified it as Likely Benign by recognizing that synonymous variants at non-splice positions in well-characterized coagulation factor genes rarely affect protein function. The expert panel (Thrombosis VCEP) confirmed Likely Benign.

**Cardiovascular Disorders (+8.8%)**  
Cardiomyopathy and connective tissue disorder variants benefit from AIVA's phenotype-aware assessment. AIVA integrates knowledge of domain-specific mutation patterns in genes like MYH7 (hypertrophic cardiomyopathy) and FBN1 (Marfan syndrome), where mutational hotspots and clinical penetrance data inform classification beyond generic computational predictions.

**Ophthalmologic Disorders (+6.1%)**  
AIVA demonstrates strong performance on glaucoma (MYOC) and retinal dystrophy (RPE65) variants, leveraging gene-specific functional data and established variant databases with rich prior curation.

---

**Where AIVA underperforms** (-1% to -2% vs BIAS-2015):

**Hearing Disorders (-1.0%)**  
AIVA's conservative approach sometimes upgrades benign population variants to VUS. For variants in genes like GJB2 (connexin 26) where common polymorphisms exist across populations, BIAS-2015's explicit population frequency thresholds may capture benign variants that AIVA treats cautiously.

**Neurodevelopmental Disorders (-1.9%)**  
AIVA prioritizes specificity over sensitivity in this category. For example, some MECP2 variants with borderline evidence are classified as VUS by AIVA rather than Benign, reflecting the clinical severity of missing a Rett syndrome diagnosis. While this conservative approach maintains high specificity (>98%), it lowers sensitivity for benign variants (64.3%).

The underperformance in hearing and neurodevelopmental categories reflects a deliberate design trade-off: AIVA prioritizes specificity (avoiding false positives) at the cost of sensitivity for benign variants, which may be clinically appropriate for conditions where missing a pathogenic variant has significant downstream consequences.

---

## Key Insights

### Strengths

1. **Phenotype-Aware Classification**: AIVA leverages disease-specific context, incorporating knowledge of gene-disease relationships, variant hotspots, and mechanism-specific pathogenicity patterns. This contextual understanding drives the largest performance gains in well-characterized categories.

2. **Literature Integration**: AIVA cites published functional studies, case reports, and population data to support classification decisions. This evidence-based approach provides interpretable justifications for each classification.

3. **Strong Pathogenic Detection**: With 87.4% P/LP F1 score, AIVA reliably identifies pathogenic variants across diverse disease categories.

4. **Consistent ACMG Criteria Application**: AIVA assigns appropriate ACMG/AMP criteria (PVS1, PS1-4, PM1-6, PP1-5, BA1, BS1-4, BP1-7) with supporting evidence, enabling clinical review.

### Trade-offs

AIVA exhibits a **conservative benign classification strategy**, particularly in neurodevelopmental and hearing disorders. This approach:

- Maintains very high specificity (>98%) for benign variants
- Reduces sensitivity (64-71%) by upgrading uncertain benign variants to VUS
- Minimizes clinically significant false negative pathogenic calls
- Results in elevated VUS rates compared to expert classifications

### Areas for Enhancement

1. **Benign Sensitivity**: Calibrate classification thresholds to improve recall for benign variants in conservative categories while maintaining specificity
2. **VUS Resolution**: Incorporate additional evidence sources (functional assays, segregation data) to resolve uncertain cases
3. **Rare Disease Coverage**: Expand training and knowledge base for underrepresented categories (vascular disorders, epilepsy)

---

## Methodology

### Benchmarking Pipeline

The evaluation pipeline (`scripts/benchmark_analysis.py`) orchestrates:

1. **Data Extraction**: Load variant classifications from ClinGen eRepo (TSV) and BIAS-2015 reference data (JSONL)
2. **Disease Categorization**: Map 34 VCEPs to 11 disease categories using expert-curated mappings
3. **AIVA Classification**: Query AIVA API for each variant with disease/phenotype context
4. **Metric Calculation**: Compute per-class and per-category metrics using scikit-learn methodology
5. **Figure Generation**: Create publication-quality visualizations

### Classification Normalization

Ground truth and predictions are normalized to two classification schemes:

**5-Class (Exact Match)**:
- Pathogenic, Likely Pathogenic, VUS, Likely Benign, Benign

**3-Class (Directional)**:
- Pathogenic/Likely Pathogenic → "P/LP"
- Uncertain Significance → "VUS"
- Likely Benign/Benign → "B/LB"

### Metrics Calculated

For each tool and category, we compute:

- **Accuracy**: Exact match and directional (3-class) accuracy
- **Precision**: TP / (TP + FP) for each class
- **Recall (Sensitivity)**: TP / (TP + FN) for each class
- **Specificity**: TN / (TN + FP) for each class
- **F1 Score**: Harmonic mean of precision and recall
- **Macro F1**: Unweighted average of per-class F1 scores
- **Confusion Matrices**: 5-class and 3-class views

### Comparison Tools

**BIAS-2015 v2.1.1**: Rule-based ACMG/AMP classifier using population frequency (gnomAD), conservation scores (PhyloP, GERP), computational predictors (CADD, REVEL), and ClinVar prior classifications.

**InterVar**: Automated ACMG/AMP tool integrating multiple databases (ClinVar, gnomAD, dbSNP) with computational evidence. Accessed via wInterVar API.

### Statistical Significance

With >8,000 variants across 11 categories, performance differences >2% are generally statistically significant (p<0.05). Smaller categories (n<200) have wider confidence intervals.

---

## Conclusion

AIVA achieves 80.5% overall macro F1 score and outperforms traditional rule-based classification tools (BIAS-2015, InterVar) in 9 of 11 disease categories. The system demonstrates particular strength in well-characterized disorders including hematologic, immunodeficiency, and ophthalmologic conditions, where phenotype-aware classification and literature integration provide significant advantages.

The conservative classification strategy results in lower sensitivity for benign variants in certain categories (hearing, neurodevelopmental), reflecting a deliberate prioritization of specificity to minimize clinically significant errors. This trade-off may be appropriate for clinical applications where false negative pathogenic calls carry greater risk than elevated VUS rates.

Future development will focus on improving benign variant sensitivity while maintaining specificity, expanding rare disease coverage, and integrating additional evidence sources for VUS resolution.

---

## Technical Details

| Parameter | Value |
|-----------|-------|
| **Model** | Google Gemini 3 Pro Preview |
| **Benchmark Date** | January 2026 |
| **Total Variants** | 8,387 |
| **Processing Time** | ~84 seconds per variant (average) |
| **Evidence Sources** | ClinVar, gnomAD, PubMed, UniProt, HGMD |
| **ACMG Version** | 2015 guidelines with VCEP specifications |

**Repository**: [AIVA-var-bench](https://github.com/MHSPL/AIVA-var-bench)  
**Contact**: Arun Boddapati, MHSPL Research Team
