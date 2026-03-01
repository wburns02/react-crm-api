#!/usr/bin/env python3
"""
Travis County SepticSearchScraper ETL: Ingest ~7,945 OSSF/wastewater permits
from the SepticSearchScraper JSON (scraped Dec 2025 from MGOConnect portal,
separate scrape with richer fields than the generic MGO DB).

Source: /mnt/win11/Claude_Code/SepticSearchScraper/data/travis_ossf_20251215_160957.json

Key fields not in the MGO dataset:
  - specific_use (e.g., "On-Site Wastewater (Residential)")
  - designation (Residential, Commercial, Multi-Family)
  - parcel_number
  - lot

Usage:
    python scripts/travis_sss_etl.py --dry-run
    python scripts/travis_sss_etl.py --batch-size 2500
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

DEFAULT_JSON_PATH = "/mnt/win11/Claude_Code/SepticSearchScraper/data/travis_ossf_20251215_160957.json"
DEFAULT_API_URL = "https://react-crm-api-production.up.railway.app/api/v2"
DEFAULT_BATCH_SIZE = 2500
SOURCE_PORTAL_CODE = "sss_travis_county"

LOGIN_EMAIL = "will@macseptic.com"
LOGIN_PASSWORD = "#Espn2025"

# Keywords to filter septic/OSSF/wastewater records
SEPTIC_KEYWORDS = ["ossf", "septic", "wastewater", "on-site", "on site", "sewage"]

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

RE_GPD = re.compile(r"(\d{2,5})\s+gallons?\s+per\s+day", re.IGNORECASE)
RE_BEDROOMS = re.compile(r"(\d{1,2})[- ]bedroom", re.IGNORECASE)
RE_SQFT = re.compile(r"([\d,]+)\s*sq\.?\s*ft", re.IGNORECASE)


# ── Row Mapper ──────────────────────────────────────────────────────────────

def map_row(row: dict) -> dict | None:
    """Map a SepticSearchScraper record to PermitCreate schema."""

    address = (row.get("address") or "").strip()
    if not address:
        return None

    # Parse created_date: "01/02/2014 10:23 AM"
    permit_date = None
    scraped_at = datetime.now().isoformat()
    cd = row.get("created_date", "")
    if cd:
        for fmt in ("%m/%d/%Y %I:%M %p", "%m/%d/%Y %H:%M", "%m/%d/%Y"):
            try:
                permit_date = datetime.strptime(cd.strip(), fmt).strftime("%Y-%m-%d")
                break
            except ValueError:
                continue

    # System type from description + specific_use
    text = " ".join([
        row.get("description", ""),
        row.get("specific_use", ""),
    ]).lower()

    system_type = None
    for keyword, st in KEYWORD_SYSTEM_TYPES:
        if keyword in text:
            system_type = st
            break

    # Extract GPD, bedrooms, sqft from description
    desc = row.get("description", "")
    daily_flow_gpd = None
    bedrooms = None
    home_sqft = None

    m = RE_GPD.search(desc)
    if m:
        gpd = int(m.group(1))
        if 50 <= gpd <= 50000:
            daily_flow_gpd = gpd

    m = RE_BEDROOMS.search(desc)
    if m:
        br = int(m.group(1))
        if 1 <= br <= 20:
            bedrooms = br

    m = RE_SQFT.search(desc)
    if m:
        sqft = int(m.group(1).replace(",", ""))
        if 200 <= sqft <= 100000:
            home_sqft = sqft

    # Build raw_data
    raw_data = {
        "source": "SepticSearchScraper",
        "portal": "mgoconnect.org",
    }
    if row.get("specific_use"):
        raw_data["specific_use"] = row["specific_use"]
    if row.get("designation"):
        raw_data["designation"] = row["designation"]
    if row.get("description"):
        raw_data["description"] = row["description"][:2000]
    if row.get("project_name"):
        raw_data["project_name"] = row["project_name"]
    if row.get("status"):
        raw_data["status"] = row["status"]
    if row.get("lot"):
        raw_data["lot"] = row["lot"]
    if row.get("unit"):
        raw_data["unit"] = row["unit"]
    if home_sqft:
        raw_data["home_sqft"] = home_sqft
    if system_type:
        raw_data["system_type_source"] = "keyword"

    # Quality score
    score = 0
    if address:
        score += 20
    if row.get("project_number"):
        score += 10
    if permit_date:
        score += 5
    if row.get("parcel_number"):
        score += 10
    if system_type:
        score += 8
    if daily_flow_gpd:
        score += 10
    if bedrooms:
        score += 10
    if row.get("designation"):
        score += 5
    if row.get("specific_use"):
        score += 5
    raw_data["quality_score"] = min(score, 100)

    return {
        "state_code": "TX",
        "county_name": "Travis County",
        "permit_number": row.get("project_number"),
        "address": address,
        "city": None,  # Not in SSS data
        "zip_code": None,
        "parcel_number": row.get("parcel_number"),
        "latitude": None,
        "longitude": None,
        "owner_name": None,
        "applicant_name": None,
        "permit_date": permit_date,
        "expiration_date": None,
        "system_type": system_type,
        "daily_flow_gpd": daily_flow_gpd,
        "bedrooms": bedrooms,
        "source_portal_code": SOURCE_PORTAL_CODE,
        "scraped_at": scraped_at,
        "raw_data": raw_data,
    }


def is_septic_record(row: dict) -> bool:
    """Check if a record is OSSF/septic/wastewater related."""
    text = " ".join([
        row.get("specific_use", ""),
        row.get("description", ""),
    ]).lower()
    return any(kw in text for kw in SEPTIC_KEYWORDS)


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
        description="Travis County SepticSearchScraper ETL → Railway PostgreSQL"
    )
    parser.add_argument("--json-path", default=DEFAULT_JSON_PATH, help="Path to JSON file")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API base URL")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE)
    parser.add_argument("--limit", type=int, default=0, help="Max records (0 = all)")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--all-records", action="store_true",
                        help="Include all records, not just septic/wastewater")
    args = parser.parse_args()

    json_path = Path(args.json_path)
    if not json_path.exists():
        print(f"JSON file not found: {json_path}")
        sys.exit(1)

    # Load data
    print(f"Loading {json_path}...")
    with open(json_path) as f:
        raw_data = json.load(f)
    print(f"Total records in file: {len(raw_data):,}")

    # Filter to septic records
    if args.all_records:
        filtered = raw_data
        print(f"Using ALL records (--all-records)")
    else:
        filtered = [r for r in raw_data if is_septic_record(r)]
        print(f"Septic/OSSF/wastewater records: {len(filtered):,}")

    if args.limit > 0:
        filtered = filtered[:args.limit]
        print(f"Limited to: {len(filtered):,}")

    # Map records
    permits = []
    unmapped = 0
    for row in filtered:
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
    with_parcel = sum(1 for p in permits if p.get("parcel_number"))
    with_gpd = sum(1 for p in permits if p.get("daily_flow_gpd"))
    with_bedrooms = sum(1 for p in permits if p.get("bedrooms"))

    print(f"── Extraction Stats ──")
    print(f"  system_type:    {with_system_type:>6} ({with_system_type/len(permits)*100:.1f}%)")
    print(f"  parcel_number:  {with_parcel:>6} ({with_parcel/len(permits)*100:.1f}%)")
    print(f"  daily_flow_gpd: {with_gpd:>6} ({with_gpd/len(permits)*100:.1f}%)")
    print(f"  bedrooms:       {with_bedrooms:>6} ({with_bedrooms/len(permits)*100:.1f}%)")
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
    print("Travis County SepticSearchScraper ETL — RESULTS")
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
