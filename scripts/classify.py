"""
Call AIVA API for variant classification.

Usage:
    python scripts/classify.py                              # Use default sample
    python scripts/classify.py --input data/sample_200.jsonl
    python scripts/classify.py --concurrency 3              # Limit concurrent requests
"""

import argparse
import asyncio
import json
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import httpx

sys.path.insert(0, str(Path(__file__).parent.parent))
from config import (
    DATA_DIR, RESULTS_DIR, AIVA_API_URL, AIVA_API_TOKEN,
    DEFAULT_ASSEMBLY, CLASSIFICATION_TYPE, CONCURRENCY_LIMIT,
    REQUEST_TIMEOUT, MAX_RETRIES, RETRY_DELAY, RATE_LIMIT_DELAY,
    DEFAULT_MODEL
)


class AIVAClient:
    """Async client for AIVA variant classification API."""

    def __init__(
        self,
        base_url: str = AIVA_API_URL,
        token: str = AIVA_API_TOKEN,
        timeout: int = REQUEST_TIMEOUT
    ):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._client: Optional[httpx.AsyncClient] = None

    async def __aenter__(self):
        self._client = httpx.AsyncClient(
            base_url=self.base_url,
            headers={
                "Authorization": f"Bearer {self.token}",
                "Content-Type": "application/json"
            },
            timeout=httpx.Timeout(self.timeout)
        )
        return self

    async def __aexit__(self, *args):
        if self._client:
            await self._client.aclose()

    async def classify_variant(
        self,
        variant_data: dict,
        classification_type: str = CLASSIFICATION_TYPE,
        assembly: str = DEFAULT_ASSEMBLY,
        model: Optional[str] = None,
        phenotype_terms: Optional[str] = None,
        description: Optional[str] = None,
        additional_context: Optional[str] = None,
        retries: int = MAX_RETRIES
    ) -> dict:
        """
        Call AIVA API to classify a variant.

        Args:
            variant_data: Dict with variant info (hgvs, rsid, or coordinates)
            classification_type: "acmg" or "amp"
            assembly: "GRCh37" or "GRCh38"
            model: LLM model to use (e.g., "openai/gpt-4o", "google/gemini-2.5-flash")
            phenotype_terms: Disease/phenotype description
            description: Sample description
            additional_context: Additional notes
            retries: Number of retries on failure

        Returns:
            API response dict
        """
        payload = {
            "variant_data": variant_data,
            "classification_type": classification_type,
            "assembly": assembly
        }

        if model:
            payload["model"] = model
        if phenotype_terms:
            payload["phenotype_terms"] = phenotype_terms
        if description:
            payload["description"] = description
        if additional_context:
            payload["additional_context"] = additional_context

        last_error = None
        for attempt in range(retries + 1):
            try:
                response = await self._client.post(
                    "/api/analyze/classify-variant",
                    json=payload
                )
                response.raise_for_status()
                return response.json()

            except httpx.TimeoutException as e:
                last_error = f"Timeout after {self.timeout}s"
                if attempt < retries:
                    delay = RETRY_DELAY * (2 ** attempt)  # Exponential backoff
                    await asyncio.sleep(delay)

            except httpx.HTTPStatusError as e:
                last_error = f"HTTP {e.response.status_code}: {e.response.text[:200]}"

                # Special handling for rate limit (429)
                if e.response.status_code == 429:
                    if attempt < retries:
                        delay = RATE_LIMIT_DELAY * (attempt + 1)  # Increasing delay for rate limits
                        print(f"\n  Rate limited, waiting {delay}s before retry {attempt + 1}/{retries}...")
                        await asyncio.sleep(delay)
                    continue

                # Don't retry on other 4xx errors (client errors)
                if 400 <= e.response.status_code < 500:
                    break

                if attempt < retries:
                    delay = RETRY_DELAY * (2 ** attempt)
                    await asyncio.sleep(delay)

            except Exception as e:
                last_error = str(e)
                if attempt < retries:
                    delay = RETRY_DELAY * (2 ** attempt)
                    await asyncio.sleep(delay)

        return {"error": last_error}


def load_variants(filepath: Path) -> list[dict]:
    """Load variants from JSONL file."""
    variants = []
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                variants.append(json.loads(line))
    return variants


