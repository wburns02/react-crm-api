"""Source adapters for the unified permit pipeline.

Each adapter reads from its native format and yields NormalizedPermit dicts.
All shared parsing logic lives in normalizer.py; adapters handle only
source-specific field mapping and I/O.
"""

from __future__ import annotations

import json
import re
import sqlite3
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from .normalizer import (
    compute_address_hash,
    extract_system_type_keyword,
    is_septic_record,
    map_work_type,
    normalize_address,
    normalize_county,
    normalize_state,
    parse_date,
    parse_datetime,
    parse_mgo_description,
    parse_ossf_details,
    parse_tank_size,
)
from .quality import compute_quality_score
from .types import NormalizedPermit

# ── MGO constants ─────────────────────────────────────────────────────

OSSF_PROJECT_TYPES = (
    "OSSF",
    "On-Site Sewage Facility (OSSF) Permits",
    "On-Site Sewage Facility (Septic) Permit",
)

# ── Base class ────────────────────────────────────────────────────────


class BaseAdapter(ABC):
    """Base class for all source adapters."""

    name: str  # e.g. "mgo", "sss"

    @abstractmethod
    def read(self, **kwargs: Any) -> Iterator[NormalizedPermit]:
        """Yield NormalizedPermit records from the source."""
        ...

    @abstractmethod
    def count(self, **kwargs: Any) -> int:
        """Return total record count (for progress reporting)."""
        ...

    def _validate_coords(self, permit: dict) -> None:
        """Validate and clean lat/lng in place."""
        for coord, lo, hi in [
            ("latitude", -90, 90),
            ("longitude", -180, 180),
        ]:
            val = permit.get(coord)
            if val is not None:
                try:
                    val = float(val)
                    if not (lo <= val <= hi):
                        val = None
                except (ValueError, TypeError):
                    val = None
                permit[coord] = val

    def _finalize(self, permit: dict) -> NormalizedPermit | None:
        """Normalize address, compute hash, score quality."""
        addr = permit.get("address")
        if not addr or not addr.strip():
            return None

        # Normalize
        norm_addr = normalize_address(addr)
        county = normalize_county(permit.get("county_name"))
        state = normalize_state(permit.get("state_code")) or permit.get("state_code")

        if not norm_addr:
            return None

        permit["address"] = norm_addr
        permit["county_name"] = county or permit.get("county_name", "")
        permit["state_code"] = state or "TX"

        # Compute address hash
        permit["address_hash"] = compute_address_hash(
            norm_addr, county or "", state or "TX"
        )

        # Validate coordinates
        self._validate_coords(permit)

        # Quality score
        permit["quality_score"] = compute_quality_score(permit)
        if permit.get("raw_data") is None:
            permit["raw_data"] = {}
        permit["raw_data"]["quality_score"] = permit["quality_score"]

        return permit  # type: ignore[return-value]


# ── MGO Adapter ───────────────────────────────────────────────────────


