#!/usr/bin/env python3
"""
T430 Permit Search Service — FastAPI on port 8001.

Serves 269M+ permit records from local PostgreSQL with:
- Full-text search (tsvector + GIN)
- Geographic radius search (PostGIS)
- Fuzzy address search (pg_trgm)
- Analytics/aggregation endpoints

Run: uvicorn t430_permit_service:app --host 0.0.0.0 --port 8001
"""

import os
from contextlib import asynccontextmanager
from datetime import datetime

import asyncpg
from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://will@localhost/permits"
)

pool: asyncpg.Pool = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global pool
    pool = await asyncpg.create_pool(DATABASE_URL, min_size=5, max_size=20)
    yield
    await pool.close()


app = FastAPI(
    title="T430 Permit Search API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET"],
    allow_headers=["*"],
)


class PermitResult(BaseModel):
    id: int
    permit_number: str | None
    address: str | None
    city: str | None
    state_code: str
    zip_code: str | None
    county: str | None
    lat: float | None
    lng: float | None
    trade: str | None
    project_type: str | None
    work_type: str | None
    description: str | None
    status: str | None
    date_created: str | None
    owner_name: str | None
    rank: float | None = None


class SearchResponse(BaseModel):
    results: list[dict]
    total: int
    page: int
    limit: int
    query: str


class StatsOverview(BaseModel):
    total_records: int
    states: int
    with_coordinates: int
    by_state: list[dict]
    by_trade: list[dict]


@app.get("/health")
async def health():
    async with pool.acquire() as conn:
        count = await conn.fetchval("SELECT COUNT(*) FROM permits")
        return {
            "status": "healthy",
            "database": "permits",
            "total_records": count,
            "timestamp": datetime.now().isoformat(),
        }


@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="Search query"),
    state: str | None = Query(None, description="Filter by state (2-letter code)"),
    county: str | None = Query(None, description="Filter by county"),
    trade: str | None = Query(None, description="Filter by trade"),
    zip_code: str | None = Query(None, description="Filter by ZIP code"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    """Full-text search across all permit records."""
    offset = (page - 1) * limit
    conditions = ["search_vector @@ plainto_tsquery('english', $1)"]
    params = [q]
    param_idx = 2

    if state:
        conditions.append(f"state_code = ${param_idx}")
        params.append(state.upper())
        param_idx += 1
    if county:
        conditions.append(f"county ILIKE ${param_idx}")
        params.append(f"%{county}%")
        param_idx += 1
    if trade:
        conditions.append(f"trade = ${param_idx}")
        params.append(trade)
        param_idx += 1
    if zip_code:
        conditions.append(f"zip_code = ${param_idx}")
        params.append(zip_code)
        param_idx += 1

    where = " AND ".join(conditions)

    async with pool.acquire() as conn:
        # Count
        count_sql = f"SELECT COUNT(*) FROM permits WHERE {where}"
        total = await conn.fetchval(count_sql, *params)

        # Results
        results_sql = f"""
            SELECT id, permit_number, address, city, state_code, zip_code,
                   county, lat, lng, trade, project_type, work_type,
                   description, status, date_created::text, owner_name,
                   ts_rank(search_vector, plainto_tsquery('english', $1)) as rank
            FROM permits
            WHERE {where}
            ORDER BY rank DESC
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """
        params.extend([limit, offset])
        rows = await conn.fetch(results_sql, *params)

        return SearchResponse(
            results=[dict(r) for r in rows],
            total=total,
            page=page,
            limit=limit,
            query=q,
        )


@app.get("/search/geo")
async def search_geo(
    lat: float = Query(..., description="Latitude"),
    lng: float = Query(..., description="Longitude"),
    radius_miles: float = Query(5.0, ge=0.1, le=100, description="Radius in miles"),
    trade: str | None = Query(None),
    state: str | None = Query(None),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=500),
):
    """Geographic radius search using PostGIS."""
    radius_meters = radius_miles * 1609.34
    offset = (page - 1) * limit
    conditions = ["ST_DWithin(geom, ST_MakePoint($1, $2)::geography, $3)"]
    params = [lng, lat, radius_meters]
    param_idx = 4

    if trade:
        conditions.append(f"trade = ${param_idx}")
        params.append(trade)
        param_idx += 1
    if state:
        conditions.append(f"state_code = ${param_idx}")
        params.append(state.upper())
        param_idx += 1

    where = " AND ".join(conditions)

    async with pool.acquire() as conn:
        total = await conn.fetchval(
            f"SELECT COUNT(*) FROM permits WHERE {where}", *params
        )

        rows = await conn.fetch(f"""
            SELECT id, permit_number, address, city, state_code, zip_code,
                   county, lat, lng, trade, project_type, work_type,
                   description, status, date_created::text, owner_name,
                   ST_Distance(geom, ST_MakePoint($1, $2)::geography) as distance_meters
            FROM permits
            WHERE {where}
            ORDER BY distance_meters
            LIMIT ${param_idx} OFFSET ${param_idx + 1}
        """, *params, limit, offset)

        return {
            "results": [dict(r) for r in rows],
            "total": total,
            "page": page,
            "limit": limit,
            "center": {"lat": lat, "lng": lng},
            "radius_miles": radius_miles,
        }