def get_variant_data(variant: dict) -> dict:
    """Extract variant data for API call with smart fallback."""
    cand = variant.get("variation", "").strip()
    if not cand or cand.lower() in ("single allele", "none", "n/a"):
        cand = None

    exprs = variant.get("hgvs_expressions", [])
    GRCH37_NC_VERSIONS = {
        "NC_000001.10", "NC_000002.11", "NC_000003.11", "NC_000004.11", "NC_000005.9", "NC_000006.11",
        "NC_000007.13", "NC_000008.10", "NC_000009.11", "NC_000010.10", "NC_000011.9", "NC_000012.11",
        "NC_000013.10", "NC_000014.8", "NC_000015.9", "NC_000016.9", "NC_000017.10", "NC_000018.9",
        "NC_000019.9", "NC_000020.10", "NC_000021.8", "NC_000022.10", "NC_000023.10", "NC_000024.9"
    }

    def is_clean(s: str) -> bool:
        return bool(s and "(" not in s and ")" not in s and "[" not in s and "]" not in s and not s.startswith("NR_"))

    # 1. Look for clean GRCh37 NC expressions first (most reliable for genomic mapping on GRCh37)
    for e in exprs:
        if e.startswith("NC_") and is_clean(e):
            acc = e.split(":")[0]
            if acc in GRCH37_NC_VERSIONS:
                return {"hgvs": e}

    # 2. Look for clean NM_ coding transcript expressions
    for e in exprs:
        if e.startswith("NM_") and is_clean(e) and (":c." in e or ":g." in e):
            return {"hgvs": e}

    # 3. Clean candidate variation if clean
    if cand and is_clean(cand) and (":c." in cand or ":g." in cand):
        return {"hgvs": cand.split(" ")[0].strip()}

    # 4. Any other clean expression
    for e in exprs:
        if is_clean(e) and (":c." in e or ":g." in e):
            return {"hgvs": e}

    # 5. Fallback to variant_key coordinates
    if variant.get("variant_key"):
        parts = variant["variant_key"].split(":")
        if len(parts) == 4:
            return {
                "chromosome": parts[0].replace("chr", ""),
                "position": int(parts[1]),
                "ref": parts[2],
                "alt": parts[3]
            }

    return {}


def already_classified(paths, model: Optional[str] = None) -> set[str]:
    """
    variant_ids a previous run classified without error, for this model.
    Read from the result files themselves so coverage cannot drift out of sync
    with what is actually on disk. A run that half-finished still counts for the
    rows it wrote. Rows with an error are not counted, so they get retried.
    """
    done = set()
    files = []
    for path in paths:
        path = Path(path)
        if path.is_dir():
            files.extend(sorted(path.glob("*.jsonl")))
        elif path.exists():
            files.append(path)
    for path in files:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cls = rec.get("aiva_classification")
                if rec.get("error") or not cls or cls == "Not classified":
                    continue
                if model and rec.get("model_used") != model:
                    continue
                if rec.get("variant_id"):
                    done.add(rec["variant_id"])
    return done


async def classify_batch(
    client: AIVAClient,
    variants: list[dict],
    concurrency: int = CONCURRENCY_LIMIT,
    model: Optional[str] = None,
    progress_callback=None,
    sink=None
) -> list[dict]:
    """
    Classify a batch of variants with concurrency control.

    Args:
        client: AIVA API client
        variants: List of variant dicts from parsed JSONL
        concurrency: Max concurrent requests
        model: LLM model to use for classification
        progress_callback: Optional callback(completed, total)
        sink: Optional open file handle for real-time streaming results.

    Returns:
        List of result dicts
    """
    semaphore = asyncio.Semaphore(concurrency)
    sink_lock = asyncio.Lock()
    results = []
    completed = 0

    async def emit(res: dict):
        if sink is not None:
            async with sink_lock:
                sink.write(json.dumps(res) + "\n")
                sink.flush()

    async def classify_one(variant: dict) -> dict:
        nonlocal completed

        async with semaphore:
            start_time = time.time()

            variant_data = get_variant_data(variant)
            if not variant_data:
                res = {
                    "variant_id": variant.get("id"),
                    "variant": variant.get("variation"),
                    "error": "No valid variant identifier",
                    "execution_time_ms": 0
                }
                await emit(res)
                return res

            response = await client.classify_variant(
                variant_data=variant_data,
                model=model,
                phenotype_terms=variant.get("disease"),
                description=f"Gene: {variant.get('gene_symbol', 'Unknown')}",
                additional_context=f"Mode of inheritance: {variant.get('mode_of_inheritance', 'Unknown')}"
            )

            execution_time = int((time.time() - start_time) * 1000)

            result = {
                "variant_id": variant.get("id"),
                "variant": variant.get("variation"),
                "gene": variant.get("gene_symbol"),
                "disease": variant.get("disease"),
                "ground_truth": variant.get("classification"),
                "ground_truth_criteria": variant.get("criteria_met", []),
                "expert_panel": variant.get("expert_panel"),
                "execution_time_ms": execution_time,
                "model_used": model
            }

            if "error" in response:
                result["error"] = response["error"]
            else:
                data = response.get("data", response)
                result["aiva_classification"] = data.get("classification")
                result["aiva_confidence"] = data.get("confidence")
                result["aiva_criteria"] = data.get("criteria_met", [])
                result["aiva_evidence"] = data.get("evidence_summary", {})

            await emit(result)

            completed += 1
            if progress_callback:
                progress_callback(completed, len(variants))

            await asyncio.sleep(1)
            return result

    tasks = [classify_one(v) for v in variants]
    results = await asyncio.gather(*tasks)
    return results


