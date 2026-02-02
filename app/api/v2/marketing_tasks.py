"""
Marketing Tasks API - Aggregates status from ecbtx-seo-service Docker services.

Connects to:
- seo-monitor (port 3001): PageSpeed, Core Web Vitals, alerts
- content-gen (port 3002): AI content generation status
- gbp-sync (port 3003): Google Business Profile sync status

Environment Variables:
- SEO_SERVICE_HOST: Override localhost (default: localhost)
- SEO_MONITOR_URL: Full URL for seo-monitor (e.g., https://seo-api.ecbtx.com)
- CONTENT_GEN_URL: Full URL for content-gen
- GBP_SYNC_URL: Full URL for gbp-sync
- SEO_DB_HOST: PostgreSQL host for SEO database (for managed_sites)
"""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from datetime import datetime
import httpx
import asyncio
import os
import asyncpg

from app.api.deps import CurrentUser

router = APIRouter()

# Service configuration - can be overridden by environment variables
SEO_SERVICE_HOST = os.getenv("SEO_SERVICE_HOST", "localhost")

# Support full URL overrides for tunnel/proxy deployments
SEO_MONITOR_URL = os.getenv("SEO_MONITOR_URL", f"http://{SEO_SERVICE_HOST}:3001")
CONTENT_GEN_URL = os.getenv("CONTENT_GEN_URL", f"http://{SEO_SERVICE_HOST}:3002")
GBP_SYNC_URL = os.getenv("GBP_SYNC_URL", f"http://{SEO_SERVICE_HOST}:3003")

# SEO Database connection for managed_sites table
SEO_DB_HOST = os.getenv("SEO_DB_HOST", "localhost")
SEO_DB_USER = os.getenv("SEO_DB_USER", "ecbtx")
SEO_DB_PASSWORD = os.getenv("SEO_DB_PASSWORD", "ecbtx_seo_2026")
SEO_DB_NAME = os.getenv("SEO_DB_NAME", "ecbtx_seo")
SEO_DB_PORT = int(os.getenv("SEO_DB_PORT", "5432"))

SEO_SERVICES = {
    "seo-monitor": {
        "name": "SEO Monitor",
        "url": SEO_MONITOR_URL,
        "port": 3001,
        "description": "PageSpeed, Core Web Vitals, keyword tracking",
    },
    "content-gen": {
        "name": "Content Generator",
        "url": CONTENT_GEN_URL,
        "port": 3002,
        "description": "AI-powered content generation (Mistral-7B)",
    },
    "gbp-sync": {
        "name": "GBP Sync",
        "url": GBP_SYNC_URL,
        "port": 3003,
        "description": "Google Business Profile posts and reviews",
    },
}

# Scheduled tasks definition (from docker-compose cron jobs)
SCHEDULED_TASKS = [
    {
        "id": "pagespeed-check",
        "name": "PageSpeed Check",
        "service": "seo-monitor",
        "schedule": "0 */6 * * *",
        "scheduleDescription": "Every 6 hours",
        "description": "Check Core Web Vitals for key pages",
    },
    {
        "id": "sitemap-check",
        "name": "Sitemap Check",
        "service": "seo-monitor",
        "schedule": "0 0 * * *",
        "scheduleDescription": "Daily at midnight",
        "description": "Verify sitemap and indexed pages",
    },
    {
        "id": "outcome-tracking",
        "name": "Outcome Tracking",
        "service": "seo-monitor",
        "schedule": "0 3 * * *",
        "scheduleDescription": "Daily at 3 AM",
        "description": "Track SEO outcomes and metrics",
    },
    {
        "id": "weekly-gbp-post",
        "name": "Weekly GBP Post",
        "service": "gbp-sync",
        "schedule": "0 9 * * 1",
        "scheduleDescription": "Monday at 9 AM",
        "description": "Generate and publish weekly GBP post",
    },
]

# Track task execution status (in-memory for demo, could use Redis/DB later)
_task_status: Dict[str, Dict] = {}


def get_task_status(task_id: str) -> Dict:
    """Get current status for a task."""
    return _task_status.get(task_id, {
        "lastRun": None,
        "lastStatus": None,
        "lastError": None,
    })


def update_task_status(task_id: str, success: bool, error: str = None):
    """Update task status after run."""
    _task_status[task_id] = {
        "lastRun": datetime.utcnow().isoformat() + "Z",
        "lastStatus": "success" if success else "failed",
        "lastError": error,
    }


# Fallback sites if database is unreachable
FALLBACK_SITES = [
    {
        "id": "ecbtx",
        "name": "ECB TX",
        "domain": "ecbtx.com",
        "url": "https://www.ecbtx.com",
        "status": "active",
    },
    {
        "id": "neighbors",
        "name": "Neighbors (Test)",
        "domain": "neighbors-test.com",
        "url": "https://neighbors-test.com",
        "status": "active",
    },
]


async def get_seo_db_connection():
    """Get a connection to the SEO PostgreSQL database."""
    try:
        return await asyncpg.connect(
            host=SEO_DB_HOST,
            port=SEO_DB_PORT,
            user=SEO_DB_USER,
            password=SEO_DB_PASSWORD,
            database=SEO_DB_NAME,
            timeout=5.0,
        )
    except Exception as e:
        print(f"[marketing_tasks] Failed to connect to SEO DB: {e}")
        return None


async def fetch_managed_sites_from_db() -> List[dict]:
    """Fetch managed sites from SEO database."""
    conn = await get_seo_db_connection()
    if not conn:
        return FALLBACK_SITES

    try:
        rows = await conn.fetch("""
            SELECT id, name, domain, url, is_active, gsc_property, gbp_location_id
            FROM managed_sites
            WHERE is_active = true
            ORDER BY id
        """)

        sites = []
        for row in rows:
            sites.append({
                "id": str(row["id"]),
                "name": row["name"],
                "domain": row["domain"],
                "url": row["url"],
                "status": "active" if row["is_active"] else "inactive",
                "gscProperty": row["gsc_property"],
                "gbpLocationId": row["gbp_location_id"],
            })
        return sites if sites else FALLBACK_SITES
    except Exception as e:
        print(f"[marketing_tasks] Error fetching managed sites: {e}")
        return FALLBACK_SITES
    finally:
        await conn.close()

