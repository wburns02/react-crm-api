from fastapi import APIRouter
from app.api.v2 import auth, customers, work_orders, communications, technicians, invoices, dashboard, schedule, reports

api_router = APIRouter()

# Include all v2 routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(work_orders.router, prefix="/work-orders", tags=["work-orders"])
api_router.include_router(communications.router, prefix="/communications", tags=["communications"])
api_router.include_router(technicians.router, prefix="/technicians", tags=["technicians"])
api_router.include_router(invoices.router, prefix="/invoices", tags=["invoices"])
api_router.include_router(dashboard.router, prefix="/dashboard", tags=["dashboard"])
api_router.include_router(schedule.router, prefix="/schedule", tags=["schedule"])
api_router.include_router(reports.router, prefix="/reports", tags=["reports"])
