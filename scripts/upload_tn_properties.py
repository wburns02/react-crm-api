#!/usr/bin/env python3
"""
Upload Tennessee property records to production via the bulk-load API endpoint.

Usage:
  python scripts/upload_tn_properties.py
"""

import json
import os
import re
import sys
import requests

API_BASE = "https://react-crm-api-production.up.railway.app"
LOGIN_URL = f"{API_BASE}/api/v2/auth/login"
BULK_URL = f"{API_BASE}/api/v2/properties/estimate-tank/bulk-load"

# Admin credentials
EMAIL = "will@macseptic.com"
PASSWORD = "#Espn2025"

BATCH_SIZE = 2000  # Records per API call


def normalize_address(address: str) -> str:
    addr = address.upper().strip()
    replacements = {
        " STREET": " ST", " DRIVE": " DR", " ROAD": " RD", " AVENUE": " AVE",
        " BOULEVARD": " BLVD", " LANE": " LN", " COURT": " CT", " CIRCLE": " CIR",
        " PLACE": " PL", " PIKE": " PK", " HIGHWAY": " HWY", " PARKWAY": " PKWY",
        ",": "", ".": "",
    }
    for old, new in replacements.items():
        addr = addr.replace(old, new)
    return re.sub(r"\s+", " ", addr).strip()


def estimate_from_sqft(sqft):
    if sqft <= 0: return 1000, "low", "default"
    if sqft < 1500: return 750, "high", "sqft"
    if sqft < 2500: return 1000, "high", "sqft"
    if sqft < 3500: return 1250, "medium", "sqft"
    return 1500, "medium", "sqft"


def estimate_from_acres_value(acres, impr_value):
    if acres > 2.0 and impr_value > 400000: return 1500, "medium", "acres_value"
    if acres > 5.0 and impr_value > 300000: return 1500, "medium", "acres_value"
    if acres > 1.0 and impr_value > 500000: return 1500, "medium", "acres_value"
    if impr_value > 600000: return 1250, "medium", "acres_value"
    if impr_value > 350000: return 1000, "medium", "acres_value"
    if impr_value < 150000: return 750, "medium", "acres_value"
    return 1000, "medium", "acres_value"


def estimate_from_system_type(system_type, designation):
    st = (system_type or "").lower()
    des = (designation or "").lower()
    if "commercial" in des: return 1500, "medium", "system_type"
    if "multi-family" in des: return 1500, "medium", "system_type"
    if "drip irrigation" in st: return 1250, "medium", "system_type"
    if "low pressure dose" in st: return 1250, "medium", "system_type"
    if "absorptive mound" in st: return 1250, "medium", "system_type"
    if "standard trench" in st or "leaching chamber" in st: return 1000, "medium", "system_type"
    if "surface application" in st: return 1000, "medium", "system_type"
    if "single family" in des: return 1000, "medium", "system_type"
    return 1000, "low", "default"


def load_davidson(path):
    print(f"Loading Davidson County...")
    with open(path) as f:
        data = json.load(f)
    records = []
    for r in data:
        addr = r.get("PropAddr", "")
        if not addr or addr == "0" or len(addr) < 3: continue
        acres = r.get("Acres") or 0
        impr = int(r.get("ImprAppr") or 0)
        total = int(r.get("TotlAppr") or 0)
        gal, conf, src = estimate_from_acres_value(acres, impr)
        records.append({
            "address_normalized": normalize_address(addr),
            "address_raw": addr,
            "city": (r.get("PropCity") or "NASHVILLE").upper(),
            "state": "TN", "zip_code": r.get("PropZip"),
            "county": "Davidson",
            "acres": acres if acres > 0 else None,
            "improvement_value": impr if impr > 0 else None,
            "total_value": total if total > 0 else None,
            "land_use": r.get("LUDesc"),
            "estimated_tank_gallons": gal, "estimation_confidence": conf,
            "estimation_source": src, "data_source": "davidson_property",
            "source_id": str(r.get("ParID")),
        })
    print(f"  {len(records)} records")
    return records


def load_rutherford(path):
    print(f"Loading Rutherford County...")
    with open(path) as f:
        data = json.load(f)
    records = []
    for r in data:
        addr = r.get("FormattedLocation", "")
        if not addr or len(addr) < 3: continue
        sqft = int(r.get("TotalFinishedArea") or 0)
        total = int(r.get("TotalValue") or 0)
        yr = int(r.get("YearBuilt") or 0)
        gal, conf, src = estimate_from_sqft(sqft) if sqft > 0 else (1000, "low", "default")
        records.append({
            "address_normalized": normalize_address(addr),
            "address_raw": addr,
            "city": (r.get("CITY") or "").upper() or None,
            "state": "TN", "zip_code": r.get("ZIP"),
            "county": "Rutherford",
            "sqft": sqft if sqft > 0 else None,
            "total_value": total if total > 0 else None,
            "year_built": yr if yr > 0 else None,
            "land_use": r.get("LandUseCode"),
            "estimated_tank_gallons": gal, "estimation_confidence": conf,
            "estimation_source": src, "data_source": "rutherford_property",
        })
    print(f"  {len(records)} records")
    return records