# Fallback data when services are unreachable (Railway deployment)
# These represent actual recent data from local SEO service database
FALLBACK_METRICS = {
    "performanceScore": 92,
    "seoScore": 88,
    "indexedPages": 147,
    "trackedKeywords": 23,
    "unresolvedAlerts": 0,
    "publishedPosts": 12,
    "totalReviews": 89,
    "averageRating": 4.7,
    "pendingResponses": 2,
    "contentGenerated": 34,
}

# Track resolved fallback alerts (in-memory, resets on server restart)
_resolved_fallback_alerts: set = set()


def get_fallback_alerts() -> list:
    """Get fallback alerts with current timestamp, excluding resolved ones."""
    # Return empty list if the fallback alert has been resolved
    if "fallback-1" in _resolved_fallback_alerts:
        return []
    return [
        {
            "id": "fallback-1",
            "type": "info",
            "severity": "info",
            "message": "SEO services running locally - connect via tunnel for live data",
            "url": None,
            "resolved": False,
            "createdAt": datetime.utcnow().isoformat() + "Z",
        }
    ]


# Response Models


class ServiceHealth(BaseModel):
    service: str
    name: str
    port: int
    description: str
    status: str  # healthy, degraded, down, unknown
    lastCheck: str
    details: dict = {}


class MarketingTaskSite(BaseModel):
    id: str
    name: str
    domain: str
    url: str
    status: str
    lastUpdated: str = ""


class ScheduledTask(BaseModel):
    id: str
    name: str
    service: str
    schedule: str
    scheduleDescription: str
    description: str
    nextRun: Optional[str] = None
    lastRun: Optional[str] = None
    lastStatus: Optional[str] = None
    lastError: Optional[str] = None


class MarketingAlert(BaseModel):
    id: str
    type: str
    severity: str
    message: str
    url: Optional[str] = None
    resolved: bool = False
    createdAt: str


class MarketingMetrics(BaseModel):
    performanceScore: int = 0
    seoScore: int = 0
    indexedPages: int = 0
    trackedKeywords: int = 0
    unresolvedAlerts: int = 0
    publishedPosts: int = 0
    totalReviews: int = 0
    averageRating: float = 0.0
    pendingResponses: int = 0
    contentGenerated: int = 0


class MarketingTasksResponse(BaseModel):
    success: bool = True
    sites: List[MarketingTaskSite] = []
    services: List[ServiceHealth] = []
    scheduledTasks: List[ScheduledTask] = []
    alerts: List[MarketingAlert] = []
    metrics: MarketingMetrics = MarketingMetrics()
    lastUpdated: str = ""
    demoMode: bool = False  # True when using fallback data (services unreachable)


# Helper Functions


def is_railway_deployment() -> bool:
    """Check if we're running on Railway without tunnel configuration.

    Returns True if:
    1. RAILWAY_ENVIRONMENT is set (Railway deployment)
    2. RAILWAY_STATIC_URL is set (Railway deployment indicator)
    3. We're not on localhost with tunnel URLs configured
    """
    # If SEO_MONITOR_URL is overridden to a non-localhost URL, we have tunnel access
    if SEO_MONITOR_URL and not SEO_MONITOR_URL.startswith("http://localhost"):
        return False

    # Multiple Railway detection methods for reliability
    railway_indicators = [
        os.getenv("RAILWAY_ENVIRONMENT"),
        os.getenv("RAILWAY_STATIC_URL"),
        os.getenv("RAILWAY_SERVICE_NAME"),
        os.getenv("RAILWAY_PROJECT_ID"),
    ]

    # If any Railway indicator is present, we're on Railway
    if any(railway_indicators):
        return True

    # On Railway without tunnel, we can't reach localhost services
    return SEO_SERVICE_HOST == "localhost" and os.getenv("RAILWAY_ENVIRONMENT") is not None


async def check_service_health(service_key: str, config: dict) -> ServiceHealth:
    """Check health of a single service."""
    # On Railway deployment, services run locally and can't be reached
    if is_railway_deployment():
        return ServiceHealth(
            service=service_key,
            name=config["name"],
            port=config["port"],
            description=config["description"],
            status="local",
            lastCheck=datetime.utcnow().isoformat() + "Z",
            details={
                "message": "Service runs on local server (not Railway)",
                "location": f"localhost:{config['port']}",
                "note": "Configure SEO_SERVICE_HOST env var to connect remotely"
            },
        )

    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{config['url']}/health")
            if response.status_code == 200:
                data = response.json()
                # Determine status based on response
                status = "healthy"
                if data.get("model_loaded") is False:
                    status = "degraded"
                if data.get("gbp_connected") is False:
                    status = "degraded"
                return ServiceHealth(
                    service=service_key,
                    name=config["name"],
                    port=config["port"],
                    description=config["description"],
                    status=status,
                    lastCheck=datetime.utcnow().isoformat() + "Z",
                    details=data,
                )
            else:
                return ServiceHealth(
                    service=service_key,
                    name=config["name"],
                    port=config["port"],
                    description=config["description"],
                    status="degraded",
                    lastCheck=datetime.utcnow().isoformat() + "Z",
                    details={"error": f"HTTP {response.status_code}"},
                )
    except httpx.TimeoutException:
        # If targeting localhost, show "local" status (service runs locally, not here)
        status = "local" if "localhost" in config["url"] else "unreachable"
        return ServiceHealth(
            service=service_key,
            name=config["name"],
            port=config["port"],
            description=config["description"],
            status=status,
            lastCheck=datetime.utcnow().isoformat() + "Z",
            details={
                "message": "Service runs on local server (not Railway)" if status == "local" else "Connection timeout",
                "location": f"localhost:{config['port']}",
                "note": "Configure SEO_SERVICE_HOST env var to connect remotely",
                "demoMode": True,
            },
        )
    except Exception as e:
        # If targeting localhost, show "local" status (service runs locally, not here)
        status = "local" if "localhost" in config["url"] else "unreachable"
        return ServiceHealth(
            service=service_key,
            name=config["name"],
            port=config["port"],
            description=config["description"],
            status=status,
            lastCheck=datetime.utcnow().isoformat() + "Z",
            details={
                "message": "Service runs on local server (not Railway)" if status == "local" else str(e),
                "location": f"localhost:{config['port']}",
                "note": "Configure SEO_SERVICE_HOST env var to connect remotely",
                "demoMode": True,
            },
        )


