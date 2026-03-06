#!/usr/bin/env python3
"""
ETL script to load Tennessee property records into property_lookups table.

Sources:
  - Davidson County (Nashville): 155K records - acres, improvement value
  - Rutherford County (Murfreesboro): 104K records - sqft, year built
  - Wilson County (Lebanon): 15K records - coordinates, year built
  - Williamson County (septic permits): 32K records - system type

Tank size estimation rules:
  - sqft < 1500 or equivalent → 1000 gal
  - sqft 1500-2500 → 1000 gal
  - sqft 2500-3500 → 1250 gal
  - sqft > 3500 → 1500 gal
  - Large acreage (>2 acres) + high value → 1500 gal
  - Commercial → 1500+ gal

Usage:
  python scripts/load_tn_properties.py

  # Or with DATABASE_URL override:
  DATABASE_URL=postgresql://... python scripts/load_tn_properties.py
"""

import json
import os
import re
import sys
import uuid
from datetime import datetime

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def normalize_address(address: str) -> str:
    """Normalize address for matching."""
    addr = address.upper().strip()
    replacements = {
        " STREET": " ST",
        " DRIVE": " DR",
        " ROAD": " RD",
        " AVENUE": " AVE",
        " BOULEVARD": " BLVD",
        " LANE": " LN",
        " COURT": " CT",
        " CIRCLE": " CIR",
        " PLACE": " PL",
        " PIKE": " PK",
        " HIGHWAY": " HWY",
        " PARKWAY": " PKWY",
        ",": "",
        ".": "",
    }
    for old, new in replacements.items():
        addr = addr.replace(old, new)
    addr = re.sub(r"\s+", " ", addr).strip()
    return addr


def estimate_from_sqft(sqft: int) -> tuple[int, str, str]:
    """Estimate tank gallons from square footage. Returns (gallons, confidence, source)."""
    if sqft <= 0:
        return 1000, "low", "default"
    if sqft < 1500:
        return 750, "high", "sqft"
    if sqft < 2500:
        return 1000, "high", "sqft"
    if sqft < 3500:
        return 1250, "medium", "sqft"
    return 1500, "medium", "sqft"


def estimate_from_acres_value(acres: float, impr_value: int) -> tuple[int, str, str]:
    """Estimate tank from lot size + improvement value."""
    # Large lot with significant improvement = likely bigger home
    if acres > 2.0 and impr_value > 400000:
        return 1500, "medium", "acres_value"
    if acres > 5.0 and impr_value > 300000:
        return 1500, "medium", "acres_value"
    if acres > 1.0 and impr_value > 500000:
        return 1500, "medium", "acres_value"
    if impr_value > 600000:
        return 1250, "medium", "acres_value"
    if impr_value > 350000:
        return 1000, "medium", "acres_value"
    if impr_value < 150000:
        return 750, "medium", "acres_value"
    return 1000, "medium", "acres_value"


def estimate_from_system_type(system_type: str, designation: str) -> tuple[int, str, str]:
    """Estimate from septic system type (Williamson County)."""
    st = (system_type or "").lower()
    des = (designation or "").lower()

    if "commercial" in des:
        return 1500, "medium", "system_type"
    if "multi-family" in des:
        return 1500, "medium", "system_type"

    # Drip irrigation systems typically serve larger homes
    if "drip irrigation" in st:
        return 1250, "medium", "system_type"
    if "low pressure dose" in st:
        return 1250, "medium", "system_type"
    if "absorptive mound" in st:
        return 1250, "medium", "system_type"

    # Standard systems
    if "standard trench" in st or "leaching chamber" in st:
        return 1000, "medium", "system_type"
    if "surface application" in st:
        return 1000, "medium", "system_type"

    # Default for single family
    if "single family" in des:
        return 1000, "medium", "system_type"

    return 1000, "low", "default"


