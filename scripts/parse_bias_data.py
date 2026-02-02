"""
Parse BIAS-2015 supplementary data for 4-way comparison.

Parses:
- eRepo ground truth (erepo_feb_2nd.tabbed)
- InterVar predictions (erepo_feb_2nd.hg19_multianno.txt.intervar)
- BIAS-2015 predictions (erepo_feb_2nd_bitscopic_classifications.tsv)

Creates unified dataset with matching variants for comparison.

Usage:
    python scripts/parse_bias_data.py
"""

import argparse
import csv
import json
import re
import sys
from pathlib import Path

# Increase CSV field size limit for large annotation fields
csv.field_size_limit(10 * 1024 * 1024)  # 10MB

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import DATA_DIR

BIAS_DATA_DIR = DATA_DIR / "bias_2015"


def chrom_num_to_name(chrom_num: int) -> str:
    """Convert chromosome number to name."""
    if chrom_num == 23:
        return "chrX"
    elif chrom_num == 24:
        return "chrY"
    else:
        return f"chr{chrom_num}"


def vcf_to_annovar_key(chrom: str, pos: int, ref: str, alt: str) -> str:
    """
    Convert VCF representation to ANNOVAR-style key.

    VCF uses anchor base convention, ANNOVAR doesn't.
    - VCF deletion: pos=100, REF=ATG, ALT=A -> ANNOVAR: pos=101, REF=TG, ALT=-
    - VCF insertion: pos=100, REF=A, ALT=ATG -> ANNOVAR: pos=100, REF=-, ALT=TG
    - VCF delins: pos=100, REF=AGAC, ALT=ACTT -> ANNOVAR: pos=101, REF=GAC, ALT=CTT
    - VCF MNV: pos=100, REF=GG, ALT=GA -> ANNOVAR: pos=101, REF=G, ALT=A (if last differs)
    """
    # SNV - no conversion needed
    if len(ref) == 1 and len(alt) == 1:
        return f'{chrom}:{pos}:{ref}:{alt}'

    # Find common prefix length
    prefix_len = 0
    for i in range(min(len(ref), len(alt))):
        if ref[i] == alt[i]:
            prefix_len += 1
        else:
            break

    # Remove common prefix
    new_ref = ref[prefix_len:] if prefix_len < len(ref) else ""
    new_alt = alt[prefix_len:] if prefix_len < len(alt) else ""
    new_pos = pos + prefix_len

    # Pure deletion
    if new_alt == "" or (len(new_ref) > 0 and len(new_alt) == 0):
        return f'{chrom}:{new_pos}:{new_ref}:-'

    # Pure insertion (position is before the insertion point in ANNOVAR)
    if new_ref == "" or (len(new_ref) == 0 and len(new_alt) > 0):
        # ANNOVAR puts insertion at position of last matching base
        return f'{chrom}:{new_pos - 1}:-:{new_alt}'

    # Delins or MNV - ANNOVAR keeps as substitution
    return f'{chrom}:{new_pos}:{new_ref}:{new_alt}'


def vcf_to_annovar_keys(chrom: str, pos: int, ref: str, alt: str) -> list[str]:
    """
    Generate multiple possible ANNOVAR keys for a VCF variant.

    Some variants may match different ANNOVAR representations.
    """
    keys = [vcf_to_annovar_key(chrom, pos, ref, alt)]

    # For MNVs, also try matching as individual SNVs (ANNOVAR may decompose)
    if len(ref) == len(alt) and len(ref) > 1:
        # Find positions where bases differ
        for i in range(len(ref)):
            if ref[i] != alt[i]:
                snv_key = f'{chrom}:{pos + i}:{ref[i]}:{alt[i]}'
                keys.append(snv_key)

    return keys


# hg19 (GRCh37) chromosome accession versions
# Different chromosomes have different version numbers in hg19
HG19_ACCESSIONS = {
    1: "NC_000001.10", 2: "NC_000002.11", 3: "NC_000003.11", 4: "NC_000004.11",
    5: "NC_000005.9", 6: "NC_000006.11", 7: "NC_000007.13", 8: "NC_000008.10",
    9: "NC_000009.11", 10: "NC_000010.10", 11: "NC_000011.9", 12: "NC_000012.11",
    13: "NC_000013.10", 14: "NC_000014.8", 15: "NC_000015.9", 16: "NC_000016.9",
    17: "NC_000017.10", 18: "NC_000018.9", 19: "NC_000019.9", 20: "NC_000020.10",
    21: "NC_000021.8", 22: "NC_000022.10", 23: "NC_000023.10", 24: "NC_000024.9"
}