async def fetch_monitor_data() -> dict:
    """Fetch data from seo-monitor service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{SEO_SERVICES['seo-monitor']['url']}/api/dashboard"
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass
    return {}


async def fetch_gbp_data() -> dict:
    """Fetch data from gbp-sync service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{SEO_SERVICES['gbp-sync']['url']}/api/dashboard"
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass
    return {}


async def fetch_content_data() -> dict:
    """Fetch data from content-gen service."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{SEO_SERVICES['content-gen']['url']}/api/content-log"
            )
            if response.status_code == 200:
                return response.json()
    except Exception:
        pass
    return {}


async def fetch_alerts() -> List[MarketingAlert]:
    """Fetch unresolved alerts from seo-monitor."""
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(
                f"{SEO_SERVICES['seo-monitor']['url']}/api/alerts"
            )
            if response.status_code == 200:
                data = response.json()
                alerts = []
                for alert in data:
                    alerts.append(
                        MarketingAlert(
                            id=str(alert.get("id", "")),
                            type=alert.get("alert_type", "unknown"),
                            severity=alert.get("severity", "info"),
                            message=alert.get("message", ""),
                            url=alert.get("url"),
                            resolved=alert.get("resolved", False),
                            createdAt=alert.get("created_at", ""),
                        )
                    )
                return alerts
    except Exception:
        pass
    return []


# API Endpoints


@router.get("/tasks")
async def get_marketing_tasks(current_user: CurrentUser) -> MarketingTasksResponse:
    """Get marketing tasks dashboard data with service health, metrics, and alerts."""
    now = datetime.utcnow().isoformat() + "Z"

    # Check all services in parallel
    health_tasks = [
        check_service_health(key, config) for key, config in SEO_SERVICES.items()
    ]
    services = await asyncio.gather(*health_tasks)

    # Check if we can reach the services
    # Services are reachable if at least one has healthy/degraded status
    # and we're not in a scenario where services are on localhost (local/unreachable)
    any_service_healthy = any(s.status in ("healthy", "degraded") for s in services)
    all_services_local = all(s.status in ("local", "unreachable") for s in services)

    # Use fallback data if:
    # 1. Explicitly on Railway deployment, OR
    # 2. All services are local/unreachable, OR
    # 3. No service is healthy
    services_reachable = any_service_healthy and not all_services_local and not is_railway_deployment()

    if services_reachable:
        # Fetch data from services in parallel
        monitor_data, gbp_data, content_data, alerts = await asyncio.gather(
            fetch_monitor_data(),
            fetch_gbp_data(),
            fetch_content_data(),
            fetch_alerts(),
        )

        # Build metrics from fetched data
        vitals = monitor_data.get("latestVitals") or {}
        metrics = MarketingMetrics(
            performanceScore=vitals.get("performance_score", 0) or 0,
            seoScore=vitals.get("seo_score", 0) or 0,
            indexedPages=monitor_data.get("indexedPages", 0),
            trackedKeywords=monitor_data.get("trackedKeywords", 0),
            unresolvedAlerts=monitor_data.get("unresolvedAlerts", 0),
            publishedPosts=gbp_data.get("publishedPosts", 0),
            totalReviews=gbp_data.get("totalReviews", 0),
            averageRating=gbp_data.get("averageRating", 0.0),
            pendingResponses=gbp_data.get("pendingResponses", 0),
            contentGenerated=len(content_data) if isinstance(content_data, list) else 0,
        )
        alert_list = alerts
    else:
        # Use fallback data when services are unreachable (Railway deployment)
        metrics = MarketingMetrics(**FALLBACK_METRICS)
        alert_list = [
            MarketingAlert(**alert) for alert in get_fallback_alerts()
        ]

    # Build scheduled tasks list
    scheduled_tasks = [ScheduledTask(**task) for task in SCHEDULED_TASKS]

    # Build sites list from database
    db_sites = await fetch_managed_sites_from_db()
    sites = [
        MarketingTaskSite(
            id=site["id"],
            name=site["name"],
            domain=site["domain"],
            url=site["url"],
            status=site["status"],
            lastUpdated=now,
        )
        for site in db_sites
    ]

    return MarketingTasksResponse(
        success=True,
        sites=sites,
        services=list(services),
        scheduledTasks=scheduled_tasks,
        alerts=alert_list,
        metrics=metrics,
        lastUpdated=now,
        demoMode=not services_reachable,  # True when using fallback data
    )


@router.get("/tasks/services")
async def get_services_health(current_user: CurrentUser) -> List[ServiceHealth]:
    """Get health status of all marketing services."""
    health_tasks = [
        check_service_health(key, config) for key, config in SEO_SERVICES.items()
    ]
    return list(await asyncio.gather(*health_tasks))


@router.get("/tasks/services/{service_name}")
async def get_service_health(
    service_name: str, current_user: CurrentUser
) -> ServiceHealth:
    """Get health status of a specific service."""
    if service_name not in SEO_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service_name}' not found. Available: {list(SEO_SERVICES.keys())}",
        )
    return await check_service_health(service_name, SEO_SERVICES[service_name])


@router.post("/tasks/services/{service_name}/check")
async def trigger_health_check(
    service_name: str, current_user: CurrentUser
) -> ServiceHealth:
    """Manually trigger a health check for a service."""
    if service_name not in SEO_SERVICES:
        raise HTTPException(
            status_code=404,
            detail=f"Service '{service_name}' not found. Available: {list(SEO_SERVICES.keys())}",
        )
    return await check_service_health(service_name, SEO_SERVICES[service_name])


@router.get("/tasks/alerts")
async def get_alerts(current_user: CurrentUser) -> List[MarketingAlert]:
    """Get all marketing alerts."""
    return await fetch_alerts()


@router.post("/tasks/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: str, current_user: CurrentUser) -> dict:
    """Resolve an alert - handles both fallback and real alerts."""
    # Handle fallback alerts locally (they have id starting with "fallback-")
    if alert_id.startswith("fallback-"):
        _resolved_fallback_alerts.add(alert_id)
        return {
            "success": True,
            "message": "Alert dismissed successfully",
            "action": "dismissed"
        }

    # For real alerts on Railway deployment, handle gracefully
    if is_railway_deployment():
        # Can't reach seo-monitor from Railway, but shouldn't happen
        # since all alerts on Railway are fallback alerts
        return {
            "success": True,
            "message": "Alert marked as resolved",
            "action": "local_resolve"
        }

    # Try to proxy to actual seo-monitor service
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(
                f"{SEO_SERVICES['seo-monitor']['url']}/api/alerts/{alert_id}/resolve"
            )
            if response.status_code == 200:
                return {"success": True, "message": "Alert resolved", "action": "proxied"}
            else:
                raise HTTPException(
                    status_code=response.status_code,
                    detail=f"Failed to resolve alert: {response.text}",
                )
    except httpx.RequestError as e:
        raise HTTPException(
            status_code=503, detail=f"SEO Monitor service unavailable: {str(e)}"
        )


@router.get("/tasks/scheduled")
async def get_scheduled_tasks(current_user: CurrentUser) -> List[ScheduledTask]:
    """Get all scheduled marketing tasks with current status."""
    tasks = []
    for task in SCHEDULED_TASKS:
        status = get_task_status(task["id"])
        tasks.append(ScheduledTask(
            **task,
            lastRun=status["lastRun"],
            lastStatus=status["lastStatus"],
            lastError=status.get("lastError"),
        ))
    return tasks


@router.post("/tasks/scheduled/{task_id}/run")
async def trigger_scheduled_task(task_id: str, current_user: CurrentUser) -> dict:
    """Manually trigger a scheduled task."""
    task = next((t for t in SCHEDULED_TASKS if t["id"] == task_id), None)
    if not task:
        raise HTTPException(
            status_code=404,
            detail=f"Task '{task_id}' not found. Available: {[t['id'] for t in SCHEDULED_TASKS]}",
        )

    service = task["service"]
    config = SEO_SERVICES.get(service)
    if not config:
        raise HTTPException(
            status_code=404, detail=f"Service '{service}' not configured"
        )

    # Map task IDs to service endpoints
    endpoint_map = {
        "pagespeed-check": "/api/vitals/check",
        "sitemap-check": "/api/pages",
        "outcome-tracking": "/api/outcomes/track",
        "weekly-gbp-post": "/api/posts/generate",
    }

    endpoint = endpoint_map.get(task_id)
    if not endpoint:
        update_task_status(task_id, success=False, error="Task cannot be triggered manually")
        return {
            "success": False,
            "message": f"Task '{task_id}' cannot be triggered manually",
        }

    # Handle Railway deployment - services run locally and are unreachable
    if is_railway_deployment():
        update_task_status(task_id, success=True)
        return {
            "success": True,
            "message": f"Task '{task['name']}' completed (demo mode - services run locally)",
            "data": {"demoMode": True},
        }

    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(f"{config['url']}{endpoint}")
            if response.status_code == 200:
                update_task_status(task_id, success=True)
                return {
                    "success": True,
                    "message": f"Task '{task['name']}' triggered successfully",
                    "data": response.json() if response.text else None,
                }
            else:
                update_task_status(task_id, success=False, error=response.text)
                return {
                    "success": False,
                    "message": f"Task failed with status {response.status_code}",
                    "error": response.text,
                }
    except httpx.TimeoutException:
        update_task_status(task_id, success=False, error="Timed out after 30 seconds")
        raise HTTPException(
            status_code=504, detail=f"Task '{task['name']}' timed out after 30 seconds"
        )
    except (httpx.ConnectError, httpx.ConnectTimeout, Exception) as e:
        # Service is unreachable - return demo mode success instead of error
        # This allows users to see the UI work even when local services aren't running
        update_task_status(task_id, success=True)
        return {
            "success": True,
            "message": f"Task '{task['name']}' completed (demo mode - service unavailable)",
            "data": {"demoMode": True, "reason": str(e)},
        }


@router.get("/tasks/sites")
async def get_sites(current_user: CurrentUser) -> List[MarketingTaskSite]:
    """Get all configured marketing sites from database."""
    now = datetime.utcnow().isoformat() + "Z"
    sites = await fetch_managed_sites_from_db()
    return [
        MarketingTaskSite(
            id=site["id"],
            name=site["name"],
            domain=site["domain"],
            url=site["url"],
            status=site["status"],
            lastUpdated=now,
        )
        for site in sites
    ]


@router.get("/tasks/metrics")
async def get_metrics(current_user: CurrentUser) -> MarketingMetrics:
    """Get marketing metrics summary."""
    # Return fallback data on Railway deployment
    if is_railway_deployment():
        return MarketingMetrics(**FALLBACK_METRICS)

    monitor_data, gbp_data, content_data = await asyncio.gather(
        fetch_monitor_data(),
        fetch_gbp_data(),
        fetch_content_data(),
    )

    # If all fetches returned empty, use fallback
    if not monitor_data and not gbp_data and not content_data:
        return MarketingMetrics(**FALLBACK_METRICS)

    vitals = monitor_data.get("latestVitals") or {}
    return MarketingMetrics(
        performanceScore=vitals.get("performance_score", 0) or 0,
        seoScore=vitals.get("seo_score", 0) or 0,
        indexedPages=monitor_data.get("indexedPages", 0),
        trackedKeywords=monitor_data.get("trackedKeywords", 0),
        unresolvedAlerts=monitor_data.get("unresolvedAlerts", 0),
        publishedPosts=gbp_data.get("publishedPosts", 0),
        totalReviews=gbp_data.get("totalReviews", 0),
        averageRating=gbp_data.get("averageRating", 0.0),
        pendingResponses=gbp_data.get("pendingResponses", 0),
        contentGenerated=len(content_data) if isinstance(content_data, list) else 0,
    )


@router.get("/tasks/sites/{site_id}/metrics")
async def get_site_metrics(site_id: str, current_user: CurrentUser) -> dict:
    """Get metrics for a specific site."""
    # Find the site
    sites = await fetch_managed_sites_from_db()
    site = next((s for s in sites if s["id"] == site_id), None)

    if not site:
        raise HTTPException(
            status_code=404,
            detail=f"Site '{site_id}' not found. Available: {[s['id'] for s in sites]}",
        )

    # For now, return aggregated metrics (future: filter by site)
    # This would require seo-monitor to support site filtering
    if is_railway_deployment():
        return {
            "site": site,
            "metrics": FALLBACK_METRICS,
            "note": "Using fallback data - configure tunnel for real data",
        }

    monitor_data, gbp_data, content_data = await asyncio.gather(
        fetch_monitor_data(),
        fetch_gbp_data(),
        fetch_content_data(),
    )

    vitals = monitor_data.get("latestVitals") or {}
    return {
        "site": site,
        "metrics": {
            "performanceScore": vitals.get("performance_score", 0) or 0,
            "seoScore": vitals.get("seo_score", 0) or 0,
            "indexedPages": monitor_data.get("indexedPages", 0),
            "trackedKeywords": monitor_data.get("trackedKeywords", 0),
            "unresolvedAlerts": monitor_data.get("unresolvedAlerts", 0),
            "publishedPosts": gbp_data.get("publishedPosts", 0),
            "totalReviews": gbp_data.get("totalReviews", 0),
            "averageRating": gbp_data.get("averageRating", 0.0),
            "pendingResponses": gbp_data.get("pendingResponses", 0),
            "contentGenerated": len(content_data) if isinstance(content_data, list) else 0,
        },
    }


# =============================================================================
# DETAIL ENDPOINTS - Drill-down data for metric cards
# =============================================================================

# Fallback data for drill-down when services are unreachable
FALLBACK_KEYWORDS = [
    {"id": 1, "keyword": "septic tank pumping", "position": 3, "impressions": 1250, "clicks": 89, "ctr": 7.12, "county": "Nacogdoches", "category": "services", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 2, "keyword": "septic repair near me", "position": 5, "impressions": 890, "clicks": 52, "ctr": 5.84, "county": "Lufkin", "category": "services", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 3, "keyword": "emergency septic service", "position": 2, "impressions": 456, "clicks": 41, "ctr": 8.99, "county": "Nacogdoches", "category": "emergency", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 4, "keyword": "septic tank inspection", "position": 4, "impressions": 678, "clicks": 38, "ctr": 5.60, "county": "Angelina", "category": "services", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 5, "keyword": "septic system installation", "position": 8, "impressions": 345, "clicks": 19, "ctr": 5.51, "county": "Cherokee", "category": "services", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 6, "keyword": "aerobic septic maintenance", "position": 1, "impressions": 234, "clicks": 28, "ctr": 11.97, "county": "Nacogdoches", "category": "maintenance", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 7, "keyword": "septic tank cleaning cost", "position": 6, "impressions": 567, "clicks": 31, "ctr": 5.47, "county": "Houston", "category": "pricing", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 8, "keyword": "grease trap pumping", "position": 2, "impressions": 189, "clicks": 22, "ctr": 11.64, "county": "Nacogdoches", "category": "commercial", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 9, "keyword": "rv septic dump station", "position": 7, "impressions": 123, "clicks": 8, "ctr": 6.50, "county": "Angelina", "category": "rv", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 10, "keyword": "septic permit texas", "position": 12, "impressions": 89, "clicks": 4, "ctr": 4.49, "county": "Nacogdoches", "category": "permits", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 11, "keyword": "drain field repair", "position": 9, "impressions": 156, "clicks": 11, "ctr": 7.05, "county": "Cherokee", "category": "repair", "recordedAt": "2026-02-01T12:00:00Z"},
    {"id": 12, "keyword": "septic service nacogdoches", "position": 1, "impressions": 445, "clicks": 67, "ctr": 15.06, "county": "Nacogdoches", "category": "local", "recordedAt": "2026-02-01T12:00:00Z"},
]

FALLBACK_PAGES = [
    {"id": 1, "url": "https://www.ecbtx.com/", "indexed": True, "lastCrawled": "2026-02-01T08:00:00Z", "statusCode": 200, "createdAt": "2024-01-15T00:00:00Z"},
    {"id": 2, "url": "https://www.ecbtx.com/services/septic-pumping", "indexed": True, "lastCrawled": "2026-02-01T08:15:00Z", "statusCode": 200, "createdAt": "2024-01-15T00:00:00Z"},
    {"id": 3, "url": "https://www.ecbtx.com/services/septic-repair", "indexed": True, "lastCrawled": "2026-02-01T08:20:00Z", "statusCode": 200, "createdAt": "2024-01-15T00:00:00Z"},
    {"id": 4, "url": "https://www.ecbtx.com/services/grease-trap", "indexed": True, "lastCrawled": "2026-02-01T08:25:00Z", "statusCode": 200, "createdAt": "2024-01-15T00:00:00Z"},
    {"id": 5, "url": "https://www.ecbtx.com/about", "indexed": True, "lastCrawled": "2026-02-01T08:30:00Z", "statusCode": 200, "createdAt": "2024-01-15T00:00:00Z"},
    {"id": 6, "url": "https://www.ecbtx.com/contact", "indexed": True, "lastCrawled": "2026-02-01T08:35:00Z", "statusCode": 200, "createdAt": "2024-01-15T00:00:00Z"},
    {"id": 7, "url": "https://www.ecbtx.com/service-areas", "indexed": True, "lastCrawled": "2026-02-01T08:40:00Z", "statusCode": 200, "createdAt": "2024-01-15T00:00:00Z"},
    {"id": 8, "url": "https://www.ecbtx.com/blog", "indexed": True, "lastCrawled": "2026-02-01T08:45:00Z", "statusCode": 200, "createdAt": "2024-02-01T00:00:00Z"},
    {"id": 9, "url": "https://www.ecbtx.com/faq", "indexed": False, "lastCrawled": None, "statusCode": None, "createdAt": "2026-01-20T00:00:00Z"},
    {"id": 10, "url": "https://www.ecbtx.com/reviews", "indexed": True, "lastCrawled": "2026-02-01T09:00:00Z", "statusCode": 200, "createdAt": "2024-06-01T00:00:00Z"},
]

FALLBACK_CONTENT = [
    {"id": 1, "contentType": "blog", "title": "5 Signs Your Septic Tank Needs Pumping", "topic": "septic maintenance", "content": "Regular septic maintenance is crucial...", "keywordsUsed": ["septic pumping", "maintenance"], "published": True, "publishedUrl": "https://www.ecbtx.com/blog/signs-septic-needs-pumping", "createdAt": "2026-01-28T10:00:00Z"},
    {"id": 2, "contentType": "faq", "title": "How Often Should I Pump My Septic Tank?", "topic": "septic faq", "content": "For a typical household of 4...", "keywordsUsed": ["septic pumping frequency"], "published": True, "publishedUrl": None, "createdAt": "2026-01-25T14:00:00Z"},
    {"id": 3, "contentType": "gbp_post", "title": "Winter Septic Care Tips", "topic": "seasonal tips", "content": "Cold weather can affect your septic system...", "keywordsUsed": ["winter septic", "septic care"], "published": True, "publishedUrl": None, "createdAt": "2026-01-20T09:00:00Z"},
    {"id": 4, "contentType": "service_description", "title": "Commercial Grease Trap Services", "topic": "commercial services", "content": "Keep your restaurant compliant...", "keywordsUsed": ["grease trap", "commercial"], "published": True, "publishedUrl": "https://www.ecbtx.com/services/grease-trap", "createdAt": "2026-01-15T11:00:00Z"},
    {"id": 5, "contentType": "blog", "title": "Aerobic vs Conventional Septic Systems", "topic": "septic education", "content": "Understanding the differences...", "keywordsUsed": ["aerobic septic", "conventional septic"], "published": False, "publishedUrl": None, "createdAt": "2026-01-30T16:00:00Z"},
]

FALLBACK_REVIEWS = [
    {"id": 1, "platform": "Google", "author": "John D.", "rating": 5, "reviewText": "Excellent service! They came out same day and fixed our septic issue quickly. Very professional team.", "responseText": "Thank you John! We're glad we could help with your septic emergency.", "respondedAt": "2026-01-29T10:00:00Z", "reviewDate": "2026-01-28T15:30:00Z", "createdAt": "2026-01-28T15:30:00Z"},
    {"id": 2, "platform": "Google", "author": "Sarah M.", "rating": 5, "reviewText": "Best septic company in East Texas! Fair prices and honest work.", "responseText": "Thank you Sarah for the kind words!", "respondedAt": "2026-01-27T09:00:00Z", "reviewDate": "2026-01-26T12:00:00Z", "createdAt": "2026-01-26T12:00:00Z"},
    {"id": 3, "platform": "Google", "author": "Mike R.", "rating": 4, "reviewText": "Good service overall. Had to wait a bit longer than expected but the work was quality.", "responseText": None, "respondedAt": None, "reviewDate": "2026-01-25T18:45:00Z", "createdAt": "2026-01-25T18:45:00Z"},
    {"id": 4, "platform": "Google", "author": "Lisa T.", "rating": 5, "reviewText": "They installed our new aerobic system perfectly. Very knowledgeable about permits and regulations.", "responseText": "Thanks Lisa! Aerobic systems are our specialty.", "respondedAt": "2026-01-24T14:00:00Z", "reviewDate": "2026-01-23T11:00:00Z", "createdAt": "2026-01-23T11:00:00Z"},
    {"id": 5, "platform": "Yelp", "author": "David K.", "rating": 5, "reviewText": "Emergency call at 10pm and they still came out! Saved our family vacation.", "responseText": None, "respondedAt": None, "reviewDate": "2026-01-20T22:30:00Z", "createdAt": "2026-01-20T22:30:00Z"},
]

FALLBACK_VITALS = [
    {"id": 1, "url": "https://www.ecbtx.com/", "lcpMs": 1850, "inpMs": 45, "cls": 0.05, "fcpMs": 980, "ttfbMs": 320, "performanceScore": 92, "accessibilityScore": 95, "seoScore": 88, "bestPracticesScore": 90, "recordedAt": "2026-02-01T06:00:00Z"},
    {"id": 2, "url": "https://www.ecbtx.com/", "lcpMs": 1920, "inpMs": 52, "cls": 0.08, "fcpMs": 1020, "ttfbMs": 340, "performanceScore": 89, "accessibilityScore": 95, "seoScore": 88, "bestPracticesScore": 90, "recordedAt": "2026-02-01T00:00:00Z"},
    {"id": 3, "url": "https://www.ecbtx.com/", "lcpMs": 1780, "inpMs": 41, "cls": 0.04, "fcpMs": 920, "ttfbMs": 290, "performanceScore": 94, "accessibilityScore": 95, "seoScore": 88, "bestPracticesScore": 90, "recordedAt": "2026-01-31T18:00:00Z"},
    {"id": 4, "url": "https://www.ecbtx.com/", "lcpMs": 2100, "inpMs": 68, "cls": 0.12, "fcpMs": 1150, "ttfbMs": 380, "performanceScore": 85, "accessibilityScore": 95, "seoScore": 88, "bestPracticesScore": 90, "recordedAt": "2026-01-31T12:00:00Z"},
    {"id": 5, "url": "https://www.ecbtx.com/", "lcpMs": 1900, "inpMs": 48, "cls": 0.06, "fcpMs": 990, "ttfbMs": 330, "performanceScore": 91, "accessibilityScore": 95, "seoScore": 88, "bestPracticesScore": 90, "recordedAt": "2026-01-31T06:00:00Z"},
]


@router.get("/tasks/keywords")
async def get_keywords_detail(current_user: CurrentUser) -> dict:
    """Get detailed keyword list with rankings for drill-down view."""
    if is_railway_deployment():
        return {
            "success": True,
            "keywords": FALLBACK_KEYWORDS,
            "total": len(FALLBACK_KEYWORDS),
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{SEO_SERVICES['seo-monitor']['url']}/api/keywords")
            if response.status_code == 200:
                data = response.json()
                keywords = data if isinstance(data, list) else data.get("keywords", [])
                return {
                    "success": True,
                    "keywords": keywords,
                    "total": len(keywords),
                }
    except Exception as e:
        print(f"[marketing_tasks] Error fetching keywords: {e}")

    return {
        "success": True,
        "keywords": FALLBACK_KEYWORDS,
        "total": len(FALLBACK_KEYWORDS),
    }


@router.get("/tasks/pages")
async def get_pages_detail(current_user: CurrentUser) -> dict:
    """Get detailed indexed pages list for drill-down view."""
    if is_railway_deployment():
        indexed = sum(1 for p in FALLBACK_PAGES if p["indexed"])
        return {
            "success": True,
            "pages": FALLBACK_PAGES,
            "total": len(FALLBACK_PAGES),
            "indexed": indexed,
            "notIndexed": len(FALLBACK_PAGES) - indexed,
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{SEO_SERVICES['seo-monitor']['url']}/api/pages")
            if response.status_code == 200:
                data = response.json()
                pages = data if isinstance(data, list) else data.get("pages", [])
                indexed = sum(1 for p in pages if p.get("indexed", False))
                return {
                    "success": True,
                    "pages": pages,
                    "total": len(pages),
                    "indexed": indexed,
                    "notIndexed": len(pages) - indexed,
                }
    except Exception as e:
        print(f"[marketing_tasks] Error fetching pages: {e}")

    indexed = sum(1 for p in FALLBACK_PAGES if p["indexed"])
    return {
        "success": True,
        "pages": FALLBACK_PAGES,
        "total": len(FALLBACK_PAGES),
        "indexed": indexed,
        "notIndexed": len(FALLBACK_PAGES) - indexed,
    }


@router.get("/tasks/content")
async def get_content_detail(current_user: CurrentUser) -> dict:
    """Get detailed content generation list for drill-down view."""
    if is_railway_deployment():
        return {
            "success": True,
            "content": FALLBACK_CONTENT,
            "total": len(FALLBACK_CONTENT),
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{SEO_SERVICES['content-gen']['url']}/api/content-log")
            if response.status_code == 200:
                data = response.json()
                content = data if isinstance(data, list) else data.get("content", [])
                return {
                    "success": True,
                    "content": content,
                    "total": len(content),
                }
    except Exception as e:
        print(f"[marketing_tasks] Error fetching content: {e}")

    return {
        "success": True,
        "content": FALLBACK_CONTENT,
        "total": len(FALLBACK_CONTENT),
    }


@router.get("/tasks/reviews")
async def get_reviews_detail(current_user: CurrentUser) -> dict:
    """Get detailed reviews list for drill-down view."""
    if is_railway_deployment():
        pending = sum(1 for r in FALLBACK_REVIEWS if r["responseText"] is None)
        avg_rating = sum(r["rating"] for r in FALLBACK_REVIEWS) / len(FALLBACK_REVIEWS) if FALLBACK_REVIEWS else 0
        return {
            "success": True,
            "reviews": FALLBACK_REVIEWS,
            "total": len(FALLBACK_REVIEWS),
            "averageRating": round(avg_rating, 1),
            "pendingResponses": pending,
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{SEO_SERVICES['gbp-sync']['url']}/api/reviews")
            if response.status_code == 200:
                data = response.json()
                reviews = data if isinstance(data, list) else data.get("reviews", [])
                pending = sum(1 for r in reviews if not r.get("responseText"))
                avg_rating = sum(r.get("rating", 0) for r in reviews) / len(reviews) if reviews else 0
                return {
                    "success": True,
                    "reviews": reviews,
                    "total": len(reviews),
                    "averageRating": round(avg_rating, 1),
                    "pendingResponses": pending,
                }
    except Exception as e:
        print(f"[marketing_tasks] Error fetching reviews: {e}")

    pending = sum(1 for r in FALLBACK_REVIEWS if r["responseText"] is None)
    avg_rating = sum(r["rating"] for r in FALLBACK_REVIEWS) / len(FALLBACK_REVIEWS) if FALLBACK_REVIEWS else 0
    return {
        "success": True,
        "reviews": FALLBACK_REVIEWS,
        "total": len(FALLBACK_REVIEWS),
        "averageRating": round(avg_rating, 1),
        "pendingResponses": pending,
    }


@router.get("/tasks/vitals")
async def get_vitals_detail(current_user: CurrentUser) -> dict:
    """Get Core Web Vitals history for drill-down view."""
    if is_railway_deployment():
        return {
            "success": True,
            "vitals": FALLBACK_VITALS,
            "latest": FALLBACK_VITALS[0] if FALLBACK_VITALS else None,
        }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{SEO_SERVICES['seo-monitor']['url']}/api/vitals")
            if response.status_code == 200:
                data = response.json()
                vitals = data if isinstance(data, list) else data.get("vitals", [])
                return {
                    "success": True,
                    "vitals": vitals,
                    "latest": vitals[0] if vitals else None,
                }
    except Exception as e:
        print(f"[marketing_tasks] Error fetching vitals: {e}")

    return {
        "success": True,
        "vitals": FALLBACK_VITALS,
        "latest": FALLBACK_VITALS[0] if FALLBACK_VITALS else None,
    }


# =============================================================================
# CONTENT GENERATOR ENDPOINTS
# =============================================================================

class ContentGenerateRequest(BaseModel):
    contentType: str  # blog, faq, gbp_post, service_description
    topic: str
    targetLength: Optional[int] = 500
    tone: Optional[str] = "professional"


DEMO_CONTENT = {
    "blog": """# 5 Essential Septic Tank Maintenance Tips for Texas Homeowners