def load_davidson(path: str) -> list[dict]:
    """Load Nashville/Davidson County property data."""
    print(f"Loading Davidson County from {path}...")
    with open(path) as f:
        data = json.load(f)

    records = []
    for r in data:
        addr = r.get("PropAddr", "")
        if not addr or addr == "0" or len(addr) < 3:
            continue

        acres = r.get("Acres") or 0
        impr = int(r.get("ImprAppr") or 0)
        total = int(r.get("TotlAppr") or 0)

        gallons, confidence, source = estimate_from_acres_value(acres, impr)

        records.append({
            "address_normalized": normalize_address(addr),
            "address_raw": addr,
            "city": (r.get("PropCity") or "NASHVILLE").upper(),
            "state": "TN",
            "zip_code": r.get("PropZip"),
            "county": "Davidson",
            "acres": acres if acres > 0 else None,
            "improvement_value": impr if impr > 0 else None,
            "total_value": total if total > 0 else None,
            "land_use": r.get("LUDesc"),
            "estimated_tank_gallons": gallons,
            "estimation_confidence": confidence,
            "estimation_source": source,
            "data_source": "davidson_property",
            "source_id": str(r.get("ParID")),
        })

    print(f"  Prepared {len(records)} Davidson records")
    return records


def load_rutherford(path: str) -> list[dict]:
    """Load Rutherford County property data (has sqft)."""
    print(f"Loading Rutherford County from {path}...")
    with open(path) as f:
        data = json.load(f)

    records = []
    for r in data:
        addr = r.get("FormattedLocation", "")
        if not addr or len(addr) < 3:
            continue

        sqft = int(r.get("TotalFinishedArea") or 0)
        total = int(r.get("TotalValue") or 0)
        yr = int(r.get("YearBuilt") or 0)

        if sqft > 0:
            gallons, confidence, source = estimate_from_sqft(sqft)
        else:
            gallons, confidence, source = 1000, "low", "default"

        records.append({
            "address_normalized": normalize_address(addr),
            "address_raw": addr,
            "city": (r.get("CITY") or "").upper() or None,
            "state": "TN",
            "zip_code": r.get("ZIP"),
            "county": "Rutherford",
            "sqft": sqft if sqft > 0 else None,
            "total_value": total if total > 0 else None,
            "year_built": yr if yr > 0 else None,
            "land_use": r.get("LandUseCode"),
            "estimated_tank_gallons": gallons,
            "estimation_confidence": confidence,
            "estimation_source": source,
            "data_source": "rutherford_property",
            "source_id": None,
        })

    print(f"  Prepared {len(records)} Rutherford records")
    return records


def load_wilson(path: str) -> list[dict]:
    """Load Wilson County property data."""
    print(f"Loading Wilson County from {path}...")
    with open(path) as f:
        data = json.load(f)

    records = []
    for r in data:
        num = r.get("PhysLcStreetNumber", "")
        name = r.get("PhysLcStreetName", "")
        if not name or len(name) < 2:
            continue
        addr = f"{num} {name}".strip() if num else name

        total = int(r.get("TotalFMVCurrent") or 0)
        yr = int(r.get("YearActuallyBuilt1Imp") or 0)

        # Wilson has less data — use total value as proxy
        if total > 500000:
            gallons, confidence = 1500, "low"
        elif total > 300000:
            gallons, confidence = 1000, "low"
        else:
            gallons, confidence = 1000, "low"

        records.append({
            "address_normalized": normalize_address(addr),
            "address_raw": addr,
            "city": None,  # Wilson data doesn't have city
            "state": "TN",
            "zip_code": None,
            "county": "Wilson",
            "total_value": total if total > 0 else None,
            "year_built": yr if yr > 0 else None,
            "estimated_tank_gallons": gallons,
            "estimation_confidence": confidence,
            "estimation_source": "total_value" if total > 0 else "default",
            "data_source": "wilson_property",
            "source_id": None,
        })

    print(f"  Prepared {len(records)} Wilson records")
    return records


