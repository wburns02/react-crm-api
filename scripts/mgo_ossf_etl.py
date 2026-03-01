#!/usr/bin/env python3
"""
MGO OSSF ETL: Enhanced TX OSSF permit extraction from crm_permits.db.

Targets ~98K TX OSSF permits from the MGO (MyGovernmentOnline) database
and extracts rich structured data from description templates and work_type
fields that the generic t430_etl_ingest.py ignores.

Key enhancements over t430_etl_ingest.py:
  - Regex extraction from templated descriptions (GPD, bedrooms, sqft, system type)
  - work_type → system_type mapping (41K+ records)
  - ossf_details JSON parsing (designation_type, specific_use, designer/installer)
  - Quality score 0-100 based on field completeness
  - Per-county source portal codes for dedup tracking
  - Dry-run mode with detailed extraction statistics

Usage:
    python scripts/mgo_ossf_etl.py \\
        --db /mnt/win11/fedora-moved/Data/crm_permits.db \\
        --county "Williamson County" \\
        --dry-run

    python scripts/mgo_ossf_etl.py \\
        --db /mnt/win11/fedora-moved/Data/crm_permits.db \\
        --batch-size 5000 --limit 100
"""

import argparse
import json
import re
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ── Config ──────────────────────────────────────────────────────────────────

DEFAULT_API_URL = "https://react-crm-api-production.up.railway.app/api/v2"
DEFAULT_BATCH_SIZE = 5000

LOGIN_EMAIL = "will@macseptic.com"
LOGIN_PASSWORD = "#Espn2025"

OSSF_PROJECT_TYPES = (
    "OSSF",
    "On-Site Sewage Facility (OSSF) Permits",
    "On-Site Sewage Facility (Septic) Permit",
)

# ── Work Type → System Type Mapping ─────────────────────────────────────────

WORK_TYPE_MAP = {
    # Residential [SFR]
    "Aerobic": "Aerobic Treatment Unit",
    "Surface Application [SFR]": "Surface Application",
    "Conventional (Residential)": "Conventional Septic",
    "Drip Irrigation [SFR]": "Drip Irrigation",
    "Low Pressure Dose [SFR]": "Low Pressure Dosing",
    "Leaching Chambers [SFR]": "Leaching Chambers",
    "Standard Trench / Bed [SFR]": "Standard Septic",
    "Evapotranspiration Bed [SFR]": "Evapotranspiration",
    "Absorptive Mounds [SFR]": "Mound System",
    # Commercial variants
    "Conventional(Commercial)": "Conventional Septic",
    "Drip Irrigation (C)": "Drip Irrigation",
    "Surface Application (C)": "Surface Application",
    "Low Pressure Dose (C)": "Low Pressure Dosing",
    "Leaching Chambers (C)": "Leaching Chambers",
    # Non-SFR variants
    "Surface Application [Non-SFR]": "Surface Application",
    "Leaching Chambers [Non-SFR]": "Leaching Chambers",
    # Commercial [COM] variants
    "Surface Irrigation [COM]": "Surface Application",
    "Drip Irrigation [COM]": "Drip Irrigation",
    "Low Pressure Dose [COM]": "Low Pressure Dosing",
    # Short codes
    "LPD": "Low Pressure Dosing",
    "Standard": "Standard Septic",
}

# ── Keyword → System Type Fallback ──────────────────────────────────────────

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
    ("soil substitution", "Mound System"),
    ("septic", "Standard Septic"),
]

# ── Description Template Regex ──────────────────────────────────────────────

