"""Enrichment modules: parcel matching and geocoding.

ParcelIndex: fast in-memory matching (~621K records, ~40MB).
CensusGeocoder: Census Geocoder API (free, no key, ~1 req/s).
"""

from __future__ import annotations

import re
import time
from pathlib import Path
from typing import Any

import requests

from .api_client import CRMClient

# ── Parcel Index ──────────────────────────────────────────────────────

DEFAULT_PARCEL_INDEX = "/mnt/win11/fedora-moved/Data/central_tx_parcels_index.txt"

# Street suffix alternates for variant matching
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


class ParcelIndex:
    """In-memory lookup of central TX parcel records.

    File format: address|owner|geo_id|mkt_value|county  (pipe-delimited)
    """

    def __init__(self, path: str = DEFAULT_PARCEL_INDEX) -> None:
        self.path = path
        self._index: dict[str, dict[str, str]] = {}
        self._loaded = False

    def load(self) -> int:
        """Load the parcel index file. Returns record count."""
        if self._loaded:
            return len(self._index)

        p = Path(self.path)
        if not p.exists():
            print(f"ParcelIndex: File not found: {self.path}")
            self._loaded = True
            return 0

        with open(p) as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) >= 5:
                    addr = parts[0].strip().upper()
                    if addr and len(addr) >= 5:
                        self._index[addr] = {
                            "owner_name": parts[1].strip(),
                            "geo_id": parts[2].strip(),
                            "mkt_value": parts[3].strip(),
                            "county": parts[4].strip(),
                        }

        self._loaded = True
        print(f"ParcelIndex: {len(self._index):,} records loaded")
        return len(self._index)

    @staticmethod
    def _address_variants(addr: str | None) -> list[str]:
        """Generate address variants for fuzzy matching."""
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

    def match(self, address: str | None) -> tuple[dict[str, str] | None, str | None]:
        """Try to match an address against the parcel index.

        Returns (parcel_data, match_type) where match_type is
        "exact" or "variant", or (None, None) if no match.
        """
        if not self._loaded:
            self.load()

        for i, variant in enumerate(self._address_variants(address)):
            parcel = self._index.get(variant)
            if parcel:
                return parcel, "exact" if i == 0 else "variant"
        return None, None

    def enrich_permit(self, permit: dict) -> dict:
        """Enrich a permit dict with parcel data in-place."""
        parcel, match_type = self.match(permit.get("address"))
        if parcel:
            if parcel.get("owner_name"):
                permit["parcel_owner_name"] = parcel["owner_name"]
                # Also set owner_name if not already present
                if not permit.get("owner_name"):
                    permit["owner_name"] = parcel["owner_name"]
            if "raw_data" not in permit or permit["raw_data"] is None:
                permit["raw_data"] = {}
            permit["raw_data"]["parcel_geo_id"] = parcel.get("geo_id")
            permit["raw_data"]["parcel_mkt_value"] = parcel.get("mkt_value")
            permit["raw_data"]["parcel_county"] = parcel.get("county")
            permit["raw_data"]["parcel_match"] = match_type
            permit["parcel_match_type"] = match_type
            permit["parcel_geo_id"] = parcel.get("geo_id")
            permit["parcel_mkt_value"] = parcel.get("mkt_value")
        return permit


# ── Census Geocoder ───────────────────────────────────────────────────

CENSUS_GEOCODER_URL = (
    "https://geocoding.geo.census.gov/geocoder/geographies/onelineaddress"
)
DELAY_BETWEEN_REQUESTS = 0.3  # seconds


class CensusGeocoder:
    """Geocode addresses via Census Geocoder API (free, no key)."""

    def __init__(self) -> None:
        self.session = requests.Session()
        self._count = 0
        self._matched = 0

    def geocode(self, address: str, state: str = "TX") -> dict[str, Any] | None:
        """Geocode a single address.

        Returns dict with latitude, longitude, city, zip_code, matched_address
        or None on failure.
        """
        full = f"{address}, {state}" if state and state not in address else address

        params = {
            "address": full,
            "benchmark": "Public_AR_Current",
            "vintage": "Current_Current",
            "format": "json",
        }

        try:
            resp = self.session.get(CENSUS_GEOCODER_URL, params=params, timeout=15)
            self._count += 1
            time.sleep(DELAY_BETWEEN_REQUESTS)

            if resp.status_code != 200:
                return None

            data = resp.json()
            matches = data.get("result", {}).get("addressMatches", [])
            if not matches:
                return None

            match = matches[0]
            coords = match.get("coordinates", {})
            components = match.get("addressComponents", {})

            self._matched += 1
            return {
                "latitude": coords.get("y"),
                "longitude": coords.get("x"),
                "city": components.get("city", "").title(),
                "zip_code": components.get("zip", ""),
                "matched_address": match.get("matchedAddress", ""),
            }

        except Exception as e:
            print(f"  Geocode error for '{address}': {e}")
            return None

    @property
    def stats(self) -> dict[str, int]:
        return {
            "attempted": self._count,
            "matched": self._matched,
            "unmatched": self._count - self._matched,
        }


