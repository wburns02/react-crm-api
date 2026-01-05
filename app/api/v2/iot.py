"""
IoT Integration API Endpoints

Connected equipment and predictive maintenance:
- Device management
- Telemetry data
- Alerts and rules
- Equipment health scoring
"""

from fastapi import APIRouter, Query, HTTPException
from datetime import datetime, date, timedelta
from pydantic import BaseModel, Field
from typing import Optional
from uuid import uuid4

from app.api.deps import DbSession, CurrentUser


router = APIRouter()


# =============================================================================
# Pydantic Schemas
# =============================================================================

class Device(BaseModel):
    """Connected IoT device."""
    id: str
    device_type: str  # thermostat, water_heater, septic_monitor, hvac
    provider: str  # ecobee, nest, custom
    name: str
    customer_id: str
    equipment_id: Optional[str] = None
    serial_number: Optional[str] = None
    is_online: bool = True
    is_active: bool = True
    last_reading_at: Optional[str] = None
    firmware_version: Optional[str] = None
    metadata: dict = Field(default_factory=dict)
    created_at: str


class DeviceReading(BaseModel):
    """Device telemetry reading."""
    id: str
    device_id: str
    timestamp: str
    metrics: dict  # temperature, humidity, level, etc.


class DeviceAlert(BaseModel):
    """Device alert."""
    id: str
    device_id: str
    device_name: str
    alert_type: str
    severity: str  # info, warning, critical
    message: str
    acknowledged: bool = False
    acknowledged_at: Optional[str] = None
    created_at: str


class AlertRule(BaseModel):
    """Alert rule definition."""
    id: str
    name: str
    device_type: Optional[str] = None
    condition: dict  # metric, operator, threshold
    severity: str
    notification_channels: list[str] = Field(default_factory=list)
    is_active: bool = True
    created_at: str


class EquipmentHealth(BaseModel):
    """Equipment health score."""
    equipment_id: str
    equipment_type: str
    customer_id: str
    health_score: float
    risk_level: str  # low, medium, high, critical
    last_reading: Optional[dict] = None
    trends: dict = Field(default_factory=dict)
    issues: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    next_maintenance_date: Optional[str] = None


class MaintenanceRecommendation(BaseModel):
    """Maintenance recommendation."""
    id: str
    equipment_id: str
    equipment_type: str
    customer_id: str
    customer_name: str
    priority: str  # low, medium, high, urgent
    issue: str
    recommendation: str
    estimated_cost: Optional[float] = None
    status: str  # pending, scheduled, declined
    created_at: str


class IoTProviderConnection(BaseModel):
    """IoT provider connection."""
    provider: str
    connected: bool
    account_name: Optional[str] = None
    device_count: int = 0
    last_sync: Optional[str] = None


# =============================================================================
# Mock Data
# =============================================================================

MOCK_DEVICES = [
    Device(
        id="dev-001",
        device_type="thermostat",
        provider="ecobee",
        name="Main Floor Thermostat",
        customer_id="cust-123",
        equipment_id="equip-hvac-1",
        is_online=True,
        last_reading_at=datetime.utcnow().isoformat(),
        created_at="2024-01-15T00:00:00Z"
    ),
    Device(
        id="dev-002",
        device_type="septic_monitor",
        provider="custom",
        name="Septic Tank Level Monitor",
        customer_id="cust-456",
        equipment_id="equip-septic-1",
        is_online=True,
        last_reading_at=datetime.utcnow().isoformat(),
        created_at="2024-02-01T00:00:00Z"
    ),
]


# =============================================================================
# Device Endpoints
# =============================================================================

@router.get("/devices")
async def get_devices(
    db: DbSession,
    current_user: CurrentUser,
    customer_id: Optional[str] = None,
) -> dict:
    """Get all connected devices."""
    devices = MOCK_DEVICES.copy()
    if customer_id:
        devices = [d for d in devices if d.customer_id == customer_id]
    return {"devices": [d.model_dump() for d in devices]}


