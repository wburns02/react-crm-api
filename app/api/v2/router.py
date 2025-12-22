from fastapi import APIRouter
from app.api.v2 import auth, customers, work_orders, communications

api_router = APIRouter()

# Include all v2 routers
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(customers.router, prefix="/customers", tags=["customers"])
api_router.include_router(work_orders.router, prefix="/work-orders", tags=["work-orders"])
api_router.include_router(communications.router, prefix="/communications", tags=["communications"])