FETCH_PAGE_SIZE = 500  # API caps at 5000; use 500 for safety


def run_geocode_backlog(
    client: CRMClient,
    limit: int = 2000,
    source: str | None = None,
) -> dict[str, int]:
    """Fetch permits needing geocoding from API and geocode them.

    Paginates through the needs-geocoding endpoint in pages of 500,
    geocodes each batch, and sends updates. Re-logins on auth failures.
    """
    geocoder = CensusGeocoder()
    total_processed = 0
    updated = 0
    start_time = time.time()

    while total_processed < limit:
        page_size = min(FETCH_PAGE_SIZE, limit - total_processed)
        permits = client.fetch_permits_needing_geocoding(
            limit=page_size, source=source
        )

        if not permits:
            if total_processed == 0:
                print("No permits need geocoding.")
            else:
                print(f"No more permits to geocode (processed {total_processed}).")
            break

        print(f"\nFetched {len(permits)} permits needing geocoding (batch starting at {total_processed})")
        updates: list[dict] = []

        for i, p in enumerate(permits):
            addr = p.get("address", "")
            state = p.get("state_code", "TX") or "TX"
            result = geocoder.geocode(addr, state)

            if result:
                update: dict = {
                    "id": p["id"],
                    "latitude": result["latitude"],
                    "longitude": result["longitude"],
                }
                if result.get("city"):
                    update["city"] = result["city"]
                if result.get("zip_code"):
                    update["zip_code"] = result["zip_code"]
                updates.append(update)

            # Send in batches of 50
            if len(updates) >= 50:
                resp = client.batch_geocode(updates)
                if isinstance(resp, dict):
                    if resp.get("status") == "failed":
                        # Re-login and retry
                        print("  Auth expired, re-logging in...")
                        client.login()
                        resp = client.batch_geocode(updates)
                    updated += resp.get("updated", 0)
                updates = []

            total_processed += 1
            if total_processed % 100 == 0:
                s = geocoder.stats
                elapsed = time.time() - start_time
                rate = s["attempted"] / elapsed if elapsed > 0 else 0
                remaining = limit - total_processed
                eta = remaining / rate / 60 if rate > 0 else 0
                print(
                    f"  Progress: {total_processed}/{limit} "
                    f"(geocoded={s['matched']}, failed={s['unmatched']}) "
                    f"rate={rate:.1f}/s ETA={eta:.0f}min"
                )

        # Final batch for this page
        if updates:
            resp = client.batch_geocode(updates)
            if isinstance(resp, dict):
                if resp.get("status") == "failed":
                    client.login()
                    resp = client.batch_geocode(updates)
                updated += resp.get("updated", 0)

    stats = geocoder.stats
    stats["updated"] = updated
    print(f"\nGeocoding complete: {stats}")
    return stats


def run_parcel_enrichment(
    client: CRMClient,
    parcel_index: ParcelIndex,
    limit: int = 25000,
    source: str | None = None,
    dry_run: bool = False,
) -> dict[str, int]:
    """Fetch permits needing parcel data and enrich them.

    This is the post-ingestion parcel step (--step parcel).
    """
    parcel_index.load()

    permits = client.fetch_permits_needing_parcel(limit=limit, source=source)
    if not permits:
        print("No permits need parcel enrichment.")
        return {"matched": 0, "unmatched": 0, "updated": 0}

    print(f"Enriching {len(permits)} permits with parcel data...")

    matched = 0
    unmatched = 0
    updated = 0
    batch: list[dict] = []

    for p in permits:
        addr = p.get("address", "")
        parcel, match_type = parcel_index.match(addr)

        if parcel:
            update: dict[str, Any] = {"id": p["id"]}
            if parcel.get("owner_name"):
                update["owner_name"] = parcel["owner_name"]
            update["raw_data"] = {
                "parcel_geo_id": parcel.get("geo_id"),
                "parcel_mkt_value": parcel.get("mkt_value"),
                "parcel_county": parcel.get("county"),
                "parcel_match": match_type,
            }
            batch.append(update)
            matched += 1
        else:
            unmatched += 1

        if len(batch) >= 50 and not dry_run:
            resp = client.batch_enrich(batch)
            updated += resp.get("updated", 0) if isinstance(resp, dict) else 0
            batch = []

    # Final batch
    if batch and not dry_run:
        resp = client.batch_enrich(batch)
        updated += resp.get("updated", 0) if isinstance(resp, dict) else 0

    total = matched + unmatched
    rate = matched / total * 100 if total else 0
    print(f"\nParcel enrichment: matched={matched}, unmatched={unmatched} ({rate:.1f}%), updated={updated}")
    return {"matched": matched, "unmatched": unmatched, "updated": updated}