# Build regex pattern that matches any hg19 accession
HG19_ACCESSION_PATTERN = "|".join(
    re.escape(acc) for acc in HG19_ACCESSIONS.values()
)


def parse_hg19_coord(hgvs_list: str) -> tuple[str, int, str, str, str] | None:
    """
    Extract hg19 genomic coordinates from HGVS expressions list.

    Returns: (chrom, pos, ref, alt, hgvs_g) or None
    """
    for expr in hgvs_list.split(", "):
        expr = expr.strip()

        # Match hg19 genomic HGVS: NC_000001.10:g.12345A>G (SNV)
        match = re.match(rf'(({HG19_ACCESSION_PATTERN}):g\.(\d+)([ACGT]+)>([ACGT]+))', expr)
        if match:
            hgvs_g = match.group(1)
            accession = match.group(2)
            pos = int(match.group(3))
            ref = match.group(4)
            alt = match.group(5)
            # Extract chromosome number from accession
            chrom_num = int(re.search(r'NC_0000(\d{2})', accession).group(1))
            return (chrom_num_to_name(chrom_num), pos, ref, alt, hgvs_g)

        # Match deletion: NC_000001.10:g.12345del or NC_000001.10:g.12345delA
        match = re.match(rf'(({HG19_ACCESSION_PATTERN}):g\.(\d+)(?:_\d+)?del([ACGT]*))', expr)
        if match:
            hgvs_g = match.group(1)
            accession = match.group(2)
            pos = int(match.group(3))
            ref = match.group(4) if match.group(4) else "-"
            chrom_num = int(re.search(r'NC_0000(\d{2})', accession).group(1))
            return (chrom_num_to_name(chrom_num), pos, ref, "-", hgvs_g)

        # Match insertion: NC_000001.10:g.12345_12346insACG
        match = re.match(rf'(({HG19_ACCESSION_PATTERN}):g\.(\d+)_\d+ins([ACGT]+))', expr)
        if match:
            hgvs_g = match.group(1)
            accession = match.group(2)
            pos = int(match.group(3))
            alt = match.group(4)
            chrom_num = int(re.search(r'NC_0000(\d{2})', accession).group(1))
            return (chrom_num_to_name(chrom_num), pos, "-", alt, hgvs_g)

        # Match delins: NC_000001.10:g.12345_12346delinsACG
        match = re.match(rf'(({HG19_ACCESSION_PATTERN}):g\.(\d+)(?:_\d+)?delins([ACGT]+))', expr)
        if match:
            hgvs_g = match.group(1)
            accession = match.group(2)
            pos = int(match.group(3))
            alt = match.group(4)
            chrom_num = int(re.search(r'NC_0000(\d{2})', accession).group(1))
            return (chrom_num_to_name(chrom_num), pos, "delins", alt, hgvs_g)

        # Match dup: NC_000001.10:g.12345dup or NC_000001.10:g.12345_12346dup
        match = re.match(rf'(({HG19_ACCESSION_PATTERN}):g\.(\d+)(?:_\d+)?dup([ACGT]*))', expr)
        if match:
            hgvs_g = match.group(1)
            accession = match.group(2)
            pos = int(match.group(3))
            dup_seq = match.group(4) if match.group(4) else "dup"
            chrom_num = int(re.search(r'NC_0000(\d{2})', accession).group(1))
            return (chrom_num_to_name(chrom_num), pos, "-", dup_seq, hgvs_g)

    return None


