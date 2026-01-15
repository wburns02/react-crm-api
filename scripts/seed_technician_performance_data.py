#!/usr/bin/env python3
"""
Seed realistic fake historical data for existing technicians.

This script generates:
- Completed work orders over the past 12 months
- Associated job costs (labor, materials)
- Realistic revenue and job distribution

IMPORTANT: Only seeds data for technicians that:
1. Already exist in the database
2. Were NOT created today (to avoid seeding test technicians)
"""

import asyncio
import os
import sys
import random
import uuid
from datetime import datetime, timedelta, date
from decimal import Decimal

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Job type distributions and revenue ranges
JOB_TYPES = {
    "pumping": {"weight": 50, "min_revenue": 250, "max_revenue": 600},
    "grease_trap": {"weight": 15, "min_revenue": 200, "max_revenue": 450},
    "repair": {"weight": 20, "min_revenue": 300, "max_revenue": 1500},
    "maintenance": {"weight": 10, "min_revenue": 150, "max_revenue": 500},
    "inspection": {"weight": 5, "min_revenue": 100, "max_revenue": 250},
}

# Service locations (realistic Texas addresses)
SERVICE_LOCATIONS = [
    "123 Main St, Austin, TX",
    "456 Oak Ave, San Antonio, TX",
    "789 Pine Rd, Houston, TX",
    "321 Elm St, Dallas, TX",
    "654 Cedar Ln, Fort Worth, TX",
    "987 Maple Dr, Plano, TX",
    "147 Birch Way, Round Rock, TX",
    "258 Willow Ct, Georgetown, TX",
    "369 Ash Blvd, Pflugerville, TX",
    "741 Spruce St, Kyle, TX",
    "852 Hickory Ave, Buda, TX",
    "963 Walnut Rd, Leander, TX",
    "159 Cherry Ln, Cedar Park, TX",
    "267 Pecan St, Lakeway, TX",
    "378 Cypress Dr, Dripping Springs, TX",
]

# Notes templates for pump outs
PUMP_OUT_NOTES = [
    "Pumped {gallons} gallons from {tank_size} gallon tank. System in good condition.",
    "Residential pump out - {gallons} gallons removed. {tank_size} gallon tank.",
    "Standard septic pump - {gallons} gal. Tank size: {tank_size} gal. No issues found.",
    "Pumped {gallons} gallons. {tank_size} gallon system. Recommended inspection in 2 years.",
    "Emergency pump out - {gallons} gallons. {tank_size} gal tank was near overflow.",
    "Routine maintenance pump - {gallons} gallons from {tank_size} gallon septic.",
]

GREASE_TRAP_NOTES = [
    "Grease trap cleaning - {gallons} gallons removed. {tank_size} gallon capacity.",
    "Commercial grease trap service - pumped {gallons} gal. Restaurant account.",
    "Grease trap pump out: {gallons} gallons. {tank_size} gal trap cleaned.",
]

REPAIR_NOTES = [
    "Replaced effluent filter and cleaned tank. Parts: filter kit, gaskets.",
    "Repaired broken baffle. Installed new PVC baffle. Labor: 3 hours.",
    "Fixed leaking tank lid. Replaced riser seal and lid gasket.",
    "Pump replacement - installed new 1/2 HP effluent pump with float switch.",
    "Drain field repair - replaced 20ft of distribution pipe.",
    "Repaired inlet pipe connection. New 4\" adapter and coupling.",
    "Alarm system repair - replaced float switch and control panel.",
]

MAINTENANCE_NOTES = [
    "Annual maintenance check. System operating normally.",
    "Quarterly inspection - checked pump, floats, and alarm. All good.",
    "Preventive maintenance visit. Cleaned filters and tested alarm.",
    "Maintenance inspection - minor adjustments to float levels.",
]


def weighted_choice(choices_dict):
    """Select a random choice based on weights."""
    items = list(choices_dict.items())
    total_weight = sum(item[1]["weight"] for item in items)
    r = random.uniform(0, total_weight)
    upto = 0
    for item_name, item_data in items:
        upto += item_data["weight"]
        if upto >= r:
            return item_name, item_data
    return items[-1]


def generate_work_order_id():
    """Generate a UUID string for work order ID."""
    return str(uuid.uuid4())


