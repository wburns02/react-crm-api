"""DNC / suppression logic for the AI Interaction Analyzer.

When triage returns ``do_not_contact_signal=True`` (unsubscribe, hostile,
competitor referral, etc.) the worker calls ``suppress(...)`` to:

  1. Add the contact's email to the DNC email list (80a4fae6-...).
  2. Add the contact's phone to the DNC phone list (de1c70ee-...). Phone
     is stored in the EmailSubscriber.email column as a workaround — there
     is no separate phone-DNC table at the time this was written.
  3. Patch the linked Customer (lead_source="do_not_email", is_archived=True,
     append "unsubscribed,do_not_email" tags).

Idempotent: re-running on an already-suppressed contact is a no-op.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer import Customer
from app.models.customer_interaction import CustomerInteraction
from app.models.email_list import EmailSubscriber

logger = logging.getLogger(__name__)


# Spec-defined list IDs (see plan decisions §7).
DNC_EMAIL_LIST_ID = UUID("80a4fae6-868a-4feb-b469-b85fa7b64d1e")
DNC_PHONE_LIST_ID = UUID("de1c70ee-6e63-4689-a70e-de2b5ea2e937")

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
_PHONE_RE = re.compile(r"^\+?[\d\s()\-]{7,}$")

_SUPPRESSION_TAGS = ("unsubscribed", "do_not_email")


def _looks_like_email(value: str | None) -> bool:
    if not value:
        return False
    return bool(_EMAIL_RE.match(value.strip()))


def _looks_like_phone(value: str | None) -> bool:
    if not value:
        return False
    candidate = value.strip()
    if "@" in candidate:
        return False
    return bool(_PHONE_RE.match(candidate))


async def _upsert_subscriber(
    db: AsyncSession,
    list_id: UUID,
    contact_value: str,
    *,
    source: str,
    metadata_note: str | None = None,
) -> None:
    """Insert or update an EmailSubscriber row to mark it 'unsubscribed'.

    EmailSubscriber.email is reused for phone DNC entries (see module docstring).
    """
    if not contact_value:
        return
    contact_value = contact_value.strip()
    stmt = select(EmailSubscriber).where(
        EmailSubscriber.list_id == list_id,
        EmailSubscriber.email == contact_value,
    )
    existing = (await db.execute(stmt)).scalars().first()

    now = datetime.now(timezone.utc)
    if existing is None:
        meta: dict[str, str] | None = None
        if metadata_note:
            meta = {"note": metadata_note}
        sub = EmailSubscriber(
            list_id=list_id,
            email=contact_value,
            source=source,
            status="unsubscribed",
            unsubscribed_at=now,
            metadata_=meta,
        )
        db.add(sub)
    else:
        if existing.status != "unsubscribed":
            existing.status = "unsubscribed"
            existing.unsubscribed_at = now


def _merge_tags(current: str | None) -> str:
    """Append the suppression tags to a CSV string, deduping case-insensitively."""
    parts = []
    seen: set[str] = set()
    if current:
        for raw in str(current).split(","):
            cleaned = raw.strip()
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen:
                continue
            seen.add(key)
            parts.append(cleaned)
    for tag in _SUPPRESSION_TAGS:
        if tag.lower() not in seen:
            seen.add(tag.lower())
            parts.append(tag)
    return ",".join(parts)


async def suppress(
    db: AsyncSession,
    interaction: CustomerInteraction,
    customer: Customer | None,
) -> None:
    """Suppress a contact based on do_not_contact_signal=True analysis.

    Idempotent. Always commits at the END (caller is expected to rely on
    a single transaction, but we flush so subsequent reads in the worker
    see the change).
    """
    # 1. Email DNC -----------------------------------------------------------
    email_candidates: list[str] = []
    if _looks_like_email(interaction.from_address):
        email_candidates.append(interaction.from_address.strip().lower())
    if customer is not None and _looks_like_email(customer.email):
        email_candidates.append(customer.email.strip().lower())
    seen_emails: set[str] = set()
    for value in email_candidates:
        if value in seen_emails:
            continue
        seen_emails.add(value)
        await _upsert_subscriber(
            db,
            DNC_EMAIL_LIST_ID,
            value,
            source="ai_analyzer",
        )

    # 2. Phone DNC -----------------------------------------------------------
    phone_candidates: list[str] = []
    if _looks_like_phone(interaction.from_address):
        phone_candidates.append(interaction.from_address.strip())
    if customer is not None and customer.phone:
        phone_candidates.append(customer.phone.strip())
    seen_phones: set[str] = set()
    for value in phone_candidates:
        normalized = value.strip()
        if not normalized or normalized in seen_phones:
            continue
        seen_phones.add(normalized)
        await _upsert_subscriber(
            db,
            DNC_PHONE_LIST_ID,
            normalized,
            source="ai_analyzer",
            metadata_note="phone_dnc",
        )

    # 3. Customer patch ------------------------------------------------------
    if customer is not None:
        if customer.lead_source != "do_not_email":
            customer.lead_source = "do_not_email"
        if not customer.is_archived:
            customer.is_archived = True
        merged = _merge_tags(customer.tags)
        if merged != (customer.tags or ""):
            customer.tags = merged

    await db.flush()
    logger.info(
        "Suppression applied: interaction=%s emails=%d phones=%d customer=%s",
        interaction.id,
        len(seen_emails),
        len(seen_phones),
        getattr(customer, "id", None),
    )


__all__ = [
    "DNC_EMAIL_LIST_ID",
    "DNC_PHONE_LIST_ID",
    "suppress",
]