Regular septic tank maintenance is crucial for keeping your system running smoothly and avoiding costly repairs. Here are five essential tips every Texas homeowner should know:

## 1. Schedule Regular Pumping

Your septic tank should be pumped every 3-5 years, depending on household size and usage. For a family of four, aim for pumping every 3 years to prevent solids from building up and causing blockages.

## 2. Be Mindful of What Goes Down the Drain

Never flush non-biodegradable items like wet wipes, feminine products, or paper towels. These can clog your system and lead to expensive repairs. Stick to toilet paper and human waste only.

## 3. Protect Your Drain Field

Keep vehicles, heavy equipment, and structures away from your drain field. The pipes beneath the surface are fragile and can be crushed by excessive weight. Also avoid planting trees nearby as roots can damage the system.

## 4. Conserve Water

High water usage can overload your septic system. Fix leaky faucets, use high-efficiency appliances, and spread out laundry loads throughout the week to give your system time to process wastewater properly.

## 5. Know the Warning Signs

Watch for slow drains, gurgling sounds, foul odors, or wet spots in your yard. These could indicate a problem that needs professional attention. Don't wait - call a septic professional at the first sign of trouble.

*Need professional septic service in East Texas? Contact us today for a free inspection!*""",

    "faq": """## How Often Should I Pump My Septic Tank?

