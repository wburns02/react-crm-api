"""
Enterprise API Endpoints

Multi-region, franchise management, and RBAC:
- Region CRUD and performance metrics
- Franchise royalty management
- Territory management
- Role-based access control
- Audit logging
"""

from fastapi import APIRouter, Query, HTTPException, status
from sqlalchemy import select, func, and_
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4

from app.api.deps import DbSession, CurrentUser


router = APIRouter()


# =============================================================================
# Pydantic Response Schemas
# =============================================================================


class Region(BaseModel):
    """Region/location data."""

    id: str
    name: str
    code: str
    timezone: str
    currency: str = "USD"
    is_active: bool = True
    manager_id: Optional[str] = None
    manager_name: Optional[str] = None
    address: Optional[str] = None
    phone: Optional[str] = None
    settings: dict = Field(default_factory=dict)
    created_at: str
    updated_at: Optional[str] = None


class RegionPerformance(BaseModel):
    """Performance metrics for a region."""

    region_id: str
    region_name: str
    revenue: float
    revenue_target: float
    revenue_pct: float
    jobs_completed: int
    jobs_scheduled: int
    technician_count: int
    customer_count: int
    avg_job_value: float
    first_time_fix_rate: float
    customer_satisfaction: Optional[float] = None
    trend: str  # up, down, stable


class FranchiseRoyalty(BaseModel):
    """Franchise royalty calculation."""

    id: str
    franchise_id: str
    franchise_name: str
    period_start: str
    period_end: str
    gross_revenue: float
    royalty_rate: float
    royalty_amount: float
    marketing_fee: float
    total_due: float
    status: str  # pending, invoiced, paid, overdue
    due_date: Optional[str] = None
    paid_date: Optional[str] = None
    payment_reference: Optional[str] = None


class Territory(BaseModel):
    """Territory definition."""

    id: str
    name: str
    region_id: str
    region_name: Optional[str] = None
    franchise_id: Optional[str] = None
    zip_codes: list[str] = Field(default_factory=list)
    boundary_geojson: Optional[dict] = None
    assigned_technicians: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: str


class Role(BaseModel):
    """User role definition."""

    id: str
    name: str
    description: Optional[str] = None
    permissions: list[dict] = Field(default_factory=list)
    is_system_role: bool = False
    user_count: int = 0
    created_at: str
    updated_at: Optional[str] = None


class UserRoleAssignment(BaseModel):
    """User role assignment."""

    id: str
    user_id: str
    user_name: Optional[str] = None
    user_email: Optional[str] = None
    role_id: str
    role_name: Optional[str] = None
    region_id: Optional[str] = None
    region_name: Optional[str] = None
    assigned_by: Optional[str] = None
    assigned_at: str
    expires_at: Optional[str] = None


class AuditLog(BaseModel):
    """Audit log entry."""

    id: str
    timestamp: str
    user_id: str
    user_name: Optional[str] = None
    action: str
    resource_type: str
    resource_id: Optional[str] = None
    region_id: Optional[str] = None
    old_values: Optional[dict] = None
    new_values: Optional[dict] = None
    ip_address: Optional[str] = None
    user_agent: Optional[str] = None


class ComplianceReport(BaseModel):
    """Compliance report."""

    generated_at: str
    period_start: str
    period_end: str
    overall_score: float
    categories: list[dict] = Field(default_factory=list)
    issues: list[dict] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


# =============================================================================
# Mock Data (In production, use database)
# =============================================================================

MOCK_REGIONS = [
    Region(
        id="region-1",
        name="Austin Metro",
        code="ATX",
        timezone="America/Chicago",
        is_active=True,
        manager_name="John Smith",
        address="123 Main St, Austin, TX",
        created_at="2024-01-01T00:00:00Z",
    ),
    Region(
        id="region-2",
        name="San Antonio",
        code="SAT",
        timezone="America/Chicago",
        is_active=True,
        manager_name="Jane Doe",
        address="456 Oak Ave, San Antonio, TX",
        created_at="2024-02-01T00:00:00Z",
    ),
]