@router.get("/devices/{device_id}")
async def get_device(
    db: DbSession,
    current_user: CurrentUser,
    device_id: str,
) -> dict:
    """Get single device."""
    for d in MOCK_DEVICES:
        if d.id == device_id:
            return {"device": d.model_dump()}
    raise HTTPException(status_code=404, detail="Device not found")


@router.get("/devices/{device_id}/telemetry")
async def get_device_telemetry(
    db: DbSession,
    current_user: CurrentUser,
    device_id: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    resolution: str = "hour",
    metrics: Optional[str] = None,
) -> dict:
    """Get device telemetry readings."""
    readings = []
    now = datetime.utcnow()
    for i in range(24):
        readings.append(DeviceReading(
            id=f"reading-{i}",
            device_id=device_id,
            timestamp=(now - timedelta(hours=i)).isoformat(),
            metrics={
                "temperature": 72 + (i % 5),
                "humidity": 45 + (i % 10),
                "level": 65 - (i * 0.5) if "septic" in device_id else None
            }
        ))
    return {"readings": [r.model_dump() for r in readings]}


@router.get("/devices/{device_id}/latest")
async def get_latest_reading(
    db: DbSession,
    current_user: CurrentUser,
    device_id: str,
) -> dict:
    """Get latest reading for a device."""
    reading = DeviceReading(
        id="latest",
        device_id=device_id,
        timestamp=datetime.utcnow().isoformat(),
        metrics={
            "temperature": 72,
            "humidity": 48,
            "level": 62
        }
    )
    return {"reading": reading.model_dump()}


@router.post("/devices")
async def connect_device(
    db: DbSession,
    current_user: CurrentUser,
    device_type: str,
    provider: str,
    name: str,
    customer_id: str,
    equipment_id: Optional[str] = None,
) -> dict:
    """Connect a new device."""
    device = Device(
        id=f"dev-{uuid4().hex[:8]}",
        device_type=device_type,
        provider=provider,
        name=name,
        customer_id=customer_id,
        equipment_id=equipment_id,
        created_at=datetime.utcnow().isoformat()
    )
    return {"device": device.model_dump()}


@router.patch("/devices/{device_id}")
async def update_device(
    db: DbSession,
    current_user: CurrentUser,
    device_id: str,
    name: Optional[str] = None,
    is_active: Optional[bool] = None,
) -> dict:
    """Update device settings."""
    for d in MOCK_DEVICES:
        if d.id == device_id:
            if name:
                d.name = name
            if is_active is not None:
                d.is_active = is_active
            return {"device": d.model_dump()}
    raise HTTPException(status_code=404, detail="Device not found")


@router.delete("/devices/{device_id}")
async def disconnect_device(
    db: DbSession,
    current_user: CurrentUser,
    device_id: str,
) -> dict:
    """Disconnect a device."""
    return {"success": True}


# =============================================================================
# Alert Endpoints
# =============================================================================

@router.get("/alerts")
async def get_device_alerts(
    db: DbSession,
    current_user: CurrentUser,
    acknowledged: Optional[bool] = None,
    severity: Optional[str] = None,
) -> dict:
    """Get device alerts."""
    alerts = [
        DeviceAlert(
            id="alert-001",
            device_id="dev-002",
            device_name="Septic Tank Level Monitor",
            alert_type="high_level",
            severity="warning",
            message="Tank level at 85% - schedule pumping soon",
            acknowledged=False,
            created_at=datetime.utcnow().isoformat()
        ),
        DeviceAlert(
            id="alert-002",
            device_id="dev-001",
            device_name="Main Floor Thermostat",
            alert_type="offline",
            severity="info",
            message="Device was offline for 2 hours",
            acknowledged=True,
            acknowledged_at=(datetime.utcnow() - timedelta(hours=1)).isoformat(),
            created_at=(datetime.utcnow() - timedelta(hours=3)).isoformat()
        ),
    ]

    if acknowledged is not None:
        alerts = [a for a in alerts if a.acknowledged == acknowledged]
    if severity:
        alerts = [a for a in alerts if a.severity == severity]

    return {"alerts": [a.model_dump() for a in alerts]}


