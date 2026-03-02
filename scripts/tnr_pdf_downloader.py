#!/usr/bin/env python3
"""
TNR PDF Downloader: Downloads septic permit PDFs from the Travis County
TNR Public Access Portal. Stores PDFs on the T430 dataPool.

API: GET https://tcobweb.traviscountytx.gov/PublicAccess/api/Document/{encodedDocId}/

Source metadata: /mnt/win11/fedora-moved/Data/tnr_septic_metadata.ndjson
Output: T430:/dataPool/data/records/tnr_septic_pdfs/

Usage (run on local machine, saves to T430 via SSH):
    python scripts/tnr_pdf_downloader.py --dry-run
    python scripts/tnr_pdf_downloader.py --workers 4
    python scripts/tnr_pdf_downloader.py --resume
"""

import argparse
import json
import os
import subprocess
import sys
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import requests

# ── Config ──────────────────────────────────────────────────────────────────

DEFAULT_NDJSON_PATH = "/mnt/win11/fedora-moved/Data/tnr_septic_metadata.ndjson"
T430_HOST = "will@100.122.216.15"
T430_PDF_DIR = "/dataPool/data/records/tnr_septic_pdfs"
CHECKPOINT_FILE = "/mnt/win11/fedora-moved/Data/tnr_pdf_checkpoint.json"

TNR_API_BASE = "https://tcobweb.traviscountytx.gov/PublicAccess/api"
TNR_DOC_ENDPOINT = "/Document/"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Referer": "https://tcobweb.traviscountytx.gov/PublicAccess/",
    "Accept": "application/pdf, application/octet-stream, */*",
}

DELAY_BETWEEN_REQUESTS = 0.5  # seconds


# ── Helpers ─────────────────────────────────────────────────────────────────

def load_checkpoint() -> set:
    """Load set of already-downloaded document IDs."""
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            data = json.load(f)
            return set(data.get("downloaded", []))
    return set()


def save_checkpoint(downloaded: set):
    """Save checkpoint of downloaded document IDs."""
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump({"downloaded": list(downloaded), "count": len(downloaded)}, f)


def sanitize_filename(doc_id: str) -> str:
    """Create a safe filename from document ID."""
    # Use a hash-like approach: replace special chars
    safe = doc_id.replace("/", "_").replace("\\", "_").replace("=", "")
    safe = safe.replace("+", "p").replace(" ", "_")
    # Truncate to reasonable length
    if len(safe) > 80:
        import hashlib
        safe = hashlib.md5(doc_id.encode()).hexdigest()
    return safe + ".pdf"


def download_pdf(session: requests.Session, doc_id: str) -> bytes | None:
    """Download a single PDF from the TNR portal."""
    encoded_id = urllib.parse.quote(doc_id, safe="")
    url = f"{TNR_API_BASE}{TNR_DOC_ENDPOINT}{encoded_id}/"

    try:
        resp = session.get(url, headers=HEADERS, timeout=30)
        if resp.status_code == 200 and len(resp.content) > 100:
            return resp.content
        else:
            return None
    except Exception as e:
        print(f"  Error downloading {doc_id[:40]}: {e}")
        return None


def scp_to_t430(local_path: str, remote_path: str) -> bool:
    """SCP a file to the T430."""
    try:
        result = subprocess.run(
            ["scp", "-o", "ConnectTimeout=10", "-q", local_path, f"{T430_HOST}:{remote_path}"],
            capture_output=True, timeout=30
        )
        return result.returncode == 0
    except Exception:
        return False


