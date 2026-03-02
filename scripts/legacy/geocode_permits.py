#!/usr/bin/env python3
"""
Geocode Travis County septic permit addresses using the Census Geocoder API.
Updates permits in the CRM with lat/lng, city, and zip_code.

Census Geocoder: https://geocoding.geo.census.gov/geocoder/
- Free, no API key needed
- Single address API (batch API has file format limitations)
- Rate: ~1 req/sec is safe

Usage:
    python scripts/geocode_permits.py --dry-run
    python scripts/geocode_permits.py --source tnr_travis_county
    python scripts/geocode_permits.py --source all --limit 100
"""

import argparse
import json
import sys
import time
from datetime import datetime
from urllib.parse import quote_plus

import requests

# ── Config ──────────────────────────────────────────────────────────────────

DEFAULT_API_URL = "https://react-crm-api-production.up.railway.app/api/v2"
CENSUS_GEOCODER_URL = "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"

LOGIN_EMAIL = "will@macseptic.com"
LOGIN_PASSWORD = "#Espn2025"

DELAY_BETWEEN_REQUESTS = 0.3  # seconds — Census API is generous


# ── Census Geocoder ─────────────────────────────────────────────────────────

def geocode_address(session: requests.Session, address: str, state: str = "TX") -> dict | None:
    """Geocode a single address using Census Geocoder.

    Returns dict with lat, lng, city, zip_code, matched_address or None.
    """
    full_address = f"{address}, {state}" if state and state not in address else address

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
            "matched_address": match.get("matchedAddress", ""),
        }
    except Exception as e:
        print(f"  Geocode error: {e}")
        return None


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


def get_permits_to_geocode(session: requests.Session, api_url: str,
                           source: str = "all", limit: int = 1000) -> list:
    """Fetch permits that need geocoding (no lat/lng)."""
    params = {"limit": limit, "needs_geocoding": "true"}
    if source != "all":
        params["source_portal_code"] = source

    resp = session.get(f"{api_url}/permits/search", params=params, timeout=30)
    if resp.status_code != 200:
        print(f"Failed to fetch permits: {resp.status_code}")
        return []

    data = resp.json()
    return data.get("permits", data) if isinstance(data, dict) else data


def update_permit_geocode(session: requests.Session, api_url: str,
                          permit_id: str, geocode_data: dict) -> bool:
    """Update a permit with geocoded data."""
    payload = {}
    if geocode_data.get("latitude"):
        payload["latitude"] = geocode_data["latitude"]
    if geocode_data.get("longitude"):
        payload["longitude"] = geocode_data["longitude"]
    if geocode_data.get("city"):
        payload["city"] = geocode_data["city"]
    if geocode_data.get("zip_code"):
        payload["zip_code"] = geocode_data["zip_code"]

    if not payload:
        return False

    resp = session.patch(
        f"{api_url}/permits/{permit_id}",
        json=payload,
        timeout=15,
    )
    return resp.status_code == 200


# ── Main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Geocode septic permits via Census API")
    parser.add_argument("--api-url", default=DEFAULT_API_URL)
    parser.add_argument("--source", default="all",
                        help="Source portal code to filter (or 'all')")
    parser.add_argument("--limit", type=int, default=500,
                        help="Max permits to geocode per run")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--ndjson-path", default=None,
                        help="Geocode from local NDJSON file instead of API")
    args = parser.parse_args()

    session = requests.Session()

    if args.ndjson_path:
        # Geocode from local file (batch mode for initial data)
        geocode_from_file(session, args)
    else:
        # Geocode from CRM API (update existing permits)
        geocode_from_api(session, args)