class MGOAdapter(BaseAdapter):
    """Read from MGO SQLite database (crm_permits.db).

    The most complex adapter: description regex, work_type mapping,
    OSSF JSON parsing, jurisdiction-based source codes.
    """

    name = "mgo"

    def __init__(
        self,
        db_path: str,
        county: str | None = None,
        source_code: str | None = None,
        offset: int = 0,
        limit: int = 0,
    ) -> None:
        self.db_path = db_path
        self.county = county
        self.source_code_override = source_code
        self.offset = offset
        self.limit = limit

    def _build_query(self) -> tuple[str, list]:
        placeholders = ",".join(["?"] * len(OSSF_PROJECT_TYPES))
        where = f"state = 'TX' AND (project_type IN ({placeholders}) OR trade = 'septic')"
        params: list = list(OSSF_PROJECT_TYPES)

        if self.county:
            where += " AND jurisdiction_name = ?"
            params.append(self.county)

        return where, params

    def count(self, **kwargs: Any) -> int:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        where, params = self._build_query()
        cursor = conn.execute(f"SELECT COUNT(*) FROM permits WHERE {where}", params)
        total = cursor.fetchone()[0]
        conn.close()
        return total

    def read(self, **kwargs: Any) -> Iterator[NormalizedPermit]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        where, params = self._build_query()
        query = f"SELECT * FROM permits WHERE {where} ORDER BY jurisdiction_name, created_date"

        if self.limit > 0:
            query += f" LIMIT {self.limit}"
        if self.offset > 0:
            query += f" OFFSET {self.offset}"

        cursor = conn.execute(query, params)

        for row in cursor:
            row_dict = dict(row)
            permit = self._map_row(row_dict)
            if permit:
                result = self._finalize(permit)
                if result:
                    yield result

        conn.close()

    def _map_row(self, row: dict) -> dict | None:
        state = (row.get("state") or "").strip().upper()
        if not state or len(state) != 2:
            return None

        # Description parsing (highest-value extraction)
        desc_data = parse_mgo_description(row.get("description"))

        # OSSF details JSON
        ossf_data = parse_ossf_details(row.get("ossf_details"))

        # System type priority chain
        system_type = None
        system_type_source = None

        if desc_data.get("system_type"):
            system_type = desc_data["system_type"]
            system_type_source = "description"
        else:
            wt = map_work_type(row.get("work_type"))
            if wt:
                system_type = wt
                system_type_source = "work_type"
            else:
                text = f"{row.get('ossf_details') or ''} {row.get('description') or ''}"
                kw = extract_system_type_keyword(text)
                if kw:
                    system_type = kw
                    system_type_source = "keyword"

        # Dates
        permit_date = parse_date(row.get("issued_date")) or parse_date(
            row.get("created_date")
        )

        # Source portal code
        jurisdiction = (row.get("jurisdiction_name") or "unknown").strip()
        slug = re.sub(r"[^a-z0-9]+", "_", jurisdiction.lower()).strip("_")
        source_code = self.source_code_override or f"mgo_ossf_{slug}"

        # Raw data
        raw_data: dict[str, Any] = {}
        for key in (
            "original_id", "trade", "project_type", "work_type",
            "status", "subdivision", "lot", "apt_lot", "source_file",
        ):
            val = row.get(key)
            if val:
                raw_data[key] = val

        if row.get("description"):
            raw_data["description"] = row["description"][:2000]
        if row.get("ossf_details"):
            raw_data["ossf_details"] = row["ossf_details"]

        # Extracted structured metadata
        if desc_data.get("sqft"):
            raw_data["home_sqft"] = desc_data["sqft"]
        if desc_data.get("maintenance_contract_required") or ossf_data.get(
            "maintenance_contract_required"
        ):
            raw_data["maintenance_contract_required"] = True
        if desc_data.get("chlorine_required"):
            raw_data["chlorine_required"] = True
        if desc_data.get("renewal_years"):
            raw_data["renewal_period_years"] = desc_data["renewal_years"]
        if system_type_source:
            raw_data["system_type_source"] = system_type_source

        for key in (
            "designation_type", "specific_use", "designer_name",
            "designer_license", "installer_name", "installer_license",
        ):
            if ossf_data.get(key):
                raw_data[key] = ossf_data[key]

        return {
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
            "daily_flow_gpd": desc_data.get("daily_flow_gpd"),
            "bedrooms": desc_data.get("bedrooms"),
            "source_portal_code": source_code,
            "scraped_at": parse_datetime(row.get("scraped_at")) or datetime.now().isoformat(),
            "raw_data": raw_data,
        }


# ── SSS Adapter (SepticSearchScraper) ────────────────────────────────


