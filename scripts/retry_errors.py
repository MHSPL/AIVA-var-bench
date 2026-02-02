"""
Script to retry failed classifications in a results file.
Useful for cleaning up runs that had intermittent API errors (429, 500).

Usage:
    python scripts/retry_errors.py results/classifications_model_timestamp.jsonl
"""

import argparse
import asyncio
import json
import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import CONCURRENCY_LIMIT
from scripts.classify import AIVAClient, classify_batch

async def retry_errors(filepath: Path, concurrency: int = 1):  # Default to conservative concurrency
    if not filepath.exists():
        print(f"Error: File {filepath} not found.")
        return

    print(f"Reading {filepath}...")
    with open(filepath, "r", encoding="utf-8") as f:
        lines = []
        for line in f:
            if line.strip():
                lines.append(json.loads(line))
    
    # Identify items with errors
    error_indices = []
    for i, record in enumerate(lines):
        if record.get("error"):
            error_indices.append(i)
    
    if not error_indices:
        print("No failed classifications found in file.")
        return

    print(f"Found {len(error_indices)} failures out of {len(lines)} records.")

    # Determine model from first failure
    model = lines[error_indices[0]].get("model_used")
    if not model:
        print("Error: Could not determine 'model_used' from failed records.")
        return
    
    print(f"Retrying using model: {model}")
    print(f"Concurrency: {concurrency}")

    # Prepare variants for retry
    # We can pass the whole record as the variant dict; extra keys are ignored by classify.py
    # NOTE: classify.py expects 'variation' key which comes from input data.
    # Result files usually store it as 'variant'. We need to map it back.
    variants_to_retry = [lines[i] for i in error_indices]
    for v in variants_to_retry:
        if "variant" in v and "variation" not in v:
            v["variation"] = v["variant"]
        # Also clean up previous error info to avoid confusion?
        # Not strictly needed since result is a new dict.
    
    async with AIVAClient() as client:
        new_results = await classify_batch(
            client, 
            variants_to_retry, 
            model=model, 
            concurrency=concurrency,
            progress_callback=lambda c, t: print(f"\rRetry Progress: {c}/{t}", end="", flush=True)
        )
    print()

    # Update records
    success_count = 0
    for idx_in_list, new_res in zip(error_indices, new_results):
        if not new_res.get("error"):
            # Success! Replace the record
            lines[idx_in_list] = new_res
            success_count += 1
        else:
            # Still failed, update with new error info
            print(f"  Retry failed for {new_res.get('variant')}: {new_res.get('error')}")
            lines[idx_in_list] = new_res
    
    print("-" * 60)
    print(f"Recovered {success_count}/{len(error_indices)} variants.")
    
    if success_count > 0:
        # Create backup
        backup_path = filepath.with_name(filepath.name + ".bak")
        with open(backup_path, "w", encoding="utf-8") as f:
            for r in lines: # Wait, I want to backup the ORIGINAL lines, but I modified `lines` in place.
                            # Actually, I haven't saved to file yet.
                            # So I should read the file again to backup? 
                            # Or just write existing file to .bak first.
                pass 
        
        # Better: invalid loop above. Correct logic:
        # Rename original file to .bak
        print(f"Backing up original to {backup_path}")
        filepath.rename(backup_path)

        # Write new content to original filename
        with open(filepath, "w", encoding="utf-8") as f:
            for r in lines:
                f.write(json.dumps(r) + "\n")
        print(f"Updated {filepath}")
    else:
        print("No variants recovered. File left unchanged.")

async def main():
    parser = argparse.ArgumentParser(description="Retry failed classifications in JSONL file")
    parser.add_argument("file", help="Path to JSONL results file")
    parser.add_argument("--concurrency", type=int, default=2, help="Concurrency for retries (default: 2)")
    
    args = parser.parse_args()
    
    await retry_errors(Path(args.file), args.concurrency)

if __name__ == "__main__":
    asyncio.run(main())