def geocode_from_file(session: requests.Session, args):
    """Geocode addresses from local NDJSON and output enriched data."""
    from pathlib import Path

    ndjson_path = Path(args.ndjson_path)
    if not ndjson_path.exists():
        print(f"File not found: {ndjson_path}")
        sys.exit(1)

    print(f"Loading {ndjson_path}...")
    records = []
    with open(ndjson_path) as f:
        for line in f:
            line = line.strip()
            if line:
                records.append(json.loads(line))

    # Deduplicate by address
    seen_addrs = {}
    for r in records:
        num = (r.get("streetNumber") or "").strip()
        name = (r.get("streetName") or "").strip()
        addr = f"{num} {name}".strip()
        if addr and addr not in seen_addrs:
            seen_addrs[addr] = r

    addrs = list(seen_addrs.keys())
    print(f"Unique addresses to geocode: {len(addrs):,}")

    if args.limit > 0:
        addrs = addrs[:args.limit]
        print(f"Limited to: {len(addrs):,}")

    if args.dry_run:
        # Test with first 3
        print("\nDRY RUN — testing first 3 addresses:")
        for addr in addrs[:3]:
            result = geocode_address(session, addr, "TX")
            print(f"  {addr} → {result}")
            time.sleep(DELAY_BETWEEN_REQUESTS)
        return

    # Geocode all
    output_path = ndjson_path.parent / "tnr_geocoded.ndjson"
    geocoded = 0
    failed = 0
    start_time = time.time()

    with open(output_path, "w") as out:
        for i, addr in enumerate(addrs):
            result = geocode_address(session, addr, "TX")
            time.sleep(DELAY_BETWEEN_REQUESTS)

            record = {
                "address": addr,
                "geocoded": result is not None,
            }
            if result:
                record.update(result)
                geocoded += 1
            else:
                failed += 1

            out.write(json.dumps(record) + "\n")

            if (i + 1) % 100 == 0:
                elapsed = time.time() - start_time
                rate = (i + 1) / elapsed
                eta = (len(addrs) - i - 1) / rate if rate > 0 else 0
                print(f"  [{i+1}/{len(addrs)}] geocoded={geocoded}, failed={failed}, "
                      f"rate={rate:.1f}/s, ETA={eta/60:.0f}min")

    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("Geocoding — RESULTS")
    print("=" * 60)
    print(f"Time: {elapsed:.0f}s")
    print(f"Geocoded: {geocoded:,} ({geocoded/len(addrs)*100:.1f}%)")
    print(f"Failed: {failed:,}")
    print(f"Output: {output_path}")
    print("=" * 60)


def geocode_from_api(session: requests.Session, args):
    """Fetch permits from CRM API, geocode, and update."""
    login(session, args.api_url)

    print(f"\nFetching permits needing geocoding (source={args.source})...")
    permits = get_permits_to_geocode(session, args.api_url, args.source, args.limit)
    print(f"Permits to geocode: {len(permits):,}")

    if not permits:
        print("No permits need geocoding.")
        return

    if args.dry_run:
        print("\nDRY RUN — would geocode:")
        for p in permits[:3]:
            addr = p.get("address", "")
            print(f"  {addr}")
            result = geocode_address(session, addr, p.get("state_code", "TX"))
            print(f"    → {result}")
            time.sleep(DELAY_BETWEEN_REQUESTS)
        return

    geocoded = 0
    updated = 0
    failed = 0
    start_time = time.time()

    for i, permit in enumerate(permits):
        addr = permit.get("address", "")
        state = permit.get("state_code", "TX")
        permit_id = permit.get("id")

        result = geocode_address(session, addr, state)
        time.sleep(DELAY_BETWEEN_REQUESTS)

        if result:
            geocoded += 1
            if update_permit_geocode(session, args.api_url, permit_id, result):
                updated += 1
        else:
            failed += 1

        if (i + 1) % 50 == 0:
            elapsed = time.time() - start_time
            rate = (i + 1) / elapsed
            eta = (len(permits) - i - 1) / rate if rate > 0 else 0
            print(f"  [{i+1}/{len(permits)}] geocoded={geocoded}, updated={updated}, "
                  f"failed={failed}, rate={rate:.1f}/s, ETA={eta/60:.0f}min")

    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("Geocoding — RESULTS")
    print("=" * 60)
    print(f"Time: {elapsed:.0f}s")
    print(f"Geocoded: {geocoded:,}")
    print(f"Updated in CRM: {updated:,}")
    print(f"Failed: {failed:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