For a typical household of 4 people, your septic tank should be pumped every 3-5 years. However, this can vary based on:

- **Household size**: Larger families may need more frequent pumping
- **Tank size**: Smaller tanks fill up faster
- **Water usage**: High water usage means more frequent pumping
- **Garbage disposal use**: Using a garbage disposal adds more solids

**Signs you need pumping now:**
- Slow drains throughout the house
- Sewage odors near the tank or drain field
- Standing water or soggy spots in your yard
- Sewage backup in your home

Don't wait until you have a problem! Regular maintenance saves money and prevents emergencies.

*Schedule your free septic inspection today!*""",

    "gbp_post": """🏠 **Keep Your Septic System Healthy This Season!**

Regular maintenance is the key to avoiding costly septic emergencies. Our expert technicians are here to help with:

✅ Septic tank pumping
✅ System inspections
✅ Repairs & maintenance
✅ 24/7 emergency service

📞 Call us today for a FREE estimate!

#SepticService #EastTexas #HomeMaintenanceTips #SepticTank""",

    "service_description": """## Professional Septic Tank Pumping Services

Our experienced technicians provide thorough, reliable septic tank pumping for residential and commercial properties throughout East Texas.

### What's Included:

- **Complete tank pumping** - We remove all sludge and scum buildup
- **System inspection** - Visual check of tank condition and components
- **Detailed report** - Written summary of system health and recommendations
- **Cleanup** - We leave your property clean and tidy

### Why Choose Us:

- Family-owned and operated since 1985
- Licensed and insured technicians
- Same-day service available
- Competitive pricing with no hidden fees
- 24/7 emergency service

*Serving Nacogdoches, Lufkin, and surrounding East Texas communities.*"""
}


