"""
Role View Model for Demo Mode Role Switching

Enables demo users (will@macseptic.com) to switch between different CRM roles
to demonstrate role-specific views and functionality.
"""

from sqlalchemy import Column, Integer, String, Boolean, DateTime, JSON, ForeignKey
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.database import Base


class RoleView(Base):
    """
    Defines available role views in the CRM system.

    Each role represents a different perspective/persona for viewing the CRM:
    - admin: Full system access (Administrator)
    - executive: High-level KPIs and reporting (Executive)
    - manager: Day-to-day operations management (Operations Manager)
    - technician: Mobile-first work order view (Field Technician)
    - phone_agent: Customer service focus (Phone Agent)
    - dispatcher: Schedule and route management (Dispatcher)
    - billing: Invoicing and payments focus (Billing Specialist)
    """

    __tablename__ = "role_views"

    id = Column(Integer, primary_key=True, index=True)
    role_key = Column(String(50), unique=True, index=True, nullable=False)
    display_name = Column(String(100), nullable=False)
    description = Column(String(500))
    icon = Column(String(10))  # Emoji icon
    color = Column(String(20))  # Tailwind color class

    # Role configuration
    visible_modules = Column(JSON, default=list)  # List of module keys visible to this role
    default_route = Column(String(100), default="/")  # Default landing page for role
    dashboard_widgets = Column(JSON, default=list)  # Widget configuration for dashboard

    # Quick actions available for this role
    quick_actions = Column(JSON, default=list)

    # Feature flags for this role
    features = Column(JSON, default=dict)

    is_active = Column(Boolean, default=True)
    sort_order = Column(Integer, default=0)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class UserRoleSession(Base):
    """
    Tracks which role a demo user is currently viewing as.
    Only applicable for demo mode users.
    """

    __tablename__ = "user_role_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("api_users.id"), index=True, nullable=False)
    current_role_key = Column(String(50), ForeignKey("role_views.role_key"), nullable=False)

    # Track when role was switched for analytics
    switched_at = Column(DateTime(timezone=True), server_default=func.now())

    # Relationship to role view
    current_role = relationship(
        "RoleView", foreign_keys=[current_role_key], primaryjoin="UserRoleSession.current_role_key == RoleView.role_key"
    )


# Demo user email constant
DEMO_USER_EMAIL = "will@macseptic.com"

# Default role configurations
DEFAULT_ROLES = [
    {
        "role_key": "admin",
        "display_name": "Administrator",
        "description": "Full system access with all features and settings",
        "icon": "👑",
        "color": "purple",
        "sort_order": 1,
        "visible_modules": ["*"],  # All modules
        "default_route": "/",
        "dashboard_widgets": ["revenue_chart", "work_orders_summary", "customer_health", "team_performance"],
        "quick_actions": ["create_work_order", "add_customer", "view_reports", "manage_users"],
        "features": {"can_manage_users": True, "can_view_reports": True, "can_manage_settings": True},
    },
    {
        "role_key": "executive",
        "display_name": "Executive",
        "description": "High-level KPIs, financial metrics, and business intelligence",
        "icon": "📊",
        "color": "blue",
        "sort_order": 2,
        "visible_modules": ["dashboard", "reports", "analytics", "customer-success"],
        "default_route": "/",
        "dashboard_widgets": ["revenue_kpi", "customer_growth", "profitability", "forecasts"],
        "quick_actions": ["view_reports", "export_data", "schedule_review"],
        "features": {"can_view_reports": True, "can_export_data": True},
    },
    {
        "role_key": "manager",
        "display_name": "Operations Manager",
        "description": "Day-to-day operations, team management, and scheduling oversight",
        "icon": "📋",
        "color": "green",
        "sort_order": 3,
        "visible_modules": ["dashboard", "schedule", "work-orders", "technicians", "customers", "reports"],
        "default_route": "/schedule",
        "dashboard_widgets": ["today_schedule", "team_availability", "pending_work_orders", "customer_issues"],
        "quick_actions": ["create_work_order", "assign_technician", "view_schedule", "contact_customer"],
        "features": {"can_assign_work": True, "can_view_reports": True, "can_manage_schedule": True},
    },
    {
        "role_key": "technician",
        "display_name": "Field Technician",
        "description": "Mobile-optimized view for field work and service completion",
        "icon": "🔧",
        "color": "orange",
        "sort_order": 4,
        "visible_modules": ["my-schedule", "work-orders", "customers", "equipment"],
        "default_route": "/my-schedule",
        "dashboard_widgets": ["my_jobs_today", "next_appointment", "route_map", "time_tracker"],
        "quick_actions": ["start_job", "complete_job", "add_notes", "call_customer"],
        "features": {"can_update_work_orders": True, "can_capture_photos": True, "can_collect_signatures": True},
    },
    {
        "role_key": "phone_agent",
        "display_name": "Phone Agent",
        "description": "Customer service focus with quick access to customer info and scheduling",
        "icon": "📞",
        "color": "cyan",
        "sort_order": 5,
        "visible_modules": ["customers", "work-orders", "schedule", "communications"],
        "default_route": "/customers",
        "dashboard_widgets": ["incoming_calls", "customer_search", "recent_interactions", "quick_schedule"],
        "quick_actions": ["search_customer", "create_work_order", "schedule_appointment", "send_sms"],
        "features": {"can_create_work_orders": True, "can_schedule": True, "can_communicate": True},
    },
    {
        "role_key": "dispatcher",
        "display_name": "Dispatcher",
        "description": "Schedule management, route optimization, and real-time tracking",
        "icon": "🗺️",
        "color": "indigo",
        "sort_order": 6,
        "visible_modules": ["schedule", "schedule-map", "work-orders", "technicians", "fleet"],
        "default_route": "/schedule-map",
        "dashboard_widgets": ["live_map", "unassigned_jobs", "technician_status", "route_efficiency"],
        "quick_actions": ["assign_job", "optimize_routes", "contact_technician", "reschedule"],
        "features": {"can_assign_work": True, "can_manage_schedule": True, "can_track_fleet": True},
    },
    {
        "role_key": "billing",
        "display_name": "Billing Specialist",
        "description": "Invoicing, payments, and financial operations",
        "icon": "💰",
        "color": "emerald",
        "sort_order": 7,
        "visible_modules": ["invoices", "payments", "customers", "reports"],
        "default_route": "/invoices",
        "dashboard_widgets": ["outstanding_invoices", "payments_today", "aging_report", "collection_queue"],
        "quick_actions": ["create_invoice", "record_payment", "send_reminder", "generate_statement"],
        "features": {"can_manage_invoices": True, "can_process_payments": True, "can_view_financial_reports": True},
    },
]
