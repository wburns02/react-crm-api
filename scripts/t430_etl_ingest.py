#!/usr/bin/env python3
"""
T430 ETL: crm_permits.db → Railway PostgreSQL via batch API.

Maps SQLite crm_permits.db (3.58M records) to PermitCreate schema
and sends 5,000-record batches to POST /api/v2/permits/batch.

Usage:
    python scripts/t430_etl_ingest.py --db /path/to/crm_permits.db [--api-url URL] [--batch-size N]
"""

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, date
from pathlib import Path

import requests

# Default production API
DEFAULT_API_URL = "https://react-crm-api-production.up.railway.app/api/v2"
DEFAULT_BATCH_SIZE = 5000

# Login credentials
LOGIN_EMAIL = "will@macseptic.com"
LOGIN_PASSWORD = "#Espn2025"

# Septic-related trades to keep (filter out non-septic permits)
SEPTIC_TRADES = {
    "septic", "ossf", "on-site sewage", "onsite sewage",
    "wastewater", "sewer", "plumbing", "mechanical",
    "environmental", "health", "sanitation",
}

# Field mapping: crm_permits.db → PermitCreate
# crm_permits.db columns:
#   id, permit_number, original_id, jurisdiction_id, jurisdiction_name,
#   state, project_type_id, project_type, work_type, trade, status,
#   status_id, created_date, issued_date, expired_date, completed_date,
#   address, apt_lot, city, zip, lat, lng, parcel_id, subdivision, lot,
#   owner_name, applicant_name, applicant_company, project_name,
#   description, ossf_details, source, source_file, scraped_at, raw_original


