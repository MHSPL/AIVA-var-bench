#!/usr/bin/env python3
"""
Overnight Variant Classification for Gemini Argon (google/gemini-4-argon)
on the frozen 2,894-variant AIVA Bench v1 dataset.

Rules:
1. Input: data/aiva_bench_variants_v1_input.jsonl (2,894 variants)
2. Model: google/gemini-4-argon
3. Stop immediately ONLY on actual billing issues (HTTP 402 or structured billing lockout)
4. Catch HTTP 500 (e.g. Max turns exceeded) and client errors per variant via try/except so other variants are not punished
5. Retry rate limits (429) and transient network drops up to 4 times
6. Re-run unclassified variants in multi-pass sweeps
"""

import argparse
import asyncio
import json
import os
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional, Dict, Any, Set, Tuple

import httpx

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from config import (
    AIVA_API_URL, AIVA_API_TOKEN, DEFAULT_ASSEMBLY, CLASSIFICATION_TYPE
)
from scripts.classify import get_variant_data

MODEL_NAME = "google/gemini-4-argon"
DEFAULT_INPUT = REPO_ROOT / "data" / "aiva_bench_variants_v1_input.jsonl"
BENCHMARK_META = REPO_ROOT / "data" / "aiva_bench_variants_v1.jsonl"
OUTPUT_DIR = REPO_ROOT / "Results_Gemini_4_Argon_Analysis"
OUTPUT_FILE = OUTPUT_DIR / "argon_full.jsonl"
LOG_FILE = OUTPUT_DIR / "argon_run.log"

MAX_RETRIES = 4
REQUEST_TIMEOUT = 300  # 5 minutes per call