def load_williamson(path: str) -> list[dict]:
    """Load Williamson County septic permit data."""
    print(f"Loading Williamson County septic permits from {path}...")
    with open(path) as f:
        data = json.load(f)

    records = []
    for r in data:
        addr = r.get("address", "")
        if not addr or len(addr) < 3:
            continue

        work_type = r.get("work_type") or r.get("designation") or ""
        designation = r.get("designation", "")

        gallons, confidence, source = estimate_from_system_type(work_type, designation)

        records.append({
            "address_normalized": normalize_address(addr),
            "address_raw": addr,
            "city": None,  # Williamson data doesn't have separate city
            "state": "TN",
            "zip_code": None,
            "county": "Williamson",
            "system_type": work_type if work_type else None,
            "designation": designation if designation else None,
            "estimated_tank_gallons": gallons,
            "estimation_confidence": confidence,
            "estimation_source": source,
            "data_source": "williamson_septic",
            "source_id": r.get("project_number"),
        })

    print(f"  Prepared {len(records)} Williamson records")
    return records


def main():
    import asyncio
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
    from sqlalchemy.orm import sessionmaker

    # Get DATABASE_URL from env or .env file
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), ".env")
        if os.path.exists(env_path):
            with open(env_path) as f:
                for line in f:
                    if line.startswith("DATABASE_URL="):
                        database_url = line.split("=", 1)[1].strip().strip('"').strip("'")
                        break

    if not database_url:
        print("ERROR: DATABASE_URL not set. Set it in environment or .env file.")
        sys.exit(1)

    # Convert to async URL
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif not database_url.startswith("postgresql+asyncpg://"):
        database_url = f"postgresql+asyncpg://{database_url}"

    print(f"Connecting to database...")

    engine = create_async_engine(database_url, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    # Data file paths
    data_files = {
        "davidson": "/mnt/win11/Fedora/crown_permits/tn_nashville_davidson.json",
        "rutherford": "/mnt/win11/Fedora/crown_permits/tn_rutherford_murfreesboro.json",
        "wilson": "/mnt/win11/Fedora/crown_permits/tn_wilson_lebanon.json",
        "williamson": "/mnt/win11/Claude_Code/SepticSearchScraper/data/williamson_ossf_20251212_145006.json",
    }

    # Check files exist
    for name, path in data_files.items():
        if not os.path.exists(path):
            print(f"WARNING: {name} data file not found at {path}")

    # Load all records
    all_records = []
    if os.path.exists(data_files["davidson"]):
        all_records.extend(load_davidson(data_files["davidson"]))
    if os.path.exists(data_files["rutherford"]):
        all_records.extend(load_rutherford(data_files["rutherford"]))
    if os.path.exists(data_files["wilson"]):
        all_records.extend(load_wilson(data_files["wilson"]))
    if os.path.exists(data_files["williamson"]):
        all_records.extend(load_williamson(data_files["williamson"]))

    print(f"\nTotal records to load: {len(all_records)}")

    async def do_insert():
        async with async_session() as session:
            # Create table if not exists (fallback)
            await session.execute(text("""
                CREATE TABLE IF NOT EXISTS property_lookups (
                    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
                    address_normalized VARCHAR(500) NOT NULL,
                    address_raw VARCHAR(500),
                    city VARCHAR(100),
                    state VARCHAR(2) DEFAULT 'TN',
                    zip_code VARCHAR(10),
                    county VARCHAR(100) NOT NULL,
                    sqft INTEGER,
                    acres FLOAT,
                    improvement_value INTEGER,
                    total_value INTEGER,
                    year_built INTEGER,
                    land_use VARCHAR(100),
                    bedrooms INTEGER,
                    system_type VARCHAR(200),
                    designation VARCHAR(100),
                    estimated_tank_gallons INTEGER NOT NULL DEFAULT 1000,
                    estimation_confidence VARCHAR(20) DEFAULT 'medium',
                    estimation_source VARCHAR(50),
                    data_source VARCHAR(100) NOT NULL,
                    source_id VARCHAR(100),
                    created_at TIMESTAMPTZ DEFAULT NOW()
                )
            """))
            await session.commit()

            # Clear existing data
            result = await session.execute(text("DELETE FROM property_lookups"))
            print(f"Cleared {result.rowcount} existing records")
            await session.commit()

            # Insert in batches
            batch_size = 5000
            inserted = 0
            for i in range(0, len(all_records), batch_size):
                batch = all_records[i:i + batch_size]
                # Use raw SQL for speed
                values_parts = []
                params = {}
                for j, rec in enumerate(batch):
                    key = f"b{i+j}"
                    values_parts.append(
                        f"(gen_random_uuid(), "
                        f":{key}_addr_norm, :{key}_addr_raw, :{key}_city, :{key}_state, "
                        f":{key}_zip, :{key}_county, :{key}_sqft, :{key}_acres, "
                        f":{key}_impr, :{key}_total, :{key}_yr, :{key}_lu, "
                        f":{key}_beds, :{key}_sys, :{key}_desg, "
                        f":{key}_gal, :{key}_conf, :{key}_src, "
                        f":{key}_dsrc, :{key}_sid, NOW())"
                    )
                    params[f"{key}_addr_norm"] = rec["address_normalized"]
                    params[f"{key}_addr_raw"] = rec.get("address_raw")
                    params[f"{key}_city"] = rec.get("city")
                    params[f"{key}_state"] = rec.get("state", "TN")
                    params[f"{key}_zip"] = rec.get("zip_code")
                    params[f"{key}_county"] = rec["county"]
                    params[f"{key}_sqft"] = rec.get("sqft")
                    params[f"{key}_acres"] = rec.get("acres")
                    params[f"{key}_impr"] = rec.get("improvement_value")
                    params[f"{key}_total"] = rec.get("total_value")
                    params[f"{key}_yr"] = rec.get("year_built")
                    params[f"{key}_lu"] = rec.get("land_use")
                    params[f"{key}_beds"] = rec.get("bedrooms")
                    params[f"{key}_sys"] = rec.get("system_type")
                    params[f"{key}_desg"] = rec.get("designation")
                    params[f"{key}_gal"] = rec["estimated_tank_gallons"]
                    params[f"{key}_conf"] = rec["estimation_confidence"]
                    params[f"{key}_src"] = rec["estimation_source"]
                    params[f"{key}_dsrc"] = rec["data_source"]
                    params[f"{key}_sid"] = rec.get("source_id")

                sql = f"""INSERT INTO property_lookups (
                    id, address_normalized, address_raw, city, state, zip_code, county,
                    sqft, acres, improvement_value, total_value, year_built, land_use,
                    bedrooms, system_type, designation,
                    estimated_tank_gallons, estimation_confidence, estimation_source,
                    data_source, source_id, created_at
                ) VALUES {', '.join(values_parts)}"""

                await session.execute(text(sql), params)
                inserted += len(batch)
                print(f"  Inserted {inserted}/{len(all_records)} records...")
                await session.commit()

            # Create indexes if they don't exist
            print("Creating indexes...")
            for idx_sql in [
                "CREATE INDEX IF NOT EXISTS idx_property_lookup_addr_city ON property_lookups (address_normalized, city)",
                "CREATE INDEX IF NOT EXISTS idx_property_lookup_county ON property_lookups (county)",
                "CREATE INDEX IF NOT EXISTS idx_property_lookup_zip ON property_lookups (zip_code)",
                "CREATE EXTENSION IF NOT EXISTS pg_trgm",
                "CREATE INDEX IF NOT EXISTS idx_property_lookup_addr_trgm ON property_lookups USING gin (address_normalized gin_trgm_ops)",
            ]:
                try:
                    await session.execute(text(idx_sql))
                    await session.commit()
                except Exception as e:
                    await session.rollback()
                    print(f"  Index warning: {e}")

            # Verify
            result = await session.execute(text("SELECT COUNT(*) FROM property_lookups"))
            count = result.scalar()
            print(f"\nDone! {count} property records loaded.")

            # Stats by county
            result = await session.execute(text(
                "SELECT county, COUNT(*), AVG(estimated_tank_gallons)::int FROM property_lookups GROUP BY county ORDER BY COUNT(*) DESC"
            ))
            print("\nBy county:")
            for row in result.all():
                print(f"  {row[0]}: {row[1]:,} records (avg {row[2]} gal)")

    asyncio.run(do_insert())


if __name__ == "__main__":
    main()
