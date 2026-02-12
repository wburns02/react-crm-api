"""Contracts API - Service agreements and templates.

Features:
- CRUD for contracts and templates
- Contract generation from templates
- Expiring contracts dashboard
- Contract analytics & reports
- Renewal workflows
- Bulk operations
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func, case, and_, or_
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
import logging
import uuid

from app.api.deps import DbSession, CurrentUser
from app.models.contract import Contract
from app.models.contract_template import ContractTemplate
from app.models.customer import Customer
from app.schemas.types import UUIDStr

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================
# Pydantic Schemas
# ========================


# Contract Schemas
class ContractCreate(BaseModel):
    name: str
    contract_type: str
    customer_id: str
    customer_name: Optional[str] = None
    template_id: Optional[str] = None
    start_date: date
    end_date: date
    auto_renew: bool = False
    total_value: Optional[float] = None
    billing_frequency: str = "monthly"
    payment_terms: Optional[str] = None
    services_included: Optional[list] = None
    covered_properties: Optional[list] = None
    coverage_details: Optional[str] = None
    requires_signature: bool = True
    terms_and_conditions: Optional[str] = None
    special_terms: Optional[str] = None
    notes: Optional[str] = None


class ContractUpdate(BaseModel):
    name: Optional[str] = None
    contract_type: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    auto_renew: Optional[bool] = None
    total_value: Optional[float] = None
    billing_frequency: Optional[str] = None
    payment_terms: Optional[str] = None
    services_included: Optional[list] = None
    covered_properties: Optional[list] = None
    coverage_details: Optional[str] = None
    status: Optional[str] = None
    notes: Optional[str] = None
    internal_notes: Optional[str] = None


class ContractResponse(BaseModel):
    id: UUIDStr
    contract_number: str
    name: str
    contract_type: str
    customer_id: UUIDStr
    customer_name: Optional[str] = None
    start_date: date
    end_date: date
    auto_renew: bool
    total_value: Optional[float] = None
    billing_frequency: str
    status: str
    is_active: bool
    days_until_expiry: Optional[int] = None
    customer_signed: bool
    company_signed: bool
    document_url: Optional[str] = None
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# Template Schemas
class TemplateCreate(BaseModel):
    name: str
    code: str
    description: Optional[str] = None
    contract_type: str
    content: str
    terms_and_conditions: Optional[str] = None
    default_duration_months: int = 12
    default_billing_frequency: str = "monthly"
    default_payment_terms: Optional[str] = None
    default_auto_renew: bool = False
    default_services: Optional[list] = None
    base_price: Optional[float] = None
    variables: Optional[list] = None


class TemplateUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    content: Optional[str] = None
    terms_and_conditions: Optional[str] = None
    default_duration_months: Optional[int] = None
    default_billing_frequency: Optional[str] = None
    default_services: Optional[list] = None
    base_price: Optional[float] = None
    is_active: Optional[bool] = None


class TemplateResponse(BaseModel):
    id: UUIDStr
    name: str
    code: str
    description: Optional[str] = None
    contract_type: str
    default_duration_months: int
    default_billing_frequency: str
    base_price: Optional[float] = None
    is_active: bool
    version: int
    created_at: Optional[datetime] = None

    class Config:
        from_attributes = True


# List Response
class ListResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    page_size: int


# Generate from template request
class GenerateContractRequest(BaseModel):
    template_id: str
    customer_id: str
    customer_name: Optional[str] = None
    start_date: date
    total_value: Optional[float] = None
    services_included: Optional[list] = None
    covered_properties: Optional[list] = None
    special_terms: Optional[str] = None


# ========================
# Helper Functions
# ========================


def generate_contract_number():
    """Generate unique contract number."""
    from datetime import datetime

    return f"CTR-{datetime.now().strftime('%Y%m%d')}-{str(uuid.uuid4())[:8].upper()}"


# ========================
# Contract Endpoints
# ========================


@router.get("", response_model=ListResponse)
async def list_contracts(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    customer_id: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    contract_type: Optional[str] = Query(None),
    expiring_within_days: Optional[int] = Query(None),
):
    """List contracts with filtering."""
    try:
        query = select(Contract)

        if customer_id:
            query = query.where(Contract.customer_id == customer_id)
        if status:
            query = query.where(Contract.status == status)
        if contract_type:
            query = query.where(Contract.contract_type == contract_type)
        if expiring_within_days:
            expiry_threshold = date.today() + timedelta(days=expiring_within_days)
            query = query.where(Contract.end_date <= expiry_threshold, Contract.status == "active")

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(Contract.end_date)

        result = await db.execute(query)
        contracts = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(c.id),
                    "contract_number": c.contract_number,
                    "name": c.name,
                    "contract_type": c.contract_type,
                    "customer_id": str(c.customer_id) if c.customer_id else None,
                    "customer_name": c.customer_name,
                    "start_date": c.start_date,
                    "end_date": c.end_date,
                    "status": c.status,
                    "total_value": c.total_value,
                    "days_until_expiry": c.days_until_expiry,
                }
                for c in contracts
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing contracts: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("", response_model=ContractResponse, status_code=status.HTTP_201_CREATED)
async def create_contract(
    contract_data: ContractCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new contract."""
    try:
        data = contract_data.model_dump()
        if data.get("template_id"):
            data["template_id"] = uuid.UUID(data["template_id"])

        contract = Contract(contract_number=generate_contract_number(), created_by=current_user.email, **data)
        db.add(contract)
        await db.commit()
        await db.refresh(contract)

        return {
            "id": str(contract.id),
            "contract_number": contract.contract_number,
            "name": contract.name,
            "contract_type": contract.contract_type,
            "customer_id": str(contract.customer_id) if contract.customer_id else None,
            "customer_name": contract.customer_name,
            "start_date": contract.start_date,
            "end_date": contract.end_date,
            "auto_renew": contract.auto_renew,
            "total_value": contract.total_value,
            "billing_frequency": contract.billing_frequency,
            "status": contract.status,
            "is_active": contract.is_active,
            "days_until_expiry": contract.days_until_expiry,
            "customer_signed": contract.customer_signed,
            "company_signed": contract.company_signed,
            "document_url": contract.document_url,
            "created_at": contract.created_at,
        }
    except Exception as e:
        logger.error(f"Error creating contract: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{contract_id}", response_model=ContractResponse)