def parse_erepo_ground_truth(filepath: Path) -> tuple[dict[str, dict], dict[str, dict], dict[str, dict]]:
    """
    Parse eRepo ground truth TSV.

    Returns tuple of (variants, clinvar_index, uuid_index) where:
    - variants: dict keyed by variant_key (chr:pos:ref:alt)
    - clinvar_index: dict keyed by ClinVar ID
    - uuid_index: dict keyed by UUID
    """
    variants = {}
    clinvar_index = {}  # Secondary index by ClinVar ID
    uuid_index = {}     # Secondary index by UUID

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')

        for row in reader:
            uuid = row.get('Uuid', '')
            clinvar_id = row.get('ClinVar Variation Id', '').strip()
            hgvs_list = row.get('HGVS Expressions', '')
            
            # Parse criteria
            criteria_met = row.get('Applied Evidence Codes (Met)', '').strip()
            criteria_met = [c.strip() for c in criteria_met.split(',') if c.strip()] if criteria_met else []
            
            variant_data = {
                "id": uuid,
                "variation": row.get('#Variation', ''),
                "clinvar_id": clinvar_id,
                "allele_registry_id": row.get('Allele Registry Id', ''),
                "hgvs_expressions": hgvs_list.split(', '),
                "gene_symbol": row.get('HGNC Gene Symbol', ''),
                "disease": row.get('Disease', ''),
                "mondo_id": row.get('Mondo Id', ''),
                "mode_of_inheritance": row.get('Mode of Inheritance', ''),
                "classification": row.get('Assertion', ''),
                "criteria_met": criteria_met,
                "expert_panel": row.get('Expert Panel', ''),
            }
            
            # Try to parse hg19 coordinates
            coord = parse_hg19_coord(hgvs_list)
            if coord:
                chrom, pos, ref, alt, hgvs_g = coord
                variant_key = f"{chrom}:{pos}:{ref}:{alt}"
                variant_data["hgvs_g"] = hgvs_g
                variant_data["coord"] = {"chrom": chrom, "pos": pos, "ref": ref, "alt": alt}
                
                # Primary index by coordinate
                variants[variant_key] = variant_data
            else:
                # No coordinates parsed, but still index by ClinVar ID if available
                variant_data["hgvs_g"] = variant_data["variation"]  # Use primary variation
                variant_data["coord"] = None
            
            # Secondary indexes for fallback matching
            if clinvar_id:
                clinvar_index[clinvar_id] = variant_data
            if uuid:
                uuid_index[uuid] = variant_data
    
    return variants, clinvar_index, uuid_index


def parse_intervar_classification(intervar_field: str) -> tuple[str, list[str]]:
    """
    Parse InterVar classification and criteria from field.

    Example: "InterVar: Likely pathogenic PVS1=0 PS=[0, 0, 0, 0, 0] PM=[1, 1, 0, 0, 0, 0, 0] ..."
    """
    # Extract classification
    match = re.search(r'InterVar:\s*(\w+(?:\s+\w+)?)', intervar_field)
    if not match:
        return ("", [])

    classification = match.group(1).strip()

    # Map to standard names (handle InterVar's PVS1 suffix and case variations)
    classification_lower = classification.lower()
    if "pathogenic" in classification_lower and "likely" not in classification_lower:
        classification = "Pathogenic"
    elif "likely pathogenic" in classification_lower:
        classification = "Likely Pathogenic"
    elif "uncertain" in classification_lower:
        classification = "Uncertain Significance"
    elif "likely benign" in classification_lower:
        classification = "Likely Benign"
    elif "benign" in classification_lower:
        classification = "Benign"

    # Extract criteria that are met (value = 1)
    criteria_met = []

    # PVS1
    if re.search(r'PVS1=1', intervar_field):
        criteria_met.append("PVS1")

    # PS1-5
    ps_match = re.search(r'PS=\[([^\]]+)\]', intervar_field)
    if ps_match:
        ps_vals = [int(x.strip()) for x in ps_match.group(1).split(',')]
        for i, val in enumerate(ps_vals):
            if val == 1:
                criteria_met.append(f"PS{i+1}")

    # PM1-7
    pm_match = re.search(r'PM=\[([^\]]+)\]', intervar_field)
    if pm_match:
        pm_vals = [int(x.strip()) for x in pm_match.group(1).split(',')]
        for i, val in enumerate(pm_vals):
            if val == 1:
                criteria_met.append(f"PM{i+1}")

    # PP1-6
    pp_match = re.search(r'PP=\[([^\]]+)\]', intervar_field)
    if pp_match:
        pp_vals = [int(x.strip()) for x in pp_match.group(1).split(',')]
        for i, val in enumerate(pp_vals):
            if val == 1:
                criteria_met.append(f"PP{i+1}")

    # BA1
    if re.search(r'BA1=1', intervar_field):
        criteria_met.append("BA1")

    # BS1-5
    bs_match = re.search(r'BS=\[([^\]]+)\]', intervar_field)
    if bs_match:
        bs_vals = [int(x.strip()) for x in bs_match.group(1).split(',')]
        for i, val in enumerate(bs_vals):
            if val == 1:
                criteria_met.append(f"BS{i+1}")

    # BP1-8
    bp_match = re.search(r'BP=\[([^\]]+)\]', intervar_field)
    if bp_match:
        bp_vals = [int(x.strip()) for x in bp_match.group(1).split(',')]
        for i, val in enumerate(bp_vals):
            if val == 1:
                criteria_met.append(f"BP{i+1}")

    return (classification, criteria_met)