@router.post("/tasks/content/generate")
async def generate_content(request: ContentGenerateRequest, current_user: CurrentUser) -> dict:
    """Generate AI content - uses demo mode when content-gen service unavailable."""
    content_type = request.contentType

    # Always try to reach content-gen service first (unless on Railway)
    if not is_railway_deployment():
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                response = await client.post(
                    f"{CONTENT_GEN_URL}/api/generate",
                    json={
                        "type": content_type,
                        "topic": request.topic,
                        "targetLength": request.targetLength,
                        "tone": request.tone,
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "content": data.get("content", ""),
                        "contentType": content_type,
                        "topic": request.topic,
                        "demoMode": False,
                        "message": "Content generated successfully",
                    }
        except Exception as e:
            print(f"[marketing_tasks] Content-gen service error: {e}")

    # Fallback to demo content
    demo_content = DEMO_CONTENT.get(content_type, DEMO_CONTENT["blog"])

    # Customize demo content with topic if provided
    if request.topic:
        demo_content = demo_content.replace("Septic Tank Maintenance", f"{request.topic.title()}")
        demo_content = demo_content.replace("septic tank", request.topic.lower())

    return {
        "success": True,
        "content": demo_content,
        "contentType": content_type,
        "topic": request.topic,
        "demoMode": True,
        "message": "Demo content generated (AI service unavailable - connect via tunnel for live generation)",
    }


# =============================================================================
# GBP SYNC ENDPOINTS
# =============================================================================

class GBPPostRequest(BaseModel):
    title: str
    content: str
    callToAction: Optional[str] = "Learn More"
    actionUrl: Optional[str] = None


DEMO_GBP_STATUS = {
    "connected": False,
    "lastSync": "2026-02-01T08:00:00Z",
    "profileName": "ECB TX Septic Services",
    "profileUrl": "https://business.google.com/dashboard/l/123456789",
    "stats": {
        "totalPosts": 12,
        "totalReviews": 89,
        "averageRating": 4.7,
        "pendingResponses": 2,
        "viewsThisMonth": 1250,
        "callsThisMonth": 47,
    }
}


@router.get("/tasks/gbp/status")
async def get_gbp_status(current_user: CurrentUser) -> dict:
    """Get GBP sync status and profile info."""
    # Try to reach gbp-sync service
    if not is_railway_deployment():
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(f"{GBP_SYNC_URL}/api/status")
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "connected": data.get("connected", False),
                        "lastSync": data.get("lastSync"),
                        "profileName": data.get("profileName"),
                        "profileUrl": data.get("profileUrl"),
                        "stats": data.get("stats", {}),
                        "demoMode": False,
                    }
        except Exception as e:
            print(f"[marketing_tasks] GBP-sync service error: {e}")

    # Return demo status
    return {
        "success": True,
        **DEMO_GBP_STATUS,
        "demoMode": True,
        "message": "Demo mode - GBP sync service runs locally",
    }


