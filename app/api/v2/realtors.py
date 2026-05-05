"""Realtor Pipeline API - /api/v2/realtors.

Cloud-backed CRUD for the Realtor Pipeline feature in ReactCRM. Mirrors
the shape of the frontend's local Zustand store so a thin TanStack Query
layer can replace IndexedDB persistence with a real backend.

All endpoints require authentication.
"""

from __future__ import annotations

import logging
import uuid as _uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.orm import selectinload

from app.api.deps import CurrentUser, DbSession
from app.models.realtor import RealtorAgent, RealtorReferral
from app.schemas.realtor import (
    CallRecord,
    MigrateLocalRealtors,
    MigrateLocalRealtorsResponse,
    RealtorAgentCreate,
    RealtorAgentResponse,
    RealtorAgentUpdate,
    ReferralCreate,
    ReferralResponse,
    ReferralUpdate,
)

logger = logging.getLogger(__name__)
router = APIRouter()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _normalize_phone(phone: str) -> str:
    return "".join(c for c in phone if c.isdigit())


def _agent_to_response(a: RealtorAgent) -> RealtorAgentResponse:
    return RealtorAgentResponse.model_validate(a)


def _referral_to_response(r: RealtorReferral) -> ReferralResponse:
    return ReferralResponse.model_validate(r)


def _next_follow_up_for(stage: str) -> datetime:
    from datetime import timedelta

    now = datetime.now(timezone.utc)
    if stage == "active_referrer":
        return now + timedelta(days=14)
    if stage == "warm":
        return now + timedelta(days=21)
    if stage == "introd":
        return now + timedelta(days=28)
    return now + timedelta(days=7)


def _stage_from_disposition(current: str, disposition: str) -> str:
    if disposition == "referral_received":
        return "active_referrer"
    if disposition == "wants_quote" and current != "active_referrer":
        return "warm"
    if disposition in ("intro_complete", "one_pager_sent") and current == "cold":
        return "introd"
    return current


# ---------------------------------------------------------------------------
# Static routes BEFORE catch-all /{id} routes
# ---------------------------------------------------------------------------


@router.post("/migrate-local", response_model=MigrateLocalRealtorsResponse)
async def migrate_local(
    payload: MigrateLocalRealtors,
    db: DbSession,
    current_user: CurrentUser,
):
    """Idempotent bulk import from a browser's IndexedDB cache.

    Dedupes agents by (digits-only) phone number, referrals by id.
    """
    agents_imported = 0
    agents_skipped = 0
    referrals_imported = 0
    referrals_skipped = 0

    # Build phone index of existing agents to dedupe quickly
    existing = (await db.execute(select(RealtorAgent))).scalars().all()
    by_phone = {_normalize_phone(a.phone): a for a in existing}
    by_id = {str(a.id): a for a in existing}

    new_agents_by_legacy_id: dict[str, RealtorAgent] = {}

    for agent_in in payload.agents:
        phone_norm = _normalize_phone(agent_in.phone)
        if not phone_norm or len(phone_norm) < 10:
            agents_skipped += 1
            continue
        if phone_norm in by_phone:
            new_agents_by_legacy_id[str(agent_in.id) if agent_in.id else ""] = by_phone[phone_norm]
            agents_skipped += 1
            continue

        data = agent_in.model_dump(exclude={"id"})
        agent_id = _uuid.UUID(agent_in.id) if agent_in.id else _uuid.uuid4()
        row = RealtorAgent(id=agent_id, **data)
        db.add(row)
        by_phone[phone_norm] = row
        if agent_in.id:
            new_agents_by_legacy_id[str(agent_in.id)] = row
        agents_imported += 1

    await db.flush()

    for ref_in in payload.referrals:
        # Map referral.realtor_id (legacy local id) → real DB row if needed
        target_realtor: Optional[RealtorAgent] = by_id.get(str(ref_in.realtor_id))
        if target_realtor is None:
            target_realtor = new_agents_by_legacy_id.get(str(ref_in.realtor_id))
        if target_realtor is None:
            referrals_skipped += 1
            continue

        ref_id = _uuid.UUID(ref_in.id) if ref_in.id else _uuid.uuid4()
        existing_ref = await db.get(RealtorReferral, ref_id)
        if existing_ref is not None:
            referrals_skipped += 1
            continue

        data = ref_in.model_dump(exclude={"id", "realtor_id"})
        if data.get("referred_date") is None:
            data["referred_date"] = datetime.now(timezone.utc)
        row = RealtorReferral(id=ref_id, realtor_id=target_realtor.id, **data)
        db.add(row)
        referrals_imported += 1

    await db.commit()
    return MigrateLocalRealtorsResponse(
        agents_imported=agents_imported,
        agents_skipped=agents_skipped,
        referrals_imported=referrals_imported,
        referrals_skipped=referrals_skipped,
    )


# ---------------------------------------------------------------------------
# Agents
# ---------------------------------------------------------------------------


@router.get("/agents")
async def list_agents(
    db: DbSession,
    current_user: CurrentUser,
    stage: Optional[str] = Query(None),
):
    stmt = select(RealtorAgent)
    if stage and stage != "all":
        stmt = stmt.where(RealtorAgent.stage == stage)
    stmt = stmt.order_by(RealtorAgent.priority.desc(), RealtorAgent.last_name)
    rows = (await db.execute(stmt)).scalars().all()
    return {"agents": [_agent_to_response(a).model_dump(mode="json") for a in rows]}