@app.get("/search/address")
async def search_address(
    q: str = Query(..., min_length=3, description="Address to fuzzy match"),
    state: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
):
    """Fuzzy address search using pg_trgm similarity."""
    conditions = ["address % $1"]
    params = [q]
    param_idx = 2

    if state:
        conditions.append(f"state_code = ${param_idx}")
        params.append(state.upper())
        param_idx += 1

    where = " AND ".join(conditions)

    async with pool.acquire() as conn:
        rows = await conn.fetch(f"""
            SELECT id, permit_number, address, city, state_code, zip_code,
                   county, lat, lng, trade, owner_name,
                   similarity(address, $1) as match_score
            FROM permits
            WHERE {where}
            ORDER BY match_score DESC
            LIMIT ${param_idx}
        """, *params, limit)

        return {
            "results": [dict(r) for r in rows],
            "query": q,
        }


@app.get("/stats/overview")
async def stats_overview():
    """Overall database statistics."""
    async with pool.acquire() as conn:
        total = await conn.fetchval("SELECT COUNT(*) FROM permits")
        states = await conn.fetchval("SELECT COUNT(DISTINCT state_code) FROM permits")
        with_coords = await conn.fetchval(
            "SELECT COUNT(*) FROM permits WHERE lat IS NOT NULL"
        )

        by_state = await conn.fetch("""
            SELECT state_code, COUNT(*) as count
            FROM permits GROUP BY state_code
            ORDER BY count DESC
        """)

        by_trade = await conn.fetch("""
            SELECT trade, COUNT(*) as count
            FROM permits GROUP BY trade
            ORDER BY count DESC
        """)

        return StatsOverview(
            total_records=total,
            states=states,
            with_coordinates=with_coords,
            by_state=[dict(r) for r in by_state],
            by_trade=[dict(r) for r in by_trade],
        )


@app.get("/stats/state/{state_code}")
async def stats_state(state_code: str):
    """Per-state breakdown."""
    state_code = state_code.upper()
    async with pool.acquire() as conn:
        total = await conn.fetchval(
            "SELECT COUNT(*) FROM permits WHERE state_code = $1", state_code
        )
        if total == 0:
            raise HTTPException(404, f"No data for state {state_code}")

        counties = await conn.fetch("""
            SELECT county, COUNT(*) as count
            FROM permits WHERE state_code = $1 AND county IS NOT NULL
            GROUP BY county ORDER BY count DESC LIMIT 50
        """, state_code)

        trades = await conn.fetch("""
            SELECT trade, COUNT(*) as count
            FROM permits WHERE state_code = $1
            GROUP BY trade ORDER BY count DESC
        """, state_code)

        return {
            "state_code": state_code,
            "total_records": total,
            "counties": [dict(r) for r in counties],
            "trades": [dict(r) for r in trades],
        }


@app.get("/analytics/heatmap")
async def analytics_heatmap(
    state: str | None = Query(None),
    trade: str | None = Query(None),
    limit: int = Query(5000, ge=100, le=50000),
):
    """Return lat/lng points for heatmap visualization."""
    conditions = ["lat IS NOT NULL AND lng IS NOT NULL"]
    params = []
    param_idx = 1

    if state:
        conditions.append(f"state_code = ${param_idx}")
        params.append(state.upper())
        param_idx += 1
    if trade:
        conditions.append(f"trade = ${param_idx}")
        params.append(trade)
        param_idx += 1

    where = " AND ".join(conditions)

    async with pool.acquire() as conn:
        # Sample evenly using TABLESAMPLE for performance on large tables
        rows = await conn.fetch(f"""
            SELECT lat, lng, state_code, trade
            FROM permits
            WHERE {where}
            LIMIT ${param_idx}
        """, *params, limit)

        return {
            "points": [dict(r) for r in rows],
            "count": len(rows),
        }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8001)