class SSSAdapter(BaseAdapter):
    """Read from SepticSearchScraper JSON file."""

    name = "sss"

    # Regex for GPD, bedrooms, sqft from SSS descriptions
    _RE_GPD = re.compile(r"(\d{2,5})\s+gallons\s+per\s+day", re.IGNORECASE)
    _RE_BEDROOMS = re.compile(r"(\d{1,2})-bedroom", re.IGNORECASE)
    _RE_SQFT = re.compile(r"([\d,]+)\s*sq\.?\s*ft", re.IGNORECASE)

    DEFAULT_PATH = "/mnt/win11/Claude_Code/SepticSearchScraper/data/travis_ossf_20251215_160957.json"
    SOURCE_CODE = "sss_travis_tx"

    def __init__(
        self,
        json_path: str | None = None,
        limit: int = 0,
    ) -> None:
        self.json_path = json_path or self.DEFAULT_PATH
        self.limit = limit
        self._data: list[dict] | None = None

    def _load(self) -> list[dict]:
        if self._data is None:
            path = Path(self.json_path)
            if not path.exists():
                print(f"SSS: File not found: {self.json_path}")
                self._data = []
            else:
                with open(path) as f:
                    raw = json.load(f)
                # Filter to septic records
                self._data = [
                    r for r in raw
                    if is_septic_record(r.get("description"), r.get("specific_use"))
                ]
                print(f"SSS: {len(raw)} total → {len(self._data)} septic records")
        return self._data

    def count(self, **kwargs: Any) -> int:
        data = self._load()
        return min(len(data), self.limit) if self.limit > 0 else len(data)

    def read(self, **kwargs: Any) -> Iterator[NormalizedPermit]:
        data = self._load()
        if self.limit > 0:
            data = data[: self.limit]

        for row in data:
            permit = self._map_row(row)
            if permit:
                result = self._finalize(permit)
                if result:
                    yield result

    def _map_row(self, row: dict) -> dict | None:
        address = (row.get("address") or "").strip()
        if not address:
            return None

        # Date
        permit_date = parse_date(row.get("created_date"))

        # System type from keywords
        text = f"{row.get('description', '')} {row.get('specific_use', '')}".lower()
        system_type = extract_system_type_keyword(text)

        # Extract GPD, bedrooms from description
        desc = row.get("description", "")
        daily_flow_gpd = None
        bedrooms = None

        m = self._RE_GPD.search(desc)
        if m:
            gpd = int(m.group(1))
            if 50 <= gpd <= 50000:
                daily_flow_gpd = gpd

        m = self._RE_BEDROOMS.search(desc)
        if m:
            br = int(m.group(1))
            if 1 <= br <= 20:
                bedrooms = br

        home_sqft = None
        m = self._RE_SQFT.search(desc)
        if m:
            sqft = int(m.group(1).replace(",", ""))
            if 200 <= sqft <= 100000:
                home_sqft = sqft

        # Raw data
        raw_data: dict[str, Any] = {
            "source": "SepticSearchScraper",
            "portal": "mgoconnect.org",
        }
        for key in ("specific_use", "designation", "project_name", "status", "lot", "unit"):
            if row.get(key):
                raw_data[key] = row[key]
        if row.get("description"):
            raw_data["description"] = row["description"][:2000]
        if home_sqft:
            raw_data["home_sqft"] = home_sqft
        if system_type:
            raw_data["system_type_source"] = "keyword"

        return {
            "state_code": "TX",
            "county_name": "Travis County",
            "permit_number": row.get("project_number"),
            "address": address,
            "city": None,
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
            "source_portal_code": self.SOURCE_CODE,
            "scraped_at": datetime.now().isoformat(),
            "raw_data": raw_data,
        }


# ── TNR Adapter (Travis County TNR) ──────────────────────────────────


