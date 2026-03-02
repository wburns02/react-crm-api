#!/usr/bin/env python3
"""
Enrich Travis County septic permits with:
1. Geocoding (Census Geocoder API → lat/lng, city, zip)
2. Owner names from TX StratMap parcels (on T430)
3. Cross-reference between data sources

Processes in batches: fetch permits → geocode → match parcels → update CRM.

Usage:
    python scripts/enrich_permits.py --dry-run
    python scripts/enrich_permits.py --step geocode --limit 500
    python scripts/enrich_permits.py --step parcels --limit 500
    python scripts/enrich_permits.py --step all
"""

import argparse
import csv
import json
import subprocess
import sys
import time
from io import StringIO
from typing import Optional

import requests

# ── Config ──────────────────────────────────────────────────────────────────

DEFAULT_API_URL = "https://react-crm-api-production.up.railway.app/api/v2"
CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"

LOGIN_EMAIL = "will@macseptic.com"
LOGIN_PASSWORD = "#Espn2025"

T430_HOST = "will@100.122.216.15"
TX_PARCELS_PATH = "/dataPool/data/records/state_parcels/texas/tx_stratmap_parcels_2025.csv"

GEOCODE_DELAY = 0.3  # seconds between Census API calls
BATCH_SIZE = 50  # permits per CRM batch update


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


def fetch_permits_needing_geocoding(session: requests.Session, api_url: str,
                                     source: Optional[str] = None,
                                     limit: int = 500, offset: int = 0) -> list:
    """Fetch permits without lat/lng from CRM."""
    params = {"limit": limit, "offset": offset}
    if source:
        params["source_portal_code"] = source

    resp = session.get(f"{api_url}/permits/needs-geocoding", params=params, timeout=30)
    if resp.status_code != 200:
        print(f"Failed to fetch permits: {resp.status_code} {resp.text[:200]}")
        return []

    data = resp.json()
    return data.get("permits", [])


def batch_geocode_update(session: requests.Session, api_url: str,
                          updates: list) -> dict:
    """Send batch geocode updates to CRM."""
    resp = session.post(
        f"{api_url}/permits/batch-geocode",
        json=updates,
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"Batch geocode update failed: {resp.status_code} {resp.text[:200]}")
        return {"updated": 0, "errors": len(updates)}
    return resp.json()


def batch_enrich_update(session: requests.Session, api_url: str,
                         updates: list) -> dict:
    """Send batch enrichment updates to CRM."""
    resp = session.post(
        f"{api_url}/permits/batch-enrich",
        json=updates,
        timeout=60,
    )
    if resp.status_code != 200:
        print(f"Batch enrich update failed: {resp.status_code} {resp.text[:200]}")
        return {"updated": 0, "errors": len(updates)}
    return resp.json()


# ── Census Geocoder ─────────────────────────────────────────────────────────

def geocode_address(session: requests.Session, address: str) -> dict | None:
    """Geocode a single address using Census Geocoder."""
    full_address = f"{address}, TX" if "TX" not in address.upper() else address

    params = {
        "address": full_address,
        "benchmark": "Public_AR_Current",
        "vintage": "Current_Current",
        "format": "json",
    }

    try:
        resp = session.get(CENSUS_GEOCODER_URL, params=params, timeout=15)
        if resp.status_code != 200:
            return None

        data = resp.json()
        matches = data.get("result", {}).get("addressMatches", [])
        if not matches:
            return None

        match = matches[0]
        coords = match.get("coordinates", {})
        components = match.get("addressComponents", {})

        return {
            "latitude": coords.get("y"),
            "longitude": coords.get("x"),
            "city": components.get("city", "").title(),
            "zip_code": components.get("zip", ""),
        }
    except Exception:
        return None


# ── TX Parcel Matching ──────────────────────────────────────────────────────

