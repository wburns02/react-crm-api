#!/usr/bin/env python3
"""
Travis County TNR (Texas Natural Resources) Portal ETL: Ingest ~9,366 unique
septic/OSSF property records from the TNR Public Access Portal NDJSON
(scraped Jan 2026, document-level metadata from historical PSF permits).

Source: /mnt/win11/fedora-moved/Data/tnr_septic_metadata.ndjson

The TNR data is document-level (16,021 docs for 9,366 unique addresses).
This ETL deduplicates to one record per address, using the earliest document
date as the permit date and aggregating document descriptions.

Date range: 1993-2013 (historical records predating MGO dataset)

Usage:
    python scripts/travis_tnr_etl.py --dry-run
    python scripts/travis_tnr_etl.py --batch-size 2500
"""

import argparse
import json
import re
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ── Config ──────────────────────────────────────────────────────────────────

DEFAULT_NDJSON_PATH = "/mnt/win11/fedora-moved/Data/tnr_septic_metadata.ndjson"
DEFAULT_API_URL = "https://react-crm-api-production.up.railway.app/api/v2"
DEFAULT_BATCH_SIZE = 2500
SOURCE_PORTAL_CODE = "tnr_travis_county"

LOGIN_EMAIL = "will@macseptic.com"
LOGIN_PASSWORD = "#Espn2025"

# ── System Type Extraction ─────────────────────────────────────────────────

KEYWORD_SYSTEM_TYPES = [
    ("aerobic", "Aerobic Treatment Unit"),
    ("conventional", "Conventional Septic"),
    ("mound", "Mound System"),
    ("drip", "Drip Irrigation"),
    ("spray", "Spray Distribution"),
    ("surface application", "Surface Application"),
    ("surface irrigation", "Surface Application"),
    ("low pressure", "Low Pressure Dosing"),
    ("lpd", "Low Pressure Dosing"),
    ("evapotranspiration", "Evapotranspiration"),
    ("leaching chamber", "Leaching Chambers"),
    ("cluster", "Cluster System"),
    ("cesspool", "Cesspool"),
    ("grease", "Grease Trap"),
    ("holding", "Holding Tank"),
    ("standard subsurface", "Standard Septic"),
    ("standard trench", "Standard Septic"),
    ("septic", "Standard Septic"),
]


# ── Deduplication & Mapping ────────────────────────────────────────────────

def dedup_records(records: list[dict]) -> list[dict]:
    """Deduplicate document-level records to one per address.

    Groups by (streetNumber, streetName), keeps earliest date,
    aggregates document descriptions.
    """
    by_addr: dict[str, list[dict]] = {}
    for r in records:
        num = (r.get("streetNumber") or "").strip()
        name = (r.get("streetName") or "").strip()
        addr = f"{num} {name}".strip()
        if not addr:
            continue
        by_addr.setdefault(addr, []).append(r)

    deduped = []
    for addr, docs in by_addr.items():
        # Sort by date (earliest first)
        def parse_date(d):
            try:
                return datetime.strptime(d.get("documentDate", ""), "%m/%d/%Y")
            except (ValueError, TypeError):
                return datetime.max

        docs.sort(key=parse_date)
        earliest = docs[0]

        # Aggregate all document descriptions
        all_descs = [d.get("documentDescription", "") for d in docs if d.get("documentDescription")]

        deduped.append({
            "streetNumber": earliest.get("streetNumber", ""),
            "streetName": earliest.get("streetName", ""),
            "address": addr,
            "documentDate": earliest.get("documentDate", ""),
            "documentDateRaw": earliest.get("documentDateRaw"),
            "documentId": earliest.get("documentId", ""),
            "documentName": earliest.get("documentName", ""),
            "all_descriptions": all_descs,
            "doc_count": len(docs),
            "_queryMonth": earliest.get("_queryMonth", ""),
        })

    return deduped


