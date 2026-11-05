#!/usr/bin/env python3
"""
Write the classifier input for the AIVA Bench variant set: one JSON record per
line (the format scripts/classify.py --input reads) for every variant listed in
data/aiva_bench_variants_<version>.tsv, with the fields a classifier needs and
nothing that gives the answer away (no expert classification or criteria, no
BIAS-2015 or InterVar results).

Fields, in order:
    id                   UUID of the curation record
    variation            HGVS name, e.g. NM_004958.4(MTOR):c.7280T>C (p.Leu2427Pro)
    variation_original   HGVS name as given in the source record
    variant_key          chrom:pos:ref:alt on GRCh37, e.g. chr1:11174395:A:G
    gene_symbol
    disease
    mode_of_inheritance
    genome_build         GRCh37
    expert_panel         ClinGen VCEP

Values come from data/erepo_bias_intervar_merged.jsonl. Every variant_key
position is checked against the record's own GRCh37 genomic HGVS
(NC_0000xx at its GRCh37 version); the script stops if a chromosome differs or
a position is more than MAX_OFFSET bases away. Where the source has no HGVS
name, `variation` takes the first NM_ expression in the record's ClinVar HGVS
list and `variation_original` keeps the source's empty value.

Usage:
    python scripts/build_variant_input.py
    python scripts/build_variant_input.py --version v1
"""

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = REPO_ROOT / "data"
SOURCE = DATA_DIR / "erepo_bias_intervar_merged.jsonl"
GENOME_BUILD = "GRCh37"
# VCF and HGVS place an indel at different ends of a repeat; a larger gap means another build
MAX_OFFSET = 100

FIELDS = ["id", "variation", "variation_original", "variant_key", "gene_symbol", "disease",
          "mode_of_inheritance", "genome_build", "expert_panel"]

# RefSeq accessions of the GRCh37 chromosomes
GRCH37_NC = {
    "NC_000001.10": "1", "NC_000002.11": "2", "NC_000003.11": "3", "NC_000004.11": "4",
    "NC_000005.9": "5", "NC_000006.11": "6", "NC_000007.13": "7", "NC_000008.10": "8",
    "NC_000009.11": "9", "NC_000010.10": "10", "NC_000011.9": "11", "NC_000012.11": "12",
    "NC_000013.10": "13", "NC_000014.8": "14", "NC_000015.9": "15", "NC_000016.9": "16",
    "NC_000017.10": "17", "NC_000018.9": "18", "NC_000019.9": "19", "NC_000020.10": "20",
    "NC_000021.8": "21", "NC_000022.10": "22", "NC_000023.10": "X", "NC_000024.9": "Y",
}


def read_set(path: Path) -> list[str]:
    ids = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("variant_id"):
            continue
        ids.append(line.split("\t")[0])
    return ids


def grch37_position(record: dict):
    """(chromosome, position) from the record's GRCh37 genomic HGVS, or None."""
    for expr in record.get("hgvs_expressions") or []:
        acc, _, rest = expr.partition(":g.")
        if acc in GRCH37_NC and rest:
            m = re.match(r"(\d+)", rest)
            if m:
                return GRCH37_NC[acc], int(m.group(1))
    return None


def check_build(record: dict) -> str:
    """'exact', 'near', 'unchecked' (no GRCh37 HGVS), or an error message."""
    chrom, pos = record["variant_key"].split(":")[:2]
    ref = grch37_position(record)
    if ref is None:
        return "unchecked"
    if chrom.replace("chr", "") != ref[0]:
        return f"chromosome {chrom} but GRCh37 HGVS on chr{ref[0]}"
    offset = abs(int(pos) - ref[1])
    if offset == 0:
        return "exact"
    if offset <= MAX_OFFSET:
        return "near"
    return f"position {pos} is {offset} bases from GRCh37 HGVS position {ref[1]}"


UUID = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$")
VARIANT_KEY = re.compile(r"^chr([1-9]|1[0-9]|2[0-2]|X|Y|MT?):\d+:[ACGTN]+:[ACGTN]+$")


