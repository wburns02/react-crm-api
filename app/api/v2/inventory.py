"""Inventory API - Parts, materials, and supplies management."""

from fastapi import APIRouter, HTTPException, status, Query
from sqlalchemy import select, func
from typing import Optional
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.inventory import InventoryItem
from app.models.inventory_transaction import InventoryTransaction
from app.schemas.inventory import (
    InventoryItemCreate,
    InventoryItemUpdate,
    InventoryItemResponse,
    InventoryListResponse,
    InventoryAdjustment,
)

logger = logging.getLogger(__name__)
router = APIRouter()


def inventory_to_response(item: InventoryItem) -> dict:
    """Convert InventoryItem model to response dict."""
    quantity_on_hand = item.quantity_on_hand or 0
    quantity_reserved = item.quantity_reserved or 0
    reorder_level = item.reorder_level or 0

    return {
        "id": str(item.id),
        "sku": item.sku,
        "name": item.name,
        "description": item.description,
        "category": item.category,
        "unit_price": item.unit_price,
        "cost_price": item.cost_price,
        "markup_percent": item.markup_percent,
        "quantity_on_hand": quantity_on_hand,
        "quantity_reserved": quantity_reserved,
        "quantity_available": quantity_on_hand - quantity_reserved,
        "reorder_level": reorder_level,
        "reorder_quantity": item.reorder_quantity,
        "needs_reorder": quantity_on_hand <= reorder_level,
        "unit": item.unit or "each",
        "supplier_name": item.supplier_name,
        "supplier_sku": item.supplier_sku,
        "supplier_phone": item.supplier_phone,
        "warehouse_location": item.warehouse_location,
        "vehicle_id": item.vehicle_id,
        "is_active": item.is_active if item.is_active is not None else True,
        "is_taxable": item.is_taxable if item.is_taxable is not None else True,
        "notes": item.notes,
        "created_at": item.created_at.isoformat() if item.created_at else None,
        "updated_at": item.updated_at.isoformat() if item.updated_at else None,
    }


@router.get("")
async def list_inventory(
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    category: Optional[str] = None,
    is_active: Optional[bool] = None,
    needs_reorder: Optional[bool] = None,
    search: Optional[str] = None,  # Search by SKU or name
    vehicle_id: Optional[str] = None,
):
    """List inventory items with pagination and filtering."""
    try:
        # Base query
        query = select(InventoryItem)

        # Apply filters
        if category:
            query = query.where(InventoryItem.category == category)

        if is_active is not None:
            query = query.where(InventoryItem.is_active == is_active)

        if vehicle_id:
            query = query.where(InventoryItem.vehicle_id == vehicle_id)

        if search:
            search_pattern = f"%{search}%"
            query = query.where((InventoryItem.sku.ilike(search_pattern)) | (InventoryItem.name.ilike(search_pattern)))

        # Get total count before reorder filter (need to apply it post-query for proper counting)
        if needs_reorder:
            query = query.where(InventoryItem.quantity_on_hand <= InventoryItem.reorder_level)

        count_query = select(func.count()).select_from(query.subquery())
        total_result = await db.execute(count_query)
        total = total_result.scalar()

        # Apply pagination and ordering
        offset = (page - 1) * page_size
        query = query.offset(offset).limit(page_size).order_by(InventoryItem.name)

        # Execute query
        result = await db.execute(query)
        items = result.scalars().all()

        return {
            "items": [inventory_to_response(i) for i in items],
            "total": total,
            "page": page,
            "page_size": page_size,
        }
    except Exception as e:
        import traceback

        logger.error(f"Error in list_inventory: {traceback.format_exc()}")
        return {"items": [], "total": 0, "page": page, "page_size": page_size, "error": str(e)}


