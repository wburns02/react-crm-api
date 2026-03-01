#!/usr/bin/env python3
"""
OCR ETL: adaptive_ocr.db → Railway PostgreSQL via batch API.

Maps OCR-extracted septic permit data from Guadalupe/Comal County PDFs
to PermitCreate schema and sends batches to POST /api/v2/permits/batch.

Usage:
    python scripts/ocr_etl_ingest.py --db /path/to/adaptive_ocr.db --source-name guadalupe_county_tx [--api-url URL]
"""

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# Default production API
DEFAULT_API_URL = "https://react-crm-api-production.up.railway.app/api/v2"
DEFAULT_BATCH_SIZE = 5000

# Login credentials
LOGIN_EMAIL = "will@macseptic.com"
LOGIN_PASSWORD = "#Espn2025"


def parse_date(date_str: str | None) -> str | None:
    """Parse various date formats to YYYY-MM-DD."""
    if not date_str or date_str.strip() == "":
        return None
    for fmt in ("%Y-%m-%d", "%m/%d/%Y", "%m-%d-%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%B %d, %Y", "%b %d, %Y"):
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


def parse_tank_size(raw: str | None) -> int | None:
    """Extract tank size in gallons from various formats."""
    if not raw:
        return None
    import re
    # Try to find a number followed by optional 'gal' or 'gallon'
    match = re.search(r'(\d{3,5})\s*(?:gal|gallon)?', raw.lower())
    if match:
        val = int(match.group(1))
        if 100 <= val <= 50000:  # reasonable tank size range
            return val
    return None


def classify_system_type(raw: str | None) -> str | None:
    """Classify OCR-extracted system type text into standard categories."""
    if not raw:
        return None
    text = raw.lower()

    if "aerobic" in text or "atu" in text:
        return "Aerobic Treatment Unit"
    elif "conventional" in text:
        return "Conventional Septic"
    elif "mound" in text:
        return "Mound System"
    elif "drip" in text:
        return "Drip Irrigation"
    elif "spray" in text:
        return "Spray Distribution"
    elif "low pressure" in text or "lpd" in text:
        return "Low Pressure Dosing"
    elif "evapotranspiration" in text or "et " in text:
        return "Evapotranspiration"
    elif "cluster" in text:
        return "Cluster System"
    elif "holding" in text:
        return "Holding Tank"
    elif "grease" in text:
        return "Grease Trap"
    elif "septic" in text:
        return "Standard Septic"
    return raw  # Return original if no match


def compute_quality_score(row: dict) -> int:
    """Compute data quality score 0-100 based on field completeness."""
    fields = [
        ("permit_number", 15),
        ("owner_name", 15),
        ("property_address", 20),
        ("city", 10),
        ("system_type", 10),
        ("tank_size_gallons", 5),
        ("permit_date", 10),
        ("installer_company", 5),
        ("owner_phone", 5),
        ("drainfield_type", 5),
    ]
    score = 0
    for field, weight in fields:
        val = row.get(field)
        if val and str(val).strip():
            score += weight
    return min(score, 100)


def map_ocr_row_to_permit(row: dict, source_name: str) -> dict | None:
    """Map an adaptive_ocr.db row to PermitCreate schema."""
    # Address is required for meaningful permit
    address = (row.get("property_address") or "").strip()
    if not address:
        return None

    # Parse county from source name
    county_name = None
    if "guadalupe" in source_name.lower():
        county_name = "Guadalupe"
    elif "comal" in source_name.lower():
        county_name = "Comal"

    # Build raw_data with all extra OCR fields
    raw_data = {}
    extra_fields = [
        "owner_phone", "drainfield_type", "soil_type", "gate_code",
        "lot_size", "bedrooms", "bathrooms", "daily_flow",
        "notes", "conditions", "inspector_name", "approval_date",
        "ocr_confidence", "source_pdf", "page_number",
    ]
    for f in extra_fields:
        val = row.get(f)
        if val and str(val).strip():
            raw_data[f] = str(val).strip()

    permit = {
        "state_code": "TX",
        "county_name": county_name,
        "permit_number": (row.get("permit_number") or "").strip() or None,
        "address": address,
        "city": (row.get("city") or "").strip() or None,
        "zip_code": (row.get("zip_code") or "").strip() or None,
        "owner_name": (row.get("owner_name") or "").strip() or None,
        "contractor_name": (row.get("installer_company") or "").strip() or None,
        "permit_date": parse_date(row.get("permit_date")),
        "install_date": parse_date(row.get("install_date")),
        "system_type": classify_system_type(row.get("system_type")),
        "tank_size_gallons": parse_tank_size(row.get("tank_size_gallons") or row.get("tank_size")),
        "source_portal_code": f"ocr_{source_name}",
        "scraped_at": parse_datetime(row.get("processed_at")) or datetime.now().isoformat(),
        "raw_data": raw_data if raw_data else None,
    }

    # Parse bedrooms from raw_data
    bedrooms_str = row.get("bedrooms")
    if bedrooms_str:
        try:
            import re
            match = re.search(r'(\d+)', str(bedrooms_str))
            if match:
                permit["bedrooms"] = int(match.group(1))
        except (ValueError, TypeError):
            pass

    # Parse daily flow
    flow_str = row.get("daily_flow")
    if flow_str:
        try:
            import re
            match = re.search(r'(\d+)', str(flow_str))
            if match:
                permit["daily_flow_gpd"] = int(match.group(1))
        except (ValueError, TypeError):
            pass

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