# "This <system_type> is designed to treat a maximum of <N> gallons per day
#  for a <N>-bedroom, <N> sq. ft. residence."
RE_SYSTEM_TYPE = re.compile(
    r"This\s+(.+?)\s+(?:OSSF\s+)?is\s+designed\s+to\s+treat",
    re.IGNORECASE,
)
RE_GPD = re.compile(
    r"(\d{2,5})\s+gallons\s+per\s+day",
    re.IGNORECASE,
)
RE_BEDROOMS = re.compile(
    r"(\d{1,2})-bedroom",
    re.IGNORECASE,
)
RE_SQFT = re.compile(
    r"([\d,]+)\s*sq\.?\s*ft",
    re.IGNORECASE,
)
RE_MAINTENANCE = re.compile(
    r"maintenance\s+(?:and\s+monitoring\s+)?contract\s+is\s+required",
    re.IGNORECASE,
)
RE_CHLORINE = re.compile(
    r"chlorine\s+disinfection\s+is\s+required",
    re.IGNORECASE,
)
RE_RENEWAL = re.compile(
    r"permit\s+must\s+be\s+renewed\s+every\s+(\w+)\s+years?",
    re.IGNORECASE,
)

# Word → number for renewal period
WORD_TO_NUM = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "1": 1, "2": 2, "3": 3, "4": 4, "5": 5,
}


# ── Description Parser ──────────────────────────────────────────────────────

def parse_description(description: str | None) -> dict:
    """
    Extract structured fields from MGO templated description text.

    Returns dict with keys: system_type, daily_flow_gpd, bedrooms,
    home_sqft, maintenance_contract_required, chlorine_required,
    renewal_period_years. All values None if not found.
    """
    result = {
        "system_type": None,
        "daily_flow_gpd": None,
        "bedrooms": None,
        "home_sqft": None,
        "maintenance_contract_required": None,
        "chlorine_required": None,
        "renewal_period_years": None,
    }

    if not description:
        return result

    # Strip HTML tags
    text = re.sub(r"<[^>]+>", " ", description).strip()

    # System type from template: "This <type> is designed to treat..."
    m = RE_SYSTEM_TYPE.search(text)
    if m:
        raw_type = m.group(1).strip()
        # Clean up: remove trailing "OSSF" if present
        raw_type = re.sub(r"\s+OSSF$", "", raw_type, flags=re.IGNORECASE).strip()
        # Filter out non-system-type captures
        bad_types = {"system", "ossf", "license", "permit", ""}
        if (
            raw_type
            and len(raw_type) > 3
            and "?" not in raw_type
            and raw_type.lower() not in bad_types
            and len(raw_type) < 100  # reject garbage from multi-sentence captures
        ):
            result["system_type"] = _normalize_description_system_type(raw_type)

    # GPD: "300 gallons per day" — take first match (the "designed to treat" one)
    m = RE_GPD.search(text)
    if m:
        gpd = int(m.group(1))
        if 50 <= gpd <= 50000:  # sanity range
            result["daily_flow_gpd"] = gpd

    # Bedrooms: "4-bedroom"
    m = RE_BEDROOMS.search(text)
    if m:
        bedrooms = int(m.group(1))
        if 1 <= bedrooms <= 20:
            result["bedrooms"] = bedrooms

    # Square footage: "2,346 sq. ft."
    m = RE_SQFT.search(text)
    if m:
        sqft = int(m.group(1).replace(",", ""))
        if 200 <= sqft <= 100000:
            result["home_sqft"] = sqft

    # Maintenance contract required
    if RE_MAINTENANCE.search(text):
        result["maintenance_contract_required"] = True

    # Chlorine disinfection required
    if RE_CHLORINE.search(text):
        result["chlorine_required"] = True

    # Renewal period: "renewed every two years"
    m = RE_RENEWAL.search(text)
    if m:
        period = WORD_TO_NUM.get(m.group(1).lower())
        if period:
            result["renewal_period_years"] = period

    return result