def generate_random_date(start_date, end_date):
    """Generate a random date between start and end."""
    delta = end_date - start_date
    random_days = random.randint(0, delta.days)
    return start_date + timedelta(days=random_days)


def generate_notes(job_type):
    """Generate realistic notes based on job type."""
    if job_type == "pumping":
        template = random.choice(PUMP_OUT_NOTES)
        gallons = random.choice([500, 750, 1000, 1200, 1500, 2000])
        tank_size = random.choice([500, 750, 1000, 1250, 1500, 2000])
        return template.format(gallons=gallons, tank_size=tank_size)
    elif job_type == "grease_trap":
        template = random.choice(GREASE_TRAP_NOTES)
        gallons = random.choice([100, 150, 200, 300, 500])
        tank_size = random.choice([250, 500, 750, 1000])
        return template.format(gallons=gallons, tank_size=tank_size)
    elif job_type == "repair":
        return random.choice(REPAIR_NOTES)
    elif job_type == "maintenance":
        return random.choice(MAINTENANCE_NOTES)
    else:
        return "Inspection completed. System operating within normal parameters."


async def get_existing_technicians(session):
    """Get technicians that were created before today."""
    today = date.today()
    result = await session.execute(
        text("""
            SELECT id, first_name, last_name
            FROM technicians
            WHERE is_active = true
              AND (created_at IS NULL OR created_at::date < :today)
        """),
        {"today": today}
    )
    return result.fetchall()


async def get_existing_customers(session):
    """Get existing customer IDs."""
    result = await session.execute(
        text("SELECT id FROM customers WHERE is_active = true LIMIT 50")
    )
    return [row[0] for row in result.fetchall()]


async def create_work_order(session, technician_id, technician_name, customer_id, job_type, job_data, scheduled_date):
    """Create a completed work order."""
    wo_id = generate_work_order_id()
    revenue = round(random.uniform(job_data["min_revenue"], job_data["max_revenue"]), 2)
    service_location = random.choice(SERVICE_LOCATIONS)
    notes = generate_notes(job_type) + " [SEED DATA]"

    # Duration in minutes (30 mins to 4 hours depending on job type)
    if job_type in ("pumping", "grease_trap"):
        duration = random.randint(30, 90)
    elif job_type in ("repair",):
        duration = random.randint(60, 240)
    else:
        duration = random.randint(30, 60)

    await session.execute(
        text("""
            INSERT INTO work_orders (
                id, customer_id, technician_id, assigned_technician,
                job_type, status, scheduled_date, total_amount,
                service_location, notes, total_labor_minutes,
                created_at, updated_at
            ) VALUES (
                :id, :customer_id, :technician_id, :assigned_technician,
                :job_type, 'completed', :scheduled_date, :total_amount,
                :service_location, :notes, :duration,
                :created_at, :updated_at
            )
        """),
        {
            "id": wo_id,
            "customer_id": customer_id,
            "technician_id": technician_id,
            "assigned_technician": technician_name,
            "job_type": job_type,
            "scheduled_date": scheduled_date,
            "total_amount": revenue,
            "service_location": service_location,
            "notes": notes,
            "duration": duration,
            "created_at": datetime.combine(scheduled_date, datetime.min.time()),
            "updated_at": datetime.combine(scheduled_date, datetime.min.time()),
        }
    )

    return wo_id, revenue, duration


async def create_job_costs(session, work_order_id, technician_id, technician_name, job_type, revenue, duration):
    """Create job cost records for labor and materials."""
    # Labor cost
    hourly_rate = random.uniform(65, 95)
    labor_hours = duration / 60.0
    labor_cost = round(labor_hours * hourly_rate, 2)

    await session.execute(
        text("""
            INSERT INTO job_costs (
                id, work_order_id, technician_id, technician_name,
                cost_type, description, quantity, unit, unit_cost, total_cost,
                is_billable, created_at
            ) VALUES (
                :id, :work_order_id, :technician_id, :technician_name,
                'labor', :description, :quantity, 'hour', :unit_cost, :total_cost,
                true, :created_at
            )
        """),
        {
            "id": str(uuid.uuid4()),
            "work_order_id": work_order_id,
            "technician_id": technician_id,
            "technician_name": technician_name,
            "description": f"Labor - {job_type}",
            "quantity": labor_hours,
            "unit_cost": hourly_rate,
            "total_cost": labor_cost,
            "created_at": datetime.utcnow(),
        }
    )

    # Materials cost for repairs
    if job_type in ("repair", "maintenance"):
        parts_cost = round(random.uniform(50, 400), 2)
        await session.execute(
            text("""
                INSERT INTO job_costs (
                    id, work_order_id, technician_id, technician_name,
                    cost_type, description, quantity, unit, unit_cost, total_cost,
                    is_billable, created_at
                ) VALUES (
                    :id, :work_order_id, :technician_id, :technician_name,
                    'materials', :description, :quantity, 'each', :unit_cost, :total_cost,
                    true, :created_at
                )
            """),
            {
                "id": str(uuid.uuid4()),
                "work_order_id": work_order_id,
                "technician_id": technician_id,
                "technician_name": technician_name,
                "description": "Parts and materials",
                "quantity": 1,
                "unit_cost": parts_cost,
                "total_cost": parts_cost,
                "created_at": datetime.utcnow(),
            }
        )