@router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(
    db: DbSession,
    current_user: CurrentUser,
    alert_id: str,
) -> dict:
    """Acknowledge an alert."""
    alert = DeviceAlert(
        id=alert_id,
        device_id="dev-001",
        device_name="Device",
        alert_type="acknowledged",
        severity="info",
        message="Alert acknowledged",
        acknowledged=True,
        acknowledged_at=datetime.utcnow().isoformat(),
        created_at=datetime.utcnow().isoformat()
    )
    return {"alert": alert.model_dump()}


@router.get("/alerts/rules")
async def get_alert_rules(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get alert rules."""
    rules = [
        AlertRule(
            id="rule-001",
            name="High Tank Level",
            device_type="septic_monitor",
            condition={"metric": "level", "operator": ">", "threshold": 80},
            severity="warning",
            notification_channels=["email", "sms"],
            created_at="2024-01-01T00:00:00Z"
        ),
        AlertRule(
            id="rule-002",
            name="Device Offline",
            condition={"metric": "online", "operator": "==", "threshold": False},
            severity="info",
            notification_channels=["email"],
            created_at="2024-01-01T00:00:00Z"
        ),
    ]
    return {"rules": [r.model_dump() for r in rules]}


@router.post("/alerts/rules")
async def create_alert_rule(
    db: DbSession,
    current_user: CurrentUser,
    name: str,
    condition: dict,
    severity: str,
    device_type: Optional[str] = None,
) -> dict:
    """Create an alert rule."""
    rule = AlertRule(
        id=f"rule-{uuid4().hex[:8]}",
        name=name,
        device_type=device_type,
        condition=condition,
        severity=severity,
        created_at=datetime.utcnow().isoformat()
    )
    return {"rule": rule.model_dump()}


@router.patch("/alerts/rules/{rule_id}")
async def update_alert_rule(
    db: DbSession,
    current_user: CurrentUser,
    rule_id: str,
    is_active: Optional[bool] = None,
) -> dict:
    """Update an alert rule."""
    rule = AlertRule(
        id=rule_id,
        name="Updated Rule",
        condition={},
        severity="info",
        is_active=is_active if is_active is not None else True,
        created_at="2024-01-01T00:00:00Z"
    )
    return {"rule": rule.model_dump()}


@router.delete("/alerts/rules/{rule_id}")
async def delete_alert_rule(
    db: DbSession,
    current_user: CurrentUser,
    rule_id: str,
) -> dict:
    """Delete an alert rule."""
    return {"success": True}


# =============================================================================
# Health & Maintenance Endpoints
# =============================================================================

@router.get("/health/equipment/{equipment_id}")
async def get_equipment_health(
    db: DbSession,
    current_user: CurrentUser,
    equipment_id: str,
) -> EquipmentHealth:
    """Get equipment health score."""
    return EquipmentHealth(
        equipment_id=equipment_id,
        equipment_type="septic_tank",
        customer_id="cust-123",
        health_score=78.5,
        risk_level="medium",
        last_reading={"level": 62, "temperature": 55},
        trends={"level": "increasing", "temperature": "stable"},
        issues=["Level trending higher than normal"],
        recommendations=["Schedule pumping within 30 days"],
        next_maintenance_date="2024-04-15"
    )


@router.get("/health/customer/{customer_id}")
async def get_customer_equipment_health(
    db: DbSession,
    current_user: CurrentUser,
    customer_id: str,
) -> dict:
    """Get all equipment health for a customer."""
    equipment = [
        EquipmentHealth(
            equipment_id="equip-1",
            equipment_type="septic_tank",
            customer_id=customer_id,
            health_score=78.5,
            risk_level="medium",
            issues=["Approaching service date"],
            recommendations=["Schedule pumping"]
        ),
        EquipmentHealth(
            equipment_id="equip-2",
            equipment_type="hvac",
            customer_id=customer_id,
            health_score=92.0,
            risk_level="low",
            issues=[],
            recommendations=[]
        ),
    ]
    return {"equipment": [e.model_dump() for e in equipment]}


@router.get("/maintenance/recommendations")
async def get_maintenance_recommendations(
    db: DbSession,
    current_user: CurrentUser,
    priority: Optional[str] = None,
    status: Optional[str] = None,
    customer_id: Optional[str] = None,
) -> dict:
    """Get maintenance recommendations."""
    recommendations = [
        MaintenanceRecommendation(
            id="rec-001",
            equipment_id="equip-1",
            equipment_type="septic_tank",
            customer_id="cust-123",
            customer_name="John Smith",
            priority="high",
            issue="Tank level at 85%",
            recommendation="Schedule pumping service",
            estimated_cost=350.00,
            status="pending",
            created_at="2024-03-01T00:00:00Z"
        ),
        MaintenanceRecommendation(
            id="rec-002",
            equipment_id="equip-2",
            equipment_type="hvac",
            customer_id="cust-456",
            customer_name="Jane Doe",
            priority="medium",
            issue="Filter replacement due",
            recommendation="Replace air filter",
            estimated_cost=75.00,
            status="pending",
            created_at="2024-02-28T00:00:00Z"
        ),
    ]

    if priority:
        recommendations = [r for r in recommendations if r.priority == priority]
    if status:
        recommendations = [r for r in recommendations if r.status == status]
    if customer_id:
        recommendations = [r for r in recommendations if r.customer_id == customer_id]

    return {"recommendations": [r.model_dump() for r in recommendations]}


@router.post("/maintenance/recommendations/{recommendation_id}/schedule")
async def schedule_maintenance(
    db: DbSession,
    current_user: CurrentUser,
    recommendation_id: str,
    scheduled_date: str,
    technician_id: Optional[str] = None,
) -> dict:
    """Create work order from recommendation."""
    return {
        "work_order_id": f"wo-{uuid4().hex[:8]}",
        "recommendation_id": recommendation_id,
        "scheduled_date": scheduled_date,
        "status": "scheduled"
    }


@router.post("/maintenance/recommendations/{recommendation_id}/decline")
async def decline_recommendation(
    db: DbSession,
    current_user: CurrentUser,
    recommendation_id: str,
    reason: Optional[str] = None,
) -> dict:
    """Decline a maintenance recommendation."""
    return {"success": True, "status": "declined"}


# =============================================================================
# Provider Connection Endpoints
# =============================================================================

@router.get("/providers/connections")
async def get_provider_connections(
    db: DbSession,
    current_user: CurrentUser,
) -> dict:
    """Get IoT provider connections."""
    connections = [
        IoTProviderConnection(
            provider="ecobee",
            connected=True,
            account_name="HVAC Pro Account",
            device_count=15,
            last_sync=datetime.utcnow().isoformat()
        ),
        IoTProviderConnection(
            provider="nest",
            connected=False,
            device_count=0
        ),
    ]
    return {"connections": [c.model_dump() for c in connections]}


@router.post("/providers/{provider}/connect")
async def connect_provider(
    db: DbSession,
    current_user: CurrentUser,
    provider: str,
) -> dict:
    """Initiate OAuth connection to provider."""
    return {
        "auth_url": f"https://api.{provider}.com/oauth/authorize?client_id=xxx&redirect_uri=xxx",
        "state": uuid4().hex
    }


@router.post("/providers/{provider}/callback")
async def complete_provider_connection(
    db: DbSession,
    current_user: CurrentUser,
    provider: str,
    code: str,
    state: str,
) -> dict:
    """Complete OAuth connection."""
    connection = IoTProviderConnection(
        provider=provider,
        connected=True,
        account_name=f"{provider.title()} Account",
        device_count=0,
        last_sync=datetime.utcnow().isoformat()
    )
    return {"connection": connection.model_dump()}


@router.delete("/providers/{provider}/disconnect")
async def disconnect_provider(
    db: DbSession,
    current_user: CurrentUser,
    provider: str,
) -> dict:
    """Disconnect from provider."""
    return {"success": True}


@router.post("/providers/{provider}/sync")
async def sync_provider_devices(
    db: DbSession,
    current_user: CurrentUser,
    provider: str,
) -> dict:
    """Sync devices from provider."""
    return {"synced_count": 5}