def parse_intervar_predictions(filepath: Path) -> dict[str, dict]:
    """
    Parse InterVar predictions TSV.

    Returns dict keyed by variant_key (chr:pos:ref:alt) with prediction info.
    """
    predictions = {}

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')

        for row in reader:
            chrom = row.get('#Chr', '')
            if not chrom.startswith('chr'):
                chrom = f"chr{chrom}"

            pos = int(row.get('Start', 0))
            ref = row.get('Ref', '')
            alt = row.get('Alt', '')

            variant_key = f"{chrom}:{pos}:{ref}:{alt}"

            # Parse InterVar field
            intervar_field = row.get(' InterVar: InterVar and Evidence ', '')
            classification, criteria_met = parse_intervar_classification(intervar_field)

            predictions[variant_key] = {
                "classification": classification,
                "criteria_met": criteria_met,
                "gene": row.get('Ref.Gene', ''),
                "consequence": row.get('Func.refGene', ''),
                "exonic_func": row.get('ExonicFunc.refGene', '')
            }

    return predictions


def parse_bias_predictions(filepath: Path) -> dict[str, dict]:
    """
    Parse BIAS-2015 predictions TSV.

    Returns dict keyed by variant_key (chr:pos:ref:alt) with prediction info.
    """
    predictions = {}

    with open(filepath, 'r', encoding='utf-8') as f:
        reader = csv.DictReader(f, delimiter='\t')

        for row in reader:
            chrom = row.get('chromosome', '')
            if not chrom.startswith('chr'):
                chrom = f"chr{chrom}"

            pos = int(row.get('position', 0))
            ref = row.get('refAllele', '')
            alt = row.get('altAllele', '')

            variant_key = f"{chrom}:{pos}:{ref}:{alt}"

            # Parse classification
            classification = row.get('acmgClassification', '').strip()

            # Normalize classification names
            classification_lower = classification.lower()
            if "pathogenic" in classification_lower and "likely" not in classification_lower:
                classification = "Pathogenic"
            elif "likely_pathogenic" in classification_lower or "likely pathogenic" in classification_lower:
                classification = "Likely Pathogenic"
            elif "uncertain" in classification_lower:
                classification = "Uncertain Significance"
            elif "likely_benign" in classification_lower or "likely benign" in classification_lower:
                classification = "Likely Benign"
            elif "benign" in classification_lower:
                classification = "Benign"
            else:
                classification = classification.title()

            # Parse criteria (if available in the file)
            criteria_str = row.get('acmgCriteria', '')
            criteria_met = [c.strip() for c in criteria_str.split(',') if c.strip()] if criteria_str else []

            predictions[variant_key] = {
                "classification": classification,
                "criteria_met": criteria_met,
                "gene": row.get('geneName', ''),
                "consequence": row.get('consequence', ''),
                "hgvsg": row.get('hgvsg', ''),
                "hgvsc": row.get('hgvsc', '')
            }

    return predictions