def ssh_cmd(cmd: str) -> str:
    """Run a command on T430 via SSH."""
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", T430_HOST, cmd],
            capture_output=True, text=True, timeout=30
        )
        return result.stdout.strip()
    except Exception as e:
        return f"ERROR: {e}"


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Download TNR septic PDFs to T430")
    parser.add_argument("--ndjson-path", default=DEFAULT_NDJSON_PATH)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--limit", type=int, default=0, help="Max PDFs to download (0 = all)")
    parser.add_argument("--resume", action="store_true", help="Resume from checkpoint")
    parser.add_argument("--batch-size", type=int, default=100,
                        help="PDFs per SCP batch transfer")
    args = parser.parse_args()

    # Load metadata
    print(f"Loading {args.ndjson_path}...")
    records = []
    with open(args.ndjson_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))
    print(f"Total document records: {len(records):,}")

    # Deduplicate by documentId
    seen = set()
    unique_records = []
    for r in records:
        doc_id = r.get("documentId", "")
        if doc_id and doc_id not in seen:
            seen.add(doc_id)
            unique_records.append(r)
    print(f"Unique documents: {len(unique_records):,}")

    # Resume support
    downloaded = set()
    if args.resume:
        downloaded = load_checkpoint()
        print(f"Resuming: {len(downloaded):,} already downloaded")

    # Filter out already downloaded
    to_download = [r for r in unique_records if r["documentId"] not in downloaded]
    print(f"Remaining to download: {len(to_download):,}")

    if args.limit > 0:
        to_download = to_download[:args.limit]
        print(f"Limited to: {len(to_download):,}")

    if args.dry_run:
        print("\nDRY RUN — would download:")
        print(f"  {len(to_download):,} PDFs")
        est_size_gb = len(to_download) * 0.5 / 1024  # ~500KB avg per PDF
        print(f"  Estimated size: ~{est_size_gb:.1f} GB")
        return

    # Create remote directory
    print(f"\nCreating {T430_PDF_DIR} on T430...")
    ssh_cmd(f"mkdir -p {T430_PDF_DIR}")

    # Create local temp dir for batching
    import tempfile
    tmp_dir = tempfile.mkdtemp(prefix="tnr_pdfs_")
    print(f"Temp staging dir: {tmp_dir}")

    session = requests.Session()
    total = len(to_download)
    success = 0
    failed = 0
    batch_files = []
    batch_doc_ids = []
    start_time = time.time()

    for i, record in enumerate(to_download):
        doc_id = record["documentId"]
        filename = sanitize_filename(doc_id)
        local_path = os.path.join(tmp_dir, filename)

        # Download
        pdf_data = download_pdf(session, doc_id)
        if pdf_data:
            with open(local_path, "wb") as f:
                f.write(pdf_data)
            batch_files.append(local_path)
            batch_doc_ids.append(doc_id)
            success += 1
        else:
            failed += 1

        # Rate limit
        time.sleep(DELAY_BETWEEN_REQUESTS)

        # Batch transfer to T430 every N files
        if len(batch_files) >= args.batch_size or (i == total - 1 and batch_files):
            print(f"  [{i+1}/{total}] Transferring {len(batch_files)} PDFs to T430...")
            # Use rsync for batch transfer
            try:
                result = subprocess.run(
                    ["rsync", "-az", "--timeout=30"] + batch_files + [f"{T430_HOST}:{T430_PDF_DIR}/"],
                    capture_output=True, timeout=120
                )
                if result.returncode == 0:
                    # Update checkpoint with all doc_ids in this batch
                    for did in batch_doc_ids:
                        downloaded.add(did)
                    save_checkpoint(downloaded)
                    # Clean up local files
                    for bf in batch_files:
                        os.unlink(bf)
                    batch_files = []
                    batch_doc_ids = []
                else:
                    print(f"  rsync failed: {result.stderr.decode()[:200]}")
            except Exception as e:
                print(f"  Transfer error: {e}")

        # Progress
        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            eta = (total - i - 1) / rate if rate > 0 else 0
            print(f"  Progress: {i+1}/{total} ({success} ok, {failed} failed) "
                  f"Rate: {rate:.1f}/s, ETA: {eta/60:.0f}min")

    # Final checkpoint
    save_checkpoint(downloaded)

    # Cleanup temp dir
    import shutil
    shutil.rmtree(tmp_dir, ignore_errors=True)

    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("TNR PDF Download — RESULTS")
    print("=" * 60)
    print(f"Time: {elapsed:.0f}s")
    print(f"Downloaded: {success:,}")
    print(f"Failed: {failed:,}")
    print(f"Total on T430: {len(downloaded):,}")
    print(f"Stored at: {T430_HOST}:{T430_PDF_DIR}")
    print("=" * 60)


if __name__ == "__main__":
    main()
