"""Commission auto-creation service.

This service handles automatic commission creation when work orders are completed.
It calculates commissions based on job type, applies dump fee deductions for
pumping/grease trap jobs, and links to the current payroll period.
"""

from datetime import date
from typing import Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import logging

from app.models.payroll import PayrollPeriod, Commission
from app.models.work_order import WorkOrder
from app.models.dump_site import DumpSite

logger = logging.getLogger(__name__)

# Commission rate configuration by job type
COMMISSION_RATES = {
    "pumping": {"rate": 0.20, "apply_dump_fee": True},
    "grease_trap": {"rate": 0.20, "apply_dump_fee": True},
    "inspection": {"rate": 0.15, "apply_dump_fee": False},
    "repair": {"rate": 0.15, "apply_dump_fee": False},
    "installation": {"rate": 0.10, "apply_dump_fee": False},
    "emergency": {"rate": 0.20, "apply_dump_fee": False},
    "maintenance": {"rate": 0.15, "apply_dump_fee": False},
    "camera_inspection": {"rate": 0.15, "apply_dump_fee": False},
}


async def auto_create_commission(
    db: AsyncSession,
    work_order: WorkOrder,
    dump_site_id: Optional[str] = None,
) -> Optional[Commission]:
    """
    Auto-create commission for a completed work order.

    Args:
        db: Database session
        work_order: The completed work order
        dump_site_id: Optional dump site ID for pumping/grease_trap jobs

    Returns:
        Created Commission record or None if not applicable
    """
    try:
        # Validate work order has required data
        if not work_order.technician_id:
            logger.debug(f"Work order {work_order.id} has no technician - skipping commission")
            return None

        if not work_order.total_amount or float(work_order.total_amount) <= 0:
            logger.debug(f"Work order {work_order.id} has no revenue - skipping commission")
            return None

        # Check if commission already exists for this work order
        existing_result = await db.execute(select(Commission).where(Commission.work_order_id == work_order.id))
        if existing_result.scalar_one_or_none():
            logger.debug(f"Commission already exists for work order {work_order.id}")
            return None

        # Get job type and rate config
        job_type = work_order.job_type
        if hasattr(job_type, "name"):
            job_type = job_type.name
        job_type = str(job_type) if job_type else "maintenance"

        rate_config = COMMISSION_RATES.get(job_type, {"rate": 0.15, "apply_dump_fee": False})
        commission_rate = rate_config["rate"]
        apply_dump_fee = rate_config["apply_dump_fee"]

        # Base amount is job total
        base_amount = float(work_order.total_amount)

        # Calculate dump fee deduction if applicable
        dump_fee_amount = 0.0
        dump_fee_per_gallon = None
        gallons = work_order.estimated_gallons

        if apply_dump_fee and dump_site_id and gallons:
            dump_result = await db.execute(select(DumpSite).where(DumpSite.id == dump_site_id))
            dump_site = dump_result.scalar_one_or_none()
            if dump_site and dump_site.fee_per_gallon:
                dump_fee_per_gallon = float(dump_site.fee_per_gallon)
                dump_fee_amount = float(gallons) * dump_fee_per_gallon
                logger.info(
                    f"Dump fee calculated: {gallons} gallons × ${dump_fee_per_gallon}/gal = ${dump_fee_amount:.2f}"
                )

        # Calculate commissionable amount (base - dump fees)
        commissionable_amount = max(0, base_amount - dump_fee_amount)

        # Calculate commission
        commission_amount = commissionable_amount * commission_rate

        # Find current open pay period
        today = date.today()
        period_result = await db.execute(
            select(PayrollPeriod)
            .where(
                PayrollPeriod.start_date <= today,
                PayrollPeriod.end_date >= today,
                PayrollPeriod.status == "open",
            )
            .limit(1)
        )
        payroll_period = period_result.scalar_one_or_none()

        # Create commission record
        commission = Commission(
            technician_id=work_order.technician_id,
            work_order_id=work_order.id,
            payroll_period_id=payroll_period.id if payroll_period else None,
            commission_type="job_completion",
            base_amount=base_amount,
            rate=commission_rate,
            rate_type="percent",
            commission_amount=round(commission_amount, 2),
            status="pending",
            earned_date=today,
            job_type=job_type,
            gallons_pumped=gallons,
            dump_site_id=dump_site_id,
            dump_fee_per_gallon=dump_fee_per_gallon,
            dump_fee_amount=round(dump_fee_amount, 2) if dump_fee_amount else None,
            commissionable_amount=round(commissionable_amount, 2),
        )

        db.add(commission)

        logger.info(
            f"Auto-created commission for work order {work_order.id}: "
            f"${commission_amount:.2f} ({commission_rate:.0%} of ${commissionable_amount:.2f})"
        )

        return commission

    except Exception as e:
        logger.error(f"Failed to auto-create commission for work order {work_order.id}: {e}")
        # Don't raise - commission creation failure shouldn't block work order completion
        return None