def load_travis_parcels_index() -> dict:
    """Load Travis County parcels from T430 and build address→owner index.

    Returns dict mapping normalized address → {owner_name, geo_id, mkt_value}
    """
    print("Loading Travis County parcels from T430...")

    # Extract Travis County records from the CSV on T430
    # Format: objectid,prop_id,geo_id,owner_name,legal_area,land_value,imp_value,mkt_value,situs_addr,county,fips,tax_year
    try:
        result = subprocess.run(
            ["ssh", "-o", "ConnectTimeout=10", T430_HOST,
             f"grep ',TRAVIS,' {TX_PARCELS_PATH}"],
            capture_output=True, text=True, timeout=300,
        )
        if result.returncode != 0:
            print(f"Failed to load parcels: {result.stderr[:200]}")
            return {}
    except subprocess.TimeoutExpired:
        print("Timeout loading parcels from T430")
        return {}

    # Parse CSV lines
    index = {}
    reader = csv.reader(StringIO(result.stdout))
    for row in reader:
        if len(row) < 10:
            continue

        owner_name = row[3].strip()
        situs_addr = row[8].strip()
        geo_id = row[2].strip()
        mkt_value = row[7].strip()

        if not situs_addr or situs_addr.startswith("PO BOX"):
            continue

        # Normalize: extract street number + name from situs_addr
        # Format: "7834 EL DORADO DR , TX 78737"
        normalized = normalize_parcel_address(situs_addr)
        if normalized:
            index[normalized] = {
                "owner_name": owner_name,
                "geo_id": geo_id,
                "mkt_value": mkt_value,
            }

    print(f"Loaded {len(index):,} Travis County parcels with addresses")
    return index


def normalize_parcel_address(addr: str) -> str | None:
    """Normalize a parcel situs address for matching.

    Input: "7834 EL DORADO DR , TX 78737"
    Output: "7834 EL DORADO DR"
    """
    if not addr:
        return None

    # Remove state/zip suffix
    parts = addr.split(",")
    street = parts[0].strip()

    # Remove trailing spaces
    street = " ".join(street.split())

    if not street or len(street) < 5:
        return None

    return street.upper()


def normalize_permit_address(addr: str) -> str | None:
    """Normalize a permit address for matching.

    Input: "7834 EL DORADO DR"
    Output: "7834 EL DORADO DR"
    """
    if not addr:
        return None

    # Already pretty clean, just normalize spacing and case
    normalized = " ".join(addr.upper().split())

    # Remove common suffixes that might differ
    for suffix in [", TX", ", TEXAS", " TX ", " AUSTIN"]:
        if normalized.endswith(suffix.strip()):
            normalized = normalized[:-len(suffix.strip())].strip()

    return normalized if len(normalized) >= 5 else None


# ── Enrichment Steps ────────────────────────────────────────────────────────

def step_geocode(session: requests.Session, api_url: str, limit: int,
                 source: Optional[str], dry_run: bool):
    """Step 1: Geocode permits missing lat/lng."""
    print("\n" + "=" * 60)
    print("STEP 1: GEOCODING")
    print("=" * 60)

    total_geocoded = 0
    total_failed = 0
    total_updated = 0
    offset = 0
    start_time = time.time()

    while True:
        permits = fetch_permits_needing_geocoding(
            session, api_url, source=source, limit=min(limit - total_geocoded, 500),
            offset=offset
        )

        if not permits:
            break

        print(f"\nFetched {len(permits)} permits needing geocoding (offset={offset})")

        geocode_batch = []
        for i, permit in enumerate(permits):
            if total_geocoded + total_failed >= limit:
                break

            addr = permit.get("address", "")
            result = geocode_address(session, addr)
            time.sleep(GEOCODE_DELAY)

            if result:
                geocode_batch.append({
                    "id": permit["id"],
                    **result,
                })
                total_geocoded += 1
            else:
                total_failed += 1

            if (total_geocoded + total_failed) % 50 == 0:
                elapsed = time.time() - start_time
                total = total_geocoded + total_failed
                rate = total / elapsed if elapsed > 0 else 0
                remaining = limit - total
                eta = remaining / rate if rate > 0 else 0
                print(f"  Progress: {total}/{limit} (geocoded={total_geocoded}, "
                      f"failed={total_failed}) rate={rate:.1f}/s ETA={eta/60:.0f}min")

            # Send batch when full
            if len(geocode_batch) >= BATCH_SIZE:
                if not dry_run:
                    result = batch_geocode_update(session, api_url, geocode_batch)
                    total_updated += result.get("updated", 0)
                    print(f"  Batch update: {result}")
                geocode_batch = []

        # Send remaining batch
        if geocode_batch and not dry_run:
            result = batch_geocode_update(session, api_url, geocode_batch)
            total_updated += result.get("updated", 0)
            print(f"  Final batch update: {result}")

        if total_geocoded + total_failed >= limit:
            break

        offset += len(permits)

    elapsed = time.time() - start_time
    print(f"\nGeocoding complete:")
    print(f"  Geocoded: {total_geocoded:,}")
    print(f"  Failed: {total_failed:,}")
    print(f"  Updated in CRM: {total_updated:,}")
    print(f"  Time: {elapsed:.0f}s")

    return total_geocoded