def _normalize_description_system_type(raw: str) -> str:
    """Normalize a system type string extracted from the description template."""
    lower = raw.lower()

    # Map common description patterns to standard names
    if "aerobic" in lower and "drip" in lower:
        return "Aerobic Treatment Unit with Drip Irrigation"
    if "aerobic" in lower and "surface" in lower:
        return "Aerobic Treatment Unit with Surface Application"
    if "aerobic" in lower and "spray" in lower:
        return "Aerobic Treatment Unit with Spray Distribution"
    if "aerobic" in lower:
        return "Aerobic Treatment Unit"
    if "low pressure" in lower or "low-pressure" in lower:
        return "Low Pressure Dosing"
    if "soil substitution" in lower and "mound" in lower:
        return "Soil Substitution Mound System"
    if "soil substitution" in lower and "low pressure" in lower:
        return "Soil Substitution with Low Pressure Dosing"
    if "soil substitution" in lower:
        return "Soil Substitution System"
    if "standard subsurface" in lower or "standard absorption" in lower:
        return "Standard Septic"
    if "conventional" in lower:
        return "Conventional Septic"
    if "drip" in lower:
        return "Drip Irrigation"
    if "surface" in lower and "application" in lower:
        return "Surface Application"
    if "evapotranspiration" in lower:
        return "Evapotranspiration"
    if "leaching" in lower:
        return "Leaching Chambers"
    if "mound" in lower:
        return "Mound System"

    # Return cleaned original if no mapping
    return raw.title()


# ── Work Type Mapper ────────────────────────────────────────────────────────

def map_work_type(work_type: str | None) -> str | None:
    """Map MGO work_type field to standardized CRM system_type."""
    if not work_type or not work_type.strip():
        return None

    wt = work_type.strip()

    # Direct lookup
    if wt in WORK_TYPE_MAP:
        return WORK_TYPE_MAP[wt]

    # Skip known non-system-type values
    skip_values = {
        "Other OSSF [SFR]", "Other OSSF [Non-SFR]", "Other",
        "Routine Maintenance", "Subdivision (S)",
        "Single Family Residence", "Multi-Family Residence",
        "Office / Warehouse",
    }
    if wt in skip_values:
        return None

    return None


# ── Keyword System Type (fallback) ──────────────────────────────────────────

def keyword_system_type(ossf_details: str | None, description: str | None) -> str | None:
    """Fallback keyword matching (same as t430_etl_ingest.py but with more patterns)."""
    text = ((ossf_details or "") + " " + (description or "")).lower()

    for keyword, system_type in KEYWORD_SYSTEM_TYPES:
        if keyword in text:
            return system_type

    return None


# ── OSSF Details Parser ─────────────────────────────────────────────────────

def parse_ossf_details(ossf_details_str: str | None) -> dict:
    """Parse the ossf_details JSON field for structured metadata."""
    result = {
        "designation_type": None,
        "specific_use": None,
        "designer_name": None,
        "designer_license": None,
        "installer_name": None,
        "installer_license": None,
        "maintenance_contract_required": None,
    }

    if not ossf_details_str:
        return result

    try:
        data = json.loads(ossf_details_str)
    except (json.JSONDecodeError, TypeError):
        return result

    for key in result:
        val = data.get(key)
        if val and val != "null" and str(val).strip():
            result[key] = str(val).strip()

    return result


# ── Quality Score ───────────────────────────────────────────────────────────

def compute_quality_score(permit: dict) -> int:
    """Score 0-100 based on field completeness."""
    score = 0

    if permit.get("address"):
        score += 20
    if permit.get("permit_number"):
        score += 10
    if permit.get("city") and permit.get("zip_code"):
        score += 10
    elif permit.get("city") or permit.get("zip_code"):
        score += 5

    # system_type from description template is highest quality
    raw_data = permit.get("raw_data", {})
    if permit.get("system_type"):
        if raw_data.get("system_type_source") == "description":
            score += 15
        elif raw_data.get("system_type_source") == "work_type":
            score += 12
        else:
            score += 8

    if permit.get("daily_flow_gpd"):
        score += 10
    if permit.get("bedrooms"):
        score += 10
    if permit.get("latitude") and permit.get("longitude"):
        score += 10

    if raw_data.get("subdivision"):
        score += 5
    if raw_data.get("maintenance_contract_required"):
        score += 5
    if permit.get("permit_date"):
        score += 5

    return min(score, 100)