def send_batch(session: requests.Session, api_url: str, permits: list, source_code: str, batch_num: int, total_batches: int, max_retries: int = 3) -> dict:
    """Send a batch of permits to the API with retry logic."""
    payload = {
        "source_portal_code": source_code,
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
                    print(f"  Retrying in {5 * (attempt + 1)}s...")
                    time.sleep(5 * (attempt + 1))
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


def get_ocr_table_name(cursor: sqlite3.Cursor) -> str:
    """Detect the OCR results table name in the database."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [row[0] for row in cursor.fetchall()]
    # Prefer ocr_results, fall back to other common names
    for candidate in ["ocr_results", "results", "permits", "extracted_data"]:
        if candidate in tables:
            return candidate
    if tables:
        print(f"Available tables: {tables}")
        return tables[0]
    print("ERROR: No tables found in database")
    sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="ETL adaptive_ocr.db → Railway PostgreSQL")
    parser.add_argument("--db", required=True, help="Path to adaptive_ocr.db")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API base URL")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Records per batch")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N records (for resume)")
    parser.add_argument("--limit", type=int, default=0, help="Max records to process (0 = all)")
    parser.add_argument("--dry-run", action="store_true", help="Map records but don't send to API")
    parser.add_argument("--source-name", required=True, help="Source identifier (e.g., guadalupe_county_tx)")
    parser.add_argument("--table", default=None, help="Table name in SQLite DB (auto-detected if omitted)")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    # Connect to SQLite
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # Detect table name
    table_name = args.table or get_ocr_table_name(cursor)
    print(f"Using table: {table_name}")

    # Get total count
    cursor.execute(f"SELECT COUNT(*) FROM [{table_name}]")
    total_records = cursor.fetchone()[0]
    print(f"Total records in database: {total_records:,}")

    if args.limit > 0:
        process_count = min(args.limit, total_records - args.offset)
    else:
        process_count = total_records - args.offset

    total_batches = (process_count + args.batch_size - 1) // args.batch_size
    print(f"Processing {process_count:,} records in {total_batches} batches of {args.batch_size}")
    print(f"Source: {args.source_name}")

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
    quality_scores = []
    start_time = time.time()

    query = f"SELECT * FROM [{table_name}] LIMIT ? OFFSET ?"
    offset = args.offset
    source_code = f"ocr_{args.source_name}"

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
            row_dict = dict(row)
            quality = compute_quality_score(row_dict)
            quality_scores.append(quality)

            mapped = map_ocr_row_to_permit(row_dict, args.source_name)
            if mapped:
                permits.append(mapped)
                total_mapped += 1
            else:
                total_unmapped += 1

        if permits and not args.dry_run:
            result = send_batch(session, args.api_url, permits, source_code, batch_num, total_batches)
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

    # Quality score stats
    avg_quality = sum(quality_scores) / len(quality_scores) if quality_scores else 0
    high_quality = sum(1 for s in quality_scores if s >= 70)
    medium_quality = sum(1 for s in quality_scores if 40 <= s < 70)
    low_quality = sum(1 for s in quality_scores if s < 40)

    # Final report
    print("\n" + "=" * 60)
    print("OCR ETL COMPLETE")
    print("=" * 60)
    print(f"Source: {args.source_name}")
    print(f"Time: {elapsed / 60:.1f} minutes ({elapsed:.0f} seconds)")
    print(f"Records processed: {total_mapped + total_unmapped:,}")
    print(f"  Mapped successfully: {total_mapped:,}")
    print(f"  Unmapped (no address): {total_unmapped:,}")
    if not args.dry_run:
        print(f"  Inserted: {total_inserted:,}")
        print(f"  Updated: {total_updated:,}")
        print(f"  Skipped (dupes): {total_skipped:,}")
        print(f"  Errors: {total_errors:,}")
    print(f"\nData Quality:")
    print(f"  Average score: {avg_quality:.1f}/100")
    print(f"  High (≥70): {high_quality:,}")
    print(f"  Medium (40-69): {medium_quality:,}")
    print(f"  Low (<40): {low_quality:,}")
    print(f"\nBatches: {batch_num}")
    if elapsed > 0:
        print(f"Rate: {(total_mapped + total_unmapped) / elapsed:.0f} records/second")


if __name__ == "__main__":
    main()