async def get_contract(
    contract_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific contract."""
    try:
        result = await db.execute(select(Contract).where(Contract.id == uuid.UUID(contract_id)))
        contract = result.scalar_one_or_none()

        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        return {
            "id": str(contract.id),
            "contract_number": contract.contract_number,
            "name": contract.name,
            "contract_type": contract.contract_type,
            "customer_id": str(contract.customer_id) if contract.customer_id else None,
            "customer_name": contract.customer_name,
            "start_date": contract.start_date,
            "end_date": contract.end_date,
            "auto_renew": contract.auto_renew,
            "total_value": contract.total_value,
            "billing_frequency": contract.billing_frequency,
            "status": contract.status,
            "is_active": contract.is_active,
            "days_until_expiry": contract.days_until_expiry,
            "customer_signed": contract.customer_signed,
            "company_signed": contract.company_signed,
            "document_url": contract.document_url,
            "created_at": contract.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting contract {contract_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/{contract_id}", response_model=ContractResponse)
async def update_contract(
    contract_id: str,
    update_data: ContractUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a contract."""
    try:
        result = await db.execute(select(Contract).where(Contract.id == uuid.UUID(contract_id)))
        contract = result.scalar_one_or_none()

        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(contract, key, value)

        await db.commit()
        await db.refresh(contract)

        return {
            "id": str(contract.id),
            "contract_number": contract.contract_number,
            "name": contract.name,
            "contract_type": contract.contract_type,
            "customer_id": str(contract.customer_id) if contract.customer_id else None,
            "customer_name": contract.customer_name,
            "start_date": contract.start_date,
            "end_date": contract.end_date,
            "auto_renew": contract.auto_renew,
            "total_value": contract.total_value,
            "billing_frequency": contract.billing_frequency,
            "status": contract.status,
            "is_active": contract.is_active,
            "days_until_expiry": contract.days_until_expiry,
            "customer_signed": contract.customer_signed,
            "company_signed": contract.company_signed,
            "document_url": contract.document_url,
            "created_at": contract.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating contract {contract_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/{contract_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contract(
    contract_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a contract."""
    try:
        result = await db.execute(select(Contract).where(Contract.id == uuid.UUID(contract_id)))
        contract = result.scalar_one_or_none()

        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        await db.delete(contract)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting contract {contract_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{contract_id}/activate")
async def activate_contract(
    contract_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Activate a contract."""
    try:
        result = await db.execute(select(Contract).where(Contract.id == uuid.UUID(contract_id)))
        contract = result.scalar_one_or_none()

        if not contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        if contract.requires_signature and not contract.is_fully_signed:
            raise HTTPException(status_code=400, detail="Contract requires signature before activation")

        contract.status = "active"
        await db.commit()

        return {"status": "success", "message": "Contract activated"}
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error activating contract {contract_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Template Endpoints
# ========================


@router.get("/templates/list", response_model=ListResponse)
async def list_templates(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    contract_type: Optional[str] = Query(None),
    active_only: bool = Query(True),
):
    """List contract templates."""
    try:
        query = select(ContractTemplate)

        if contract_type:
            query = query.where(ContractTemplate.contract_type == contract_type)
        if active_only:
            query = query.where(ContractTemplate.is_active == True)

        # Count
        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Paginate
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(ContractTemplate.name)

        result = await db.execute(query)
        templates = result.scalars().all()

        return {
            "items": [
                {
                    "id": str(t.id),
                    "name": t.name,
                    "code": t.code,
                    "contract_type": t.contract_type,
                    "description": t.description,
                    "default_duration_months": t.default_duration_months,
                    "base_price": t.base_price,
                    "is_active": t.is_active,
                }
                for t in templates
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        logger.error(f"Error listing templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/templates", response_model=TemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_template(
    template_data: TemplateCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new contract template."""
    try:
        template = ContractTemplate(created_by=current_user.email, **template_data.model_dump())
        db.add(template)
        await db.commit()
        await db.refresh(template)

        return {
            "id": str(template.id),
            "name": template.name,
            "code": template.code,
            "description": template.description,
            "contract_type": template.contract_type,
            "default_duration_months": template.default_duration_months,
            "default_billing_frequency": template.default_billing_frequency,
            "base_price": template.base_price,
            "is_active": template.is_active,
            "version": template.version,
            "created_at": template.created_at,
        }
    except Exception as e:
        logger.error(f"Error creating template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/templates/{template_id}", response_model=TemplateResponse)
async def get_template(
    template_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a specific template."""
    try:
        result = await db.execute(select(ContractTemplate).where(ContractTemplate.id == uuid.UUID(template_id)))
        template = result.scalar_one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        return {
            "id": str(template.id),
            "name": template.name,
            "code": template.code,
            "description": template.description,
            "contract_type": template.contract_type,
            "default_duration_months": template.default_duration_months,
            "default_billing_frequency": template.default_billing_frequency,
            "base_price": template.base_price,
            "is_active": template.is_active,
            "version": template.version,
            "created_at": template.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/templates/{template_id}", response_model=TemplateResponse)
async def update_template(
    template_id: str,
    update_data: TemplateUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a template."""
    try:
        result = await db.execute(select(ContractTemplate).where(ContractTemplate.id == uuid.UUID(template_id)))
        template = result.scalar_one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        update_dict = update_data.model_dump(exclude_unset=True)
        for key, value in update_dict.items():
            setattr(template, key, value)

        # Increment version on content update
        if "content" in update_dict:
            template.version += 1

        await db.commit()
        await db.refresh(template)

        return {
            "id": str(template.id),
            "name": template.name,
            "code": template.code,
            "description": template.description,
            "contract_type": template.contract_type,
            "default_duration_months": template.default_duration_months,
            "default_billing_frequency": template.default_billing_frequency,
            "base_price": template.base_price,
            "is_active": template.is_active,
            "version": template.version,
            "created_at": template.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error updating template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(
    template_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete a template."""
    try:
        result = await db.execute(select(ContractTemplate).where(ContractTemplate.id == uuid.UUID(template_id)))
        template = result.scalar_one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        await db.delete(template)
        await db.commit()
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting template {template_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/generate-from-template", response_model=ContractResponse)
async def generate_contract_from_template(
    request: GenerateContractRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Generate a new contract from a template."""
    try:
        # Get template
        result = await db.execute(select(ContractTemplate).where(ContractTemplate.id == uuid.UUID(request.template_id)))
        template = result.scalar_one_or_none()

        if not template:
            raise HTTPException(status_code=404, detail="Template not found")

        # Calculate end date
        end_date = request.start_date + timedelta(days=template.default_duration_months * 30)

        # Create contract from template
        contract = Contract(
            contract_number=generate_contract_number(),
            name=f"{template.name} - {request.customer_name or request.customer_id}",
            contract_type=template.contract_type,
            customer_id=request.customer_id,
            customer_name=request.customer_name,
            template_id=template.id,
            start_date=request.start_date,
            end_date=end_date,
            auto_renew=template.default_auto_renew,
            total_value=request.total_value or template.base_price,
            billing_frequency=template.default_billing_frequency,
            payment_terms=template.default_payment_terms,
            services_included=request.services_included or template.default_services,
            covered_properties=request.covered_properties,
            terms_and_conditions=template.terms_and_conditions,
            special_terms=request.special_terms,
            created_by=current_user.email,
        )

        db.add(contract)
        await db.commit()
        await db.refresh(contract)

        return {
            "id": str(contract.id),
            "contract_number": contract.contract_number,
            "name": contract.name,
            "contract_type": contract.contract_type,
            "customer_id": str(contract.customer_id) if contract.customer_id else None,
            "customer_name": contract.customer_name,
            "start_date": contract.start_date,
            "end_date": contract.end_date,
            "auto_renew": contract.auto_renew,
            "total_value": contract.total_value,
            "billing_frequency": contract.billing_frequency,
            "status": contract.status,
            "is_active": contract.is_active,
            "days_until_expiry": contract.days_until_expiry,
            "customer_signed": contract.customer_signed,
            "company_signed": contract.company_signed,
            "document_url": contract.document_url,
            "created_at": contract.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error generating contract from template: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Dashboard Endpoint
# ========================


@router.get("/dashboard/summary")
async def get_contracts_summary(
    db: DbSession,
    current_user: CurrentUser,
    expiring_within_days: int = Query(30),
):
    """Get contracts dashboard summary."""
    try:
        today = date.today()
        expiry_threshold = today + timedelta(days=expiring_within_days)

        # Counts
        total_contracts = (await db.execute(select(func.count(Contract.id)))).scalar() or 0
        active_contracts = (
            await db.execute(select(func.count(Contract.id)).where(Contract.status == "active"))
        ).scalar() or 0

        # Expiring soon
        expiring_result = await db.execute(
            select(Contract)
            .where(Contract.end_date <= expiry_threshold, Contract.status == "active")
            .order_by(Contract.end_date)
            .limit(10)
        )
        expiring_contracts = [
            {
                "id": str(c.id),
                "contract_number": c.contract_number,
                "customer_name": c.customer_name,
                "end_date": c.end_date,
                "days_until_expiry": c.days_until_expiry,
                "auto_renew": c.auto_renew,
            }
            for c in expiring_result.scalars().all()
        ]

        # Pending signature
        pending_signature = (
            await db.execute(
                select(func.count(Contract.id)).where(
                    Contract.requires_signature == True,
                    Contract.customer_signed == False,
                    Contract.status.in_(["draft", "pending"]),
                )
            )
        ).scalar() or 0

        # Total contract value
        total_value_result = await db.execute(select(func.sum(Contract.total_value)).where(Contract.status == "active"))
        total_active_value = total_value_result.scalar() or 0

        return {
            "summary": {
                "total_contracts": total_contracts,
                "active_contracts": active_contracts,
                "pending_signature": pending_signature,
                "total_active_value": total_active_value,
                "expiring_count": len(expiring_contracts),
            },
            "expiring_contracts": expiring_contracts,
        }
    except Exception as e:
        logger.error(f"Error getting contracts summary: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Reports Endpoint
# ========================


@router.get("/reports/stats")
async def get_contract_reports(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get contract reports with stats for revenue, churn, and averages by type."""
    try:
        today = date.today()
        one_year_ago = today - timedelta(days=365)

        # Total recurring revenue (active contracts annualized)
        total_revenue_result = await db.execute(
            select(func.sum(Contract.total_value)).where(Contract.status == "active")
        )
        total_recurring_revenue = float(total_revenue_result.scalar() or 0)

        # Count by status
        status_counts_result = await db.execute(
            select(Contract.status, func.count(Contract.id)).group_by(Contract.status)
        )
        status_counts = {row[0]: row[1] for row in status_counts_result.all()}

        # Churn rate: cancelled in last year / (active + cancelled in last year)
        cancelled_last_year = (await db.execute(
            select(func.count(Contract.id)).where(
                Contract.status == "cancelled",
                Contract.updated_at >= one_year_ago,
            )
        )).scalar() or 0

        active_count = status_counts.get("active", 0)
        total_for_churn = active_count + cancelled_last_year
        churn_rate = round((cancelled_last_year / total_for_churn * 100), 1) if total_for_churn > 0 else 0

        # Average value by contract type
        avg_by_type_result = await db.execute(
            select(
                Contract.contract_type,
                func.avg(Contract.total_value),
                func.count(Contract.id),
                func.sum(Contract.total_value),
            ).where(Contract.status == "active").group_by(Contract.contract_type)
        )
        avg_by_type = [
            {
                "contract_type": row[0],
                "avg_value": round(float(row[1] or 0), 2),
                "count": row[2],
                "total_value": round(float(row[3] or 0), 2),
            }
            for row in avg_by_type_result.all()
        ]

        # Contracts by month (last 12 months)
        monthly_result = await db.execute(
            select(
                func.date_trunc("month", Contract.created_at).label("month"),
                func.count(Contract.id),
                func.sum(Contract.total_value),
            ).where(Contract.created_at >= one_year_ago)
            .group_by("month")
            .order_by("month")
        )
        monthly_data = [
            {
                "month": row[0].isoformat() if row[0] else None,
                "count": row[1],
                "total_value": round(float(row[2] or 0), 2),
            }
            for row in monthly_result.all()
        ]

        # Renewal rate
        renewed_count = status_counts.get("renewed", 0)
        expired_count = status_counts.get("expired", 0)
        renewal_eligible = renewed_count + expired_count
        renewal_rate = round((renewed_count / renewal_eligible * 100), 1) if renewal_eligible > 0 else 0

        # Expiring within 30/60/90 days
        expiring_30 = (await db.execute(
            select(func.count(Contract.id)).where(
                Contract.status == "active",
                Contract.end_date <= today + timedelta(days=30),
                Contract.end_date >= today,
            )
        )).scalar() or 0

        expiring_60 = (await db.execute(
            select(func.count(Contract.id)).where(
                Contract.status == "active",
                Contract.end_date <= today + timedelta(days=60),
                Contract.end_date >= today,
            )
        )).scalar() or 0

        expiring_90 = (await db.execute(
            select(func.count(Contract.id)).where(
                Contract.status == "active",
                Contract.end_date <= today + timedelta(days=90),
                Contract.end_date >= today,
            )
        )).scalar() or 0

        # Overdue (expired but still active status — should have been renewed)
        overdue_count = (await db.execute(
            select(func.count(Contract.id)).where(
                Contract.status == "active",
                Contract.end_date < today,
            )
        )).scalar() or 0

        return {
            "total_recurring_revenue": total_recurring_revenue,
            "churn_rate": churn_rate,
            "renewal_rate": renewal_rate,
            "status_counts": status_counts,
            "avg_by_type": avg_by_type,
            "monthly_data": monthly_data,
            "expiring_30": expiring_30,
            "expiring_60": expiring_60,
            "expiring_90": expiring_90,
            "overdue_count": overdue_count,
        }
    except Exception as e:
        logger.error(f"Error getting contract reports: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Renew Endpoint
# ========================


class RenewContractRequest(BaseModel):
    new_end_date: Optional[date] = None
    new_total_value: Optional[float] = None
    notes: Optional[str] = None


@router.post("/{contract_id}/renew", response_model=ContractResponse)
async def renew_contract(
    contract_id: str,
    renew_data: RenewContractRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Renew a contract — creates a new contract and marks the old one as renewed."""
    try:
        result = await db.execute(select(Contract).where(Contract.id == uuid.UUID(contract_id)))
        old_contract = result.scalar_one_or_none()

        if not old_contract:
            raise HTTPException(status_code=404, detail="Contract not found")

        if old_contract.status not in ("active", "expired"):
            raise HTTPException(status_code=400, detail="Only active or expired contracts can be renewed")

        # Calculate new dates
        old_duration = (old_contract.end_date - old_contract.start_date).days
        new_start = old_contract.end_date + timedelta(days=1)
        new_end = renew_data.new_end_date or (new_start + timedelta(days=old_duration))

        # Create renewed contract
        new_contract = Contract(
            contract_number=generate_contract_number(),
            name=old_contract.name,
            contract_type=old_contract.contract_type,
            customer_id=old_contract.customer_id,
            customer_name=old_contract.customer_name,
            template_id=old_contract.template_id,
            start_date=new_start,
            end_date=new_end,
            auto_renew=old_contract.auto_renew,
            total_value=renew_data.new_total_value or old_contract.total_value,
            billing_frequency=old_contract.billing_frequency,
            payment_terms=old_contract.payment_terms,
            services_included=old_contract.services_included,
            covered_properties=old_contract.covered_properties,
            coverage_details=old_contract.coverage_details,
            terms_and_conditions=old_contract.terms_and_conditions,
            special_terms=old_contract.special_terms,
            notes=renew_data.notes or f"Renewed from {old_contract.contract_number}",
            status="active",
            created_by=current_user.email,
        )

        # Mark old contract as renewed
        old_contract.status = "renewed"
        old_contract.internal_notes = (old_contract.internal_notes or "") + f"\nRenewed on {date.today()} by {current_user.email}"

        db.add(new_contract)
        await db.commit()
        await db.refresh(new_contract)

        return {
            "id": str(new_contract.id),
            "contract_number": new_contract.contract_number,
            "name": new_contract.name,
            "contract_type": new_contract.contract_type,
            "customer_id": str(new_contract.customer_id) if new_contract.customer_id else None,
            "customer_name": new_contract.customer_name,
            "start_date": new_contract.start_date,
            "end_date": new_contract.end_date,
            "auto_renew": new_contract.auto_renew,
            "total_value": new_contract.total_value,
            "billing_frequency": new_contract.billing_frequency,
            "status": new_contract.status,
            "is_active": new_contract.is_active,
            "days_until_expiry": new_contract.days_until_expiry,
            "customer_signed": new_contract.customer_signed,
            "company_signed": new_contract.company_signed,
            "document_url": new_contract.document_url,
            "created_at": new_contract.created_at,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error renewing contract {contract_id}: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Bulk Action Endpoint
# ========================


class BulkActionRequest(BaseModel):
    contract_ids: List[str]
    action: str  # "activate", "cancel", "renew"


@router.post("/bulk-action")
async def bulk_contract_action(
    request: BulkActionRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Perform bulk actions on contracts."""
    try:
        if request.action not in ("activate", "cancel", "renew"):
            raise HTTPException(status_code=400, detail="Invalid action. Must be: activate, cancel, renew")

        results = {"success": [], "failed": []}

        for cid in request.contract_ids:
            try:
                result = await db.execute(select(Contract).where(Contract.id == uuid.UUID(cid)))
                contract = result.scalar_one_or_none()
                if not contract:
                    results["failed"].append({"id": cid, "error": "Not found"})
                    continue

                if request.action == "activate":
                    if contract.status in ("draft", "pending"):
                        contract.status = "active"
                        results["success"].append(cid)
                    else:
                        results["failed"].append({"id": cid, "error": f"Cannot activate from {contract.status}"})

                elif request.action == "cancel":
                    if contract.status in ("draft", "pending", "active"):
                        contract.status = "cancelled"
                        results["success"].append(cid)
                    else:
                        results["failed"].append({"id": cid, "error": f"Cannot cancel from {contract.status}"})

                elif request.action == "renew":
                    if contract.status in ("active", "expired"):
                        old_duration = (contract.end_date - contract.start_date).days
                        new_start = contract.end_date + timedelta(days=1)
                        new_end = new_start + timedelta(days=old_duration)

                        new_contract = Contract(
                            contract_number=generate_contract_number(),
                            name=contract.name,
                            contract_type=contract.contract_type,
                            customer_id=contract.customer_id,
                            customer_name=contract.customer_name,
                            template_id=contract.template_id,
                            start_date=new_start,
                            end_date=new_end,
                            auto_renew=contract.auto_renew,
                            total_value=contract.total_value,
                            billing_frequency=contract.billing_frequency,
                            payment_terms=contract.payment_terms,
                            services_included=contract.services_included,
                            covered_properties=contract.covered_properties,
                            coverage_details=contract.coverage_details,
                            terms_and_conditions=contract.terms_and_conditions,
                            special_terms=contract.special_terms,
                            notes=f"Bulk renewed from {contract.contract_number}",
                            status="active",
                            created_by=current_user.email,
                        )
                        contract.status = "renewed"
                        db.add(new_contract)
                        results["success"].append(cid)
                    else:
                        results["failed"].append({"id": cid, "error": f"Cannot renew from {contract.status}"})

            except Exception as inner_e:
                results["failed"].append({"id": cid, "error": str(inner_e)})

        await db.commit()

        return {
            "action": request.action,
            "total": len(request.contract_ids),
            "success_count": len(results["success"]),
            "failed_count": len(results["failed"]),
            "results": results,
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error performing bulk action: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Seed MAC Septic Templates
# ========================


MAC_SEPTIC_TEMPLATES = [
    {
        "name": "Initial 2-Year Evergreen",
        "code": "INIT_2YR_EVERGREEN",
        "description": "Initial 2-year evergreen maintenance contract for new customers. Includes comprehensive septic system inspection, pumping, and preventive maintenance.",
        "contract_type": "multi-year",
        "content": "Initial 2-Year Evergreen Maintenance Agreement between MAC Septic Services and the Customer.",
        "terms_and_conditions": "This agreement automatically renews for successive 1-year periods unless cancelled with 30 days written notice.",
        "default_duration_months": 24,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "default_services": [
            {"service_code": "PUMP", "description": "Septic Tank Pumping", "frequency": "annual", "quantity": 1},
            {"service_code": "INSPECT", "description": "Full System Inspection", "frequency": "annual", "quantity": 1},
            {"service_code": "MAINT", "description": "Preventive Maintenance", "frequency": "annual", "quantity": 1},
        ],
        "base_price": 575.00,
        "variables": ["customer_name", "service_address", "tank_size", "system_type"],
    },
    {
        "name": "Typical Yearly Maintenance",
        "code": "YEARLY_MAINT",
        "description": "Standard annual maintenance contract. One service visit per year including pumping and inspection.",
        "contract_type": "annual",
        "content": "Annual Maintenance Agreement between MAC Septic Services and the Customer.",
        "terms_and_conditions": "This agreement covers one calendar year and must be manually renewed.",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": False,
        "default_services": [
            {"service_code": "PUMP", "description": "Septic Tank Pumping", "frequency": "annual", "quantity": 1},
            {"service_code": "INSPECT", "description": "System Inspection", "frequency": "annual", "quantity": 1},
        ],
        "base_price": 350.00,
        "variables": ["customer_name", "service_address", "tank_size"],
    },
    {
        "name": "Evergreen Maintenance",
        "code": "EVERGREEN_MAINT",
        "description": "Evergreen maintenance contract with automatic renewal. Budget-friendly option for ongoing system care.",
        "contract_type": "maintenance",
        "content": "Evergreen Maintenance Agreement between MAC Septic Services and the Customer.",
        "terms_and_conditions": "This agreement automatically renews annually unless cancelled with 30 days written notice.",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "default_services": [
            {"service_code": "MAINT", "description": "Preventive Maintenance Visit", "frequency": "annual", "quantity": 1},
            {"service_code": "INSPECT", "description": "Basic Inspection", "frequency": "annual", "quantity": 1},
        ],
        "base_price": 300.00,
        "variables": ["customer_name", "service_address"],
    },
    {
        "name": "Evergreen Service - 1 Visit",
        "code": "EVERGREEN_SVC_1",
        "description": "Evergreen service contract with 1 annual visit. Ideal for low-usage residential systems.",
        "contract_type": "service",
        "content": "Evergreen Service Visit Agreement (1 Visit/Year) between MAC Septic Services and the Customer.",
        "terms_and_conditions": "Includes 1 scheduled service visit per year. Auto-renews annually.",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "default_services": [
            {"service_code": "SVC_VISIT", "description": "Scheduled Service Visit", "frequency": "annual", "quantity": 1},
        ],
        "base_price": 175.00,
        "variables": ["customer_name", "service_address"],
    },
    {
        "name": "Evergreen Service - 2 Visits",
        "code": "EVERGREEN_SVC_2",
        "description": "Evergreen service contract with 2 annual visits. Recommended for standard residential systems.",
        "contract_type": "service",
        "content": "Evergreen Service Visit Agreement (2 Visits/Year) between MAC Septic Services and the Customer.",
        "terms_and_conditions": "Includes 2 scheduled service visits per year. Auto-renews annually.",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "default_services": [
            {"service_code": "SVC_VISIT", "description": "Scheduled Service Visit", "frequency": "semi-annual", "quantity": 2},
        ],
        "base_price": 295.00,
        "variables": ["customer_name", "service_address"],
    },
    {
        "name": "Evergreen Service - 3 Visits",
        "code": "EVERGREEN_SVC_3",
        "description": "Evergreen service contract with 3 annual visits. Best for commercial or high-usage systems.",
        "contract_type": "service",
        "content": "Evergreen Service Visit Agreement (3 Visits/Year) between MAC Septic Services and the Customer.",
        "terms_and_conditions": "Includes 3 scheduled service visits per year. Auto-renews annually.",
        "default_duration_months": 12,
        "default_billing_frequency": "annual",
        "default_payment_terms": "due-on-receipt",
        "default_auto_renew": True,
        "default_services": [
            {"service_code": "SVC_VISIT", "description": "Scheduled Service Visit", "frequency": "quarterly", "quantity": 3},
        ],
        "base_price": 325.00,
        "variables": ["customer_name", "service_address"],
    },
]


@router.post("/seed-templates")
async def seed_mac_septic_templates(
    db: DbSession,
    current_user: CurrentUser,
):
    """Seed MAC Septic contract templates. Skips templates that already exist by code."""
    try:
        created = []
        skipped = []

        for tmpl_data in MAC_SEPTIC_TEMPLATES:
            # Check if template already exists
            existing = await db.execute(
                select(ContractTemplate).where(ContractTemplate.code == tmpl_data["code"])
            )
            if existing.scalar_one_or_none():
                skipped.append(tmpl_data["code"])
                continue

            template = ContractTemplate(
                created_by=current_user.email,
                **tmpl_data,
            )
            db.add(template)
            created.append(tmpl_data["code"])

        await db.commit()
        return {
            "created": created,
            "skipped": skipped,
            "total_created": len(created),
            "total_skipped": len(skipped),
        }
    except Exception as e:
        logger.error(f"Error seeding templates: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ========================
# Renewals Dashboard
# ========================


@router.get("/renewals/dashboard")
async def get_renewals_dashboard(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get comprehensive renewals dashboard with 30/60/90 day windows and overdue contracts."""
    try:
        today = date.today()

        # Expiring in each window (cumulative)
        windows = {}
        for days in [30, 60, 90]:
            threshold = today + timedelta(days=days)
            result = await db.execute(
                select(Contract)
                .where(
                    Contract.status == "active",
                    Contract.end_date >= today,
                    Contract.end_date <= threshold,
                )
                .order_by(Contract.end_date)
            )
            windows[f"expiring_{days}"] = [
                {
                    "id": str(c.id),
                    "contract_number": c.contract_number,
                    "name": c.name,
                    "customer_name": c.customer_name,
                    "customer_id": str(c.customer_id),
                    "contract_type": c.contract_type,
                    "end_date": c.end_date.isoformat(),
                    "days_until_expiry": c.days_until_expiry,
                    "auto_renew": c.auto_renew,
                    "total_value": c.total_value,
                }
                for c in result.scalars().all()
            ]

        # Overdue — active contracts past end date
        overdue_result = await db.execute(
            select(Contract)
            .where(
                Contract.status == "active",
                Contract.end_date < today,
            )
            .order_by(Contract.end_date)
        )
        overdue = [
            {
                "id": str(c.id),
                "contract_number": c.contract_number,
                "name": c.name,
                "customer_name": c.customer_name,
                "customer_id": str(c.customer_id),
                "contract_type": c.contract_type,
                "end_date": c.end_date.isoformat(),
                "days_overdue": (today - c.end_date).days,
                "auto_renew": c.auto_renew,
                "total_value": c.total_value,
            }
            for c in overdue_result.scalars().all()
        ]

        # Auto-renew queue (contracts marked auto_renew that are expiring in 60 days)
        auto_renew_result = await db.execute(
            select(Contract)
            .where(
                Contract.status == "active",
                Contract.auto_renew == True,
                Contract.end_date >= today,
                Contract.end_date <= today + timedelta(days=60),
            )
            .order_by(Contract.end_date)
        )
        auto_renew_queue = [
            {
                "id": str(c.id),
                "contract_number": c.contract_number,
                "name": c.name,
                "customer_name": c.customer_name,
                "end_date": c.end_date.isoformat(),
                "days_until_expiry": c.days_until_expiry,
                "total_value": c.total_value,
            }
            for c in auto_renew_result.scalars().all()
        ]

        return {
            **windows,
            "overdue": overdue,
            "auto_renew_queue": auto_renew_queue,
            "counts": {
                "expiring_30": len(windows["expiring_30"]),
                "expiring_60": len(windows["expiring_60"]),
                "expiring_90": len(windows["expiring_90"]),
                "overdue": len(overdue),
                "auto_renew": len(auto_renew_queue),
            },
        }
    except Exception as e:
        logger.error(f"Error getting renewals dashboard: {e}")
        raise HTTPException(status_code=500, detail=str(e))