# ── Date Parsers ────────────────────────────────────────────────────────────

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


# ── Row Mapper ──────────────────────────────────────────────────────────────

def map_row_to_permit(row: dict, source_code_override: str | None = None) -> dict | None:
    """
    Map a crm_permits.db OSSF row to PermitCreate schema with enhanced extraction.

    Priority for system_type:
      1. Description template regex (most specific)
      2. work_type field mapping
      3. Keyword fallback (least specific)
    """
    state = (row.get("state") or "").strip().upper()
    if not state or len(state) != 2:
        return None

    # ── Parse description template ──
    desc_data = parse_description(row.get("description"))

    # ── Parse ossf_details JSON ──
    ossf_data = parse_ossf_details(row.get("ossf_details"))

    # ── System type (priority chain) ──
    system_type = None
    system_type_source = None

    if desc_data["system_type"]:
        system_type = desc_data["system_type"]
        system_type_source = "description"
    elif map_work_type(row.get("work_type")):
        system_type = map_work_type(row.get("work_type"))
        system_type_source = "work_type"
    else:
        kw = keyword_system_type(row.get("ossf_details"), row.get("description"))
        if kw:
            system_type = kw
            system_type_source = "keyword"

    # ── Dates ──
    permit_date = parse_date(row.get("issued_date")) or parse_date(row.get("created_date"))

    # ── Source portal code ──
    jurisdiction = (row.get("jurisdiction_name") or "unknown").strip()
    jurisdiction_slug = re.sub(r"[^a-z0-9]+", "_", jurisdiction.lower()).strip("_")
    source_code = source_code_override or f"mgo_ossf_{jurisdiction_slug}"

    # ── Build raw_data with all extracted metadata ──
    raw_data = {}

    # Original fields
    if row.get("original_id"):
        raw_data["original_id"] = row["original_id"]
    if row.get("trade"):
        raw_data["trade"] = row["trade"]
    if row.get("project_type"):
        raw_data["project_type"] = row["project_type"]
    if row.get("work_type"):
        raw_data["work_type"] = row["work_type"]
    if row.get("status"):
        raw_data["status"] = row["status"]
    if row.get("description"):
        raw_data["description"] = row["description"][:2000]  # cap length
    if row.get("ossf_details"):
        raw_data["ossf_details"] = row["ossf_details"]
    if row.get("subdivision"):
        raw_data["subdivision"] = row["subdivision"]
    if row.get("lot"):
        raw_data["lot"] = row["lot"]
    if row.get("apt_lot"):
        raw_data["apt_lot"] = row["apt_lot"]
    if row.get("source_file"):
        raw_data["source_file"] = row["source_file"]

    # Extracted structured data
    if desc_data["home_sqft"]:
        raw_data["home_sqft"] = desc_data["home_sqft"]
    if desc_data["maintenance_contract_required"]:
        raw_data["maintenance_contract_required"] = True
    if ossf_data["maintenance_contract_required"]:
        raw_data["maintenance_contract_required"] = True
    if desc_data["chlorine_required"]:
        raw_data["chlorine_required"] = True
    if desc_data["renewal_period_years"]:
        raw_data["renewal_period_years"] = desc_data["renewal_period_years"]
    if system_type_source:
        raw_data["system_type_source"] = system_type_source

    # OSSF details structured fields
    if ossf_data["designation_type"]:
        raw_data["designation_type"] = ossf_data["designation_type"]
    if ossf_data["specific_use"]:
        raw_data["specific_use"] = ossf_data["specific_use"]
    if ossf_data["designer_name"]:
        raw_data["designer_name"] = ossf_data["designer_name"]
    if ossf_data["designer_license"]:
        raw_data["designer_license"] = ossf_data["designer_license"]
    if ossf_data["installer_name"]:
        raw_data["installer_name"] = ossf_data["installer_name"]
    if ossf_data["installer_license"]:
        raw_data["installer_license"] = ossf_data["installer_license"]

    # ── Build permit dict ──
    permit = {
        "state_code": state,
        "county_name": jurisdiction,
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
        "system_type": system_type,
        "daily_flow_gpd": desc_data["daily_flow_gpd"],
        "bedrooms": desc_data["bedrooms"],
        "source_portal_code": source_code,
        "scraped_at": parse_datetime(row.get("scraped_at")) or datetime.now().isoformat(),
        "raw_data": raw_data,
    }

    # ── Validate lat/lng ──
    for coord, valid_range in [("latitude", (-90, 90)), ("longitude", (-180, 180))]:
        if permit[coord] is not None:
            try:
                permit[coord] = float(permit[coord])
                if not (valid_range[0] <= permit[coord] <= valid_range[1]):
                    permit[coord] = None
            except (ValueError, TypeError):
                permit[coord] = None

    # ── Quality score ──
    permit["raw_data"]["quality_score"] = compute_quality_score(permit)

    return permit