def load_wilson(path):
    print(f"Loading Wilson County...")
    with open(path) as f:
        data = json.load(f)
    records = []
    for r in data:
        num = r.get("PhysLcStreetNumber", "")
        name = r.get("PhysLcStreetName", "")
        if not name or len(name) < 2: continue
        addr = f"{num} {name}".strip() if num else name
        total = int(r.get("TotalFMVCurrent") or 0)
        yr = int(r.get("YearActuallyBuilt1Imp") or 0)
        gal = 1500 if total > 500000 else 1000
        records.append({
            "address_normalized": normalize_address(addr),
            "address_raw": addr,
            "county": "Wilson", "state": "TN",
            "total_value": total if total > 0 else None,
            "year_built": yr if yr > 0 else None,
            "estimated_tank_gallons": gal, "estimation_confidence": "low",
            "estimation_source": "total_value" if total > 0 else "default",
            "data_source": "wilson_property",
        })
    print(f"  {len(records)} records")
    return records


def load_williamson(path):
    print(f"Loading Williamson County septic...")
    with open(path) as f:
        data = json.load(f)
    records = []
    for r in data:
        addr = r.get("address", "")
        if not addr or len(addr) < 3: continue
        wt = r.get("work_type") or r.get("designation") or ""
        des = r.get("designation", "")
        gal, conf, src = estimate_from_system_type(wt, des)
        records.append({
            "address_normalized": normalize_address(addr),
            "address_raw": addr,
            "county": "Williamson", "state": "TN",
            "system_type": wt if wt else None,
            "designation": des if des else None,
            "estimated_tank_gallons": gal, "estimation_confidence": conf,
            "estimation_source": src, "data_source": "williamson_septic",
            "source_id": r.get("project_number"),
        })
    print(f"  {len(records)} records")
    return records


def main():
    # Login
    print("Logging in...")
    session = requests.Session()
    resp = session.post(LOGIN_URL, json={"email": EMAIL, "password": PASSWORD})
    if resp.status_code != 200:
        print(f"Login failed: {resp.status_code} {resp.text[:200]}")
        sys.exit(1)
    print("  Logged in OK")

    # Load all sources
    files = {
        "davidson": ("/mnt/win11/Fedora/crown_permits/tn_nashville_davidson.json", load_davidson),
        "rutherford": ("/mnt/win11/Fedora/crown_permits/tn_rutherford_murfreesboro.json", load_rutherford),
        "wilson": ("/mnt/win11/Fedora/crown_permits/tn_wilson_lebanon.json", load_wilson),
        "williamson": ("/mnt/win11/Claude_Code/SepticSearchScraper/data/williamson_ossf_20251212_145006.json", load_williamson),
    }

    all_records = []
    for name, (path, loader) in files.items():
        if os.path.exists(path):
            all_records.extend(loader(path))
        else:
            print(f"  WARNING: {name} file not found at {path}")

    print(f"\nTotal records: {len(all_records)}")

    # Upload in batches
    first_batch = True
    uploaded = 0
    for i in range(0, len(all_records), BATCH_SIZE):
        batch = all_records[i:i + BATCH_SIZE]
        payload = {
            "records": batch,
            "clear_existing": first_batch,
        }
        first_batch = False

        resp = session.post(BULK_URL, json=payload)
        if resp.status_code != 200:
            print(f"  ERROR batch {i}: {resp.status_code} {resp.text[:300]}")
            continue

        result = resp.json()
        uploaded += result["inserted"]
        print(f"  Uploaded {uploaded}/{len(all_records)} (total in DB: {result['total']})")

    print(f"\nDone! {uploaded} records uploaded to production.")

    # Verify with stats
    resp = session.get(f"{API_BASE}/api/v2/properties/estimate-tank/stats")
    if resp.status_code == 200:
        stats = resp.json()
        print(f"Stats: {stats['total_properties']} properties across {stats['counties']}")

    # Test lookup
    test_addrs = [
        "2628 TINNIN RD, GOODLETTSVILLE, TN",
        "3213 LEXMARK CIR, MURFREESBORO, TN",
    ]
    for addr in test_addrs:
        resp = session.get(f"{API_BASE}/api/v2/properties/estimate-tank", params={"address": addr})
        if resp.status_code == 200:
            data = resp.json()
            print(f"\n  Test: {addr}")
            print(f"    → {data['estimated_gallons']} gal ({data['confidence']}) - {data['message']}")


if __name__ == "__main__":
    main()
