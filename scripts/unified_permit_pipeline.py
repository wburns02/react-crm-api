#!/usr/bin/env python3
"""Unified Permit Data Pipeline — One True Source.

Replaces 8 separate ETL/enrichment scripts with one modular pipeline:

  Source Adapters → Normalize → Enrich (parcel) → Dedup/Merge → API Batch

Usage:
    # Full pipeline: all sources
    python scripts/unified_permit_pipeline.py --step ingest --sources all

    # Single source
    python scripts/unified_permit_pipeline.py --step ingest --sources mgo \
        --db /mnt/win11/fedora-moved/Data/crm_permits.db --county "Williamson County"

    # Geocode backlog (daily cron)
    python scripts/unified_permit_pipeline.py --step geocode --limit 2000

    # Parcel enrichment only
    python scripts/unified_permit_pipeline.py --step parcel

    # Dry run (map only, don't send)
    python scripts/unified_permit_pipeline.py --step ingest --sources all --dry-run

    # Stats
    python scripts/unified_permit_pipeline.py --step stats
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

# Ensure the project root is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from pipeline.adapters import (
    ADAPTER_CLASSES,
    MGOAdapter,
    OCRAdapter,
    SSSAdapter,
    TNRAdapter,
)
from pipeline.api_client import CRMClient, DEFAULT_API_URL
from pipeline.deduplicator import Deduplicator
from pipeline.enrichment import (
    ParcelIndex,
    run_geocode_backlog,
    run_parcel_enrichment,
)
from pipeline.types import ALL_SOURCES, NormalizedPermit

# ── Defaults ──────────────────────────────────────────────────────────

DEFAULT_MGO_DB = "/mnt/win11/fedora-moved/Data/crm_permits.db"
DEFAULT_SSS_JSON = "/mnt/win11/Claude_Code/SepticSearchScraper/data/travis_ossf_20251215_160957.json"
DEFAULT_TNR_NDJSON = "/mnt/win11/fedora-moved/Data/tnr_septic_metadata.ndjson"
DEFAULT_PARCEL_INDEX = "/mnt/win11/fedora-moved/Data/central_tx_parcels_index.txt"

CHECKPOINT_PATH = "/mnt/win11/fedora-moved/Data/pipeline_checkpoint.json"

# ── Checkpoint ────────────────────────────────────────────────────────


def load_checkpoint() -> dict:
    """Load incremental run checkpoint."""
    p = Path(CHECKPOINT_PATH)
    if p.exists():
        try:
            with open(p) as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_checkpoint(data: dict) -> None:
    """Save checkpoint for incremental runs."""
    p = Path(CHECKPOINT_PATH)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w") as f:
        json.dump(data, f, indent=2)
    print(f"Checkpoint saved: {p}")


# ── Adapter Factory ───────────────────────────────────────────────────


def create_adapters(
    sources: list[str], args: argparse.Namespace
) -> list[tuple[str, object]]:
    """Create adapter instances from CLI args."""
    adapters = []

    for src in sources:
        if src == "mgo":
            db = args.db or DEFAULT_MGO_DB
            if not Path(db).exists():
                print(f"MGO: DB not found: {db} — skipping")
                continue
            adapters.append((
                "mgo",
                MGOAdapter(
                    db_path=db,
                    county=args.county,
                    source_code=args.source_code,
                    offset=args.offset,
                    limit=args.limit,
                ),
            ))

        elif src == "sss":
            json_path = args.json_path or DEFAULT_SSS_JSON
            if not Path(json_path).exists():
                print(f"SSS: JSON not found: {json_path} — skipping")
                continue
            adapters.append((
                "sss",
                SSSAdapter(json_path=json_path, limit=args.limit),
            ))

        elif src == "tnr":
            ndjson_path = args.ndjson_path or DEFAULT_TNR_NDJSON
            if not Path(ndjson_path).exists():
                print(f"TNR: NDJSON not found: {ndjson_path} — skipping")
                continue
            adapters.append((
                "tnr",
                TNRAdapter(ndjson_path=ndjson_path, limit=args.limit),
            ))

        elif src == "ocr":
            if not args.ocr_db:
                print("OCR: --ocr-db required for OCR source — skipping")
                continue
            if not Path(args.ocr_db).exists():
                print(f"OCR: DB not found: {args.ocr_db} — skipping")
                continue
            if not args.ocr_source_name:
                print("OCR: --ocr-source-name required — skipping")
                continue
            adapters.append((
                "ocr",
                OCRAdapter(
                    db_path=args.ocr_db,
                    source_name=args.ocr_source_name,
                    table=args.ocr_table,
                    offset=args.offset,
                    limit=args.limit,
                ),
            ))

        else:
            print(f"Unknown source: {src} — skipping")

    return adapters


# ── Steps ─────────────────────────────────────────────────────────────


def step_ingest(args: argparse.Namespace) -> None:
    """Ingest step: read sources → normalize → enrich → dedup → send."""
    sources = ALL_SOURCES if args.sources == "all" else args.sources.split(",")
    adapters = create_adapters(sources, args)

    if not adapters:
        print("No valid adapters configured. Check source files exist.")
        sys.exit(1)

    # Optional parcel enrichment before ingestion
    parcel_index = None
    if not args.skip_parcel:
        pi_path = args.parcel_index or DEFAULT_PARCEL_INDEX
        if Path(pi_path).exists():
            parcel_index = ParcelIndex(pi_path)
            parcel_index.load()
        else:
            print(f"Parcel index not found: {pi_path} — skipping pre-enrichment")

    # Deduplicator for cross-source merge
    dedup = Deduplicator()

    # Read all sources
    total_start = time.time()
    source_stats: dict[str, dict] = {}

    for name, adapter in adapters:
        print(f"\n{'='*60}")
        print(f"SOURCE: {name.upper()}")
        print(f"{'='*60}")

        count = adapter.count()
        print(f"Records available: {count:,}")

        start = time.time()
        mapped = 0
        skipped = 0

        for permit in adapter.read():
            # Pre-enrichment: parcel matching (fast, in-memory)
            if parcel_index:
                parcel_index.enrich_permit(permit)

            dedup.add(permit)
            mapped += 1

            if mapped % 10000 == 0:
                elapsed = time.time() - start
                rate = mapped / elapsed if elapsed > 0 else 0
                print(f"  {name}: {mapped:,} mapped ({rate:.0f}/s)")

        elapsed = time.time() - start
        rate = mapped / elapsed if elapsed > 0 else 0
        print(f"  {name} done: {mapped:,} mapped in {elapsed:.1f}s ({rate:.0f}/s)")

        source_stats[name] = {
            "available": count,
            "mapped": mapped,
            "elapsed": elapsed,
        }

    # Merge cross-source duplicates
    print(f"\n{'='*60}")
    print("DEDUPLICATION")
    print(f"{'='*60}")
    merged = dedup.merge()
    ds = dedup.stats
    print(f"Input records: {ds['total_input']:,}")
    print(f"Unique addresses: {ds['unique_addresses']:,}")
    print(f"Single-source: {ds['single_source']:,}")
    print(f"Multi-source merged: {ds['multi_source']:,}")
    print(f"Output records: {len(merged):,}")

    # Send to API
    if args.dry_run:
        print(f"\n[DRY RUN] Would send {len(merged):,} permits to API")
        _print_sample(merged)
    else:
        print(f"\n{'='*60}")
        print("API INGESTION")
        print(f"{'='*60}")

        client = CRMClient(args.api_url)
        client.login()

        # Group by source_portal_code for batch sending
        by_source: dict[str, list[dict]] = {}
        for p in merged:
            src = p.get("source_portal_code", "unknown")
            by_source.setdefault(src, []).append(p)

        total_stats = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
        for src_code, permits in sorted(by_source.items()):
            print(f"\n  Source: {src_code} ({len(permits):,} permits)")
            stats = client.send_all(permits, src_code, batch_size=args.batch_size)
            for k in total_stats:
                total_stats[k] += stats.get(k, 0)

        print(f"\n{'='*60}")
        print("TOTALS")
        print(f"{'='*60}")
        print(f"Inserted: {total_stats['inserted']:,}")
        print(f"Updated: {total_stats['updated']:,}")
        print(f"Skipped: {total_stats['skipped']:,}")
        print(f"Errors: {total_stats['errors']:,}")

    # Save checkpoint
    checkpoint = load_checkpoint()
    checkpoint["last_run"] = datetime.now().isoformat()
    checkpoint["source_stats"] = source_stats
    checkpoint["dedup_stats"] = ds
    save_checkpoint(checkpoint)

    total_elapsed = time.time() - total_start
    print(f"\nPipeline complete in {total_elapsed:.1f}s")


def step_geocode(args: argparse.Namespace) -> None:
    """Geocode step: update permits missing lat/lng via Census API."""
    client = CRMClient(args.api_url)
    client.login()

    limit = args.limit if args.limit > 0 else 2000
    source = args.source_filter

    stats = run_geocode_backlog(client, limit=limit, source=source)
    print(f"\nGeocoding results: {stats}")


def step_parcel(args: argparse.Namespace) -> None:
    """Parcel step: enrich existing permits with parcel owner data."""
    client = CRMClient(args.api_url)
    client.login()

    pi_path = args.parcel_index or DEFAULT_PARCEL_INDEX
    parcel_index = ParcelIndex(pi_path)

    limit = args.limit if args.limit > 0 else 25000
    source = args.source_filter

    stats = run_parcel_enrichment(
        client, parcel_index,
        limit=limit, source=source,
        dry_run=args.dry_run,
    )
    print(f"\nParcel enrichment results: {stats}")


def step_stats(args: argparse.Namespace) -> None:
    """Stats step: show pipeline state and checkpoint info."""
    checkpoint = load_checkpoint()

    if not checkpoint:
        print("No checkpoint found. Run --step ingest first.")
        return

    print(f"{'='*60}")
    print("PIPELINE STATUS")
    print(f"{'='*60}")
    print(f"Last run: {checkpoint.get('last_run', 'never')}")

    ss = checkpoint.get("source_stats", {})
    if ss:
        print(f"\nSource stats from last run:")
        for name, st in ss.items():
            print(f"  {name}: {st.get('mapped', 0):,} mapped from {st.get('available', 0):,} available")

    ds = checkpoint.get("dedup_stats", {})
    if ds:
        print(f"\nDedup stats:")
        print(f"  Input: {ds.get('total_input', 0):,}")
        print(f"  Unique: {ds.get('unique_addresses', 0):,}")
        print(f"  Multi-source merges: {ds.get('multi_source', 0):,}")

    # Check source file existence
    print(f"\nSource files:")
    for label, path in [
        ("MGO DB", DEFAULT_MGO_DB),
        ("SSS JSON", DEFAULT_SSS_JSON),
        ("TNR NDJSON", DEFAULT_TNR_NDJSON),
        ("Parcel Index", DEFAULT_PARCEL_INDEX),
    ]:
        exists = Path(path).exists()
        size = ""
        if exists:
            sz = Path(path).stat().st_size
            if sz > 1024 * 1024 * 1024:
                size = f" ({sz / 1024 / 1024 / 1024:.1f} GB)"
            elif sz > 1024 * 1024:
                size = f" ({sz / 1024 / 1024:.0f} MB)"
            else:
                size = f" ({sz / 1024:.0f} KB)"
        status = f"OK{size}" if exists else "MISSING"
        print(f"  {label}: {status} — {path}")


def _print_sample(permits: list[dict], n: int = 5) -> None:
    """Print sample records for dry-run inspection."""
    print(f"\nSample records (first {n}):")
    for p in permits[:n]:
        addr = p.get("address", "?")
        county = p.get("county_name", "?")
        st = p.get("system_type", "—")
        date = p.get("permit_date", "—")
        owner = p.get("owner_name", "—")
        score = p.get("quality_score", 0)
        src = p.get("source_portal_code", "?")
        merged = (p.get("raw_data") or {}).get("merged_sources")
        merge_info = f" [merged: {','.join(merged)}]" if merged else ""
        print(f"  {addr} | {county} | {st} | {date} | owner={owner} | q={score} | {src}{merge_info}")


# ── CLI ───────────────────────────────────────────────────────────────


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified Permit Data Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--step",
        choices=["ingest", "geocode", "parcel", "stats"],
        required=True,
        help="Pipeline step to run",
    )
    parser.add_argument(
        "--sources",
        default="all",
        help="Comma-separated source names (mgo,sss,tnr,ocr) or 'all'",
    )
    parser.add_argument(
        "--api-url",
        default=DEFAULT_API_URL,
        help="CRM API base URL",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=5000,
        help="Records per API batch (default: 5000)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=0,
        help="Max records per source (0 = all)",
    )
    parser.add_argument(
        "--offset",
        type=int,
        default=0,
        help="Skip first N records (MGO/OCR only)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Map only, don't send to API",
    )

    # Source-specific paths
    parser.add_argument("--db", help="MGO SQLite database path")
    parser.add_argument("--county", help="Filter MGO to specific county")
    parser.add_argument("--source-code", help="Override source_portal_code")
    parser.add_argument("--json-path", help="SSS JSON file path")
    parser.add_argument("--ndjson-path", help="TNR NDJSON file path")
    parser.add_argument("--ocr-db", help="OCR SQLite database path")
    parser.add_argument("--ocr-source-name", help="OCR source identifier")
    parser.add_argument("--ocr-table", help="OCR SQLite table name")

    # Enrichment
    parser.add_argument("--parcel-index", help="Parcel index file path")
    parser.add_argument(
        "--skip-parcel",
        action="store_true",
        help="Skip parcel enrichment during ingest",
    )
    parser.add_argument(
        "--source-filter",
        help="Filter geocode/parcel step to specific source_portal_code",
    )

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()

    print(f"Unified Permit Pipeline v1.0.0")
    print(f"Step: {args.step}")
    print(f"API: {args.api_url}")
    if args.dry_run:
        print("[DRY RUN MODE]")
    print()

    if args.step == "ingest":
        step_ingest(args)
    elif args.step == "geocode":
        step_geocode(args)
    elif args.step == "parcel":
        step_parcel(args)
    elif args.step == "stats":
        step_stats(args)


if __name__ == "__main__":
    main()