def parse_date(date_str: str | None) -> str | None:
    """Parse various date formats to YYYY-MM-DD."""
    if not date_str or date_str.strip() == "":
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S"):
        try:
            return datetime.strptime(date_str.strip(), fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def parse_datetime(dt_str: str | None) -> str | None:
    """Parse datetime string to ISO format."""
    if not dt_str or dt_str.strip() == "":
        return None
    for fmt in ("%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(dt_str.strip(), fmt).isoformat()
        except ValueError:
            continue
    return None


def parse_system_type(ossf_details: str | None, description: str | None) -> str | None:
    """Extract system type from ossf_details or description."""
    text = (ossf_details or "") + " " + (description or "")
    text_lower = text.lower()

    if "aerobic" in text_lower:
        return "Aerobic Treatment Unit"
    elif "conventional" in text_lower:
        return "Conventional Septic"
    elif "mound" in text_lower:
        return "Mound System"
    elif "drip" in text_lower:
        return "Drip Irrigation"
    elif "spray" in text_lower:
        return "Spray Distribution"
    elif "low pressure" in text_lower or "lpd" in text_lower:
        return "Low Pressure Dosing"
    elif "evapotranspiration" in text_lower or "et " in text_lower:
        return "Evapotranspiration"
    elif "cluster" in text_lower:
        return "Cluster System"
    elif "cesspool" in text_lower:
        return "Cesspool"
    elif "grease" in text_lower:
        return "Grease Trap"
    elif "holding" in text_lower:
        return "Holding Tank"
    elif "septic" in text_lower:
        return "Standard Septic"
    return None


def map_row_to_permit(row: dict) -> dict | None:
    """Map a crm_permits.db row to PermitCreate schema."""
    state = (row.get("state") or "").strip().upper()
    if not state or len(state) != 2:
        return None

    # Use issued_date first, fall back to created_date
    permit_date = parse_date(row.get("issued_date")) or parse_date(row.get("created_date"))

    # Build source portal code from source field
    source = row.get("source") or "t430_crm_permits"
    source_portal_code = f"t430_{source}".replace(" ", "_").lower()[:100]

    permit = {
        "state_code": state,
        "county_name": row.get("jurisdiction_name"),
        "permit_number": row.get("permit_number"),
        "address": row.get("address"),
        "city": row.get("city"),
        "zip_code": row.get("zip"),
        "parcel_number": row.get("parcel_id"),
        "latitude": row.get("lat"),
        "longitude": row.get("lng"),
        "owner_name": row.get("owner_name"),
        "applicant_name": row.get("applicant_name") or row.get("applicant_company"),
        "permit_date": permit_date,
        "expiration_date": parse_date(row.get("expired_date")),
        "system_type": parse_system_type(row.get("ossf_details"), row.get("description")),
        "source_portal_code": source_portal_code,
        "scraped_at": parse_datetime(row.get("scraped_at")) or datetime.now().isoformat(),
        "raw_data": {
            "original_id": row.get("original_id"),
            "trade": row.get("trade"),
            "project_type": row.get("project_type"),
            "work_type": row.get("work_type"),
            "status": row.get("status"),
            "description": row.get("description"),
            "ossf_details": row.get("ossf_details"),
            "subdivision": row.get("subdivision"),
            "lot": row.get("lot"),
            "apt_lot": row.get("apt_lot"),
            "source_file": row.get("source_file"),
        },
    }

    # Clean up None values in raw_data
    permit["raw_data"] = {k: v for k, v in permit["raw_data"].items() if v is not None}

    # Clean up lat/lng
    if permit["latitude"] is not None:
        try:
            permit["latitude"] = float(permit["latitude"])
            if not (-90 <= permit["latitude"] <= 90):
                permit["latitude"] = None
        except (ValueError, TypeError):
            permit["latitude"] = None

    if permit["longitude"] is not None:
        try:
            permit["longitude"] = float(permit["longitude"])
            if not (-180 <= permit["longitude"] <= 180):
                permit["longitude"] = None
        except (ValueError, TypeError):
            permit["longitude"] = None

    return permit


def login(session: requests.Session, api_url: str) -> str:
    """Login and get session cookie."""
    print(f"Logging in to {api_url}...")
    resp = session.post(
        f"{api_url}/auth/login",
        json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
    )
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text}")
        sys.exit(1)
    print("Login successful")
    return resp.cookies.get("session", "")


def send_batch(session: requests.Session, api_url: str, permits: list, source_code: str, batch_num: int, total_batches: int) -> dict:
    """Send a batch of permits to the API."""
    payload = {
        "source_portal_code": source_code,
        "permits": permits,
    }

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


def main():
    parser = argparse.ArgumentParser(description="ETL crm_permits.db → Railway PostgreSQL")
    parser.add_argument("--db", required=True, help="Path to crm_permits.db")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API base URL")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Records per batch")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N records (for resume)")
    parser.add_argument("--limit", type=int, default=0, help="Max records to process (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Map records but don't send to API")
    parser.add_argument("--source-code", default="t430_crm_permits", help="Source portal code")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    # Connect to SQLite
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Get total count
    cursor.execute("SELECT COUNT(*) FROM permits")
    total_records = cursor.fetchone()[0]
    print(f"Total records in database: {total_records:,}")

    if args.limit > 0:
        process_count = min(args.limit, total_records - args.offset)
    else:
        process_count = total_records - args.offset

    total_batches = (process_count + args.batch_size - 1) // args.batch_size
    print(f"Processing {process_count:,} records in {total_batches} batches of {args.batch_size}")

    # Setup API session
    session = requests.Session()
    if not args.dry_run:
        login(session, args.api_url)

    # Process in batches
    batch_num = 0
    total_inserted = 0
    total_updated = 0
    total_skipped = 0
    total_errors = 0
    total_mapped = 0
    total_unmapped = 0
    start_time = time.time()

    query = "SELECT * FROM permits LIMIT ? OFFSET ?"
    offset = args.offset

    while offset < args.offset + process_count:
        batch_num += 1
        remaining = args.offset + process_count - offset
        current_batch_size = min(args.batch_size, remaining)

        cursor.execute(query, (current_batch_size, offset))
        rows = cursor.fetchall()

        if not rows:
            break

        # Map rows to PermitCreate
        permits = []
        for row in rows:
            mapped = map_row_to_permit(dict(row))
            if mapped:
                permits.append(mapped)
                total_mapped += 1
            else:
                total_unmapped += 1

        if permits and not args.dry_run:
            result = send_batch(session, args.api_url, permits, args.source_code, batch_num, total_batches)
            stats = result.get("stats", {})
            total_inserted += stats.get("inserted", 0)
            total_updated += stats.get("updated", 0)
            total_skipped += stats.get("skipped", 0)
            total_errors += stats.get("errors", 0)
        elif args.dry_run:
            print(f"  Batch {batch_num}/{total_batches}: {len(permits)} permits mapped (dry run)")

        offset += current_batch_size

        # Progress update every 10 batches
        if batch_num % 10 == 0:
            elapsed = time.time() - start_time
            rate = (offset - args.offset) / elapsed if elapsed > 0 else 0
            eta = (process_count - (offset - args.offset)) / rate if rate > 0 else 0
            print(f"\n  === Progress: {offset - args.offset:,}/{process_count:,} ({(offset - args.offset) / process_count * 100:.1f}%) | {rate:.0f} rec/s | ETA: {eta / 60:.1f} min ===\n")

    elapsed = time.time() - start_time
    conn.close()

    # Final report
    print("\n" + "=" * 60)
    print("ETL COMPLETE")
    print("=" * 60)
    print(f"Time: {elapsed / 60:.1f} minutes ({elapsed:.0f} seconds)")
    print(f"Records processed: {total_mapped + total_unmapped:,}")
    print(f"  Mapped successfully: {total_mapped:,}")
    print(f"  Unmapped (bad state): {total_unmapped:,}")
    if not args.dry_run:
        print(f"  Inserted: {total_inserted:,}")
        print(f"  Updated: {total_updated:,}")
        print(f"  Skipped (dupes): {total_skipped:,}")
        print(f"  Errors: {total_errors:,}")
    print(f"Batches: {batch_num}")
    print(f"Rate: {(total_mapped + total_unmapped) / elapsed:.0f} records/second" if elapsed > 0 else "")


if __name__ == "__main__":
    main()