class TNRAdapter(BaseAdapter):
    """Read from Travis County TNR NDJSON file.

    Includes document-level deduplication (16K docs → ~9K unique addresses).
    """

    name = "tnr"

    DEFAULT_PATH = "/mnt/win11/fedora-moved/Data/tnr_septic_metadata.ndjson"
    SOURCE_CODE = "tnr_travis_tx"

    def __init__(
        self,
        ndjson_path: str | None = None,
        limit: int = 0,
    ) -> None:
        self.ndjson_path = ndjson_path or self.DEFAULT_PATH
        self.limit = limit
        self._deduped: list[dict] | None = None

    def _load_and_dedup(self) -> list[dict]:
        if self._deduped is not None:
            return self._deduped

        path = Path(self.ndjson_path)
        if not path.exists():
            print(f"TNR: File not found: {self.ndjson_path}")
            self._deduped = []
            return self._deduped

        # Load NDJSON
        records = []
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        records.append(json.loads(line))
                    except json.JSONDecodeError:
                        continue

        print(f"TNR: Loaded {len(records)} documents")

        # Dedup by address
        by_addr: dict[str, list[dict]] = {}
        for r in records:
            num = (r.get("streetNumber") or "").strip()
            name = (r.get("streetName") or "").strip()
            addr = f"{num} {name}".strip()
            if not addr:
                continue
            by_addr.setdefault(addr, []).append(r)

        deduped = []
        for addr, docs in by_addr.items():
            # Sort by date (earliest first)
            def _parse_doc_date(d: dict) -> datetime:
                try:
                    return datetime.strptime(d.get("documentDate", ""), "%m/%d/%Y")
                except (ValueError, TypeError):
                    return datetime.max

            docs.sort(key=_parse_doc_date)
            earliest = docs[0]

            all_descs = [
                d.get("documentDescription", "")
                for d in docs
                if d.get("documentDescription")
            ]

            deduped.append({
                "streetNumber": earliest.get("streetNumber", ""),
                "streetName": earliest.get("streetName", ""),
                "address": addr,
                "documentDate": earliest.get("documentDate", ""),
                "documentId": earliest.get("documentId", ""),
                "all_descriptions": all_descs,
                "doc_count": len(docs),
                "_queryMonth": earliest.get("_queryMonth", ""),
            })

        print(f"TNR: Deduped to {len(deduped)} unique addresses")
        self._deduped = deduped
        return self._deduped

    def count(self, **kwargs: Any) -> int:
        data = self._load_and_dedup()
        return min(len(data), self.limit) if self.limit > 0 else len(data)

    def read(self, **kwargs: Any) -> Iterator[NormalizedPermit]:
        data = self._load_and_dedup()
        if self.limit > 0:
            data = data[: self.limit]

        for row in data:
            permit = self._map_row(row)
            if permit:
                result = self._finalize(permit)
                if result:
                    yield result

    def _map_row(self, row: dict) -> dict | None:
        address = row.get("address", "").strip()
        if not address:
            return None

        # Parse earliest date
        permit_date = parse_date(row.get("documentDate"))

        # System type from aggregated descriptions
        text = " ".join(row.get("all_descriptions", [])).lower()
        system_type = extract_system_type_keyword(text)

        # Raw data
        raw_data: dict[str, Any] = {
            "source": "TNR Public Access Portal",
            "portal": "Travis County TNR",
            "doc_count": row.get("doc_count", 1),
        }
        if row.get("documentId"):
            raw_data["document_id"] = row["documentId"][:200]
        if row.get("all_descriptions"):
            raw_data["document_descriptions"] = row["all_descriptions"][:10]
        if row.get("_queryMonth"):
            raw_data["query_month"] = row["_queryMonth"]
        if system_type:
            raw_data["system_type_source"] = "keyword"

        return {
            "state_code": "TX",
            "county_name": "Travis County",
            "permit_number": None,
            "address": address,
            "city": None,
            "zip_code": None,
            "parcel_number": None,
            "latitude": None,
            "longitude": None,
            "owner_name": None,
            "applicant_name": None,
            "permit_date": permit_date,
            "expiration_date": None,
            "system_type": system_type,
            "daily_flow_gpd": None,
            "bedrooms": None,
            "source_portal_code": self.SOURCE_CODE,
            "scraped_at": datetime.now().isoformat(),
            "raw_data": raw_data,
        }


# ── OCR Adapter ───────────────────────────────────────────────────────