def map_row(row: dict) -> dict | None:
    """Map a deduplicated TNR record to PermitCreate schema."""

    address = row.get("address", "").strip()
    if not address:
        return None

    # Parse document date: "1/15/1993"
    permit_date = None
    scraped_at = datetime.now().isoformat()
    dd = row.get("documentDate", "")
    if dd:
        for fmt in ("%m/%d/%Y", "%m/%d/%y"):
            try:
                permit_date = datetime.strptime(dd.strip(), fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    # System type from all document descriptions
    text = " ".join(row.get("all_descriptions", [])).lower()
    system_type = None
    for keyword, st in KEYWORD_SYSTEM_TYPES:
        if keyword in text:
            system_type = st
            break

    # Build raw_data
    raw_data = {
        "source": "TNR Public Access Portal",
        "portal": "Travis County TNR",
        "doc_count": row.get("doc_count", 1),
    }
    if row.get("documentId"):
        raw_data["document_id"] = row["documentId"][:200]
    if row.get("all_descriptions"):
        raw_data["document_descriptions"] = row["all_descriptions"][:10]
    if row.get("_queryMonth"):
        raw_data["query_month"] = row["_queryMonth"]
    if system_type:
        raw_data["system_type_source"] = "keyword"

    # Quality score
    score = 0
    if address:
        score += 20
    if permit_date:
        score += 5
    if system_type:
        score += 8
    if row.get("doc_count", 1) > 1:
        score += 5  # Multiple docs = more confidence
    raw_data["quality_score"] = min(score, 100)

    return {
        "state_code": "TX",
        "county_name": "Travis County",
        "permit_number": None,  # TNR data has no permit numbers
        "address": address,
        "city": None,
        "zip_code": None,
        "parcel_number": None,
        "latitude": None,
        "longitude": None,
        "owner_name": None,
        "applicant_name": None,
        "permit_date": permit_date,
        "expiration_date": None,
        "system_type": system_type,
        "daily_flow_gpd": None,
        "bedrooms": None,
        "source_portal_code": SOURCE_PORTAL_CODE,
        "scraped_at": scraped_at,
        "raw_data": raw_data,
    }


# ── API Helpers ─────────────────────────────────────────────────────────────

def login(session: requests.Session, api_url: str) -> None:
    print(f"Logging in to {api_url}...")
    resp = session.post(
        f"{api_url}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
    )
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    print("Login successful")


def send_batch(
    session: requests.Session,
    api_url: str,
    permits: list,
    batch_num: int,
    total_batches: int,
    max_retries: int = 3,
) -> dict:
    payload = {
        "source_portal_code": SOURCE_PORTAL_CODE,
        "permits": permits,
    }

    for attempt in range(max_retries):
        try:
            resp = session.post(
                f"{api_url}/permits/batch",
                json=payload,
                timeout=300,
            )

            if resp.status_code != 200:
                print(f"  Batch {batch_num}/{total_batches} FAILED: {resp.status_code}")
                try:
                    detail = resp.json().get("detail", resp.text[:200])
                except Exception:
                    detail = resp.text[:200]
                print(f"  Error: {detail}")
                if attempt < max_retries - 1:
                    wait = 5 * (attempt + 1)
                    print(f"  Retrying in {wait}s...")
                    time.sleep(wait)
                    continue
                return {"status": "failed", "error": detail}

            result = resp.json()
            stats = result.get("stats", {})
            print(
                f"  Batch {batch_num}/{total_batches}: "
                f"inserted={stats.get('inserted', 0)}, "
                f"updated={stats.get('updated', 0)}, "
                f"skipped={stats.get('skipped', 0)}, "
                f"errors={stats.get('errors', 0)}"
            )
            return result

        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            print(f"  Batch {batch_num}/{total_batches} connection error (attempt {attempt + 1}/{max_retries}): {e}")
            if attempt < max_retries - 1:
                wait = 10 * (attempt + 1)
                print(f"  Retrying in {wait}s...")
                time.sleep(wait)
                try:
                    login(session, api_url)
                except Exception:
                    pass
            else:
                return {"status": "failed", "error": str(e)}

    return {"status": "failed", "error": "Max retries exceeded"}


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Travis County TNR Portal ETL → Railway PostgreSQL"
    )
    parser.add_argument("--ndjson-path", default=DEFAULT_NDJSON_PATH, help="Path to NDJSON file")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API base URL")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=0, help="Max records (0 = all)")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    ndjson_path = Path(args.ndjson_path)
    if not ndjson_path.exists():
        print(f"NDJSON file not found: {ndjson_path}")
        sys.exit(1)

    # Load data (NDJSON = one JSON object per line)
    print(f"Loading {ndjson_path}...")
    raw_records = []
    with open(ndjson_path) as f:
        for line in f:
            line = line.strip()
            if line:
                raw_records.append(json.loads(line))
    print(f"Total document records in file: {len(raw_records):,}")

    # Deduplicate to one record per address
    deduped = dedup_records(raw_records)
    print(f"Unique addresses after dedup: {len(deduped):,}")

    if args.limit > 0:
        deduped = deduped[:args.limit]
        print(f"Limited to: {len(deduped):,}")

    # Map records
    permits = []
    unmapped = 0
    for row in deduped:
        mapped = map_row(row)
        if mapped:
            permits.append(mapped)
        else:
            unmapped += 1

    print(f"Mapped: {len(permits):,}, Unmapped (no address): {unmapped}")
    print()

    if not permits:
        print("No records to ingest.")
        return

    # Stats
    with_system_type = sum(1 for p in permits if p.get("system_type"))
    with_date = sum(1 for p in permits if p.get("permit_date"))

    print(f"── Extraction Stats ──")
    print(f"  permit_date:    {with_date:>6} ({with_date/len(permits)*100:.1f}%)")
    print(f"  system_type:    {with_system_type:>6} ({with_system_type/len(permits)*100:.1f}%)")
    print()

    # System type breakdown
    st_counts = {}
    for p in permits:
        st = p.get("system_type") or "(none)"
        st_counts[st] = st_counts.get(st, 0) + 1
    print("── System Types ──")
    for st, c in sorted(st_counts.items(), key=lambda x: -x[1])[:15]:
        print(f"  {c:>6}  {st}")
    print()

    # Date range
    dates = [p["permit_date"] for p in permits if p.get("permit_date")]
    if dates:
        print(f"── Date Range ──")
        print(f"  Earliest: {min(dates)}")
        print(f"  Latest:   {max(dates)}")
        print()

    if args.dry_run:
        print("DRY RUN — no data sent to API")
        return

    # Send to API
    session = requests.Session()
    login(session, args.api_url)
    print()

    total_batches = (len(permits) + args.batch_size - 1) // args.batch_size
    total_inserted = 0
    total_updated = 0
    total_skipped = 0
    total_errors = 0
    start_time = time.time()

    for batch_num in range(1, total_batches + 1):
        start_idx = (batch_num - 1) * args.batch_size
        end_idx = min(start_idx + args.batch_size, len(permits))
        batch = permits[start_idx:end_idx]

        result = send_batch(session, args.api_url, batch, batch_num, total_batches)
        stats = result.get("stats", {})
        total_inserted += stats.get("inserted", 0)
        total_updated += stats.get("updated", 0)
        total_skipped += stats.get("skipped", 0)
        total_errors += stats.get("errors", 0)

    elapsed = time.time() - start_time

    print()
    print("=" * 60)
    print("Travis County TNR Portal ETL — RESULTS")
    print("=" * 60)
    print(f"Time: {elapsed:.0f}s")
    print(f"Records sent: {len(permits):,}")
    print(f"  Inserted: {total_inserted:,}")
    print(f"  Updated:  {total_updated:,}")
    print(f"  Skipped:  {total_skipped:,}")
    print(f"  Errors:   {total_errors:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