def save_results(results: list[dict], output_path: Path):
    """Save classification results to JSONL file."""
    with open(output_path, "w", encoding="utf-8") as f:
        for r in results:
            f.write(json.dumps(r) + "\n")
    print(f"Saved {len(results)} results to {output_path}")


async def main():
    parser = argparse.ArgumentParser(description="Classify variants using AIVA API")
    parser.add_argument("--input", help="Input JSONL file with variants")
    parser.add_argument("--output", help="Output JSONL file for results")
    parser.add_argument("--concurrency", type=int, default=CONCURRENCY_LIMIT,
                        help=f"Max concurrent requests (default: {CONCURRENCY_LIMIT})")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help="LLM model to use (e.g., openai/gpt-4o, google/gemini-2.5-flash)")
    parser.add_argument("--limit", type=int, help="Limit number of variants to classify")
    parser.add_argument("--api-url", default=AIVA_API_URL, help="AIVA API URL")
    parser.add_argument("--no-resume", action="store_true",
                        help="classify every input row, even ones already done, and overwrite the output file")
    parser.add_argument("--skip-dir", action="append",
                        help="extra results dir or file whose variants count as done (repeatable; default: the output's directory)")

    args = parser.parse_args()

    # Find input file
    if args.input:
        input_path = Path(args.input)
    else:
        sample_files = list(DATA_DIR.glob("sample_*.jsonl"))
        if not sample_files:
            print("Error: No sample files found. Run parse_erepo.py first.")
            sys.exit(1)
        input_path = max(sample_files, key=lambda p: p.stat().st_mtime)
        print(f"Using most recent sample: {input_path}")

    # Load variants
    variants = load_variants(input_path)
    print(f"Loaded {len(variants)} variants")

    # Setup output path
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if args.output:
        output_path = Path(args.output)
    else:
        output_path = RESULTS_DIR / f"classifications_{timestamp}.jsonl"

    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Check for already classified variants to resume
    write_mode = "w" if args.no_resume else "a"
    if not args.no_resume:
        sources = [output_path.parent]
        if args.skip_dir:
            sources.extend(args.skip_dir)
        done = already_classified(sources, model=args.model)
        if done:
            print(f"Already done for {args.model or 'AIVA default'}: {len(done)} (from {', '.join(str(s) for s in sources)})")
            variants = [v for v in variants if v.get("id") not in done]
            if not variants:
                print("Nothing left to classify.")
                return

    if args.limit:
        variants = variants[:args.limit]
        print(f"Limited to {len(variants)} variants")

    print(f"To classify: {len(variants)}")

    # Check for API token
    if not AIVA_API_TOKEN:
        print("Error: AIVA_API_TOKEN not set. Add it to .env file.")
        sys.exit(1)

    # Progress callback
    def show_progress(completed: int, total: int):
        pct = 100 * completed / total
        print(f"\rProgress: {completed}/{total} ({pct:.1f}%)", end="", flush=True)

    # Run classifications
    model_display = args.model or "AIVA default"
    print(f"\nClassifying variants (concurrency={args.concurrency}, model={model_display})...")
    start_time = time.time()

    with open(output_path, write_mode, encoding="utf-8") as sink:
        async with AIVAClient(base_url=args.api_url) as client:
            results = await classify_batch(
                client, variants,
                concurrency=args.concurrency,
                model=args.model,
                progress_callback=show_progress,
                sink=sink
            )

    elapsed = time.time() - start_time
    print(f"\n\nCompleted in {elapsed:.1f}s ({elapsed/len(variants):.1f}s per variant)")
    verb = "Wrote" if write_mode == "w" else "Appended"
    print(f"{verb} {len(results)} results to {output_path}")

    # Quick stats
    errors = sum(1 for r in results if r.get("error"))
    successful = len(results) - errors
    print(f"\nResults: {successful} successful, {errors} errors")

    if successful > 0:
        avg_time = sum(r["execution_time_ms"] for r in results if not r.get("error")) / successful
        print(f"Average execution time: {avg_time:.0f}ms")

    print(f"\nRun benchmark.py to calculate metrics:\n  python scripts/benchmark.py --input {output_path}")


if __name__ == "__main__":
    asyncio.run(main())