def step_parcels(session: requests.Session, api_url: str, limit: int,
                 source: Optional[str], dry_run: bool):
    """Step 2: Enrich with TX parcel data (owner names)."""
    print("\n" + "=" * 60)
    print("STEP 2: PARCEL ENRICHMENT")
    print("=" * 60)

    # Load parcel index from T430
    parcel_index = load_travis_parcels_index()
    if not parcel_index:
        print("No parcel data loaded. Skipping.")
        return 0

    # Fetch all permits (we'll match by address)
    total_matched = 0
    total_unmatched = 0
    total_updated = 0
    offset = 0
    start_time = time.time()

    # We need permits with addresses — use needs-geocoding endpoint for those
    # that haven't been enriched, but we actually need ALL permits
    # Let's fetch in batches via the search endpoint
    while True:
        params = {
            "limit": min(limit - total_matched - total_unmatched, 500),
            "offset": offset,
        }
        if source:
            params["source_portal_code"] = source

        resp = session.get(
            f"{api_url}/permits/needs-geocoding",
            params=params,
            timeout=30,
        )
        if resp.status_code != 200:
            # Try alternative: get all permits by searching
            break

        data = resp.json()
        permits = data.get("permits", [])
        if not permits:
            break

        print(f"\nMatching {len(permits)} permits against parcels (offset={offset})")

        enrich_batch = []
        for permit in permits:
            if total_matched + total_unmatched >= limit:
                break

            addr = normalize_permit_address(permit.get("address", ""))
            if not addr:
                total_unmatched += 1
                continue

            # Try exact match
            parcel = parcel_index.get(addr)
            if not parcel:
                # Try without street type suffix (DR, ST, LN, etc.)
                import re
                addr_no_suffix = re.sub(
                    r'\s+(DR|ST|LN|CT|CIR|BLVD|AVE|RD|WAY|PL|TRL|CV|LOOP|PASS|RUN|BND|HLS|VW)$',
                    '', addr
                )
                parcel = parcel_index.get(addr_no_suffix)

            if parcel:
                update = {"id": permit["id"]}
                if parcel.get("owner_name"):
                    update["owner_name"] = parcel["owner_name"]
                if parcel.get("geo_id"):
                    update["raw_data"] = {
                        "tcad_geo_id": parcel["geo_id"],
                        "tcad_mkt_value": parcel.get("mkt_value"),
                        "parcel_match": "exact",
                    }
                enrich_batch.append(update)
                total_matched += 1
            else:
                total_unmatched += 1

            # Send batch when full
            if len(enrich_batch) >= BATCH_SIZE:
                if not dry_run:
                    result = batch_enrich_update(session, api_url, enrich_batch)
                    total_updated += result.get("updated", 0)
                    print(f"  Batch enrich: {result}")
                enrich_batch = []

        # Send remaining batch
        if enrich_batch and not dry_run:
            result = batch_enrich_update(session, api_url, enrich_batch)
            total_updated += result.get("updated", 0)
            print(f"  Final batch enrich: {result}")

        if total_matched + total_unmatched >= limit:
            break
        offset += len(permits)

    elapsed = time.time() - start_time
    print(f"\nParcel enrichment complete:")
    print(f"  Matched: {total_matched:,}")
    print(f"  Unmatched: {total_unmatched:,}")
    print(f"  Updated in CRM: {total_updated:,}")
    print(f"  Time: {elapsed:.0f}s")

    return total_matched


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Enrich septic permits with geocoding and parcel data")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--step", choices=["geocode", "parcels", "all"], default="all")
    parser.add_argument("--source", default=None,
                        help="Source portal code to filter (e.g., tnr_travis_county)")
    parser.add_argument("--limit", type=int, default=500,
                        help="Max permits to process per step")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    session = requests.Session()
    login(session, args.api_url)

    if args.step in ("geocode", "all"):
        step_geocode(session, args.api_url, args.limit, args.source, args.dry_run)

    if args.step in ("parcels", "all"):
        step_parcels(session, args.api_url, args.limit, args.source, args.dry_run)

    print("\n" + "=" * 60)
    print("ENRICHMENT COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