MOCK_ROLES = [
    Role(
        id="role-admin",
        name="Administrator",
        description="Full system access",
        permissions=[{"resource": "*", "actions": ["*"], "scope": "all"}],
        is_system_role=True,
        user_count=2,
        created_at="2024-01-01T00:00:00Z",
    ),
    Role(
        id="role-manager",
        name="Manager",
        description="Regional management access",
        permissions=[
            {"resource": "work_orders", "actions": ["read", "write", "delete"], "scope": "region"},
            {"resource": "technicians", "actions": ["read", "write"], "scope": "region"},
            {"resource": "reports", "actions": ["read"], "scope": "region"},
        ],
        is_system_role=True,
        user_count=5,
        created_at="2024-01-01T00:00:00Z",
    ),
    Role(
        id="role-technician",
        name="Technician",
        description="Field technician access",
        permissions=[
            {"resource": "work_orders", "actions": ["read", "update"], "scope": "assigned"},
            {"resource": "customers", "actions": ["read"], "scope": "assigned"},
        ],
        is_system_role=True,
        user_count=15,
        created_at="2024-01-01T00:00:00Z",
    ),
]


# =============================================================================
# Region Endpoints
# =============================================================================


@router.get("/regions")
async def get_regions(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get all regions."""
    return {"regions": [r.model_dump() for r in MOCK_REGIONS]}


@router.get("/regions/{region_id}")
async def get_region(
    db: DbSession,
    current_user: CurrentUser,
    region_id: str,
) -> dict:
    """Get single region."""
    for r in MOCK_REGIONS:
        if r.id == region_id:
            return {"region": r.model_dump()}
    raise HTTPException(status_code=404, detail="Region not found")


@router.post("/regions")
async def create_region(
    db: DbSession,
    current_user: CurrentUser,
    name: str,
    code: str,
    timezone: str = "America/Chicago",
) -> dict:
    """Create a new region."""
    region = Region(
        id=f"region-{uuid4().hex[:8]}",
        name=name,
        code=code,
        timezone=timezone,
        created_at=datetime.utcnow().isoformat(),
    )
    return {"region": region.model_dump()}


@router.patch("/regions/{region_id}")
async def update_region(
    db: DbSession,
    current_user: CurrentUser,
    region_id: str,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> dict:
    """Update a region."""
    for r in MOCK_REGIONS:
        if r.id == region_id:
            if name:
                r.name = name
            if is_active is not None:
                r.is_active = is_active
            r.updated_at = datetime.utcnow().isoformat()
            return {"region": r.model_dump()}
    raise HTTPException(status_code=404, detail="Region not found")


@router.get("/regions/performance")
async def get_region_performance(
    db: DbSession,
    current_user: CurrentUser,
    period: str = Query("month", description="Period: week, month, quarter, year"),
) -> dict:
    """Get performance metrics for all regions."""
    performance = []
    for r in MOCK_REGIONS:
        perf = RegionPerformance(
            region_id=r.id,
            region_name=r.name,
            revenue=125000.00,
            revenue_target=150000.00,
            revenue_pct=83.3,
            jobs_completed=245,
            jobs_scheduled=280,
            technician_count=8,
            customer_count=520,
            avg_job_value=510.20,
            first_time_fix_rate=87.5,
            customer_satisfaction=4.6,
            trend="up",
        )
        performance.append(perf)
    return {"performance": [p.model_dump() for p in performance]}


@router.get("/regions/compare")
async def get_region_comparison(
    db: DbSession,
    current_user: CurrentUser,
    metric: str = Query(..., description="Metric to compare"),
) -> dict:
    """Get cross-region comparison for a metric."""
    comparison = {
        "metric": metric,
        "regions": [
            {"region_id": "region-1", "region_name": "Austin Metro", "value": 125000, "rank": 1},
            {"region_id": "region-2", "region_name": "San Antonio", "value": 98000, "rank": 2},
        ],
        "average": 111500,
        "leader": "region-1",
    }
    return comparison


# =============================================================================
# Franchise Endpoints
# =============================================================================


@router.get("/franchise/royalties")
async def get_franchise_royalties(
    db: DbSession,
    current_user: CurrentUser,
    franchise_id: Optional[str] = None,
) -> dict:
    """Get franchise royalty reports."""
    royalties = [
        FranchiseRoyalty(
            id="roy-001",
            franchise_id="franchise-1",
            franchise_name="Austin North Franchise",
            period_start="2024-01-01",
            period_end="2024-01-31",
            gross_revenue=85000.00,
            royalty_rate=0.06,
            royalty_amount=5100.00,
            marketing_fee=1700.00,
            total_due=6800.00,
            status="paid",
            due_date="2024-02-15",
            paid_date="2024-02-12",
        ),
        FranchiseRoyalty(
            id="roy-002",
            franchise_id="franchise-1",
            franchise_name="Austin North Franchise",
            period_start="2024-02-01",
            period_end="2024-02-29",
            gross_revenue=92000.00,
            royalty_rate=0.06,
            royalty_amount=5520.00,
            marketing_fee=1840.00,
            total_due=7360.00,
            status="pending",
            due_date="2024-03-15",
        ),
    ]
    return {"royalties": [r.model_dump() for r in royalties]}


@router.post("/franchise/royalties/generate")
async def generate_royalty_invoice(
    db: DbSession,
    current_user: CurrentUser,
    franchise_id: str,
    period_start: str,
    period_end: str,
) -> dict:
    """Generate royalty invoice for a franchise."""
    royalty = FranchiseRoyalty(
        id=f"roy-{uuid4().hex[:8]}",
        franchise_id=franchise_id,
        franchise_name="Generated Franchise",
        period_start=period_start,
        period_end=period_end,
        gross_revenue=75000.00,
        royalty_rate=0.06,
        royalty_amount=4500.00,
        marketing_fee=1500.00,
        total_due=6000.00,
        status="invoiced",
        due_date=(datetime.now() + timedelta(days=15)).strftime("%Y-%m-%d"),
    )
    return {"royalty": royalty.model_dump()}


@router.post("/franchise/royalties/{royalty_id}/paid")
async def mark_royalty_paid(
    db: DbSession,
    current_user: CurrentUser,
    royalty_id: str,
    paid_date: str,
    reference: Optional[str] = None,
) -> dict:
    """Mark royalty as paid."""
    royalty = FranchiseRoyalty(
        id=royalty_id,
        franchise_id="franchise-1",
        franchise_name="Franchise",
        period_start="2024-01-01",
        period_end="2024-01-31",
        gross_revenue=75000.00,
        royalty_rate=0.06,
        royalty_amount=4500.00,
        marketing_fee=1500.00,
        total_due=6000.00,
        status="paid",
        paid_date=paid_date,
        payment_reference=reference,
    )
    return {"royalty": royalty.model_dump()}


# =============================================================================
# Territory Endpoints
# =============================================================================


@router.get("/territories")
async def get_territories(
    db: DbSession,
    current_user: CurrentUser,
    region_id: Optional[str] = None,
) -> dict:
    """Get territories."""
    territories = [
        Territory(
            id="territory-1",
            name="North Austin",
            region_id="region-1",
            region_name="Austin Metro",
            zip_codes=["78701", "78702", "78703"],
            assigned_technicians=["tech-1", "tech-2"],
            created_at="2024-01-01T00:00:00Z",
        ),
        Territory(
            id="territory-2",
            name="South Austin",
            region_id="region-1",
            region_name="Austin Metro",
            zip_codes=["78704", "78745", "78748"],
            assigned_technicians=["tech-3"],
            created_at="2024-01-15T00:00:00Z",
        ),
    ]
    if region_id:
        territories = [t for t in territories if t.region_id == region_id]
    return {"territories": [t.model_dump() for t in territories]}


@router.post("/territories")
async def create_territory(
    db: DbSession,
    current_user: CurrentUser,
    name: str,
    region_id: str,
    zip_codes: list[str] = [],
) -> dict:
    """Create a territory."""
    territory = Territory(
        id=f"territory-{uuid4().hex[:8]}",
        name=name,
        region_id=region_id,
        zip_codes=zip_codes,
        created_at=datetime.utcnow().isoformat(),
    )
    return {"territory": territory.model_dump()}


@router.patch("/territories/{territory_id}")
async def update_territory(
    db: DbSession,
    current_user: CurrentUser,
    territory_id: str,
    name: Optional[str] = None,
    zip_codes: Optional[list[str]] = None,
) -> dict:
    """Update a territory."""
    territory = Territory(
        id=territory_id,
        name=name or "Updated Territory",
        region_id="region-1",
        zip_codes=zip_codes or [],
        created_at="2024-01-01T00:00:00Z",
    )
    return {"territory": territory.model_dump()}


# =============================================================================
# RBAC Endpoints
# =============================================================================


@router.get("/roles")
async def get_roles(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get all roles."""
    return {"roles": [r.model_dump() for r in MOCK_ROLES]}


@router.get("/roles/{role_id}")
async def get_role(
    db: DbSession,
    current_user: CurrentUser,
    role_id: str,
) -> dict:
    """Get single role."""
    for r in MOCK_ROLES:
        if r.id == role_id:
            return {"role": r.model_dump()}
    raise HTTPException(status_code=404, detail="Role not found")


@router.post("/roles")
async def create_role(
    db: DbSession,
    current_user: CurrentUser,
    name: str,
    description: Optional[str] = None,
    permissions: list[dict] = [],
) -> dict:
    """Create a custom role."""
    role = Role(
        id=f"role-{uuid4().hex[:8]}",
        name=name,
        description=description,
        permissions=permissions,
        is_system_role=False,
        created_at=datetime.utcnow().isoformat(),
    )
    return {"role": role.model_dump()}


@router.patch("/roles/{role_id}")
async def update_role(
    db: DbSession,
    current_user: CurrentUser,
    role_id: str,
    name: Optional[str] = None,
    permissions: Optional[list[dict]] = None,
) -> dict:
    """Update a role."""
    for r in MOCK_ROLES:
        if r.id == role_id:
            if r.is_system_role:
                raise HTTPException(status_code=400, detail="Cannot modify system roles")
            if name:
                r.name = name
            if permissions is not None:
                r.permissions = permissions
            r.updated_at = datetime.utcnow().isoformat()
            return {"role": r.model_dump()}
    raise HTTPException(status_code=404, detail="Role not found")


@router.delete("/roles/{role_id}")
async def delete_role(
    db: DbSession,
    current_user: CurrentUser,
    role_id: str,
) -> dict:
    """Delete a role."""
    for r in MOCK_ROLES:
        if r.id == role_id:
            if r.is_system_role:
                raise HTTPException(status_code=400, detail="Cannot delete system roles")
            return {"deleted": True}
    raise HTTPException(status_code=404, detail="Role not found")


@router.get("/role-assignments")
async def get_role_assignments(
    db: DbSession,
    current_user: CurrentUser,
    user_id: Optional[str] = None,
) -> dict:
    """Get user role assignments."""
    assignments = [
        UserRoleAssignment(
            id="assign-1",
            user_id="user-1",
            user_name="John Admin",
            user_email="john@example.com",
            role_id="role-admin",
            role_name="Administrator",
            assigned_by="system",
            assigned_at="2024-01-01T00:00:00Z",
        ),
        UserRoleAssignment(
            id="assign-2",
            user_id="user-2",
            user_name="Jane Manager",
            user_email="jane@example.com",
            role_id="role-manager",
            role_name="Manager",
            region_id="region-1",
            region_name="Austin Metro",
            assigned_by="user-1",
            assigned_at="2024-01-15T00:00:00Z",
        ),
    ]
    if user_id:
        assignments = [a for a in assignments if a.user_id == user_id]
    return {"assignments": [a.model_dump() for a in assignments]}


@router.post("/role-assignments")
async def assign_role(
    db: DbSession,
    current_user: CurrentUser,
    user_id: str,
    role_id: str,
    region_id: Optional[str] = None,
    expires_at: Optional[str] = None,
) -> dict:
    """Assign a role to a user."""
    assignment = UserRoleAssignment(
        id=f"assign-{uuid4().hex[:8]}",
        user_id=user_id,
        role_id=role_id,
        region_id=region_id,
        assigned_by=str(current_user.id),
        assigned_at=datetime.utcnow().isoformat(),
        expires_at=expires_at,
    )
    return {"assignment": assignment.model_dump()}


@router.delete("/role-assignments/{assignment_id}")
async def remove_role_assignment(
    db: DbSession,
    current_user: CurrentUser,
    assignment_id: str,
) -> dict:
    """Remove a role assignment."""
    return {"deleted": True}


@router.get("/permissions/me")
async def get_current_permissions(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get current user's effective permissions."""
    # In production, calculate from actual role assignments
    return {
        "roles": ["Administrator"] if current_user.is_superuser else ["User"],
        "permissions": [{"resource": "*", "actions": ["*"], "scope": "all"}]
        if current_user.is_superuser
        else [{"resource": "work_orders", "actions": ["read"], "scope": "assigned"}],
        "regions": [],  # All regions if admin
    }


# =============================================================================
# Audit & Compliance Endpoints
# =============================================================================


@router.get("/audit/logs")
async def get_audit_logs(
    db: DbSession,
    current_user: CurrentUser,
    user_id: Optional[str] = None,
    resource_type: Optional[str] = None,
    action: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
) -> dict:
    """Get audit logs."""
    logs = [
        AuditLog(
            id="log-1",
            timestamp="2024-03-01T10:30:00Z",
            user_id="user-1",
            user_name="John Admin",
            action="update",
            resource_type="work_order",
            resource_id="wo-123",
            old_values={"status": "scheduled"},
            new_values={"status": "completed"},
        ),
        AuditLog(
            id="log-2",
            timestamp="2024-03-01T11:15:00Z",
            user_id="user-2",
            user_name="Jane Manager",
            action="create",
            resource_type="customer",
            resource_id="cust-456",
            new_values={"name": "New Customer"},
        ),
    ]
    return {"logs": [l.model_dump() for l in logs], "total": len(logs), "page": page, "page_size": page_size}


@router.post("/audit/export")
async def export_audit_logs(
    db: DbSession,
    current_user: CurrentUser,
    start_date: str,
    end_date: str,
    format: str = "csv",
    region_id: Optional[str] = None,
) -> dict:
    """Export audit logs."""
    # In production, generate actual export file
    return {"download_url": f"/api/v2/enterprise/audit/downloads/export-{uuid4().hex[:8]}.{format}"}


@router.get("/compliance/report")
async def get_compliance_report(
    db: DbSession,
    current_user: CurrentUser,
    region_id: Optional[str] = None,
) -> ComplianceReport:
    """Get compliance report."""
    return ComplianceReport(
        generated_at=datetime.utcnow().isoformat(),
        period_start=(date.today() - timedelta(days=30)).isoformat(),
        period_end=date.today().isoformat(),
        overall_score=87.5,
        categories=[
            {"name": "Data Privacy", "score": 92.0, "status": "compliant"},
            {"name": "Access Control", "score": 88.0, "status": "compliant"},
            {"name": "Audit Trail", "score": 95.0, "status": "compliant"},
            {"name": "License Compliance", "score": 75.0, "status": "needs_attention"},
        ],
        issues=[
            {
                "category": "License Compliance",
                "severity": "medium",
                "description": "3 technician licenses expiring within 30 days",
                "action_required": "Renew licenses before expiration",
            }
        ],
        recommendations=[
            "Schedule license renewals for upcoming expirations",
            "Review access permissions for inactive users",
            "Enable two-factor authentication for admin accounts",
        ],
    )
