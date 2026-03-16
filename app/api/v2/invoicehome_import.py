"""InvoiceHome Import — Bulk import invoices from InvoiceHome PDF export.

One-time migration endpoint for importing historical invoice data from
InvoiceHome (invoicehome.com) into the CRM. Handles:
- Customer matching by name (case-insensitive)
- Customer creation for unmatched names
- Invoice creation with proper status mapping
- Duplicate detection by invoice number
"""

from fastapi import APIRouter, HTTPException, status
from sqlalchemy import select, func
from typing import Optional, List
from datetime import datetime, date
from pydantic import BaseModel
import uuid
import logging

from app.api.deps import DbSession, CurrentUser
from app.models.invoice import Invoice
from app.models.customer import Customer

logger = logging.getLogger(__name__)
router = APIRouter()


# ========================
# Schemas
# ========================


class InvoiceHomeRecord(BaseModel):
    customer: str
    document: str = "Invoice"
    number: int
    date: Optional[str] = None
    paid_date: Optional[str] = None
    due_date: Optional[str] = None
    subtotal: float = 0.0
    tax: float = 0.0
    paid_amount: float = 0.0
    total: float = 0.0
    currency: str = "USD"
    status: str = "unpaid"


class InvoiceHomeImportRequest(BaseModel):
    records: List[InvoiceHomeRecord]
    dry_run: bool = False


class ImportSummary(BaseModel):
    total_records: int
    imported: int
    skipped_duplicates: int
    customers_created: int
    customers_matched: int
    errors: List[dict]
    dry_run: bool


# ========================
# Endpoints
# ========================


@router.post("/import-invoicehome", response_model=ImportSummary)
async def import_invoicehome(
    request: InvoiceHomeImportRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Import invoices from InvoiceHome export data.

    Requires superuser. Accepts JSON array of invoice records parsed
    from InvoiceHome PDF report.
    """
    if not current_user.is_superuser:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Superuser required for bulk import",
        )

    records = request.records
    dry_run = request.dry_run

    imported = 0
    skipped = 0
    customers_created = 0
    customers_matched = 0
    errors = []

    # Build customer name cache for matching
    # Load all customers into memory for fast fuzzy matching
    result = await db.execute(
        select(Customer.id, Customer.first_name, Customer.last_name)
    )
    all_customers = result.fetchall()

    # Build name→id lookup (case-insensitive)
    customer_cache = {}
    for cust_id, first_name, last_name in all_customers:
        full_name = f"{first_name or ''} {last_name or ''}".strip().lower()
        customer_cache[full_name] = cust_id
        # Also index by last_name only for single-word matches
        if last_name:
            last_key = last_name.strip().lower()
            if last_key not in customer_cache:
                customer_cache[last_key] = cust_id

    # Check existing invoice numbers for duplicate detection
    result = await db.execute(select(Invoice.invoice_number))
    existing_numbers = {row[0] for row in result.fetchall()}

    logger.info(
        f"InvoiceHome import: {len(records)} records, "
        f"{len(customer_cache)} customers in cache, "
        f"{len(existing_numbers)} existing invoices"
    )

    for i, record in enumerate(records):
        try:
            # Generate invoice number from InvoiceHome number
            inv_number = f"IH-{record.number}"

            # Skip duplicates
            if inv_number in existing_numbers:
                skipped += 1
                continue

            # Match customer by name
            customer_name = record.customer.strip()
            name_lower = customer_name.lower()
            customer_id = customer_cache.get(name_lower)

            if not customer_id:
                # Try partial matching - first word + last word
                parts = customer_name.split()
                if len(parts) >= 2:
                    # Try "First Last" format
                    first_last = f"{parts[0]} {parts[-1]}".lower()
                    customer_id = customer_cache.get(first_last)

            if not customer_id:
                # Create new customer
                if not dry_run:
                    parts = customer_name.split(None, 1)
                    first_name = parts[0] if parts else customer_name
                    last_name = parts[1] if len(parts) > 1 else ""

                    new_customer = Customer(
                        id=uuid.uuid4(),
                        first_name=first_name,
                        last_name=last_name,
                        customer_type="commercial",
                        tags="invoicehome-import",
                        lead_source="invoicehome",
                    )
                    db.add(new_customer)
                    await db.flush()
                    customer_id = new_customer.id
                    customer_cache[name_lower] = customer_id

                customers_created += 1
            else:
                customers_matched += 1

            if dry_run:
                imported += 1
                continue

            # Parse dates
            issue_date = None
            if record.date:
                try:
                    issue_date = datetime.strptime(record.date, "%Y-%m-%d").date()
                except ValueError:
                    issue_date = date.today()

            paid_date_val = None
            if record.paid_date:
                try:
                    paid_date_val = datetime.strptime(record.paid_date, "%Y-%m-%d").date()
                except ValueError:
                    pass

            due_date_val = None
            if record.due_date:
                try:
                    due_date_val = datetime.strptime(record.due_date, "%Y-%m-%d").date()
                except ValueError:
                    pass

            # Map status
            if record.status == "paid" or (record.paid_amount >= record.total > 0):
                inv_status = "paid"
            elif record.paid_amount > 0:
                inv_status = "partial"
            else:
                # Old unpaid invoices — mark as sent (they were issued)
                inv_status = "sent"

            # Create invoice
            invoice = Invoice(
                id=uuid.uuid4(),
                customer_id=customer_id,
                invoice_number=inv_number,
                issue_date=issue_date,
                due_date=due_date_val,
                paid_date=paid_date_val,
                amount=record.total,
                paid_amount=record.paid_amount,
                currency=record.currency,
                status=inv_status,
                line_items=[{
                    "service": f"{record.document} #{record.number}",
                    "description": f"Imported from InvoiceHome — {record.customer}",
                    "quantity": 1,
                    "rate": record.subtotal,
                    "amount": record.subtotal,
                }],
                notes=f"Imported from InvoiceHome on {date.today().isoformat()}. "
                      f"Original #{record.number}, {record.document}.",
            )
            db.add(invoice)
            existing_numbers.add(inv_number)
            imported += 1

            # Batch commit every 200 records
            if imported % 200 == 0:
                await db.flush()
                logger.info(f"  ...flushed {imported} invoices")

        except Exception as e:
            errors.append({
                "record_index": i,
                "invoice_number": record.number,
                "customer": record.customer,
                "error": str(e),
            })
            if len(errors) > 50:
                break

    # Final commit
    if not dry_run and imported > 0:
        await db.commit()

    summary = ImportSummary(
        total_records=len(records),
        imported=imported,
        skipped_duplicates=skipped,
        customers_created=customers_created,
        customers_matched=customers_matched,
        errors=errors[:50],
        dry_run=dry_run,
    )

    logger.info(
        f"InvoiceHome import complete: {imported} imported, "
        f"{skipped} skipped, {customers_created} new customers, "
        f"{len(errors)} errors"
    )

    return summary
