"""Outbound Dialer campaign persistence - /api/v2/outbound-campaigns.

All endpoints require authentication. The `rep_user_id` on any log/callback
row is always taken from ``current_user.id`` — never trusted from the client.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime as _dt
from datetime import timezone as _tz
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select

from app.api.deps import CurrentUser, DbSession
from app.models.outbound_campaign import (
    OutboundCallAttempt,
    OutboundCallback,
    OutboundCampaign,
    OutboundCampaignContact,
)
from app.schemas.outbound_campaigns import (
    AttemptResponse,
    BulkContactsCreate,
    CallbackCreate,
    CallbackResponse,
    CallbackUpdate,
    CampaignCounters,
    CampaignCreate,
    CampaignResponse,
    CampaignUpdate,
    ContactResponse,
    ContactUpdate,
    DispositionCreate,
    MigrateLocalImported,
    MigrateLocalRequest,
    MigrateLocalResponse,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _counters_for(db, campaign_id: str) -> CampaignCounters:
    """Derive campaign counters by aggregating contact statuses."""
    cs = OutboundCampaignContact
    result = await db.execute(
        select(cs.call_status, func.count(cs.id))
        .where(cs.campaign_id == campaign_id)
        .group_by(cs.call_status)
    )
    buckets = {row[0]: row[1] for row in result.all()}
    total = sum(buckets.values())
    pending = buckets.get("pending", 0) + buckets.get("queued", 0)
    called = total - pending
    connected_states = {"connected", "interested", "not_interested", "completed"}
    connected = sum(v for k, v in buckets.items() if k in connected_states)
    completed_states = {
        "completed",
        "interested",
        "not_interested",
        "wrong_number",
        "do_not_call",
    }
    completed = sum(v for k, v in buckets.items() if k in completed_states)
    return CampaignCounters(
        total=total,
        pending=pending,
        called=called,
        connected=connected,
        interested=buckets.get("interested", 0),
        voicemail=buckets.get("voicemail", 0),
        no_answer=buckets.get("no_answer", 0),
        callback_scheduled=buckets.get("callback_scheduled", 0),
        completed=completed,
        do_not_call=buckets.get("do_not_call", 0),
    )


def _campaign_to_response(
    c: OutboundCampaign, counters: CampaignCounters
) -> CampaignResponse:
    return CampaignResponse(
        id=c.id,
        name=c.name,
        description=c.description,
        status=c.status,
        source_file=c.source_file,
        source_sheet=c.source_sheet,
        created_by=c.created_by,
        created_at=c.created_at,
        updated_at=c.updated_at,
        counters=counters,
    )


def _contact_to_response(c: OutboundCampaignContact) -> ContactResponse:
    return ContactResponse.model_validate(c)


# ---------------------------------------------------------------------------
# Campaigns
# ---------------------------------------------------------------------------


@router.get("/campaigns")
async def list_campaigns(db: DbSession, current_user: CurrentUser):
    """List all outbound campaigns with derived counters."""
    result = await db.execute(
        select(OutboundCampaign).order_by(OutboundCampaign.created_at.desc())
    )
    campaigns = result.scalars().all()
    payload = []
    for c in campaigns:
        counters = await _counters_for(db, c.id)
        payload.append(_campaign_to_response(c, counters).model_dump(mode="json"))
    return {"campaigns": payload}


@router.post("/campaigns", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    payload: CampaignCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    campaign_id = payload.id or str(_uuid.uuid4())
    existing = await db.get(OutboundCampaign, campaign_id)
    if existing is not None:
        raise HTTPException(status_code=409, detail="Campaign id already exists")
    c = OutboundCampaign(
        id=campaign_id,
        name=payload.name,
        description=payload.description,
        status=payload.status,
        source_file=payload.source_file,
        source_sheet=payload.source_sheet,
        created_by=current_user.id,
    )
    db.add(c)
    await db.commit()
    await db.refresh(c)
    counters = await _counters_for(db, c.id)
    return _campaign_to_response(c, counters).model_dump(mode="json")


@router.patch("/campaigns/{campaign_id}")
async def update_campaign(
    campaign_id: str,
    payload: CampaignUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    c = await db.get(OutboundCampaign, campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(c, k, v)
    await db.commit()
    await db.refresh(c)
    counters = await _counters_for(db, c.id)
    return _campaign_to_response(c, counters).model_dump(mode="json")


@router.delete("/campaigns/{campaign_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_campaign(
    campaign_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    c = await db.get(OutboundCampaign, campaign_id)
    if c is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    await db.delete(c)
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Contacts
# ---------------------------------------------------------------------------


@router.get("/campaigns/{campaign_id}/contacts")
async def list_contacts(
    campaign_id: str,
    db: DbSession,
    current_user: CurrentUser,
    status_filter: Optional[str] = Query(None, alias="status"),
):
    campaign = await db.get(OutboundCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    stmt = select(OutboundCampaignContact).where(
        OutboundCampaignContact.campaign_id == campaign_id
    )
    if status_filter:
        stmt = stmt.where(OutboundCampaignContact.call_status == status_filter)
    stmt = stmt.order_by(
        OutboundCampaignContact.priority.desc(),
        OutboundCampaignContact.account_name,
    )
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "contacts": [_contact_to_response(c).model_dump(mode="json") for c in rows]
    }


@router.post(
    "/campaigns/{campaign_id}/contacts", status_code=status.HTTP_201_CREATED
)
async def bulk_import_contacts(
    campaign_id: str,
    payload: BulkContactsCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    campaign = await db.get(OutboundCampaign, campaign_id)
    if campaign is None:
        raise HTTPException(status_code=404, detail="Campaign not found")
    created: List[OutboundCampaignContact] = []
    for item in payload.contacts:
        cid = item.id or str(_uuid.uuid4())
        existing = await db.get(OutboundCampaignContact, cid)
        if existing is not None:
            continue
        data = item.model_dump(exclude={"id"})
        row = OutboundCampaignContact(id=cid, campaign_id=campaign_id, **data)
        db.add(row)
        created.append(row)
    await db.commit()
    for row in created:
        await db.refresh(row)
    return {
        "contacts": [_contact_to_response(c).model_dump(mode="json") for c in created]
    }


@router.patch("/contacts/{contact_id}")
async def patch_contact(
    contact_id: str,
    payload: ContactUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    row = await db.get(OutboundCampaignContact, contact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return _contact_to_response(row).model_dump(mode="json")


@router.delete("/contacts/{contact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_contact(
    contact_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    row = await db.get(OutboundCampaignContact, contact_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    await db.delete(row)
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Dispositions
# ---------------------------------------------------------------------------


@router.post(
    "/contacts/{contact_id}/dispositions", status_code=status.HTTP_201_CREATED
)
async def create_disposition(
    contact_id: str,
    payload: DispositionCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    contact = await db.get(OutboundCampaignContact, contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")

    now = _dt.now(_tz.utc)
    contact.call_status = payload.call_status
    contact.call_attempts = (contact.call_attempts or 0) + 1
    contact.last_call_date = now
    contact.last_disposition = payload.call_status
    if payload.duration_sec is not None:
        contact.last_call_duration = payload.duration_sec
    if payload.notes is not None:
        contact.notes = payload.notes

    attempt = OutboundCallAttempt(
        contact_id=contact_id,
        campaign_id=contact.campaign_id,
        rep_user_id=current_user.id,
        dispositioned_at=now,
        call_status=payload.call_status,
        notes=payload.notes,
        duration_sec=payload.duration_sec,
    )
    db.add(attempt)
    await db.commit()
    await db.refresh(contact)
    await db.refresh(attempt)
    return {
        "contact": _contact_to_response(contact).model_dump(mode="json"),
        "attempt": AttemptResponse.model_validate(attempt).model_dump(mode="json"),
    }


# ---------------------------------------------------------------------------
# Callbacks
# ---------------------------------------------------------------------------


@router.get("/callbacks")
async def list_callbacks(
    db: DbSession,
    current_user: CurrentUser,
    status_filter: Optional[str] = Query(None, alias="status"),
    rep: Optional[str] = Query(None, description="'me' for current user"),
):
    stmt = select(OutboundCallback).order_by(OutboundCallback.scheduled_for.asc())
    if status_filter:
        stmt = stmt.where(OutboundCallback.status == status_filter)
    if rep == "me":
        stmt = stmt.where(OutboundCallback.rep_user_id == current_user.id)
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "callbacks": [
            CallbackResponse.model_validate(r).model_dump(mode="json") for r in rows
        ]
    }


@router.post("/callbacks", status_code=status.HTTP_201_CREATED)
async def create_callback(
    payload: CallbackCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    contact = await db.get(OutboundCampaignContact, payload.contact_id)
    if contact is None:
        raise HTTPException(status_code=404, detail="Contact not found")
    cb = OutboundCallback(
        contact_id=payload.contact_id,
        campaign_id=payload.campaign_id,
        rep_user_id=current_user.id,
        scheduled_for=payload.scheduled_for,
        notes=payload.notes,
    )
    db.add(cb)
    await db.commit()
    await db.refresh(cb)
    return CallbackResponse.model_validate(cb).model_dump(mode="json")


def _parse_uuid(val: str, label: str) -> _uuid.UUID:
    try:
        return _uuid.UUID(val)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=f"Invalid {label} id") from exc


@router.patch("/callbacks/{callback_id}")
async def update_callback(
    callback_id: str,
    payload: CallbackUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    cb_uuid = _parse_uuid(callback_id, "callback")
    cb = await db.get(OutboundCallback, cb_uuid)
    if cb is None:
        raise HTTPException(status_code=404, detail="Callback not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(cb, k, v)
    await db.commit()
    await db.refresh(cb)
    return CallbackResponse.model_validate(cb).model_dump(mode="json")


@router.delete("/callbacks/{callback_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_callback(
    callback_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    cb_uuid = _parse_uuid(callback_id, "callback")
    cb = await db.get(OutboundCallback, cb_uuid)
    if cb is None:
        raise HTTPException(status_code=404, detail="Callback not found")
    await db.delete(cb)
    await db.commit()
    return None


# ---------------------------------------------------------------------------
# Local migration
# ---------------------------------------------------------------------------


DIRTY_MERGEABLE_FIELDS = [
    "call_status",
    "call_attempts",
    "last_call_date",
    "last_call_duration",
    "last_disposition",
    "notes",
    "callback_date",
]

NON_DIRTY_STATUSES = {"pending", "queued"}


def _is_dirty_contact(row: dict) -> bool:
    return (row.get("call_attempts") or 0) > 0 or row.get(
        "call_status"
    ) not in NON_DIRTY_STATUSES


@router.post("/migrate-local", response_model=MigrateLocalResponse)
async def migrate_local(
    payload: MigrateLocalRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Idempotent one-shot upload of a browser's legacy IndexedDB state.

    Rules:
    1. Campaigns: upsert by id. Insert if missing, no-op if present.
    2. Contacts: upsert by id. Insert if missing. If existing + incoming is
       "dirty" (``call_attempts > 0`` or non-pending/queued status), overwrite
       the dirty-mergeable fields. Non-dirty existing rows are left alone.
    3. Attempts: synthesize one row per dirty merged contact (guarded against
       duplicate synthesis on re-run).
    4. Callbacks: insert if no row with same (contact_id, scheduled_for).
    """
    imported = {"campaigns": 0, "contacts": 0, "attempts": 0, "callbacks": 0}

    # 1. Campaigns ---------------------------------------------------------
    for cp in payload.campaigns:
        existing = await db.get(OutboundCampaign, cp.id)
        if existing is None:
            db.add(
                OutboundCampaign(
                    id=cp.id,
                    name=cp.name,
                    description=cp.description,
                    status=cp.status or "active",
                    source_file=cp.source_file,
                    source_sheet=cp.source_sheet,
                    created_by=current_user.id,
                )
            )
            imported["campaigns"] += 1
    await db.flush()

    # 2. Contacts ----------------------------------------------------------
    for cnt in payload.contacts:
        row = await db.get(OutboundCampaignContact, cnt.id)
        incoming = cnt.model_dump()
        dirty = _is_dirty_contact(incoming)

        if row is None:
            parent = await db.get(OutboundCampaign, cnt.campaign_id)
            if parent is None:
                # Orphan — skip silently rather than erroring on a whole batch.
                continue
            row = OutboundCampaignContact(
                id=cnt.id,
                campaign_id=cnt.campaign_id,
                account_number=cnt.account_number,
                account_name=cnt.account_name,
                company=cnt.company,
                phone=cnt.phone,
                email=cnt.email,
                address=cnt.address,
                city=cnt.city,
                state=cnt.state,
                zip_code=cnt.zip_code,
                service_zone=cnt.service_zone,
                system_type=cnt.system_type,
                contract_type=cnt.contract_type,
                contract_status=cnt.contract_status,
                contract_value=cnt.contract_value,
                customer_type=cnt.customer_type,
                call_priority_label=cnt.call_priority_label,
                call_status=cnt.call_status,
                call_attempts=cnt.call_attempts,
                last_call_date=cnt.last_call_date,
                last_call_duration=cnt.last_call_duration,
                last_disposition=cnt.last_disposition,
                notes=cnt.notes,
                callback_date=cnt.callback_date,
                priority=cnt.priority,
                opens=cnt.opens,
            )
            db.add(row)
            imported["contacts"] += 1
        elif dirty:
            for field in DIRTY_MERGEABLE_FIELDS:
                val = incoming.get(field)
                if val is not None:
                    setattr(row, field, val)
            imported["contacts"] += 1
        # existing + not dirty: no-op

        if dirty and cnt.last_call_date is not None:
            # Guard against duplicate synthesis on re-run.
            existing_attempt = (
                await db.execute(
                    select(OutboundCallAttempt).where(
                        OutboundCallAttempt.contact_id == cnt.id,
                        OutboundCallAttempt.dispositioned_at == cnt.last_call_date,
                        OutboundCallAttempt.call_status == cnt.call_status,
                    )
                )
            ).scalars().first()
            if existing_attempt is None:
                db.add(
                    OutboundCallAttempt(
                        contact_id=cnt.id,
                        campaign_id=cnt.campaign_id,
                        rep_user_id=current_user.id,
                        dispositioned_at=cnt.last_call_date,
                        call_status=cnt.call_status,
                        notes=cnt.notes,
                    )
                )
                imported["attempts"] += 1
    await db.flush()

    # 3. Callbacks ---------------------------------------------------------
    for cb in payload.callbacks:
        existing_cb = (
            await db.execute(
                select(OutboundCallback).where(
                    OutboundCallback.contact_id == cb.contact_id,
                    OutboundCallback.scheduled_for == cb.scheduled_for,
                )
            )
        ).scalars().first()
        if existing_cb is not None:
            continue
        contact_row = await db.get(OutboundCampaignContact, cb.contact_id)
        if contact_row is None:
            continue
        campaign_id = cb.campaign_id or contact_row.campaign_id
        db.add(
            OutboundCallback(
                contact_id=cb.contact_id,
                campaign_id=campaign_id,
                rep_user_id=current_user.id,
                scheduled_for=cb.scheduled_for,
                notes=cb.notes,
                status=cb.status or "scheduled",
            )
        )
        imported["callbacks"] += 1

    await db.commit()
    return MigrateLocalResponse(imported=MigrateLocalImported(**imported))