def log(msg: str):
    """Timestamped logging to stdout (captured by nohup / runner)."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    formatted = f"[{now}] {msg}"
    print(formatted, flush=True)


def is_billing_error(status_code: int, text: str) -> bool:
    """Check if the error is an actual billing/credit issue."""
    if status_code == 200:
        return False
    if status_code == 402:
        return True

    # Only inspect structured error payloads on HTTP errors
    try:
        err_json = json.loads(text)
        err_msg = ""
        if isinstance(err_json, dict):
            err_msg = str(err_json.get("detail") or err_json.get("error") or err_json.get("message") or "")
        err_lower = err_msg.lower()
        strict_billing_markers = [
            "insufficient_quota", "quota_exceeded", "out_of_credits",
            "insufficient credit", "billing account", "payment required",
            "exceeded your current quota"
        ]
        return any(m in err_lower for m in strict_billing_markers)
    except Exception:
        return False


def load_classified_variant_ids(output_path: Path) -> Set[str]:
    """Return set of variant IDs that have been successfully classified."""
    if not output_path.exists():
        return set()
    classified = set()
    with open(output_path, "r", encoding="utf-8") as f:
        for line in f:
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            vid = rec.get("variant_id") or rec.get("id")
            cls = rec.get("aiva_classification")
            err = rec.get("error")
            if vid and not err and cls and cls != "Not classified":
                classified.add(vid)
    return classified


def load_ground_truth_map() -> Dict[str, Tuple[Optional[str], list]]:
    """Load ground truth classification and criteria from benchmark meta file."""
    gt_map = {}
    if BENCHMARK_META.exists():
        with open(BENCHMARK_META, "r", encoding="utf-8") as f:
            for line in f:
                if not line.strip():
                    continue
                try:
                    rec = json.loads(line)
                    vid = rec.get("id") or rec.get("variant_id")
                    if vid:
                        gt_map[vid] = (
                            rec.get("classification"),
                            rec.get("criteria_met") or []
                        )
                except Exception:
                    continue
    return gt_map


def extract_variant_payload(variant: dict) -> dict:
    """
    Extract best representation for AIVA API.
    Combines clean HGVS and genomic coordinates from variant_key.
    """
    raw_var = variant.get("variation") or variant.get("variation_original") or ""
    # Strip protein changes e.g. (p.Leu2427Pro)
    cleaned = re.sub(r"\s*\(p\.[^\)]+\)", "", raw_var).strip()
    # Strip gene symbols inside parentheses e.g. NM_004958.4(MTOR):c.7280T>C -> NM_004958.4:c.7280T>C
    cleaned = re.sub(r"\(.*?\):", ":", cleaned)

    coords = None
    vk = variant.get("variant_key", "")
    if vk and ":" in vk:
        parts = vk.split(":")
        if len(parts) == 4:
            coords = {
                "chromosome": parts[0].replace("chr", ""),
                "position": int(parts[1]),
                "ref": parts[2],
                "alt": parts[3]
            }

    if cleaned and (":c." in cleaned or ":g." in cleaned or ":n." in cleaned) and "(" not in cleaned:
        res = {"hgvs": cleaned}
        if coords:
            res.update(coords)
        return res

    if coords:
        return coords

    # Fallback to get_variant_data from classify.py
    return get_variant_data(variant)


class FatalRunError(Exception):
    """Raised when a fatal stopping condition is encountered (500 or billing)."""
    pass


class ArgonClassifier:
    def __init__(self, token: str = AIVA_API_TOKEN, base_url: str = AIVA_API_URL):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json"
        }

    async def classify_variant(
        self,
        client: httpx.AsyncClient,
        variant: dict,
        gt_map: Dict[str, Tuple[Optional[str], list]],
        max_retries: int = MAX_RETRIES
    ) -> dict:
        """
        Classify single variant with strict stopping on 500 or billing,
        and up to 4 retries for rate limits or transient errors.
        """
        vid = variant.get("id") or variant.get("variant_id")
        gene_symbol = variant.get("gene_symbol") or variant.get("gene") or "Unknown"
        disease = variant.get("disease") or ""
        expert_panel = variant.get("expert_panel") or ""

        # Ground truth resolution
        gt_classification = variant.get("classification")
        gt_criteria = variant.get("criteria_met") or []
        if (not gt_classification or not gt_criteria) and vid in gt_map:
            cached_cls, cached_crit = gt_map[vid]
            gt_classification = gt_classification or cached_cls
            gt_criteria = gt_criteria or cached_crit

        variant_data = extract_variant_payload(variant)
        if not variant_data:
            return {
                "variant_id": vid,
                "variant": variant.get("variation"),
                "gene": gene_symbol,
                "disease": disease,
                "ground_truth": gt_classification,
                "ground_truth_criteria": gt_criteria,
                "expert_panel": expert_panel,
                "error": "No valid variant identifier or coordinates",
                "execution_time_ms": 0,
                "model_used": MODEL_NAME
            }

        payload = {
            "variant_data": variant_data,
            "classification_type": CLASSIFICATION_TYPE,
            "assembly": variant.get("genome_build") or DEFAULT_ASSEMBLY,
            "model": MODEL_NAME,
            "phenotype_terms": disease,
            "description": f"Gene: {gene_symbol}",
            "additional_context": f"Mode of inheritance: {variant.get('mode_of_inheritance', 'Unknown')}"
        }

        last_error = None
        for attempt in range(max_retries + 1):
            start_time = time.time()
            try:
                resp = await client.post(
                    "/api/analyze/classify-variant",
                    json=payload,
                    timeout=httpx.Timeout(REQUEST_TIMEOUT)
                )
                elapsed_ms = int((time.time() - start_time) * 1000)

                # 1. FATAL STOPPING: Check Billing (only for non-200 responses)
                if resp.status_code != 200 and is_billing_error(resp.status_code, resp.text):
                    msg = f"FATAL BILLING ERROR: HTTP {resp.status_code}: {resp.text[:300]}"
                    log(msg)
                    raise FatalRunError(msg)

                # 2. HTTP 500: Server or agent-turn limit error (e.g. Max turns exceeded)
                # Catch with exception handling so other variants are not punished
                if resp.status_code == 500:
                    err_detail = "Internal server error"
                    try:
                        err_json = resp.json()
                        err_detail = (
                            err_json.get("detail", {}).get("error", {}).get("details")
                            or err_json.get("detail", {}).get("error", {}).get("message")
                            or str(err_json.get("detail"))
                            or resp.text[:200]
                        )
                    except Exception:
                        err_detail = resp.text[:200]
                    last_error = f"HTTP 500: {err_detail}"
                    log(f"  [HTTP 500 for {gene_symbol} ({vid[:8]})]: {err_detail} (recording error, continuing with next variant)")
                    break

                # 3. RATE LIMIT: HTTP 429 -> Retry up to 4 times
                if resp.status_code == 429:
                    if attempt < max_retries:
                        backoff = 15 * (2 ** attempt)  # 15s, 30s, 60s, 120s
                        log(f"  [429 Rate Limit for {gene_symbol} ({vid[:8]})] Retrying in {backoff}s (attempt {attempt + 1}/{max_retries})...")
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        last_error = f"HTTP 429 Rate limit exceeded after {max_retries} retries"
                        break

                # 4. Other 4xx client errors (do not retry)
                if 400 <= resp.status_code < 500:
                    last_error = f"HTTP {resp.status_code}: {resp.text[:200]}"
                    break

                # 5. Non-500 5xx errors (e.g. 502/503/504 gateway errors) -> Retry up to 4 times
                if resp.status_code in (502, 503, 504):
                    if attempt < max_retries:
                        backoff = 5 * (2 ** attempt)
                        log(f"  [HTTP {resp.status_code} Gateway error for {gene_symbol} ({vid[:8]})] Retrying in {backoff}s (attempt {attempt + 1}/{max_retries})...")
                        await asyncio.sleep(backoff)
                        continue
                    else:
                        last_error = f"HTTP {resp.status_code} after {max_retries} retries"
                        break

                resp.raise_for_status()
                data = resp.json()

                # Extract classification from successful response
                cls_data = data.get("data", data)
                res = {
                    "variant_id": vid,
                    "variant": variant.get("variation"),
                    "gene": gene_symbol,
                    "disease": disease,
                    "ground_truth": gt_classification,
                    "ground_truth_criteria": gt_criteria,
                    "expert_panel": expert_panel,
                    "execution_time_ms": elapsed_ms,
                    "model_used": MODEL_NAME,
                    "aiva_classification": cls_data.get("classification"),
                    "aiva_confidence": cls_data.get("confidence"),
                    "aiva_criteria": cls_data.get("criteria_met", []),
                    "aiva_evidence": cls_data.get("evidence_summary", {}),
                    "aiva_acmg_score": cls_data.get("acmg_score"),
                    "aiva_rationale": cls_data.get("classification_rationale"),
                    "aiva_input_issue": cls_data.get("input_issue", "")
                }
                return res

            except FatalRunError:
                raise
            except httpx.TimeoutException:
                elapsed_ms = int((time.time() - start_time) * 1000)
                last_error = f"Timeout after {REQUEST_TIMEOUT}s"
                if attempt < max_retries:
                    backoff = 10 * (2 ** attempt)
                    log(f"  [Timeout for {gene_symbol} ({vid[:8]})] Retrying in {backoff}s (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(backoff)
                else:
                    break
            except Exception as e:
                elapsed_ms = int((time.time() - start_time) * 1000)
                last_error = str(e)
                if attempt < max_retries:
                    backoff = 5 * (2 ** attempt)
                    log(f"  [Network error for {gene_symbol} ({vid[:8]}): {e}] Retrying in {backoff}s (attempt {attempt + 1}/{max_retries})...")
                    await asyncio.sleep(backoff)
                else:
                    break

        return {
            "variant_id": vid,
            "variant": variant.get("variation"),
            "gene": gene_symbol,
            "disease": disease,
            "ground_truth": gt_classification,
            "ground_truth_criteria": gt_criteria,
            "expert_panel": expert_panel,
            "execution_time_ms": elapsed_ms if "elapsed_ms" in locals() else 0,
            "model_used": MODEL_NAME,
            "error": last_error
        }


async def run_overnight(input_file: Path, concurrency: int = 2, max_passes: int = 4):
    """Main overnight runner loop with retry passes for unclassified variants."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    classifier = ArgonClassifier()
    gt_map = load_ground_truth_map()

    # Load target variants from specified input file
    variants = []
    with open(input_file, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                variants.append(json.loads(line))

    total_target = len(variants)
    log("=" * 70)
    log(f"STARTING OVERNIGHT RUN: {MODEL_NAME}")
    log(f"Input Dataset: {input_file} ({total_target} variants)")
    log(f"Output File:   {OUTPUT_FILE}")
    log(f"Concurrency:   {concurrency}")
    log("Stopping rules: Immediate STOP ONLY on actual billing exhaustion (HTTP 402)")
    log("Error handling: HTTP 500 & timeouts caught per-variant via try/except (no abort)")
    log("Retry rules:    Up to 4 retries on rate limits (429) and transient errors")
    log("Pass rules:     Multi-pass sweep over any unclassified/errored variants")
    log("=" * 70)

    for pass_num in range(1, max_passes + 1):
        classified_ids = load_classified_variant_ids(OUTPUT_FILE)
        pending = [v for v in variants if (v.get("id") or v.get("variant_id")) not in classified_ids]

        log(f"--- PASS {pass_num}/{max_passes}: {len(classified_ids)}/{total_target} classified, {len(pending)} pending ---")
        if not pending:
            log(f"SUCCESS: All {total_target} variants have been successfully classified!")
            break

        semaphore = asyncio.Semaphore(concurrency)
        completed_in_pass = 0
        total_in_pass = len(pending)

        async with httpx.AsyncClient(base_url=classifier.base_url, headers=classifier.headers) as client:
            async def process_one(v: dict):
                nonlocal completed_in_pass
                var_id = v.get("id") or v.get("variant_id") or "Unknown"
                gene_name = v.get("gene_symbol") or v.get("gene") or "Unknown"

                async with semaphore:
                    try:
                        res = await classifier.classify_variant(client, v, gt_map)
                    except FatalRunError as fatal:
                        log(f"ABORTING RUN DUE TO FATAL ERROR: {fatal}")
                        raise
                    except Exception as exc:
                        log(f"Unexpected error in worker for {gene_name} ({var_id[:8]}): {exc}")
                        res = {
                            "variant_id": var_id,
                            "variant": v.get("variation"),
                            "gene": gene_name,
                            "disease": v.get("disease"),
                            "ground_truth": v.get("classification") or gt_map.get(var_id, (None, []))[0],
                            "ground_truth_criteria": v.get("criteria_met") or gt_map.get(var_id, (None, []))[1],
                            "expert_panel": v.get("expert_panel"),
                            "execution_time_ms": 0,
                            "model_used": MODEL_NAME,
                            "error": f"Worker error: {exc}"
                        }

                    # Append to jsonl
                    with open(OUTPUT_FILE, "a", encoding="utf-8") as out_f:
                        out_f.write(json.dumps(res) + "\n")

                    completed_in_pass += 1
                    status_desc = res.get("aiva_classification") or f"ERROR: {res.get('error', '')[:40]}"
                    log(f"[{completed_in_pass}/{total_in_pass} in pass] ({len(classified_ids) + completed_in_pass}/{total_target}) {gene_name} ({var_id[:8]}): {status_desc} ({res.get('execution_time_ms', 0)}ms)")

                    # Brief spacing between variant dispatches
                    await asyncio.sleep(0.5)

            tasks = [process_one(v) for v in pending]
            try:
                await asyncio.gather(*tasks)
            except FatalRunError:
                log("Fatal stopping condition triggered. Terminating runner immediately.")
                return

    # Final summary check
    final_classified = load_classified_variant_ids(OUTPUT_FILE)
    pct = (len(final_classified) / total_target) * 100 if total_target > 0 else 0
    log("=" * 70)
    log(f"OVERNIGHT RUN SUMMARY: {len(final_classified)} / {total_target} variants classified ({pct:.2f}%)")
    log(f"Results file: {OUTPUT_FILE}")
    log("=" * 70)


def main():
    parser = argparse.ArgumentParser(description="Overnight Gemini Argon Classifier")
    parser.add_argument(
        "--input",
        type=Path,
        default=DEFAULT_INPUT,
        help=f"Path to input JSONL file (default: {DEFAULT_INPUT})"
    )
    parser.add_argument(
        "--concurrency",
        type=int,
        default=7,
        help="Concurrency limit (default: 7)"
    )
    parser.add_argument(
        "--max-passes",
        type=int,
        default=4,
        help="Max retry passes for unclassified variants (default: 4)"
    )
    args = parser.parse_args()

    asyncio.run(
        run_overnight(
            input_file=args.input,
            concurrency=args.concurrency,
            max_passes=args.max_passes
        )
    )


if __name__ == "__main__":
    main()