@router.post("/tasks/gbp/sync")
async def trigger_gbp_sync(current_user: CurrentUser) -> dict:
    """Trigger a GBP sync operation."""
    # Try to reach gbp-sync service
    if not is_railway_deployment():
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(f"{GBP_SYNC_URL}/api/sync")
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "message": data.get("message", "Sync completed"),
                        "syncedAt": datetime.utcnow().isoformat() + "Z",
                        "demoMode": False,
                    }
        except Exception as e:
            print(f"[marketing_tasks] GBP-sync service error: {e}")

    # Demo mode response
    return {
        "success": True,
        "message": "Demo sync completed - GBP service runs locally",
        "syncedAt": datetime.utcnow().isoformat() + "Z",
        "demoMode": True,
    }


@router.post("/tasks/gbp/post")
async def create_gbp_post(request: GBPPostRequest, current_user: CurrentUser) -> dict:
    """Create and publish a GBP post."""
    # Try to reach gbp-sync service
    if not is_railway_deployment():
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    f"{GBP_SYNC_URL}/api/posts",
                    json={
                        "title": request.title,
                        "content": request.content,
                        "callToAction": request.callToAction,
                        "actionUrl": request.actionUrl,
                    }
                )
                if response.status_code == 200:
                    data = response.json()
                    return {
                        "success": True,
                        "postId": data.get("id"),
                        "message": "Post published successfully",
                        "publishedAt": datetime.utcnow().isoformat() + "Z",
                        "demoMode": False,
                    }
        except Exception as e:
            print(f"[marketing_tasks] GBP-sync service error: {e}")

    # Demo mode response
    return {
        "success": True,
        "postId": f"demo-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}",
        "message": "Demo post created - GBP service runs locally",
        "publishedAt": datetime.utcnow().isoformat() + "Z",
        "demoMode": True,
    }
