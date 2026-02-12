#!/usr/bin/env python3
"""
T430 Bulk Load: by_trade CSVs → PostgreSQL on T430.

Loads 269M+ permit records from by_trade CSV files into a
partitioned PostgreSQL database on the T430 using COPY for speed.

Usage:
    # On T430 (fedora-2):
    python3 scripts/t430_bulk_load.py --phase setup     # Create DB + schema
    python3 scripts/t430_bulk_load.py --phase load      # Load CSVs via COPY
    python3 scripts/t430_bulk_load.py --phase enrich    # Enrich from crm_permits.db
    python3 scripts/t430_bulk_load.py --phase index     # Build indexes + tsvector
    python3 scripts/t430_bulk_load.py --phase verify    # Verify counts
    python3 scripts/t430_bulk_load.py --phase all       # Run all phases
"""

import argparse
import csv
import io
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path

import psycopg2
from psycopg2 import sql

# Paths on T430 NAS
DATA_ROOT = Path("/dataPool/data/records/gpu_scraped_data/mgo_extraction/processed")
BY_TRADE_DIR = DATA_ROOT / "by_trade"
CRM_PERMITS_DB = Path("/dataPool/data/databases/crm_permits.db")

# Database connection
DB_NAME = "permits"
DB_USER = "will"
DB_HOST = "localhost"

# Trade CSV files in load order (largest first)
TRADE_FILES = [
    "general_building.csv",
    "electrical.csv",
    "plumbing.csv",
    "hvac.csv",
    "roofing.csv",
    "pool.csv",
    "solar.csv",
    "gas.csv",
    "septic.csv",
]

# CSV columns in by_trade files
TRADE_CSV_COLUMNS = [
    "permit_number", "address", "city", "state", "zip",
    "county", "project_type", "work_type", "project_name",
    "description", "status", "date_created", "lat", "lng", "parcel_number",
]

# Target DB columns for COPY (matching CSV order + trade column)
COPY_COLUMNS = [
    "permit_number", "address", "city", "state_code", "zip_code",
    "county", "project_type", "work_type", "project_name",
    "description", "status", "date_created", "lat", "lng", "parcel_number",
    "trade",
]

STATES = [
    "AL", "AR", "AZ", "CA", "CT", "DE", "FL", "GA", "IL", "IN",
    "KS", "LA", "MA", "MD", "MN", "MO", "MS", "ND", "NY", "OK",
    "PA", "PR", "SC", "TN", "TX", "UT", "WI", "WV", "WY",
]


def get_conn(dbname=DB_NAME):
    return psycopg2.connect(dbname=dbname, user=DB_USER, host=DB_HOST)


def get_admin_conn():
    """Connect as postgres superuser for DB creation."""
    return psycopg2.connect(dbname="postgres", user="postgres", host=DB_HOST)