@router.post("/agents", status_code=status.HTTP_201_CREATED)
async def create_agent(
    payload: RealtorAgentCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    phone_norm = _normalize_phone(payload.phone)
    if not phone_norm or len(phone_norm) < 10:
        raise HTTPException(status_code=400, detail="Invalid phone number")

    # Dedupe by phone
    dup = (
        await db.execute(
            select(RealtorAgent).where(RealtorAgent.phone == phone_norm)
        )
    ).scalar_one_or_none()
    if dup is not None:
        return _agent_to_response(dup).model_dump(mode="json")

    data = payload.model_dump(exclude={"id"})
    data["phone"] = phone_norm
    agent_id = _uuid.UUID(payload.id) if payload.id else _uuid.uuid4()
    row = RealtorAgent(id=agent_id, **data)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return _agent_to_response(row).model_dump(mode="json")


@router.get("/agents/{agent_id}")
async def get_agent(
    agent_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    row = await db.get(RealtorAgent, _uuid.UUID(agent_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    return _agent_to_response(row).model_dump(mode="json")


@router.patch("/agents/{agent_id}")
async def patch_agent(
    agent_id: str,
    payload: RealtorAgentUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    row = await db.get(RealtorAgent, _uuid.UUID(agent_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    data = payload.model_dump(exclude_unset=True)
    if "phone" in data and data["phone"]:
        data["phone"] = _normalize_phone(data["phone"])
    if "stage" in data and data["stage"] and data["stage"] != row.stage:
        data["next_follow_up"] = _next_follow_up_for(data["stage"])
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return _agent_to_response(row).model_dump(mode="json")


@router.delete("/agents/{agent_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_agent(
    agent_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    row = await db.get(RealtorAgent, _uuid.UUID(agent_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")
    await db.delete(row)
    await db.commit()
    return None


@router.post("/agents/{agent_id}/calls")
async def record_call(
    agent_id: str,
    payload: CallRecord,
    db: DbSession,
    current_user: CurrentUser,
):
    """Record a call attempt: bumps counters, may auto-advance stage."""
    row = await db.get(RealtorAgent, _uuid.UUID(agent_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Agent not found")

    new_stage = _stage_from_disposition(row.stage, payload.disposition)
    row.call_attempts = (row.call_attempts or 0) + 1
    row.last_call_date = datetime.now(timezone.utc)
    row.last_call_duration = payload.duration
    row.last_disposition = payload.disposition
    if new_stage != row.stage:
        row.stage = new_stage
    row.next_follow_up = _next_follow_up_for(row.stage)
    if payload.disposition == "one_pager_sent" and not row.one_pager_sent:
        row.one_pager_sent = True
        row.one_pager_sent_date = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(row)
    return _agent_to_response(row).model_dump(mode="json")


# ---------------------------------------------------------------------------
# Referrals
# ---------------------------------------------------------------------------


@router.get("/referrals")
async def list_referrals(
    db: DbSession,
    current_user: CurrentUser,
    realtor_id: Optional[str] = Query(None),
):
    stmt = select(RealtorReferral)
    if realtor_id:
        stmt = stmt.where(RealtorReferral.realtor_id == _uuid.UUID(realtor_id))
    stmt = stmt.order_by(RealtorReferral.referred_date.desc())
    rows = (await db.execute(stmt)).scalars().all()
    return {
        "referrals": [_referral_to_response(r).model_dump(mode="json") for r in rows]
    }


@router.post("/referrals", status_code=status.HTTP_201_CREATED)
async def create_referral(
    payload: ReferralCreate,
    db: DbSession,
    current_user: CurrentUser,
):
    realtor = await db.get(RealtorAgent, _uuid.UUID(payload.realtor_id))
    if realtor is None:
        raise HTTPException(status_code=404, detail="Realtor not found")

    data = payload.model_dump(exclude={"id", "realtor_id"})
    if data.get("referred_date") is None:
        data["referred_date"] = datetime.now(timezone.utc)
    ref_id = _uuid.UUID(payload.id) if payload.id else _uuid.uuid4()
    row = RealtorReferral(id=ref_id, realtor_id=realtor.id, **data)
    db.add(row)

    # Bump aggregates on the realtor
    realtor.total_referrals = (realtor.total_referrals or 0) + 1
    if data.get("invoice_amount"):
        realtor.total_revenue = (realtor.total_revenue or Decimal(0)) + Decimal(
            str(data["invoice_amount"])
        )
    realtor.last_referral_date = datetime.now(timezone.utc)
    if realtor.stage != "active_referrer":
        realtor.stage = "active_referrer"
        realtor.next_follow_up = _next_follow_up_for("active_referrer")

    await db.commit()
    await db.refresh(row)
    return _referral_to_response(row).model_dump(mode="json")


@router.patch("/referrals/{referral_id}")
async def patch_referral(
    referral_id: str,
    payload: ReferralUpdate,
    db: DbSession,
    current_user: CurrentUser,
):
    row = await db.get(RealtorReferral, _uuid.UUID(referral_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Referral not found")
    data = payload.model_dump(exclude_unset=True)
    for k, v in data.items():
        setattr(row, k, v)
    await db.commit()
    await db.refresh(row)
    return _referral_to_response(row).model_dump(mode="json")


@router.delete("/referrals/{referral_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_referral(
    referral_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    row = await db.get(RealtorReferral, _uuid.UUID(referral_id))
    if row is None:
        raise HTTPException(status_code=404, detail="Referral not found")
    realtor = await db.get(RealtorAgent, row.realtor_id)
    if realtor is not None:
        realtor.total_referrals = max(0, (realtor.total_referrals or 0) - 1)
        if row.invoice_amount:
            realtor.total_revenue = max(
                Decimal(0),
                (realtor.total_revenue or Decimal(0)) - Decimal(str(row.invoice_amount)),
            )
    await db.delete(row)
    await db.commit()
    return None