def create_unified_dataset(
    erepo: dict[str, dict],
    intervar: dict[str, dict],
    bias: dict[str, dict]
) -> list[dict]:
    """
    Create unified dataset with variants present in all three sources.
    """
    # Find intersection of variant keys
    common_keys = set(erepo.keys()) & set(intervar.keys()) & set(bias.keys())

    print(f"eRepo variants: {len(erepo)}")
    print(f"InterVar variants: {len(intervar)}")
    print(f"BIAS-2015 variants: {len(bias)}")
    print(f"Common variants (intersection): {len(common_keys)}")

    # Build unified records
    unified = []
    for key in sorted(common_keys):
        e = erepo[key]
        i = intervar[key]
        b = bias[key]

        record = {
            # Variant identification
            "variant_key": key,
            "id": e["id"],
            "variation": e["variation"],
            "clinvar_id": e["clinvar_id"],
            "gene_symbol": e["gene_symbol"],
            "disease": e["disease"],
            "mode_of_inheritance": e["mode_of_inheritance"],
            "hgvs_expressions": e["hgvs_expressions"],
            "hgvs_g": e["hgvs_g"],  # hg19 genomic HGVS
            "coord": e["coord"],

            # Ground truth (eRepo)
            "ground_truth": {
                "classification": e["classification"],
                "criteria_met": e["criteria_met"],
                "expert_panel": e["expert_panel"]
            },

            # InterVar prediction
            "intervar": {
                "classification": i["classification"],
                "criteria_met": i["criteria_met"]
            },

            # BIAS-2015 prediction
            "bias_2015": {
                "classification": b["classification"],
                "criteria_met": b["criteria_met"]
            }
        }

        unified.append(record)

    return unified


def save_aiva_input(unified: list[dict], output_path: Path):
    """
    Save variants in format expected by AIVA classify.py.

    Uses hg19 genomic HGVS for variant identification (assembly=GRCh37).
    """
    with open(output_path, 'w', encoding='utf-8') as f:
        for record in unified:
            # Format for AIVA input (matches existing parse_erepo.py output)
            # Use hg19 genomic HGVS as the primary variant identifier
            aiva_record = {
                "id": record["id"],
                "variation": record["hgvs_g"],  # Use hg19 genomic HGVS
                "clinvar_id": record["clinvar_id"],
                "hgvs_expressions": record["hgvs_expressions"],
                "gene_symbol": record["gene_symbol"],
                "disease": record["disease"],
                "mode_of_inheritance": record["mode_of_inheritance"],
                "classification": record["ground_truth"]["classification"],
                "criteria_met": record["ground_truth"]["criteria_met"],
                "expert_panel": record["ground_truth"]["expert_panel"],
                # Include predictions for later comparison
                "intervar_classification": record["intervar"]["classification"],
                "intervar_criteria": record["intervar"]["criteria_met"],
                "bias_classification": record["bias_2015"]["classification"],
                "bias_criteria": record["bias_2015"]["criteria_met"],
                "variant_key": record["variant_key"],
                # Original variation name for reference
                "variation_original": record["variation"]
            }
            f.write(json.dumps(aiva_record) + "\n")

    print(f"Saved {len(unified)} variants to {output_path}")
    print(f"  Assembly: GRCh37 (hg19)")


def parse_vcf(filepath: Path) -> list[dict]:
    """
    Parse VCF file to get authoritative variant list.

    Returns list of variant dicts with vcf_key and annovar_keys (multiple for complex variants).
    """
    variants = []

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            if line.startswith('#'):
                continue

            cols = line.strip().split('\t')
            chrom, pos, _, ref, alt = cols[0], int(cols[1]), cols[2], cols[3], cols[4]

            # VCF key (for BIAS-2015 matching)
            vcf_key = f"{chrom}:{pos}:{ref}:{alt}"

            # ANNOVAR keys (for InterVar matching - may have multiple for MNVs)
            annovar_keys = vcf_to_annovar_keys(chrom, pos, ref, alt)

            # Determine variant type
            if len(ref) == 1 and len(alt) == 1:
                variant_type = "SNV"
            elif len(ref) > len(alt) and len(alt) == 1:
                variant_type = "Deletion"
            elif len(alt) > len(ref) and len(ref) == 1:
                variant_type = "Insertion"
            elif len(ref) == len(alt):
                variant_type = "MNV"
            else:
                variant_type = "Delins"

            variants.append({
                "chrom": chrom,
                "pos": pos,
                "ref": ref,
                "alt": alt,
                "vcf_key": vcf_key,
                "annovar_keys": annovar_keys,
                "variant_type": variant_type
            })

    return variants


