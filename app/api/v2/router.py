from fastapi import APIRouter
from app.api.v2 import (
    auth,
    availability,
    bookings,
    customers,
    work_orders,
    communications,
    email,
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
    estimates,
    payment_plans,
    sms_consent,
    payroll,
    activities,
    tickets,
    equipment,
    inventory,
    notifications,
    calls,
    call_dispositions,
    dump_sites,
    # Phase 1: AI Infrastructure
    ai,
    ai_jobs,
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
    marketing_tasks,
    content_generator,  # World-Class AI Content Generator
    # Phase 8: Schedule Map View
    schedule_map,
    # Phase 9: Employee Portal
    employee_portal,
    # Phase 28: Technician Dashboard
    technician_dashboard,
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
    # Phase 15: Service Intervals
    service_intervals,
    # Phase 16: Analytics
    analytics,
    # WebSocket for real-time updates
    websocket,
    # Phase 17: Operations Command Center
    analytics_operations,
    analytics_financial,
    # Phase 18: Enterprise Features
    enterprise,
    # Phase 19: Integration Marketplace
    marketplace,
    # Phase 20: Embedded Fintech
    financing,
    # Phase 21: IoT Integration
    iot,
    # Phase 22: Onboarding & Help
    onboarding,
    # Phase 23: Payment Processing
    stripe_payments,
    clover_payments,
    # Phase 24: Quick Wins Bundle
    quickbooks,
    push_notifications,
    # Phase 26: Demo Mode Role Switching
    roles,
    # Phase 27: Real-Time GPS Tracking
    gps_tracking,
    # Work Order Photos
    work_order_photos,
    # Local AI (R730 ML Workstation)
    local_ai,
    # National Septic OCR Permit System
    permits,
    # Email Templates
    email_templates,
    # Social Integrations (Yelp, Facebook)
    social_integrations,
)

# Phase 25: Enterprise Customer Success Platform
from app.api.v2.customer_success import (
    health_scores_router,
    segments_router,
    journeys_router,
    playbooks_router,
    tasks_router,
    touchpoints_router,
    dashboard_router as cs_dashboard_router,
    surveys_router,
    campaigns_router,
    escalations_router,
    collaboration_router,
    ai_insights_router,
    ab_tests_router,
)
from app.api.v2.customer_success.escalations_ai import router as escalations_ai_router

# Stub endpoints for missing frontend routes
from app.api.v2.stubs import (
    sms_router as sms_stubs_router,
    templates_router as templates_stubs_router,
    reminders_router as reminders_stubs_router,
    billing_router as billing_stubs_router,
    analytics_stubs_router,
    tracking_router as tracking_stubs_router,
    predictions_stubs_router,
    help_router as help_stubs_router,
    ai_stubs_router,
)

api_router = APIRouter()

