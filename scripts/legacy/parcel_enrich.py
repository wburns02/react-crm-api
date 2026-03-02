#!/usr/bin/env python3
"""
Improved parcel enrichment: match 621K central TX parcel records against
septic permits in the CRM. Adds owner_name and parcel metadata.

Usage:
    python scripts/parcel_enrich.py --dry-run
    python scripts/parcel_enrich.py
"""

import re
import sys
import time

import requests

API = "https://react-crm-api-production.up.railway.app/api/v2"
LOGIN_EMAIL = "will@macseptic.com"
LOGIN_PASSWORD = "#Espn2025"
PARCEL_INDEX_FILE = "/mnt/win11/fedora-moved/Data/central_tx_parcels_index.txt"

SUFFIX_MAP = {
    "DR": "DRIVE", "DRIVE": "DR",
    "ST": "STREET", "STREET": "ST",
    "LN": "LANE", "LANE": "LN",
    "CT": "COURT", "COURT": "CT",
    "CIR": "CIRCLE", "CIRCLE": "CIR",
    "BLVD": "BOULEVARD", "BOULEVARD": "BLVD",
    "AVE": "AVENUE", "AVENUE": "AVE",
    "RD": "ROAD", "ROAD": "RD",
    "WAY": "WAY",
    "PL": "PLACE", "PLACE": "PL",
    "TRL": "TRAIL", "TRAIL": "TRL",
    "CV": "COVE", "COVE": "CV",
    "LOOP": "LOOP",
    "PASS": "PASS",
    "RUN": "RUN",
    "BND": "BEND", "BEND": "BND",
    "HLS": "HILLS", "HILLS": "HLS",
    "VW": "VIEW", "VIEW": "VW",
    "PKWY": "PARKWAY", "PARKWAY": "PKWY",
    "HWY": "HIGHWAY", "HIGHWAY": "HWY",
}


def normalize_for_match(addr):
    if not addr:
        return []
    addr = " ".join(addr.upper().split())
    # Remove unit/apt suffixes
    addr = re.sub(r"\s+(UNIT|APT|STE|SUITE|#)\s*.*$", "", addr)
    variants = [addr]
    words = addr.split()
    if len(words) >= 2:
        last = words[-1]
        if last in SUFFIX_MAP:
            alt = SUFFIX_MAP[last]
            variants.append(" ".join(words[:-1] + [alt]))
    return variants


def main():
    dry_run = "--dry-run" in sys.argv

    # Load parcel index
    print("Loading parcel index...")
    parcel_index = {}
    with open(PARCEL_INDEX_FILE) as f:
        for line in f:
            parts = line.strip().split("|")
            if len(parts) >= 5:
                addr = parts[0].strip().upper()
                owner = parts[1].strip()
                geo_id = parts[2].strip()
                mkt = parts[3].strip()
                county = parts[4].strip()
                if addr and len(addr) >= 5:
                    parcel_index[addr] = {
                        "owner_name": owner,
                        "geo_id": geo_id,
                        "mkt_value": mkt,
                        "county": county,
                    }
    print(f"Parcel index: {len(parcel_index):,} unique addresses")

    # Login
    session = requests.Session()
    resp = session.post(f"{API}/auth/login", json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD})
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code}")
        sys.exit(1)
    print("Login successful")

    total_matched = 0
    total_unmatched = 0
    total_updated = 0
    offset = 0
    batch = []
    start_time = time.time()

    while True:
        resp = session.get(
            f"{API}/permits/needs-geocoding",
            params={"limit": 500, "offset": offset},
        )
        if resp.status_code != 200:
            print(f"Fetch failed: {resp.status_code}")
            break

        data = resp.json()
        permits = data.get("permits", [])
        if not permits:
            break

        for p in permits:
            addr = p.get("address", "")
            matched = False

            for variant in normalize_for_match(addr):
                parcel = parcel_index.get(variant)
                if parcel:
                    update = {"id": p["id"]}
                    if parcel.get("owner_name"):
                        update["owner_name"] = parcel["owner_name"]
                    update["raw_data"] = {
                        "parcel_geo_id": parcel.get("geo_id"),
                        "parcel_mkt_value": parcel.get("mkt_value"),
                        "parcel_county": parcel.get("county"),
                        "parcel_match": "exact",
                    }
                    batch.append(update)
                    total_matched += 1
                    matched = True
                    break

            if not matched:
                total_unmatched += 1

            if len(batch) >= 50 and not dry_run:
                resp2 = session.post(f"{API}/permits/batch-enrich", json=batch, timeout=60)
                if resp2.status_code == 200:
                    result = resp2.json()
                    total_updated += result.get("updated", 0)
                batch = []

        processed = total_matched + total_unmatched
        if processed % 2000 == 0 or len(permits) < 500:
            elapsed = time.time() - start_time
            print(
                f"  Processed: {processed:,} "
                f"(matched={total_matched:,}, unmatched={total_unmatched:,}, "
                f"updated={total_updated:,})"
            )

        offset += len(permits)
        if offset >= 25000:
            break

    # Send remaining
    if batch and not dry_run:
        resp2 = session.post(f"{API}/permits/batch-enrich", json=batch, timeout=60)
        if resp2.status_code == 200:
            total_updated += resp2.json().get("updated", 0)

    elapsed = time.time() - start_time
    print()
    print("=" * 60)
    print("IMPROVED PARCEL ENRICHMENT — RESULTS")
    print("=" * 60)
    print(f"Time: {elapsed:.0f}s")
    print(f"Matched: {total_matched:,}")
    print(f"Unmatched: {total_unmatched:,}")
    total = total_matched + total_unmatched
    if total > 0:
        print(f"Match rate: {total_matched/total*100:.1f}%")
    print(f"Updated in CRM: {total_updated:,}")
    print("=" * 60)


if __name__ == "__main__":
    main()