def check_format(records: list[dict]) -> list[str]:
    """
    Every record must have the approved format: exactly FIELDS, in order, a
    unique UUID id, a chrom:pos:ref:alt variant_key, genome_build GRCh37, and
    a gene and expert panel. Nothing else (no classification, criteria or
    other tools' results) can get into the file.
    """
    problems, seen = [], set()
    for n, r in enumerate(records, 1):
        where = f"record {n} ({r.get('id', '?')})"
        if list(r) != FIELDS:
            problems.append(f"{where}: fields {list(r)} differ from {FIELDS}")
            continue
        if not UUID.match(r["id"]) or r["id"] in seen:
            problems.append(f"{where}: id is not a unique UUID")
        seen.add(r["id"])
        if not VARIANT_KEY.match(r["variant_key"]):
            problems.append(f"{where}: variant_key {r['variant_key']!r} is not chrom:pos:ref:alt")
        if r["genome_build"] != GENOME_BUILD:
            problems.append(f"{where}: genome_build is {r['genome_build']!r}")
        for field in ("variation", "gene_symbol", "disease", "expert_panel"):
            if not r[field]:
                problems.append(f"{where}: {field} is empty")
    return problems


def to_input(record: dict) -> tuple[dict, bool]:
    variation = record.get("variation") or ""
    filled = False
    if not variation:
        nm = next((e for e in record.get("hgvs_expressions") or [] if e.startswith("NM_")), "")
        variation, filled = nm, bool(nm)
    out = {
        "id": record["id"],
        "variation": variation,
        "variation_original": record.get("variation_original") or "",
        "variant_key": record.get("variant_key") or "",
        "gene_symbol": record.get("gene_symbol") or "",
        "disease": record.get("disease") or "",
        "mode_of_inheritance": record.get("mode_of_inheritance") or "",
        "genome_build": GENOME_BUILD,
        "expert_panel": record.get("expert_panel") or "",
    }
    return {k: out[k] for k in FIELDS}, filled


def main():
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--version", default="v1", help="variant set version (default v1)")
    args = parser.parse_args()

    set_file = DATA_DIR / f"aiva_bench_variants_{args.version}.tsv"
    out_file = DATA_DIR / f"aiva_bench_variants_{args.version}_input.jsonl"
    ids = read_set(set_file)
    if len(ids) != len(set(ids)):
        sys.exit(f"{set_file.name} lists a variant id more than once.")

    wanted = set(ids)
    source = {}
    with open(SOURCE, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                rec = json.loads(line)
                if rec["id"] in wanted:
                    source[rec["id"]] = rec
    missing = [i for i in ids if i not in source]
    if missing:
        sys.exit(f"{len(missing)} variant ids are not in {SOURCE.name}, e.g. {missing[0]}")

    checks = {"exact": 0, "near": 0, "unchecked": 0}
    errors = []
    for i in ids:
        result = check_build(source[i])
        if result in checks:
            checks[result] += 1
        else:
            errors.append(f"{i} {source[i]['variant_key']}: {result}")
    if errors:
        sys.exit(f"{len(errors)} variant keys do not match {GENOME_BUILD}:\n  " + "\n  ".join(errors[:10]))

    records, filled = [], []
    for i in ids:
        rec, was_filled = to_input(source[i])
        records.append(rec)
        if was_filled:
            filled.append(f"{rec['id']} {rec['gene_symbol']}: {rec['variation']}")

    problems = check_format(records)
    if problems:
        sys.exit(f"{len(problems)} records do not have the approved format; nothing written:\n  " + "\n  ".join(problems[:10]))

    with open(out_file, "w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")

    def unique(field):
        return len({r[field] for r in records if r[field]})

    def empty(field):
        return sum(1 for r in records if not r[field])

    print(f"Wrote {len(records)} records to {out_file.relative_to(REPO_ROOT)}")
    print(f"  {GENOME_BUILD} check: {checks['exact']} exact, {checks['near']} within {MAX_OFFSET} bp (indel placement), "
          f"{checks['unchecked']} without a GRCh37 HGVS to check against")
    print(f"  unique: {unique('variant_key')} variant keys, {unique('gene_symbol')} genes, "
          f"{unique('disease')} diseases, {unique('expert_panel')} expert panels")
    for field in ("variation_original", "mode_of_inheritance"):
        if empty(field):
            print(f"  {field} empty in the source for {empty(field)} records")
    if filled:
        print(f"  variation taken from the record's NM_ HGVS (source has none) for {len(filled)}:")
        for line in filled:
            print("    " + line)


if __name__ == "__main__":
    main()