def phase_setup():
    """Create database, extensions, partitioned table, and partitions."""
    print("=== PHASE: SETUP ===")

    # Create database (connect as postgres user)
    try:
        conn = get_admin_conn()
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {} OWNER {}").format(
                sql.Identifier(DB_NAME), sql.Identifier(DB_USER)))
            print(f"Created database '{DB_NAME}'")
        else:
            print(f"Database '{DB_NAME}' already exists")
        cur.close()
        conn.close()
    except psycopg2.OperationalError:
        # If can't connect as postgres, try peer auth
        print("Note: Could not connect as postgres user. Trying as current user...")
        conn = psycopg2.connect(dbname="postgres", user=DB_USER, host=DB_HOST)
        conn.autocommit = True
        cur = conn.cursor()
        cur.execute("SELECT 1 FROM pg_database WHERE datname = %s", (DB_NAME,))
        if not cur.fetchone():
            cur.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(DB_NAME)))
            print(f"Created database '{DB_NAME}'")
        else:
            print(f"Database '{DB_NAME}' already exists")
        cur.close()
        conn.close()

    # Create extensions and table
    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()

    print("Creating extensions...")
    cur.execute("CREATE EXTENSION IF NOT EXISTS postgis")
    cur.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    print("Creating partitioned table...")
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permits (
            id              BIGINT GENERATED ALWAYS AS IDENTITY,
            permit_number   TEXT,
            address         TEXT,
            city            TEXT,
            state_code      CHAR(2) NOT NULL,
            zip_code        TEXT,
            county          TEXT,
            lat             DOUBLE PRECISION,
            lng             DOUBLE PRECISION,
            geom            GEOGRAPHY(POINT, 4326),
            parcel_number   TEXT,
            project_type    TEXT,
            work_type       TEXT,
            trade           TEXT,
            category        TEXT,
            project_name    TEXT,
            description     TEXT,
            status          TEXT,
            date_created    TIMESTAMP,
            owner_name      TEXT,
            applicant_name  TEXT,
            ossf_details    TEXT,
            system_type     TEXT,
            subdivision     TEXT,
            source          TEXT,
            source_file     TEXT,
            raw_data        JSONB,
            search_vector   TSVECTOR,
            loaded_at       TIMESTAMP DEFAULT NOW(),
            PRIMARY KEY (id, state_code)
        ) PARTITION BY LIST (state_code)
    """)

    print("Creating partitions...")
    for state in STATES:
        partition_name = f"permits_{state.lower()}"
        cur.execute(sql.SQL("""
            CREATE TABLE IF NOT EXISTS {} PARTITION OF permits
            FOR VALUES IN (%s)
        """).format(sql.Identifier(partition_name)), (state,))

    # Default partition for unknown states
    cur.execute("""
        CREATE TABLE IF NOT EXISTS permits_default
        PARTITION OF permits DEFAULT
    """)

    cur.close()
    conn.close()
    print("Setup complete!")


def phase_load():
    """Load by_trade CSVs into PostgreSQL using COPY."""
    print("=== PHASE: LOAD ===")

    conn = get_conn()
    cur = conn.cursor()

    # Check current row count
    cur.execute("SELECT COUNT(*) FROM permits")
    existing = cur.fetchone()[0]
    print(f"Existing rows: {existing:,}")

    if existing > 0:
        print("WARNING: Table already has data. Skipping load to avoid duplicates.")
        print("Drop and recreate if you want to reload: DROP TABLE permits CASCADE;")
        cur.close()
        conn.close()
        return

    total_loaded = 0
    start_time = time.time()

    for trade_file in TRADE_FILES:
        csv_path = BY_TRADE_DIR / trade_file
        if not csv_path.exists():
            print(f"  SKIP: {trade_file} not found")
            continue

        trade_name = trade_file.replace(".csv", "")
        print(f"\nLoading {trade_file}...")

        # Count lines for progress
        line_count = int(subprocess.check_output(
            ["wc", "-l", str(csv_path)]
        ).decode().split()[0]) - 1  # minus header
        print(f"  Records: {line_count:,}")

        # Use COPY with a pipe — read CSV, add trade column, pipe to COPY
        batch_size = 100_000
        batch_num = 0
        file_loaded = 0

        with open(csv_path, "r", newline="", encoding="utf-8", errors="replace") as f:
            reader = csv.DictReader(f)

            while True:
                # Build batch in memory as tab-separated for COPY
                buf = io.StringIO()
                count = 0

                for row in reader:
                    state = (row.get("state") or "").strip().upper()
                    if not state or len(state) != 2:
                        continue

                    def clean(val):
                        """Strip tabs, newlines, carriage returns."""
                        if not val:
                            return "\\N"
                        return val.replace("\t", " ").replace("\n", " ").replace("\r", "").strip() or "\\N"

                    def parse_float(val, lo, hi):
                        """Parse float within range, return None if invalid."""
                        if not val or not val.strip():
                            return None
                        v = val.strip()
                        # Quick check: must start with digit, minus, or dot
                        if v[0] not in '0123456789.-':
                            return None
                        try:
                            f = float(v)
                            if lo <= f <= hi:
                                return f
                        except (ValueError, TypeError):
                            pass
                        return None

                    # Clean lat/lng
                    lat_f = parse_float(row.get("lat", ""), -90, 90)
                    lng_f = parse_float(row.get("lng", ""), -180, 180)

                    # Parse date
                    date_str = (row.get("date_created") or "").strip().replace("\r", "")
                    if date_str:
                        date_str = date_str[:19]  # YYYY-MM-DDTHH:MM:SS
                        # Validate it looks like a date
                        if len(date_str) < 8 or date_str[4:5] not in ('-', '/'):
                            date_str = "\\N"
                    else:
                        date_str = "\\N"

                    # Write tab-separated line
                    values = [
                        clean(row.get("permit_number")),
                        clean(row.get("address")),
                        clean(row.get("city")),
                        state,
                        clean(row.get("zip")),
                        clean(row.get("county")),
                        clean(row.get("project_type")),
                        clean(row.get("work_type")),
                        clean(row.get("project_name")),
                        clean(row.get("description")),
                        clean(row.get("status")),
                        date_str if date_str != "\\N" else "\\N",
                        str(lat_f) if lat_f is not None else "\\N",
                        str(lng_f) if lng_f is not None else "\\N",
                        clean(row.get("parcel_number")),
                        trade_name,
                    ]
                    buf.write("\t".join(values) + "\n")
                    count += 1

                    if count >= batch_size:
                        break

                if count == 0:
                    break

                batch_num += 1
                buf.seek(0)

                try:
                    cur.copy_from(
                        buf,
                        "permits",
                        columns=COPY_COLUMNS,
                        null="\\N",
                    )
                    conn.commit()
                except Exception as e:
                    conn.rollback()
                    print(f"  BATCH ERROR at batch {batch_num}: {e}")
                    print(f"  Skipping {count} rows and continuing...")
                    # Re-create cursor after error
                    cur.close()
                    cur = conn.cursor()

                file_loaded += count
                total_loaded += count

                if batch_num % 10 == 0:
                    elapsed = time.time() - start_time
                    rate = total_loaded / elapsed if elapsed > 0 else 0
                    print(f"  {trade_file}: {file_loaded:,}/{line_count:,} "
                          f"({file_loaded/line_count*100:.1f}%) | "
                          f"Total: {total_loaded:,} | {rate:,.0f} rec/s")

        elapsed = time.time() - start_time
        rate = total_loaded / elapsed if elapsed > 0 else 0
        print(f"  {trade_file} DONE: {file_loaded:,} loaded | "
              f"Total: {total_loaded:,} | {rate:,.0f} rec/s")

    elapsed = time.time() - start_time
    print(f"\n=== LOAD COMPLETE ===")
    print(f"Total loaded: {total_loaded:,}")
    print(f"Time: {elapsed/60:.1f} minutes")
    print(f"Rate: {total_loaded/elapsed:,.0f} records/second" if elapsed > 0 else "")

    cur.close()
    conn.close()


def phase_dedup():
    """Deduplicate records that appear in multiple trade files."""
    print("=== PHASE: DEDUPLICATE ===")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM permits")
    before = cur.fetchone()[0]
    print(f"Before dedup: {before:,}")

    print("Finding duplicates (permit_number + address + state_code)...")
    print("This may take a while on 269M rows...")

    # Delete duplicates, keeping the row with the most data
    cur.execute("""
        DELETE FROM permits a
        USING permits b
        WHERE a.id > b.id
          AND a.state_code = b.state_code
          AND a.permit_number = b.permit_number
          AND a.permit_number IS NOT NULL
          AND a.address = b.address
          AND a.address IS NOT NULL
    """)
    deleted = cur.rowcount
    conn.commit()

    cur.execute("SELECT COUNT(*) FROM permits")
    after = cur.fetchone()[0]
    print(f"Deleted: {deleted:,}")
    print(f"After dedup: {after:,}")

    cur.close()
    conn.close()


def phase_enrich():
    """Enrich permits from crm_permits.db (owner_name, applicant_name, etc.)."""
    print("=== PHASE: ENRICH ===")

    if not CRM_PERMITS_DB.exists():
        print(f"crm_permits.db not found at {CRM_PERMITS_DB}, skipping enrichment")
        return

    conn = get_conn()
    cur = conn.cursor()

    # Create temp table for CRM data
    print("Creating temp table for CRM enrichment data...")
    cur.execute("DROP TABLE IF EXISTS crm_temp")
    cur.execute("""
        CREATE TEMP TABLE crm_temp (
            permit_number TEXT,
            state TEXT,
            address TEXT,
            owner_name TEXT,
            applicant_name TEXT,
            ossf_details TEXT,
            subdivision TEXT
        )
    """)

    # Load from SQLite
    print("Loading crm_permits.db...")
    sqlite_conn = sqlite3.connect(str(CRM_PERMITS_DB))
    sqlite_conn.row_factory = sqlite3.Row
    sqlite_cur = sqlite_conn.cursor()

    sqlite_cur.execute("""
        SELECT permit_number, state, address, owner_name,
               COALESCE(applicant_name, applicant_company) as applicant_name,
               ossf_details, subdivision
        FROM permits
        WHERE owner_name IS NOT NULL OR applicant_name IS NOT NULL
           OR ossf_details IS NOT NULL
    """)

    batch = []
    total = 0
    for row in sqlite_cur:
        batch.append((
            row["permit_number"],
            (row["state"] or "").strip().upper(),
            row["address"],
            row["owner_name"],
            row["applicant_name"],
            row["ossf_details"],
            row["subdivision"],
        ))
        if len(batch) >= 10000:
            cur.executemany(
                "INSERT INTO crm_temp VALUES (%s,%s,%s,%s,%s,%s,%s)",
                batch
            )
            total += len(batch)
            batch = []
            if total % 100000 == 0:
                print(f"  Loaded {total:,} CRM records...")

    if batch:
        cur.executemany(
            "INSERT INTO crm_temp VALUES (%s,%s,%s,%s,%s,%s,%s)",
            batch
        )
        total += len(batch)

    conn.commit()
    sqlite_conn.close()
    print(f"  Loaded {total:,} CRM records into temp table")

    # Update permits with enrichment data
    print("Enriching permits with owner/applicant names...")
    cur.execute("""
        UPDATE permits p
        SET owner_name = t.owner_name,
            applicant_name = t.applicant_name,
            ossf_details = t.ossf_details,
            subdivision = t.subdivision
        FROM crm_temp t
        WHERE p.permit_number = t.permit_number
          AND p.state_code = t.state
          AND p.address = t.address
          AND (p.owner_name IS NULL OR p.applicant_name IS NULL)
    """)
    updated = cur.rowcount
    conn.commit()
    print(f"  Updated {updated:,} permits with enrichment data")

    cur.close()
    conn.close()


def phase_index():
    """Build tsvector, PostGIS geometry, and all indexes."""
    print("=== PHASE: INDEX ===")

    conn = get_conn()
    conn.autocommit = True
    cur = conn.cursor()

    # Build PostGIS geometry
    print("Building PostGIS geometry from lat/lng...")
    cur.execute("""
        UPDATE permits
        SET geom = ST_SetSRID(ST_MakePoint(lng, lat), 4326)::geography
        WHERE lat IS NOT NULL AND lng IS NOT NULL AND geom IS NULL
    """)
    print(f"  Updated {cur.rowcount:,} rows with geometry")

    # Build tsvector
    print("Building tsvector search index (this takes a while)...")
    cur.execute("""
        UPDATE permits SET search_vector =
            setweight(to_tsvector('english', COALESCE(permit_number, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(address, '')), 'A') ||
            setweight(to_tsvector('english', COALESCE(owner_name, '')), 'B') ||
            setweight(to_tsvector('english', COALESCE(city, '') || ' ' || COALESCE(county, '')), 'B') ||
            setweight(to_tsvector('english', COALESCE(description, '')), 'C')
        WHERE search_vector IS NULL
    """)
    print(f"  Updated {cur.rowcount:,} rows with search vectors")

    # Create indexes
    indexes = [
        ("idx_permits_search", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_permits_search ON permits USING GIN (search_vector)"),
        ("idx_permits_address_trgm", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_permits_address_trgm ON permits USING GIN (address gin_trgm_ops)"),
        ("idx_permits_geom", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_permits_geom ON permits USING GIST (geom)"),
        ("idx_permits_date_brin", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_permits_date_brin ON permits USING BRIN (date_created)"),
        ("idx_permits_permit_number", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_permits_permit_number ON permits (permit_number)"),
        ("idx_permits_zip", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_permits_zip ON permits (zip_code)"),
        ("idx_permits_trade", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_permits_trade ON permits (trade)"),
        ("idx_permits_county", "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_permits_county ON permits (county)"),
    ]

    for name, ddl in indexes:
        print(f"  Creating {name}...")
        start = time.time()
        cur.execute(ddl)
        elapsed = time.time() - start
        print(f"  {name} done ({elapsed:.0f}s)")

    # Analyze
    print("Running ANALYZE...")
    cur.execute("ANALYZE permits")

    cur.close()
    conn.close()
    print("Index phase complete!")


def phase_verify():
    """Verify data loaded correctly."""
    print("=== PHASE: VERIFY ===")

    conn = get_conn()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM permits")
    total = cur.fetchone()[0]
    print(f"Total records: {total:,}")

    print("\nBy state (top 10):")
    cur.execute("""
        SELECT state_code, COUNT(*) as cnt
        FROM permits GROUP BY state_code
        ORDER BY cnt DESC LIMIT 10
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    print("\nBy trade:")
    cur.execute("""
        SELECT trade, COUNT(*) as cnt
        FROM permits GROUP BY trade
        ORDER BY cnt DESC
    """)
    for row in cur.fetchall():
        print(f"  {row[0]}: {row[1]:,}")

    print("\nWith lat/lng:")
    cur.execute("SELECT COUNT(*) FROM permits WHERE lat IS NOT NULL")
    geo = cur.fetchone()[0]
    print(f"  {geo:,} ({geo/total*100:.1f}%)" if total > 0 else "  0")

    print("\nWith owner_name:")
    cur.execute("SELECT COUNT(*) FROM permits WHERE owner_name IS NOT NULL")
    owners = cur.fetchone()[0]
    print(f"  {owners:,}")

    # Test full-text search
    print("\nFull-text search test: 'septic harris county'")
    cur.execute("""
        SELECT permit_number, address, city, state_code, trade
        FROM permits
        WHERE search_vector @@ plainto_tsquery('english', 'septic harris county')
        LIMIT 5
    """)
    for row in cur.fetchall():
        print(f"  {row[0]} | {row[1]}, {row[2]}, {row[3]} | {row[4]}")

    cur.close()
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="T430 Bulk Load: CSVs → PostgreSQL")
    parser.add_argument("--phase", required=True,
                        choices=["setup", "load", "dedup", "enrich", "index", "verify", "all"],
                        help="Which phase to run")
    args = parser.parse_args()

    if args.phase == "all":
        phase_setup()
        phase_load()
        phase_dedup()
        phase_enrich()
        phase_index()
        phase_verify()
    elif args.phase == "setup":
        phase_setup()
    elif args.phase == "load":
        phase_load()
    elif args.phase == "dedup":
        phase_dedup()
    elif args.phase == "enrich":
        phase_enrich()
    elif args.phase == "index":
        phase_index()
    elif args.phase == "verify":
        phase_verify()


if __name__ == "__main__":
    main()
