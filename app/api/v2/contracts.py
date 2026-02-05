"""Contracts API - Service agreements and templates.

Features:
- CRUD for contracts and templates
- Contract generation from templates
- Expiring contracts dashboard
- Contract analytics
"""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional, List
from pydantic import BaseModel, Field
from datetime import datetime, date, timedelta
import logging
import uuid

from app.api.deps import DbSession, CurrentUser
from app.models.contract import Contract
from app.models.contract_template import ContractTemplate

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
    id: str
    contract_number: str
    name: str
    contract_type: str
    customer_id: str
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
    id: str
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
                    "customer_id": c.customer_id,
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
            "customer_id": contract.customer_id,
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
            "customer_id": contract.customer_id,
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
            "customer_id": contract.customer_id,
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
            "customer_id": contract.customer_id,
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