# Include all v2 routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(prospects.router, prefix="/prospects", tags=["prospects"])
api_router.include_router(work_orders.router, prefix="/work-orders", tags=["work-orders"])
api_router.include_router(communications.router, prefix="/communications", tags=["communications"])
api_router.include_router(email.router, prefix="/email", tags=["email"])
api_router.include_router(technicians.router, prefix="/technicians", tags=["technicians"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(payments.router, prefix="/payments", tags=["payments"])
api_router.include_router(quotes.router, prefix="/quotes", tags=["quotes"])
api_router.include_router(estimates.router, prefix="/estimates", tags=["estimates"])
api_router.include_router(payment_plans.router, prefix="/payment-plans", tags=["payment-plans"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(schedule.router, prefix="/schedule", tags=["schedule"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
api_router.include_router(ringcentral.router, prefix="/ringcentral", tags=["ringcentral"])
api_router.include_router(twilio.router, prefix="/twilio", tags=["twilio"])
api_router.include_router(sms_consent.router, prefix="/sms-consent", tags=["sms-consent"])
api_router.include_router(payroll.router, prefix="/payroll", tags=["payroll"])
api_router.include_router(dump_sites.router, prefix="/dump-sites", tags=["dump-sites"])
api_router.include_router(activities.router, prefix="/activities", tags=["activities"])
api_router.include_router(tickets.router, prefix="/tickets", tags=["tickets"])
api_router.include_router(equipment.router, prefix="/equipment", tags=["equipment"])
api_router.include_router(inventory.router, prefix="/inventory", tags=["inventory"])
api_router.include_router(notifications.router, prefix="/notifications", tags=["notifications"])
api_router.include_router(calls.router, prefix="/calls", tags=["calls"])
api_router.include_router(call_dispositions.router, prefix="/call-dispositions", tags=["call-dispositions"])

# Phase 1: AI Infrastructure
api_router.include_router(ai.router, prefix="/ai", tags=["ai"])
api_router.include_router(ai_jobs.router, prefix="/ai/jobs", tags=["ai-jobs"])

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
api_router.include_router(marketing_tasks.router, prefix="/marketing-hub", tags=["marketing-tasks"])
api_router.include_router(content_generator.router, prefix="/content-generator", tags=["content-generator"])

# Phase 8: Schedule Map View
api_router.include_router(schedule_map.router, prefix="/schedule-map", tags=["schedule-map"])

# Phase 9: Employee Portal
api_router.include_router(employee_portal.router, prefix="/employee", tags=["employee"])

# Phase 28: Technician Dashboard (aggregated endpoint for field techs)
api_router.include_router(technician_dashboard.router, prefix="/technician-dashboard", tags=["technician-dashboard"])

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

# Phase 15: Service Intervals
api_router.include_router(service_intervals.router, prefix="/service-intervals", tags=["service-intervals"])

# Phase 16: Analytics
api_router.include_router(analytics.router, prefix="/analytics", tags=["analytics"])

# WebSocket for real-time updates
api_router.include_router(websocket.router, tags=["websocket"])

# Phase 17: Operations Command Center
api_router.include_router(analytics_operations.router, prefix="/analytics/operations", tags=["analytics-operations"])
api_router.include_router(analytics_financial.router, prefix="/analytics/financial", tags=["analytics-financial"])

# Phase 18: Enterprise Features
api_router.include_router(enterprise.router, prefix="/enterprise", tags=["enterprise"])

# Phase 19: Integration Marketplace
api_router.include_router(marketplace.router, prefix="/marketplace", tags=["marketplace"])

# Phase 20: Embedded Fintech
api_router.include_router(financing.router, prefix="/financing", tags=["financing"])

# Phase 21: IoT Integration
api_router.include_router(iot.router, prefix="/iot", tags=["iot"])

# Phase 22: Onboarding & Help
api_router.include_router(onboarding.router, prefix="/onboarding", tags=["onboarding"])

# Phase 23: Payment Processing
api_router.include_router(stripe_payments.router, prefix="/payments/stripe", tags=["stripe-payments"])
api_router.include_router(clover_payments.router, prefix="/payments/clover", tags=["clover-payments"])

# Phase 24: Quick Wins Bundle
api_router.include_router(quickbooks.router, prefix="/integrations/quickbooks", tags=["quickbooks"])
api_router.include_router(push_notifications.router, prefix="/notifications/push", tags=["push-notifications"])

# Phase 25: Enterprise Customer Success Platform
api_router.include_router(health_scores_router, prefix="/cs/health-scores", tags=["customer-success"])
api_router.include_router(segments_router, prefix="/cs/segments", tags=["customer-success"])
api_router.include_router(journeys_router, prefix="/cs/journeys", tags=["customer-success"])
api_router.include_router(playbooks_router, prefix="/cs/playbooks", tags=["customer-success"])
api_router.include_router(tasks_router, prefix="/cs/tasks", tags=["customer-success"])
api_router.include_router(touchpoints_router, prefix="/cs/touchpoints", tags=["customer-success"])
api_router.include_router(cs_dashboard_router, prefix="/cs/dashboard", tags=["customer-success"])
api_router.include_router(surveys_router, prefix="/cs/surveys", tags=["customer-success"])
api_router.include_router(campaigns_router, prefix="/cs/campaigns", tags=["customer-success"])
api_router.include_router(escalations_router, prefix="/cs/escalations", tags=["customer-success"])
api_router.include_router(escalations_ai_router, prefix="/cs/escalations", tags=["customer-success-ai"])
api_router.include_router(collaboration_router, prefix="/cs/collaboration", tags=["customer-success"])
api_router.include_router(ai_insights_router, prefix="/cs/ai", tags=["customer-success"])
api_router.include_router(ab_tests_router, prefix="/cs/ab-tests", tags=["customer-success"])

# Phase 26: Demo Mode Role Switching
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])

# Phase 27: Real-Time GPS Tracking
api_router.include_router(gps_tracking.router, tags=["gps-tracking"])

# Work Order Photos (same prefix as work_orders)
api_router.include_router(work_order_photos.router, prefix="/work-orders", tags=["work-order-photos"])

# Local AI (R730 ML Workstation) - Vision, OCR, Transcription
api_router.include_router(local_ai.router, prefix="/local-ai", tags=["local-ai"])

# National Septic OCR Permit System
api_router.include_router(permits.router, prefix="/permits", tags=["permits"])

# Email Templates
api_router.include_router(email_templates.router, prefix="/email-templates", tags=["email-templates"])

# Social Integrations (Yelp, Facebook)
api_router.include_router(social_integrations.router, prefix="/integrations/social", tags=["social-integrations"])

# Public Availability API (Lead Form - No Auth Required)
api_router.include_router(availability.router, prefix="/availability", tags=["availability"])

# Public Bookings API (Book & Pay - Supports Test Mode)
api_router.include_router(bookings.router, prefix="/bookings", tags=["bookings"])

# Stub endpoints: empty responses for routes the frontend calls but aren't implemented yet.
# Each stub returns X-Stub: true header. Replace with real implementations as needed.
api_router.include_router(sms_stubs_router, prefix="/sms", tags=["stubs"])
api_router.include_router(templates_stubs_router, prefix="/templates", tags=["stubs"])
api_router.include_router(reminders_stubs_router, prefix="/reminders", tags=["stubs"])
api_router.include_router(billing_stubs_router, prefix="/billing", tags=["stubs"])
api_router.include_router(analytics_stubs_router, prefix="/analytics", tags=["stubs"])
api_router.include_router(tracking_stubs_router, prefix="/tracking", tags=["stubs"])
api_router.include_router(predictions_stubs_router, prefix="/predictions", tags=["stubs"])
api_router.include_router(help_stubs_router, prefix="/help", tags=["stubs"])
api_router.include_router(ai_stubs_router, prefix="/ai", tags=["stubs"])

# Observability: Prometheus Metrics
from app.api.v2.endpoints.metrics import router as metrics_router

api_router.include_router(metrics_router, prefix="/metrics", tags=["metrics"])
