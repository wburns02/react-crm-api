"""Shared API client for CRM permit ingestion.

Consolidates the login, batch-send, retry, and progress reporting
logic that was copy-pasted across all 8 ETL scripts.
"""

from __future__ import annotations

import sys
import time
from typing import Any

import requests

DEFAULT_API_URL = "https://react-crm-api-production.up.railway.app/api/v2"
LOGIN_EMAIL = "will@macseptic.com"
LOGIN_PASSWORD = "#Espn2025"


class CRMClient:
    """Authenticated client for the CRM permit batch API."""

    def __init__(self, api_url: str = DEFAULT_API_URL) -> None:
        self.api_url = api_url.rstrip("/")
        self.session = requests.Session()
        self._logged_in = False

    def login(self) -> None:
        """Authenticate and store session cookie."""
        print(f"Logging in to {self.api_url}...")
        resp = self.session.post(
            f"{self.api_url}/auth/login",
            json={"email": LOGIN_EMAIL, "password": LOGIN_PASSWORD},
        )
        if resp.status_code != 200:
            print(f"Login failed: {resp.status_code} {resp.text}")
            sys.exit(1)
        self._logged_in = True
        print("Login successful")

    def ensure_logged_in(self) -> None:
        if not self._logged_in:
            self.login()

    # ── Batch Ingestion ───────────────────────────────────────────────

    def send_batch(
        self,
        permits: list[dict[str, Any]],
        source_code: str,
        batch_num: int = 1,
        total_batches: int = 1,
        max_retries: int = 3,
    ) -> dict[str, Any]:
        """Send a batch of permits to POST /permits/batch with retry."""
        self.ensure_logged_in()

        payload = {
            "source_portal_code": source_code,
            "permits": permits,
        }

        for attempt in range(max_retries):
            try:
                resp = self.session.post(
                    f"{self.api_url}/permits/batch",
                    json=payload,
                    timeout=300,
                )
                if resp.status_code != 200:
                    detail = resp.text[:200]
                    print(
                        f"  Batch {batch_num}/{total_batches} failed "
                        f"(HTTP {resp.status_code}): {detail}"
                    )
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
                    f"inserted={stats.get('inserted', 0)} "
                    f"updated={stats.get('updated', 0)} "
                    f"skipped={stats.get('skipped', 0)} "
                    f"errors={stats.get('errors', 0)}"
                )
                return result

            except (
                requests.exceptions.ConnectionError,
                requests.exceptions.Timeout,
            ) as e:
                print(f"  Connection error (attempt {attempt + 1}): {e}")
                if attempt < max_retries - 1:
                    wait = 10 * (attempt + 1)
                    print(f"  Re-logging in and retrying in {wait}s...")
                    time.sleep(wait)
                    try:
                        self.login()
                    except Exception:
                        pass
                else:
                    return {"status": "failed", "error": str(e)}

        return {"status": "failed", "error": "Max retries exceeded"}

    def send_all(
        self,
        permits: list[dict[str, Any]],
        source_code: str,
        batch_size: int = 5000,
    ) -> dict[str, int]:
        """Send all permits in batches, return aggregate stats."""
        self.ensure_logged_in()

        if not permits:
            print("No permits to send.")
            return {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}

        total_batches = (len(permits) + batch_size - 1) // batch_size
        totals = {"inserted": 0, "updated": 0, "skipped": 0, "errors": 0}
        start = time.time()

        for i in range(0, len(permits), batch_size):
            batch = permits[i : i + batch_size]
            batch_num = (i // batch_size) + 1

            result = self.send_batch(
                batch, source_code, batch_num, total_batches
            )
            stats = result.get("stats", {})
            for key in totals:
                totals[key] += stats.get(key, 0)

        elapsed = time.time() - start
        rate = len(permits) / elapsed if elapsed > 0 else 0
        print(
            f"\nDone: {len(permits)} permits in {elapsed:.1f}s "
            f"({rate:.0f}/s)"
        )
        print(
            f"  Inserted: {totals['inserted']}, "
            f"Updated: {totals['updated']}, "
            f"Skipped: {totals['skipped']}, "
            f"Errors: {totals['errors']}"
        )
        return totals

    # ── Geocoding Update ──────────────────────────────────────────────

    def update_permit_geocode(
        self, permit_id: str, geocode_data: dict[str, Any]
    ) -> bool:
        """PATCH a single permit with geocoded lat/lng/city/zip."""
        self.ensure_logged_in()

        payload: dict[str, Any] = {}
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

        try:
            resp = self.session.patch(
                f"{self.api_url}/permits/{permit_id}",
                json=payload,
                timeout=15,
            )
            return resp.status_code == 200
        except Exception:
            return False

    def batch_geocode(
        self, updates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """POST /permits/batch-geocode with a list of updates."""
        self.ensure_logged_in()
        try:
            resp = self.session.post(
                f"{self.api_url}/permits/batch-geocode",
                json={"updates": updates},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"  batch-geocode error: {e}")
        return {"status": "failed"}

    def batch_enrich(
        self, updates: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """POST /permits/batch-enrich with parcel enrichment data."""
        self.ensure_logged_in()
        try:
            resp = self.session.post(
                f"{self.api_url}/permits/batch-enrich",
                json={"updates": updates},
                timeout=60,
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"  batch-enrich error: {e}")
        return {"status": "failed"}

    def fetch_permits_needing_geocoding(
        self, limit: int = 500, source: str | None = None
    ) -> list[dict[str, Any]]:
        """GET permits that have no lat/lng yet."""
        self.ensure_logged_in()
        params: dict[str, Any] = {"limit": limit}
        if source:
            params["source"] = source
        try:
            resp = self.session.get(
                f"{self.api_url}/permits/needs-geocoding",
                params=params,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else data.get("permits", [])
        except Exception as e:
            print(f"  fetch error: {e}")
        return []

    def fetch_permits_needing_parcel(
        self, limit: int = 500, source: str | None = None
    ) -> list[dict[str, Any]]:
        """GET permits that have no owner_name from parcel data."""
        self.ensure_logged_in()
        params: dict[str, Any] = {"limit": limit}
        if source:
            params["source"] = source
        try:
            resp = self.session.get(
                f"{self.api_url}/permits/needs-parcel",
                params=params,
                timeout=30,
            )
            if resp.status_code == 200:
                data = resp.json()
                return data if isinstance(data, list) else data.get("permits", [])
        except Exception as e:
            print(f"  fetch error: {e}")
        return []