async def seed_technician_data(session, technician, customers, jobs_per_tech=75):
    """Seed data for a single technician."""
    tech_id, first_name, last_name = technician
    tech_name = f"{first_name} {last_name}"

    print(f"\nSeeding data for {tech_name} (ID: {tech_id})")

    # Generate jobs over past 12 months
    end_date = date.today() - timedelta(days=1)  # Yesterday
    start_date = end_date - timedelta(days=365)

    total_revenue = 0
    job_counts = {"pumping": 0, "grease_trap": 0, "repair": 0, "maintenance": 0, "inspection": 0}

    # Track customer visits for creating "returns"
    customer_visits = {}  # customer_id -> list of dates

    for i in range(jobs_per_tech):
        # Select job type
        job_type, job_data = weighted_choice(JOB_TYPES)

        # Select customer (sometimes repeat for "returns")
        if random.random() < 0.15 and customer_visits:  # 15% chance of return visit
            customer_id = random.choice(list(customer_visits.keys()))
        else:
            customer_id = random.choice(customers)

        # Generate date (weighted toward recent months)
        if random.random() < 0.4:  # 40% in last 3 months
            scheduled_date = generate_random_date(end_date - timedelta(days=90), end_date)
        elif random.random() < 0.7:  # 30% in months 3-6
            scheduled_date = generate_random_date(end_date - timedelta(days=180), end_date - timedelta(days=90))
        else:  # 30% older
            scheduled_date = generate_random_date(start_date, end_date - timedelta(days=180))

        # Track customer visit
        if customer_id not in customer_visits:
            customer_visits[customer_id] = []
        customer_visits[customer_id].append(scheduled_date)

        # Create work order and job costs
        wo_id, revenue, duration = await create_work_order(
            session, tech_id, tech_name, customer_id, job_type, job_data, scheduled_date
        )
        await create_job_costs(session, wo_id, tech_id, tech_name, job_type, revenue, duration)

        total_revenue += revenue
        job_counts[job_type] += 1

    await session.commit()

    print(f"  Created {jobs_per_tech} work orders")
    print(f"  Total revenue: ${total_revenue:,.2f}")
    print(f"  Job distribution: {job_counts}")


async def main():
    """Main function to seed technician performance data."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    print("=" * 60)
    print("Technician Performance Data Seeder")
    print("=" * 60)
    print(f"Database: {DATABASE_URL[:50]}...")

    # Create engine and session
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get existing technicians (created before today)
        technicians = await get_existing_technicians(session)
        if not technicians:
            print("\nNo existing technicians found (created before today).")
            print("This script only seeds data for pre-existing technicians.")
            return

        print(f"\nFound {len(technicians)} existing technicians:")
        for tech in technicians:
            print(f"  - {tech[1]} {tech[2]} (ID: {tech[0]})")

        # Get existing customers
        customers = await get_existing_customers(session)
        if not customers:
            print("\nNo existing customers found. Cannot seed work orders.")
            return

        print(f"\nFound {len(customers)} customers to use for work orders.")

        # Confirm before seeding
        print("\nThis will create approximately 75 completed work orders per technician.")
        print("All seeded data will be marked with '[SEED DATA]' in notes.")

        # Seed data for each technician
        for tech in technicians:
            await seed_technician_data(session, tech, customers, jobs_per_tech=75)

    print("\n" + "=" * 60)
    print("Seeding complete!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