# ── API Helpers ─────────────────────────────────────────────────────────────

def login(session: requests.Session, api_url: str) -> None:
    """Login and establish session cookie."""
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
    source_code: str,
    batch_num: int,
    total_batches: int,
    max_retries: int = 3,
) -> dict:
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
        description="Enhanced MGO OSSF ETL: TX OSSF permits → Railway PostgreSQL with description parsing"
    )
    parser.add_argument("--db", required=True, help="Path to crm_permits.db")
    parser.add_argument("--api-url", default=DEFAULT_API_URL, help="API base URL")
    parser.add_argument("--batch-size", type=int, default=DEFAULT_BATCH_SIZE, help="Records per batch")
    parser.add_argument("--offset", type=int, default=0, help="Skip first N records")
    parser.add_argument("--limit", type=int, default=0, help="Max records (0 = all)")
    parser.add_argument("--county", default=None, help="Filter to specific county (e.g. 'Williamson County')")
    parser.add_argument("--dry-run", action="store_true", help="Map + report stats, don't send to API")
    parser.add_argument("--source-code", default=None, help="Override source portal code")
    args = parser.parse_args()

    db_path = Path(args.db)
    if not db_path.exists():
        print(f"Database not found: {db_path}")
        sys.exit(1)

    # ── Connect to SQLite ──
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    # ── Build query ──
    # Match OSSF project types OR any record with trade='septic' (catches ~24K extra)
    placeholders = ",".join(["?"] * len(OSSF_PROJECT_TYPES))
    where = f"state = 'TX' AND (project_type IN ({placeholders}) OR trade = 'septic')"
    params: list = list(OSSF_PROJECT_TYPES)

    if args.county:
        where += " AND jurisdiction_name = ?"
        params.append(args.county)

    # Total count
    cursor.execute(f"SELECT COUNT(*) FROM permits WHERE {where}", params)
    total_records = cursor.fetchone()[0]
    print(f"TX septic records matching filter: {total_records:,}")

    if total_records == 0:
        print("No records found. Check --county filter.")
        conn.close()
        sys.exit(0)

    if args.limit > 0:
        process_count = min(args.limit, total_records - args.offset)
    else:
        process_count = total_records - args.offset

    total_batches = (process_count + args.batch_size - 1) // args.batch_size
    print(f"Processing {process_count:,} records in {total_batches} batches of {args.batch_size}")
    print()

    # ── Setup API session ──
    session = requests.Session()
    if not args.dry_run:
        login(session, args.api_url)
        print()

    # ── Extraction stats ──
    stats = {
        "total_processed": 0,
        "mapped": 0,
        "unmapped": 0,
        "with_system_type": 0,
        "system_type_from_description": 0,
        "system_type_from_work_type": 0,
        "system_type_from_keyword": 0,
        "with_daily_flow_gpd": 0,
        "with_bedrooms": 0,
        "with_home_sqft": 0,
        "with_maintenance_contract": 0,
        "with_chlorine_required": 0,
        "with_renewal_period": 0,
        "with_coordinates": 0,
        "with_designation_type": 0,
        "with_specific_use": 0,
        "quality_score_sum": 0,
        "system_type_counts": {},
        "county_counts": {},
    }

    # API stats
    total_inserted = 0
    total_updated = 0
    total_skipped = 0
    total_errors = 0

    start_time = time.time()

    # ── Process in batches ──
    query = f"SELECT * FROM permits WHERE {where} ORDER BY jurisdiction_name, created_date LIMIT ? OFFSET ?"
    offset = args.offset
    batch_num = 0

    while offset < args.offset + process_count:
        batch_num += 1
        remaining = args.offset + process_count - offset
        current_batch_size = min(args.batch_size, remaining)

        cursor.execute(query, params + [current_batch_size, offset])
        rows = cursor.fetchall()

        if not rows:
            break

        # Map rows
        permits = []
        for row in rows:
            row_dict = dict(row)
            mapped = map_row_to_permit(row_dict, args.source_code)
            stats["total_processed"] += 1

            if not mapped:
                stats["unmapped"] += 1
                continue

            stats["mapped"] += 1
            raw = mapped.get("raw_data", {})

            # Track extraction stats
            if mapped.get("system_type"):
                stats["with_system_type"] += 1
                st = mapped["system_type"]
                stats["system_type_counts"][st] = stats["system_type_counts"].get(st, 0) + 1
                src = raw.get("system_type_source")
                if src == "description":
                    stats["system_type_from_description"] += 1
                elif src == "work_type":
                    stats["system_type_from_work_type"] += 1
                elif src == "keyword":
                    stats["system_type_from_keyword"] += 1

            if mapped.get("daily_flow_gpd"):
                stats["with_daily_flow_gpd"] += 1
            if mapped.get("bedrooms"):
                stats["with_bedrooms"] += 1
            if raw.get("home_sqft"):
                stats["with_home_sqft"] += 1
            if raw.get("maintenance_contract_required"):
                stats["with_maintenance_contract"] += 1
            if raw.get("chlorine_required"):
                stats["with_chlorine_required"] += 1
            if raw.get("renewal_period_years"):
                stats["with_renewal_period"] += 1
            if mapped.get("latitude") and mapped.get("longitude"):
                stats["with_coordinates"] += 1
            if raw.get("designation_type"):
                stats["with_designation_type"] += 1
            if raw.get("specific_use"):
                stats["with_specific_use"] += 1

            stats["quality_score_sum"] += raw.get("quality_score", 0)

            county = mapped.get("county_name", "Unknown")
            stats["county_counts"][county] = stats["county_counts"].get(county, 0) + 1

            permits.append(mapped)

        # Send or report
        if permits and not args.dry_run:
            # Use first permit's source_portal_code for the batch
            batch_source = permits[0]["source_portal_code"]
            result = send_batch(session, args.api_url, permits, batch_source, batch_num, total_batches)
            batch_stats = result.get("stats", {})
            total_inserted += batch_stats.get("inserted", 0)
            total_updated += batch_stats.get("updated", 0)
            total_skipped += batch_stats.get("skipped", 0)
            total_errors += batch_stats.get("errors", 0)
        elif args.dry_run:
            print(f"  Batch {batch_num}/{total_batches}: {len(permits)} permits mapped (dry run)")

        offset += current_batch_size

        # Progress every 5 batches
        if batch_num % 5 == 0:
            elapsed = time.time() - start_time
            processed = offset - args.offset
            rate = processed / elapsed if elapsed > 0 else 0
            eta = (process_count - processed) / rate if rate > 0 else 0
            print(
                f"\n  === Progress: {processed:,}/{process_count:,} "
                f"({processed / process_count * 100:.1f}%) | "
                f"{rate:.0f} rec/s | ETA: {eta / 60:.1f} min ===\n"
            )

    elapsed = time.time() - start_time
    conn.close()

    # ── Final Report ──
    avg_quality = stats["quality_score_sum"] / stats["mapped"] if stats["mapped"] > 0 else 0

    print()
    print("=" * 70)
    print("MGO OSSF ETL — EXTRACTION REPORT")
    print("=" * 70)
    print(f"Time: {elapsed / 60:.1f} minutes ({elapsed:.0f} seconds)")
    print(f"Records processed: {stats['total_processed']:,}")
    print(f"  Mapped: {stats['mapped']:,}")
    print(f"  Unmapped (bad state): {stats['unmapped']:,}")
    print()

    print("── Field Extraction ──")
    print(f"  system_type:        {stats['with_system_type']:>7,} ({_pct(stats['with_system_type'], stats['mapped'])})")
    print(f"    from description: {stats['system_type_from_description']:>7,}")
    print(f"    from work_type:   {stats['system_type_from_work_type']:>7,}")
    print(f"    from keyword:     {stats['system_type_from_keyword']:>7,}")
    print(f"  daily_flow_gpd:     {stats['with_daily_flow_gpd']:>7,} ({_pct(stats['with_daily_flow_gpd'], stats['mapped'])})")
    print(f"  bedrooms:           {stats['with_bedrooms']:>7,} ({_pct(stats['with_bedrooms'], stats['mapped'])})")
    print(f"  home_sqft:          {stats['with_home_sqft']:>7,} ({_pct(stats['with_home_sqft'], stats['mapped'])})")
    print(f"  maintenance_req:    {stats['with_maintenance_contract']:>7,} ({_pct(stats['with_maintenance_contract'], stats['mapped'])})")
    print(f"  chlorine_req:       {stats['with_chlorine_required']:>7,} ({_pct(stats['with_chlorine_required'], stats['mapped'])})")
    print(f"  renewal_period:     {stats['with_renewal_period']:>7,} ({_pct(stats['with_renewal_period'], stats['mapped'])})")
    print(f"  coordinates:        {stats['with_coordinates']:>7,} ({_pct(stats['with_coordinates'], stats['mapped'])})")
    print(f"  designation_type:   {stats['with_designation_type']:>7,} ({_pct(stats['with_designation_type'], stats['mapped'])})")
    print(f"  specific_use:       {stats['with_specific_use']:>7,} ({_pct(stats['with_specific_use'], stats['mapped'])})")
    print()

    print(f"── Quality Score: {avg_quality:.1f}/100 avg ──")
    print()

    print("── System Types (top 15) ──")
    sorted_types = sorted(stats["system_type_counts"].items(), key=lambda x: -x[1])
    for st, count in sorted_types[:15]:
        print(f"  {count:>7,}  {st}")
    print()

    print("── Counties ──")
    sorted_counties = sorted(stats["county_counts"].items(), key=lambda x: -x[1])
    for county, count in sorted_counties:
        print(f"  {count:>7,}  {county}")
    print()

    if not args.dry_run:
        print("── API Results ──")
        print(f"  Inserted: {total_inserted:,}")
        print(f"  Updated:  {total_updated:,}")
        print(f"  Skipped:  {total_skipped:,}")
        print(f"  Errors:   {total_errors:,}")
        print()

    print(f"Batches: {batch_num}")
    if elapsed > 0:
        print(f"Rate: {stats['total_processed'] / elapsed:.0f} records/second")
    print("=" * 70)


def _pct(part: int, whole: int) -> str:
    """Format a percentage string."""
    if whole == 0:
        return "0.0%"
    return f"{part / whole * 100:.1f}%"


if __name__ == "__main__":
    main()
