from fastapi import APIRouter
from app.api.v2 import (
    auth,
    customers,
    work_orders,
    communications,
    technicians,
    invoices,
    dashboard,
    schedule,
    reports,
    ringcentral,
    twilio,
    prospects,
    payments,
    quotes,
    sms_consent,
    payroll,
    activities,
    tickets,
    equipment,
    inventory,
    notifications,
    calls,
    # Phase 1: AI Infrastructure
    ai,
    # Phase 3: E-Signatures
    signatures,
    # Phase 4: Pricing Engine
    pricing,
    # Phase 5: AI Agents
    agents,
    # Phase 6: Predictive Analytics
    predictions,
    # Phase 7: Marketing Automation
    marketing,
    marketing_hub,
    # Phase 8: Schedule Map View
    schedule_map,
    # Phase 9: Employee Portal
    employee_portal,
    # Fleet & Integrations
    samsara,
    email_marketing,
    admin,
    # Phase 11: Compliance
    compliance,
    # Phase 12: Contracts
    contracts,
    # Phase 13: Job Costing
    job_costing,
    # Phase 14: Data Import
    import_data,
)

api_router = APIRouter()

# Include all v2 routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(prospects.router, prefix="/prospects", tags=["prospects"])
api_router.include_router(work_orders.router, prefix="/work-orders", tags=["work-orders"])
api_router.include_router(communications.router, prefix="/communications", tags=["communications"])
api_router.include_router(technicians.router, prefix="/technicians", tags=["technicians"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(quotes.router, prefix="/quotes", tags=["quotes"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(schedule.router, prefix="/schedule", tags=["schedule"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(ringcentral.router, prefix="/ringcentral", tags=["ringcentral"])
api_router.include_router(twilio.router, prefix="/twilio", tags=["twilio"])
api_router.include_router(sms_consent.router, prefix="/sms-consent", tags=["sms-consent"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["payroll"])
api_router.include_router(activities.router, prefix="/activities", tags=["activities"])
api_router.include_router(tickets.router, prefix="/tickets", tags=["tickets"])
api_router.include_router(equipment.router, prefix="/equipment", tags=["equipment"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(calls.router, prefix="/calls", tags=["calls"])

# Phase 1: AI Infrastructure
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])

# Phase 3: E-Signatures
api_router.include_router(signatures.router, prefix="/signatures", tags=["signatures"])

# Phase 4: Pricing Engine
api_router.include_router(pricing.router, prefix="/pricing", tags=["pricing"])

# Phase 5: AI Agents
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])

# Phase 6: Predictive Analytics
api_router.include_router(predictions.router, prefix="/predictions", tags=["predictions"])

# Phase 7: Marketing Automation
api_router.include_router(marketing.router, prefix="/marketing", tags=["marketing"])
api_router.include_router(marketing_hub.router, prefix="/marketing-hub", tags=["marketing-hub"])

# Phase 8: Schedule Map View
api_router.include_router(schedule_map.router, prefix="/schedule-map", tags=["schedule-map"])

# Phase 9: Employee Portal
api_router.include_router(employee_portal.router, prefix="/employee", tags=["employee"])

# Fleet & Integrations
api_router.include_router(samsara.router, prefix="/samsara", tags=["samsara"])
api_router.include_router(email_marketing.router, prefix="/email-marketing", tags=["email-marketing"])
api_router.include_router(admin.router, prefix="/admin", tags=["admin"])

# Phase 11: Compliance
api_router.include_router(compliance.router, prefix="/compliance", tags=["compliance"])

# Phase 12: Contracts
api_router.include_router(contracts.router, prefix="/contracts", tags=["contracts"])

# Phase 13: Job Costing
api_router.include_router(job_costing.router, prefix="/job-costing", tags=["job-costing"])

# Phase 14: Data Import
api_router.include_router(import_data.router, prefix="/import", tags=["import"])
