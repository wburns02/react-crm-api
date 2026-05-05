"""One-shot geocoding backfill for work_orders + customers missing lat/lng.

Reads addresses from prod via DATABASE_URL, geocodes via Nominatim (free, OSM),
rate-limited to 1 req/sec per their TOS.

Usage:
    DATABASE_URL=postgresql://... python scripts/geocode_backfill.py [--limit N] [--state SC]
"""
import asyncio
import os
import sys
import time
from urllib.parse import quote_plus

import httpx
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy import text

NOMINATIM = "https://nominatim.openstreetmap.org/search"
HEADERS = {"User-Agent": "MacServicePlatform/1.0 (will@macseptic.com)"}


async def geocode(client: httpx.AsyncClient, addr: str) -> tuple[float, float] | None:
    try:
        r = await client.get(NOMINATIM, params={"q": addr, "format": "json", "limit": 1}, headers=HEADERS, timeout=10)
        rows = r.json()
        if rows:
            return float(rows[0]["lat"]), float(rows[0]["lon"])
    except Exception as e:
        print(f"  geocode error: {e}", file=sys.stderr)
    return None


async def main():
    db_url = os.environ["DATABASE_URL"]
    if db_url.startswith("postgresql://"):
        db_url = db_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    state = next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--state"), None)
    limit = int(next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "--limit"), "100"))

    engine = create_async_engine(db_url)
    async with engine.connect() as conn, httpx.AsyncClient() as http:
        # Work orders
        wo_q = """
        SELECT id, COALESCE(service_address_line1,'')||', '||COALESCE(service_city,'')||', '||COALESCE(service_state,'')||' '||COALESCE(service_postal_code,'') AS addr
        FROM work_orders
        WHERE (service_latitude IS NULL OR service_longitude IS NULL)
          AND service_address_line1 IS NOT NULL AND service_state IS NOT NULL
        """
        if state:
            wo_q += f" AND service_state='{state}'"
        wo_q += f" LIMIT {limit}"

        wos = (await conn.execute(text(wo_q))).fetchall()
        print(f"Geocoding {len(wos)} work orders...")
        wo_done = 0
        for wo_id, addr in wos:
            print(f"  WO {str(wo_id)[:8]}: {addr}")
            coords = await geocode(http, addr)
            if coords:
                await conn.execute(
                    text("UPDATE work_orders SET service_latitude=:lat, service_longitude=:lng WHERE id=:id"),
                    {"lat": coords[0], "lng": coords[1], "id": wo_id},
                )
                wo_done += 1
                print(f"    -> {coords[0]:.5f}, {coords[1]:.5f}")
            time.sleep(1.1)  # Nominatim TOS: 1 req/sec
        await conn.commit()
        print(f"Updated {wo_done}/{len(wos)} work orders\n")

        # Customers
        cust_q = """
        SELECT id, COALESCE(address_line1,'')||', '||COALESCE(city,'')||', '||COALESCE(state,'')||' '||COALESCE(postal_code,'') AS addr
        FROM customers
        WHERE (latitude IS NULL OR longitude IS NULL)
          AND address_line1 IS NOT NULL AND state IS NOT NULL
        """
        if state:
            cust_q += f" AND state='{state}'"
        cust_q += f" LIMIT {limit}"

        custs = (await conn.execute(text(cust_q))).fetchall()
        print(f"Geocoding {len(custs)} customers...")
        cust_done = 0
        for cust_id, addr in custs:
            print(f"  Cust {str(cust_id)[:8]}: {addr}")
            coords = await geocode(http, addr)
            if coords:
                await conn.execute(
                    text("UPDATE customers SET latitude=:lat, longitude=:lng WHERE id=:id"),
                    {"lat": coords[0], "lng": coords[1], "id": cust_id},
                )
                cust_done += 1
                print(f"    -> {coords[0]:.5f}, {coords[1]:.5f}")
            time.sleep(1.1)
        await conn.commit()
        print(f"Updated {cust_done}/{len(custs)} customers")


if __name__ == "__main__":
    asyncio.run(main())
