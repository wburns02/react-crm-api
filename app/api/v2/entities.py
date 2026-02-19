"""Company Entity CRUD endpoints for multi-LLC support."""

import uuid
import logging
from fastapi import APIRouter, HTTPException
from sqlalchemy import select
from app.api.deps import DbSession, CurrentUser, EntityCtx
from app.models.company_entity import CompanyEntity
from app.schemas.company_entity import (
    CompanyEntityCreate,
    CompanyEntityUpdate,
    CompanyEntityResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


@router.get("/", response_model=list[CompanyEntityResponse])
async def list_entities(db: DbSession, current_user: CurrentUser):
    """List all active company entities."""
    result = await db.execute(
        select(CompanyEntity)
        .where(CompanyEntity.is_active == True)
        .order_by(CompanyEntity.is_default.desc(), CompanyEntity.name)
    )
    entities = result.scalars().all()
    return [CompanyEntityResponse.from_orm_entity(e) for e in entities]


@router.get("/current", response_model=CompanyEntityResponse)
async def get_current_entity(entity: EntityCtx):
    """Get the currently selected entity (from X-Entity-ID header or default)."""
    if not entity:
        raise HTTPException(status_code=404, detail="No entity configured")
    return CompanyEntityResponse.from_orm_entity(entity)


@router.get("/{entity_id}", response_model=CompanyEntityResponse)
async def get_entity(entity_id: str, db: DbSession, current_user: CurrentUser):
    """Get a specific entity by ID."""
    result = await db.execute(
        select(CompanyEntity).where(CompanyEntity.id == entity_id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")
    return CompanyEntityResponse.from_orm_entity(entity)


@router.post("/", response_model=CompanyEntityResponse, status_code=201)
async def create_entity(
    body: CompanyEntityCreate, db: DbSession, current_user: CurrentUser
):
    """Create a new company entity (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    entity = CompanyEntity(
        id=uuid.uuid4(),
        name=body.name,
        short_code=body.short_code,
        tax_id=body.tax_id,
        address_line1=body.address_line1,
        address_line2=body.address_line2,
        city=body.city,
        state=body.state,
        postal_code=body.postal_code,
        phone=body.phone,
        email=body.email,
        logo_url=body.logo_url,
        invoice_prefix=body.invoice_prefix or body.short_code,
        is_active=True,
        is_default=False,
    )
    db.add(entity)
    await db.commit()
    await db.refresh(entity)
    logger.info(f"Created entity: {entity.short_code} ({entity.name})")
    return CompanyEntityResponse.from_orm_entity(entity)


@router.patch("/{entity_id}", response_model=CompanyEntityResponse)
async def update_entity(
    entity_id: str,
    body: CompanyEntityUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update a company entity (admin only)."""
    if not current_user.is_admin:
        raise HTTPException(status_code=403, detail="Admin access required")

    result = await db.execute(
        select(CompanyEntity).where(CompanyEntity.id == entity_id)
    )
    entity = result.scalar_one_or_none()
    if not entity:
        raise HTTPException(status_code=404, detail="Entity not found")

    update_data = body.model_dump(exclude_unset=True)
    for key, value in update_data.items():
        setattr(entity, key, value)

    await db.commit()
    await db.refresh(entity)
    logger.info(f"Updated entity: {entity.short_code}")
    return CompanyEntityResponse.from_orm_entity(entity)