def match_erepo_variant(vcf_key: str, annovar_keys: list[str], erepo: dict,
                        clinvar_index: dict = None, uuid_index: dict = None,
                        bias_match: dict = None, intervar_match: dict = None) -> dict | None:
    """
    Multi-strategy matching for eRepo variants.
    
    Tries multiple approaches to find eRepo ground truth:
    1. Direct VCF coordinate match
    2. ANNOVAR coordinate match
    3. Position-based fuzzy matching for complex variants (±2bp window)
    4. ClinVar ID matching (if available from BIAS or InterVar metadata)
    
    Returns eRepo variant data or None if no match found.
    """
    # Strategy 1: Direct VCF key match
    erepo_match = erepo.get(vcf_key)
    if erepo_match:
        return erepo_match
    
    # Strategy 2: Try all ANNOVAR keys
    for ak in annovar_keys:
        erepo_match = erepo.get(ak)
        if erepo_match:
            return erepo_match
    
    # Strategy 3: Fuzzy positional matching for complex indels
    # Parse chromosome and position from VCF key
    try:
        parts = vcf_key.split(':')
        if len(parts) >= 4:
            chrom, pos_str = parts[0], parts[1]
            pos = int(pos_str)
            ref, alt = parts[2], parts[3]
            
            # Only try fuzzy matching for complex variants (indels)
            if len(ref) != 1 or len(alt) != 1:
                # Search for variants within ±2bp window on same chromosome
                for fuzzy_offset in [-2, -1, 0, 1, 2]:
                    fuzzy_pos = pos + fuzzy_offset
                    # Try different ref/alt combinations
                    for fuzzy_key in [
                        f"{chrom}:{fuzzy_pos}:{ref}:{alt}",
                        f"{chrom}:{fuzzy_pos}:-:{alt}",  # Insertion
                        f"{chrom}:{fuzzy_pos}:{ref}:-",  # Deletion
                    ]:
                        erepo_match = erepo.get(fuzzy_key)
                        if erepo_match:
                            return erepo_match
    except (ValueError, IndexError):
        pass
    
    # Strategy 4: ClinVar ID matching (if indexes available)
    if clinvar_index:
        # Try to get ClinVar ID from BIAS or InterVar metadata if available
        # Note: Current BIAS/InterVar parsing doesn't include ClinVar ID
        # This is a placeholder for future enhancement
        pass
    
    return None


def create_unified_dataset_v2(
    vcf_variants: list[dict],
    erepo: dict[str, dict],
    clinvar_index: dict[str, dict],
    uuid_index: dict[str, dict],
    intervar: dict[str, dict],
    bias: dict[str, dict]
) -> list[dict]:
    """
    Create unified dataset using VCF as primary source.

    Uses VCF key for BIAS-2015 matching, ANNOVAR keys for InterVar matching,
    and multi-strategy matching for eRepo ground truth.
    """
    unified = []
    stats = {
        "total": 0, 
        "matched_all": 0, 
        "matched_bias_only": 0, 
        "no_erepo": 0, 
        "no_bias": 0,
        "fuzzy_matched": 0  # Track fuzzy position matches
    }

    for vcf_var in vcf_variants:
        stats["total"] += 1
        vcf_key = vcf_var["vcf_key"]
        annovar_keys = vcf_var["annovar_keys"]

        # Match BIAS-2015 first (uses VCF format - optional)
        bias_match = bias.get(vcf_key)
        if not bias_match:
            stats["no_bias"] += 1

        # Match InterVar (uses ANNOVAR format - try all possible keys - optional)
        intervar_match = None
        matched_annovar_key = None
        for ak in annovar_keys:
            if ak in intervar:
                intervar_match = intervar[ak]
                matched_annovar_key = ak
                break

        # Match eRepo ground truth (required - try multiple strategies)
        erepo_match = match_erepo_variant(vcf_key, annovar_keys, erepo, clinvar_index, uuid_index, bias_match, intervar_match)
        
        if not erepo_match:
            stats["no_erepo"] += 1
            continue  # Need ground truth

        # Track matching stats
        if bias_match and intervar_match:
            stats["matched_all"] += 1
        elif bias_match:
            stats["matched_bias_only"] += 1

        record = {
            "variant_key": vcf_key,
            "annovar_key": matched_annovar_key or annovar_keys[0],
            "id": erepo_match["id"],
            "variation": erepo_match["variation"],
            "clinvar_id": erepo_match["clinvar_id"],
            "gene_symbol": erepo_match["gene_symbol"],
            "disease": erepo_match["disease"],
            "mode_of_inheritance": erepo_match["mode_of_inheritance"],
            "hgvs_expressions": erepo_match["hgvs_expressions"],
            "hgvs_g": erepo_match["hgvs_g"],
            "variant_type": vcf_var["variant_type"],
            "coord": erepo_match["coord"],

            "ground_truth": {
                "classification": erepo_match["classification"],
                "criteria_met": erepo_match["criteria_met"],
                "expert_panel": erepo_match["expert_panel"]
            },

            "intervar": {
                "classification": intervar_match["classification"] if intervar_match else None,
                "criteria_met": intervar_match["criteria_met"] if intervar_match else []
            },

            "bias_2015": {
                "classification": bias_match["classification"] if bias_match else None,
                "criteria_met": bias_match["criteria_met"] if bias_match else []
            }
        }

        unified.append(record)

    print(f"  VCF variants: {stats['total']}")
    print(f"  Matched all 3 (eRepo + InterVar + BIAS): {stats['matched_all']}")
    print(f"  Matched eRepo + BIAS only (no InterVar): {stats['matched_bias_only']}")
    print(f"  No eRepo match: {stats['no_erepo']}")
    print(f"  No BIAS match: {stats['no_bias']}")

    return unified