class OCRAdapter(BaseAdapter):
    """Read from adaptive_ocr.db (OCR-processed permits)."""

    name = "ocr"

    def __init__(
        self,
        db_path: str,
        source_name: str,
        table: str | None = None,
        offset: int = 0,
        limit: int = 0,
    ) -> None:
        self.db_path = db_path
        self.source_name = source_name
        self.table = table
        self.offset = offset
        self.limit = limit

    def _detect_table(self, conn: sqlite3.Connection) -> str:
        """Auto-detect the permit table name."""
        if self.table:
            return self.table
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [r[0] for r in cursor.fetchall()]
        # Prefer 'permits' or 'ocr_permits' or first table with 'permit' in name
        for candidate in ["permits", "ocr_permits"]:
            if candidate in tables:
                return candidate
        for t in tables:
            if "permit" in t.lower():
                return t
        if tables:
            return tables[0]
        raise ValueError(f"No tables found in {self.db_path}")

    def count(self, **kwargs: Any) -> int:
        conn = sqlite3.connect(self.db_path)
        table = self._detect_table(conn)
        cursor = conn.execute(f"SELECT COUNT(*) FROM [{table}]")
        total = cursor.fetchone()[0]
        conn.close()
        return total

    def read(self, **kwargs: Any) -> Iterator[NormalizedPermit]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        table = self._detect_table(conn)

        query = f"SELECT * FROM [{table}]"
        if self.limit > 0:
            query += f" LIMIT {self.limit}"
        if self.offset > 0:
            query += f" OFFSET {self.offset}"

        cursor = conn.execute(query)

        for row in cursor:
            row_dict = dict(row)
            permit = self._map_row(row_dict)
            if permit:
                result = self._finalize(permit)
                if result:
                    yield result

        conn.close()

    def _map_row(self, row: dict) -> dict | None:
        address = (row.get("property_address") or "").strip()
        if not address:
            return None

        # County from source name
        county_name = None
        sn_lower = self.source_name.lower()
        if "guadalupe" in sn_lower:
            county_name = "Guadalupe"
        elif "comal" in sn_lower:
            county_name = "Comal"

        # Raw data with OCR-specific fields
        raw_data: dict[str, Any] = {"system_type_source": "ocr"}
        for f in (
            "drainfield_type", "soil_type", "gate_code",
            "lot_size", "bedrooms", "bathrooms", "daily_flow",
            "notes", "conditions", "inspector_name", "approval_date",
            "ocr_confidence", "source_pdf", "page_number",
        ):
            val = row.get(f)
            if val and str(val).strip():
                raw_data[f] = str(val).strip()

        # System type
        system_type = None
        raw_st = row.get("system_type")
        if raw_st:
            system_type = extract_system_type_keyword(str(raw_st))
            if not system_type and str(raw_st).strip():
                system_type = str(raw_st).strip().title()

        # Bedrooms
        bedrooms = None
        br_str = row.get("bedrooms")
        if br_str:
            m = re.search(r"(\d+)", str(br_str))
            if m:
                bedrooms = int(m.group(1))

        # Daily flow
        daily_flow_gpd = None
        flow_str = row.get("daily_flow")
        if flow_str:
            m = re.search(r"(\d+)", str(flow_str))
            if m:
                daily_flow_gpd = int(m.group(1))

        return {
            "state_code": "TX",
            "county_name": county_name,
            "permit_number": (row.get("permit_number") or "").strip() or None,
            "address": address,
            "city": (row.get("city") or "").strip() or None,
            "zip_code": (row.get("zip_code") or "").strip() or None,
            "owner_name": (row.get("owner_name") or "").strip() or None,
            "owner_phone": (row.get("owner_phone") or "").strip() or None,
            "owner_email": (row.get("owner_email") or "").strip() or None,
            "contractor_name": (row.get("installer_company") or "").strip() or None,
            "permit_date": parse_date(row.get("permit_date")),
            "install_date": parse_date(row.get("install_date")),
            "system_type": system_type,
            "tank_size_gallons": parse_tank_size(
                row.get("tank_size_gallons") or row.get("tank_size")
            ),
            "daily_flow_gpd": daily_flow_gpd,
            "bedrooms": bedrooms,
            "source_portal_code": f"ocr_{self.source_name}",
            "scraped_at": parse_datetime(row.get("processed_at")) or datetime.now().isoformat(),
            "raw_data": raw_data,
        }


# ── Adapter Registry ─────────────────────────────────────────────────

ADAPTER_CLASSES: dict[str, type[BaseAdapter]] = {
    "mgo": MGOAdapter,
    "sss": SSSAdapter,
    "tnr": TNRAdapter,
    "ocr": OCRAdapter,
}