@router.get("/reorder-alerts")
async def get_reorder_alerts(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get all items that need to be reordered."""
    query = (
        select(InventoryItem)
        .where(InventoryItem.quantity_on_hand <= InventoryItem.reorder_level, InventoryItem.is_active == True)
        .order_by(InventoryItem.category, InventoryItem.name)
    )

    result = await db.execute(query)
    items = result.scalars().all()

    return {
        "items": [inventory_to_response(i) for i in items],
        "total": len(items),
    }


@router.get("/categories")
async def get_categories(
    db: DbSession,
    current_user: CurrentUser,
):
    """Get list of unique categories."""
    query = select(InventoryItem.category).where(InventoryItem.category.isnot(None)).distinct()

    result = await db.execute(query)
    categories = [row[0] for row in result.fetchall() if row[0]]

    return {"categories": sorted(categories)}


@router.get("/{item_id}/transactions")
async def get_item_transactions(
    item_id: str,
    db: DbSession,
    current_user: CurrentUser,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
):
    """Get transaction history for an inventory item."""
    # Verify item exists
    result = await db.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    if not result.scalar_one_or_none():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Inventory item not found")

    # Count
    count_q = select(func.count()).where(InventoryTransaction.item_id == item_id)
    total = (await db.execute(count_q)).scalar()

    # Fetch transactions
    offset = (page - 1) * page_size
    query = (
        select(InventoryTransaction)
        .where(InventoryTransaction.item_id == item_id)
        .order_by(InventoryTransaction.created_at.desc())
        .offset(offset)
        .limit(page_size)
    )
    result = await db.execute(query)
    transactions = result.scalars().all()

    return {
        "transactions": [
            {
                "id": t.id,
                "item_id": t.item_id,
                "adjustment": t.adjustment,
                "previous_quantity": t.previous_quantity,
                "new_quantity": t.new_quantity,
                "reason": t.reason,
                "reference_type": t.reference_type,
                "reference_id": t.reference_id,
                "performed_by": t.performed_by,
                "created_at": t.created_at.isoformat() if t.created_at else None,
            }
            for t in transactions
        ],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


@router.get("/{item_id}", response_model=InventoryItemResponse)
async def get_inventory_item(
    item_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get a single inventory item by ID."""
    result = await db.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    return inventory_to_response(item)


@router.get("/sku/{sku}", response_model=InventoryItemResponse)
async def get_inventory_by_sku(
    sku: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Get an inventory item by SKU."""
    result = await db.execute(select(InventoryItem).where(InventoryItem.sku == sku))
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    return inventory_to_response(item)


@router.post("", response_model=InventoryItemResponse, status_code=status.HTTP_201_CREATED)
async def create_inventory_item(
    item_data: InventoryItemCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Create a new inventory item."""
    # Check if SKU already exists
    existing = await db.execute(select(InventoryItem).where(InventoryItem.sku == item_data.sku))
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"SKU '{item_data.sku}' already exists",
        )

    data = item_data.model_dump()
    item = InventoryItem(**data)
    db.add(item)
    await db.commit()
    await db.refresh(item)
    return inventory_to_response(item)


@router.patch("/{item_id}", response_model=InventoryItemResponse)
async def update_inventory_item(
    item_id: str,
    item_data: InventoryItemUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    """Update an inventory item."""
    result = await db.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    # Check if SKU change conflicts with existing
    update_data = item_data.model_dump(exclude_unset=True)
    if "sku" in update_data and update_data["sku"] != item.sku:
        existing = await db.execute(select(InventoryItem).where(InventoryItem.sku == update_data["sku"]))
        if existing.scalar_one_or_none():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"SKU '{update_data['sku']}' already exists",
            )

    for field, value in update_data.items():
        setattr(item, field, value)

    await db.commit()
    await db.refresh(item)
    return inventory_to_response(item)


@router.post("/{item_id}/adjust", response_model=InventoryItemResponse)
async def adjust_inventory(
    item_id: str,
    adjustment: InventoryAdjustment,
    db: DbSession,
    current_user: CurrentUser,
):
    """Adjust inventory quantity (add or subtract)."""
    result = await db.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    new_quantity = (item.quantity_on_hand or 0) + adjustment.adjustment
    if new_quantity < 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot reduce quantity below 0. Current: {item.quantity_on_hand}, Adjustment: {adjustment.adjustment}",
        )

    previous_quantity = item.quantity_on_hand or 0
    item.quantity_on_hand = new_quantity

    # Log the adjustment to inventory_transactions
    transaction = InventoryTransaction(
        item_id=str(item.id),
        adjustment=adjustment.adjustment,
        previous_quantity=previous_quantity,
        new_quantity=new_quantity,
        reason=adjustment.reason,
        reference_type=adjustment.reference_type,
        reference_id=adjustment.reference_id,
        performed_by=current_user.id,
    )
    db.add(transaction)

    await db.commit()
    await db.refresh(item)
    return inventory_to_response(item)


@router.delete("/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_inventory_item(
    item_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Delete an inventory item."""
    result = await db.execute(select(InventoryItem).where(InventoryItem.id == item_id))
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Inventory item not found",
        )

    await db.delete(item)
    await db.commit()