def create_unified_from_erepo(
    erepo: dict[str, dict],
    intervar: dict[str, dict],
    bias: dict[str, dict]
) -> list[dict]:
    """
    Create unified dataset starting from eRepo variants.
    
    This captures variants that may not be in the VCF or have coordinate mismatches.
    """
    unified = []
    stats = {"total": 0, "with_bias": 0, "with_intervar": 0, "with_both": 0}
    
    for variant_key, erepo_match in erepo.items():
        stats["total"] += 1
        
        # Try to match BIAS and InterVar
        bias_match = bias.get(variant_key)
        if bias_match:
            stats["with_bias"] += 1
        
        # For InterVar, the key format might be different (ANNOVAR style)
        intervar_match = intervar.get(variant_key)
        if intervar_match:
            stats["with_intervar"] += 1
        
        if bias_match and intervar_match:
            stats["with_both"] += 1
        
        # Only include if we have at least BIAS or InterVar prediction
        if not (bias_match or intervar_match):
            continue
        
        record = {
            "variant_key": variant_key,
            "annovar_key": variant_key,  # Use same key
            "id": erepo_match["id"],
            "variation": erepo_match["variation"],
            "clinvar_id": erepo_match["clinvar_id"],
            "gene_symbol": erepo_match["gene_symbol"],
            "disease": erepo_match["disease"],
            "mode_of_inheritance": erepo_match["mode_of_inheritance"],
            "hgvs_expressions": erepo_match["hgvs_expressions"],
            "hgvs_g": erepo_match["hgvs_g"],
            "variant_type": "Unknown",  # Can't determine without VCF
            "coord": erepo_match["coord"],

            "ground_truth": {
                "classification": erepo_match["classification"],
                "criteria_met": erepo_match["criteria_met"],
                "expert_panel": erepo_match["expert_panel"]
            },

            "intervar": {
                "classification": intervar_match["classification"] if intervar_match else None,
                "criteria_met": intervar_match["criteria_met"] if intervar_match else []
            },

            "bias_2015": {
                "classification": bias_match["classification"] if bias_match else None,
                "criteria_met": bias_match["criteria_met"] if bias_match else []
            }
        }

        unified.append(record)
    
    print(f"  eRepo-first: {stats['total']} variants, {stats['with_both']} with both tools, {len(unified)} usable")
    
    return unified


def merge_datasets(vcf_based: list[dict], erepo_based: list[dict]) -> list[dict]:
    """
    Merge VCF-based and eRepo-based datasets, removing duplicates.
    
    Prioritizes VCF-based matches (more reliable coordinates).
    """
    # Index VCF-based by ID
    vcf_ids = {v["id"] for v in vcf_based}
    
    # Add eRepo-based variants that aren't in VCF-based
    merged = list(vcf_based)
    added = 0
    
    for erepo_var in erepo_based:
        if erepo_var["id"] not in vcf_ids:
            merged.append(erepo_var)
            added += 1
    
    print(f"  Merged: {len(vcf_based)} VCF-based + {added} additional eRepo-based = {len(merged)} total")
    
    return merged


def main():
    parser = argparse.ArgumentParser(description="Parse BIAS-2015 supplementary data")
    parser.add_argument("--output", default="erepo_bias_intervar_merged.jsonl",
                        help="Output filename (in data/ directory)")
    args = parser.parse_args()

    # Check for required files
    vcf_path = BIAS_DATA_DIR / "erepo_feb_2nd_sorted.vcf"
    erepo_path = BIAS_DATA_DIR / "erepo_feb_2nd.tabbed"
    intervar_path = BIAS_DATA_DIR / "erepo_feb_2nd.hg19_multianno.txt.intervar"
    bias_path = BIAS_DATA_DIR / "erepo_feb_2nd_bitscopic_classifications.tsv"

    # Copy VCF if not present
    if not vcf_path.exists():
        import shutil
        src = Path("/tmp/bias_supp/bias_v2.0.0_supplementary_files/erepo_feb_2nd_sorted.vcf")
        if src.exists():
            shutil.copy(src, vcf_path)
            print(f"Copied VCF to {vcf_path}")

    for path in [vcf_path, erepo_path, intervar_path, bias_path]:
        if not path.exists():
            print(f"Error: Required file not found: {path}")
            print("Run: aws s3 cp s3://bias-2015/bias_v2.0.0_supplementary_files.zip .")
            sys.exit(1)

    print("Parsing VCF (authoritative variant list)...")
    vcf_variants = parse_vcf(vcf_path)
    print(f"  Found {len(vcf_variants)} variants")

    print("Parsing eRepo ground truth...")
    erepo, clinvar_index, uuid_index = parse_erepo_ground_truth(erepo_path)
    print(f"  Parsed {len(erepo)} variants with coordinates")
    print(f"  ClinVar index: {len(clinvar_index)} entries")

    print("Parsing InterVar predictions...")
    intervar = parse_intervar_predictions(intervar_path)

    print("Parsing BIAS-2015 predictions...")
    bias = parse_bias_predictions(bias_path)

    print("\nCreating unified dataset (VCF-based matching with fuzzy fallback)...")
    unified_from_vcf = create_unified_dataset_v2(vcf_variants, erepo, clinvar_index, uuid_index, intervar, bias)
    
    print("\n  Trying eRepo-first matching to capture missed variants...")
    unified_from_erepo = create_unified_from_erepo(erepo, intervar, bias)
    
    # Merge the two datasets, preferring VCF-based matches
    unified = merge_datasets(unified_from_vcf, unified_from_erepo)

    # Save AIVA input file
    output_path = DATA_DIR / args.output
    save_aiva_input(unified, output_path)

    # Print variant type distribution
    print("\n=== Variant Type Distribution ===")
    type_counts = {}
    for record in unified:
        vtype = record["variant_type"]
        type_counts[vtype] = type_counts.get(vtype, 0) + 1
    for vtype, count in sorted(type_counts.items(), key=lambda x: -x[1]):
        print(f"  {vtype}: {count} ({100*count/len(unified):.1f}%)")

    # Print classification distribution
    print("\n=== Ground Truth Distribution ===")
    class_counts = {}
    for record in unified:
        cls = record["ground_truth"]["classification"]
        class_counts[cls] = class_counts.get(cls, 0) + 1

    for cls, count in sorted(class_counts.items(), key=lambda x: -x[1]):
        print(f"  {cls}: {count} ({100*count/len(unified):.1f}%)")

    # Check InterVar coverage
    intervar_coverage = sum(1 for r in unified if r["intervar"]["classification"])
    print(f"\n=== InterVar Coverage ===")
    print(f"  Variants with InterVar prediction: {intervar_coverage}/{len(unified)} ({100*intervar_coverage/len(unified):.1f}%)")

    print(f"\nNext steps:")
    print(f"  1. Run AIVA classification:")
    print(f"     python scripts/compare_models.py --models openai/gpt-4o google/gemini-2.5-flash --input {output_path}")
    print(f"  2. Compare all tools:")
    print(f"     python scripts/compare_tools.py --input {output_path} --results-dir results/")

