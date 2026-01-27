#!/usr/bin/env python3
"""
Seed Central Texas data for ECBTX CRM.

Uses REAL permit data from Central Texas septic permits database.
Creates:
- 5 Technicians with realistic skills and equipment
- 15 Customers from real permit holder addresses
- 10 Prospects in various pipeline stages
- Work orders and invoices for customers
"""

import asyncio
import os
import sys
import uuid
from datetime import datetime, timedelta, date, time
from decimal import Decimal
import random

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

if not DATABASE_URL:
    print("ERROR: DATABASE_URL environment variable is required")
    sys.exit(1)


# =============================================================================
# TECHNICIANS DATA - 5 technicians with Central Texas home bases
# =============================================================================
TECHNICIANS = [
    {
        "id": str(uuid.uuid4()),
        "first_name": "Marcus",
        "last_name": "Rodriguez",
        "email": "marcus.rodriguez@ecbtx.com",
        "phone": "(512) 555-0101",
        "employee_id": "TECH-001",
        "skills": ["pumping", "repairs", "inspections", "camera"],
        "assigned_vehicle": "Truck-101",
        "vehicle_capacity_gallons": 3500,
        "hourly_rate": 32.00,
        "home_city": "Round Rock",
        "home_state": "TX",
        "is_active": True,
    },
    {
        "id": str(uuid.uuid4()),
        "first_name": "Jake",
        "last_name": "Thompson",
        "email": "jake.thompson@ecbtx.com",
        "phone": "(512) 555-0102",
        "employee_id": "TECH-002",
        "skills": ["pumping", "maintenance", "emergency"],
        "assigned_vehicle": "Truck-102",
        "vehicle_capacity_gallons": 3000,
        "hourly_rate": 28.50,
        "home_city": "Georgetown",
        "home_state": "TX",
        "is_active": True,
    },
    {
        "id": str(uuid.uuid4()),
        "first_name": "Sarah",
        "last_name": "Chen",
        "email": "sarah.chen@ecbtx.com",
        "phone": "(512) 555-0103",
        "employee_id": "TECH-003",
        "skills": ["inspections", "camera", "installations"],
        "assigned_vehicle": "Truck-103",
        "vehicle_capacity_gallons": 2500,
        "hourly_rate": 30.00,
        "home_city": "Cedar Park",
        "home_state": "TX",
        "is_active": True,
    },
    {
        "id": str(uuid.uuid4()),
        "first_name": "David",
        "last_name": "Martinez",
        "email": "david.martinez@ecbtx.com",
        "phone": "(512) 555-0104",
        "employee_id": "TECH-004",
        "skills": ["pumping", "grease_trap", "repairs"],
        "assigned_vehicle": "Truck-104",
        "vehicle_capacity_gallons": 4000,
        "hourly_rate": 29.00,
        "home_city": "Austin",
        "home_state": "TX",
        "is_active": True,
    },
    {
        "id": str(uuid.uuid4()),
        "first_name": "Chris",
        "last_name": "Williams",
        "email": "chris.williams@ecbtx.com",
        "phone": "(512) 555-0105",
        "employee_id": "TECH-005",
        "skills": ["pumping", "repairs", "inspections", "camera", "installations", "emergency", "grease_trap", "maintenance"],
        "assigned_vehicle": "Truck-105",
        "vehicle_capacity_gallons": 3500,
        "hourly_rate": 35.00,
        "home_city": "Pflugerville",
        "home_state": "TX",
        "is_active": True,
    },
]


# =============================================================================
# CUSTOMERS DATA - 15 customers from REAL Central Texas permit addresses
# =============================================================================
CUSTOMERS = [
    {
        "first_name": "John",
        "last_name": "Cooke",
        "email": "john.cooke@example.com",
        "phone": "(512) 555-1001",
        "address_line1": "294 Call Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1000,
        "system_type": "Conventional",
    },
    {
        "first_name": "Brad",
        "last_name": "Hoff",
        "email": "brad.hoff@example.com",
        "phone": "(512) 555-1002",
        "address_line1": "495 July Johnson Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "Aerobic",
    },
    {
        "first_name": "Robert",
        "last_name": "Bitterli",
        "email": "robert.bitterli@example.com",
        "phone": "(512) 555-1003",
        "address_line1": "1911 Lohman Ford Rd",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "customer_type": "commercial",
        "tank_size_gallons": 2000,
        "system_type": "Conventional",
    },
    {
        "first_name": "Thomas",
        "last_name": "Vetter",
        "email": "thomas.vetter@example.com",
        "phone": "(512) 555-1004",
        "address_line1": "12961 Trail Driver",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1000,
        "system_type": "Conventional",
    },
    {
        "first_name": "Keith",
        "last_name": "Hansen",
        "email": "keith.hansen@example.com",
        "phone": "(512) 555-1005",
        "address_line1": "855 Gato Del Sol Ave",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "ATU",
    },
    {
        "first_name": "William",
        "last_name": "Curtis",
        "email": "william.curtis@example.com",
        "phone": "(830) 555-1006",
        "address_line1": "3106 Golf Course Dr",
        "city": "Horseshoe Bay",
        "state": "TX",
        "postal_code": "78657",
        "customer_type": "residential",
        "tank_size_gallons": 2000,
        "system_type": "Mound",
    },
    {
        "first_name": "Darrell",
        "last_name": "Minton",
        "email": "darrell.minton@example.com",
        "phone": "(512) 555-1007",
        "address_line1": "428 Big Brown Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1250,
        "system_type": "Conventional",
    },
    {
        "first_name": "Bobby",
        "last_name": "Dean",
        "email": "bobby.dean@example.com",
        "phone": "(512) 555-1008",
        "address_line1": "623 July Johnson Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78737",
        "customer_type": "residential",
        "tank_size_gallons": 1250,
        "system_type": "Chamber",
    },
    {
        "first_name": "Tommy",
        "last_name": "Mathis",
        "email": "tommy.mathis@lonestarbrewing.com",
        "phone": "(512) 555-1009",
        "address_line1": "2110 County Road 118",
        "city": "Burnet",
        "state": "TX",
        "postal_code": "78611",
        "customer_type": "commercial",
        "tank_size_gallons": 2500,
        "system_type": "Grease Trap",
    },
    {
        "first_name": "Alfred",
        "last_name": "Stone",
        "email": "alfred.stone@example.com",
        "phone": "(512) 555-1010",
        "address_line1": "11104 Trails End Rd",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "customer_type": "residential",
        "tank_size_gallons": 1000,
        "system_type": "Conventional",
    },
    {
        "first_name": "John",
        "last_name": "Miller",
        "email": "john.miller@example.com",
        "phone": "(830) 555-1011",
        "address_line1": "2905 Blue Lake Dr",
        "city": "Horseshoe Bay",
        "state": "TX",
        "postal_code": "78657",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "Conventional",
    },
    {
        "first_name": "Charles",
        "last_name": "Castro",
        "email": "charles.castro@example.com",
        "phone": "(830) 555-1012",
        "address_line1": "406 Lakeview Dr",
        "city": "Horseshoe Bay",
        "state": "TX",
        "postal_code": "78657",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "Aerobic",
    },
    {
        "first_name": "Eugene",
        "last_name": "Zimmermann",
        "email": "eugene.zimmermann@example.com",
        "phone": "(325) 555-1013",
        "address_line1": "4016 River Oaks Dr",
        "city": "Kingsland",
        "state": "TX",
        "postal_code": "78639",
        "customer_type": "residential",
        "tank_size_gallons": 1500,
        "system_type": "Conventional",
    },
    {
        "first_name": "Robert",
        "last_name": "Anderson",
        "email": "robert.anderson@example.com",
        "phone": "(512) 555-1014",
        "address_line1": "129 Lakeway Dr",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78734",
        "customer_type": "residential",
        "tank_size_gallons": 1000,
        "system_type": "Conventional",
    },
    {
        "first_name": "Steven",
        "last_name": "Wellman",
        "email": "steven.wellman@example.com",
        "phone": "(512) 555-1015",
        "address_line1": "1305 Cat Hollow Club Dr",
        "city": "Spicewood",
        "state": "TX",
        "postal_code": "78669",
        "customer_type": "residential",
        "tank_size_gallons": 2000,
        "system_type": "ATU",
    },
]


# =============================================================================
# PROSPECTS DATA - 10 prospects from REAL Central Texas permit addresses
# =============================================================================
PROSPECTS = [
    {
        "first_name": "Dennis",
        "last_name": "Glover",
        "email": "dennis.glover@example.com",
        "phone": "(512) 555-2001",
        "address_line1": "21802 Mockingbird St",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "qualified",
        "estimated_value": 4500.00,
        "lead_source": "Google",
        "lead_notes": "ATU repair needed - compressor failing",
    },
    {
        "first_name": "Teresa",
        "last_name": "Wildi",
        "email": "teresa.wildi@example.com",
        "phone": "(512) 555-2002",
        "address_line1": "18222 Center St",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "new_lead",
        "estimated_value": 350.00,
        "lead_source": "Referral",
        "lead_notes": "Due for routine pump out",
    },
    {
        "first_name": "Michael",
        "last_name": "Kaspar",
        "email": "michael.kaspar@example.com",
        "phone": "(512) 555-2003",
        "address_line1": "21909 Surrey Ln",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "quoted",
        "estimated_value": 8200.00,
        "lead_source": "Website",
        "lead_notes": "New septic system installation - new construction",
    },
    {
        "first_name": "Jester King",
        "last_name": "Holdings LLC",
        "email": "info@jesterkingbrewery.com",
        "phone": "(512) 555-2004",
        "address_line1": "13187 Fitzhugh Rd",
        "city": "Austin",
        "state": "TX",
        "postal_code": "78736",
        "prospect_stage": "negotiation",
        "estimated_value": 12000.00,
        "lead_source": "Cold Call",
        "lead_notes": "Commercial brewery - multiple grease traps",
        "customer_type": "commercial",
    },
    {
        "first_name": "Harriet",
        "last_name": "Brandon",
        "email": "harriet.brandon@example.com",
        "phone": "(830) 555-2005",
        "address_line1": "613 Highland Dr",
        "city": "Marble Falls",
        "state": "TX",
        "postal_code": "78654",
        "prospect_stage": "contacted",
        "estimated_value": 450.00,
        "lead_source": "Facebook",
        "lead_notes": "Inspection request before home sale",
    },
    {
        "first_name": "Jack",
        "last_name": "O'Leary",
        "email": "jack.oleary@example.com",
        "phone": "(512) 555-2006",
        "address_line1": "8621 Grandview Dr",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "qualified",
        "estimated_value": 2800.00,
        "lead_source": "Google",
        "lead_notes": "ATU maintenance contract inquiry",
    },
    {
        "first_name": "James",
        "last_name": "Collins",
        "email": "james.collins@example.com",
        "phone": "(512) 555-2007",
        "address_line1": "716 Cutlass",
        "city": "Lakeway",
        "state": "TX",
        "postal_code": "78734",
        "prospect_stage": "quoted",
        "estimated_value": 6500.00,
        "lead_source": "Referral",
        "lead_notes": "Quarterly service contract for lakefront property",
    },
    {
        "first_name": "Kimberly",
        "last_name": "McDonald",
        "email": "kimberly.mcdonald@example.com",
        "phone": "(512) 555-2008",
        "address_line1": "128 Firebird St",
        "city": "Lakeway",
        "state": "TX",
        "postal_code": "78734",
        "prospect_stage": "new_lead",
        "estimated_value": 375.00,
        "lead_source": "Yelp",
        "lead_notes": "Residential pump out request",
    },
    {
        "first_name": "Daniel",
        "last_name": "Yannitell",
        "email": "daniel.yannitell@example.com",
        "phone": "(512) 555-2009",
        "address_line1": "4001 Outpost Trce",
        "city": "Leander",
        "state": "TX",
        "postal_code": "78641",
        "prospect_stage": "negotiation",
        "estimated_value": 24000.00,
        "lead_source": "Website",
        "lead_notes": "Multi-unit property - annual contract negotiation",
        "customer_type": "commercial",
    },
    {
        "first_name": "Patrick",
        "last_name": "Wendland",
        "email": "patrick.wendland@example.com",
        "phone": "(512) 555-2010",
        "address_line1": "915 Porpoise St",
        "city": "Lakeway",
        "state": "TX",
        "postal_code": "78734",
        "prospect_stage": "contacted",
        "estimated_value": 1200.00,
        "lead_source": "Door-to-door",
        "lead_notes": "Inspection + pump out combo requested",
    },
]


# Job types for work orders
JOB_TYPES = ["pumping", "inspection", "repair", "maintenance", "grease_trap", "camera_inspection"]
STATUSES = ["completed", "scheduled", "in_progress"]


async def seed_technicians(session: AsyncSession):
    """Insert technicians into the database."""
    print("\n=== Seeding Technicians ===")

    for tech in TECHNICIANS:
        # Check if technician already exists
        result = await session.execute(
            text("SELECT id FROM technicians WHERE employee_id = :emp_id"),
            {"emp_id": tech["employee_id"]}
        )
        existing = result.fetchone()

        if existing:
            print(f"  Technician {tech['first_name']} {tech['last_name']} already exists, skipping...")
            continue

        # Insert technician
        await session.execute(
            text("""
                INSERT INTO technicians (
                    id, first_name, last_name, email, phone, employee_id,
                    skills, assigned_vehicle, vehicle_capacity_gallons,
                    hourly_rate, home_city, home_state, is_active, created_at
                ) VALUES (
                    :id, :first_name, :last_name, :email, :phone, :employee_id,
                    :skills, :assigned_vehicle, :vehicle_capacity_gallons,
                    :hourly_rate, :home_city, :home_state, :is_active, NOW()
                )
            """),
            {
                "id": tech["id"],
                "first_name": tech["first_name"],
                "last_name": tech["last_name"],
                "email": tech["email"],
                "phone": tech["phone"],
                "employee_id": tech["employee_id"],
                "skills": tech["skills"],
                "assigned_vehicle": tech["assigned_vehicle"],
                "vehicle_capacity_gallons": tech["vehicle_capacity_gallons"],
                "hourly_rate": tech["hourly_rate"],
                "home_city": tech["home_city"],
                "home_state": tech["home_state"],
                "is_active": tech["is_active"],
            }
        )
        print(f"  Created technician: {tech['first_name']} {tech['last_name']} ({tech['employee_id']})")

    await session.commit()
    print(f"  Total: {len(TECHNICIANS)} technicians processed")


async def seed_customers(session: AsyncSession) -> list:
    """Insert customers into the database and return their IDs."""
    print("\n=== Seeding Customers ===")
    customer_ids = []

    for cust in CUSTOMERS:
        # Check if customer already exists by email
        result = await session.execute(
            text("SELECT id FROM customers WHERE email = :email"),
            {"email": cust["email"]}
        )
        existing = result.fetchone()

        if existing:
            print(f"  Customer {cust['first_name']} {cust['last_name']} already exists, using existing ID...")
            customer_ids.append(existing[0])
            continue

        # Insert customer
        result = await session.execute(
            text("""
                INSERT INTO customers (
                    first_name, last_name, email, phone,
                    address_line1, city, state, postal_code,
                    customer_type, tank_size_gallons, system_type,
                    is_active, created_at
                ) VALUES (
                    :first_name, :last_name, :email, :phone,
                    :address_line1, :city, :state, :postal_code,
                    :customer_type, :tank_size_gallons, :system_type,
                    true, NOW()
                )
                RETURNING id
            """),
            cust
        )
        customer_id = result.fetchone()[0]
        customer_ids.append(customer_id)
        print(f"  Created customer: {cust['first_name']} {cust['last_name']} - {cust['city']} (ID: {customer_id})")

    await session.commit()
    print(f"  Total: {len(CUSTOMERS)} customers processed")
    return customer_ids


async def seed_prospects(session: AsyncSession):
    """Insert prospects into the database (customers with prospect_stage set)."""
    print("\n=== Seeding Prospects ===")

    for prospect in PROSPECTS:
        # Check if prospect already exists by email
        result = await session.execute(
            text("SELECT id FROM customers WHERE email = :email"),
            {"email": prospect["email"]}
        )
        existing = result.fetchone()

        if existing:
            print(f"  Prospect {prospect['first_name']} {prospect['last_name']} already exists, skipping...")
            continue

        # Insert prospect (customer with prospect_stage)
        await session.execute(
            text("""
                INSERT INTO customers (
                    first_name, last_name, email, phone,
                    address_line1, city, state, postal_code,
                    prospect_stage, estimated_value, lead_source, lead_notes,
                    customer_type, is_active, created_at
                ) VALUES (
                    :first_name, :last_name, :email, :phone,
                    :address_line1, :city, :state, :postal_code,
                    :prospect_stage, :estimated_value, :lead_source, :lead_notes,
                    :customer_type, true, NOW()
                )
            """),
            {
                **prospect,
                "customer_type": prospect.get("customer_type", "residential"),
            }
        )
        print(f"  Created prospect: {prospect['first_name']} {prospect['last_name']} - {prospect['prospect_stage']} (${prospect['estimated_value']})")

    await session.commit()
    print(f"  Total: {len(PROSPECTS)} prospects processed")


async def seed_work_orders(session: AsyncSession, customer_ids: list):
    """Create work orders for existing customers."""
    print("\n=== Seeding Work Orders ===")

    # Get technician IDs
    result = await session.execute(text("SELECT id FROM technicians WHERE is_active = true"))
    tech_ids = [row[0] for row in result.fetchall()]

    if not tech_ids:
        print("  No technicians found, skipping work orders")
        return

    work_order_count = 0

    # Create 2-3 work orders per customer
    for customer_id in customer_ids[:10]:  # First 10 customers get work orders
        num_orders = random.randint(2, 3)

        for i in range(num_orders):
            wo_id = str(uuid.uuid4())
            tech_id = random.choice(tech_ids)
            job_type = random.choice(JOB_TYPES)

            # Random date in the past 6 months
            days_ago = random.randint(1, 180)
            scheduled_date = date.today() - timedelta(days=days_ago)
            status = "completed" if days_ago > 7 else random.choice(["scheduled", "in_progress"])

            # Calculate amount based on job type
            amounts = {
                "pumping": random.randint(275, 450),
                "inspection": random.randint(150, 250),
                "repair": random.randint(350, 1200),
                "maintenance": random.randint(175, 350),
                "grease_trap": random.randint(300, 600),
                "camera_inspection": random.randint(200, 400),
            }
            amount = amounts.get(job_type, 350)

            try:
                await session.execute(
                    text("""
                        INSERT INTO work_orders (
                            id, customer_id, technician_id, job_type, status, priority,
                            scheduled_date, estimated_duration_hours, total_amount,
                            notes, created_at
                        ) VALUES (
                            :id, :customer_id, :technician_id, :job_type, :status, 'normal',
                            :scheduled_date, :duration, :amount,
                            :notes, NOW()
                        )
                    """),
                    {
                        "id": wo_id,
                        "customer_id": customer_id,
                        "technician_id": tech_id,
                        "job_type": job_type,
                        "status": status,
                        "scheduled_date": scheduled_date,
                        "duration": random.uniform(1.0, 3.0),
                        "amount": amount,
                        "notes": f"Standard {job_type} service",
                    }
                )
                work_order_count += 1
            except Exception as e:
                print(f"  Warning: Could not create work order for customer {customer_id}: {e}")

    await session.commit()
    print(f"  Total: {work_order_count} work orders created")


async def seed_invoices(session: AsyncSession, customer_ids: list):
    """Create invoices for existing customers."""
    print("\n=== Seeding Invoices ===")

    invoice_count = 0
    invoice_num = 10001

    # Create invoices for first 8 customers
    for customer_id in customer_ids[:8]:
        # Create a UUID that represents the customer_id (for the legacy schema)
        # Use a deterministic UUID based on customer_id
        customer_uuid = uuid.uuid5(uuid.NAMESPACE_DNS, f"customer-{customer_id}")

        num_invoices = random.randint(1, 2)

        for i in range(num_invoices):
            invoice_id = uuid.uuid4()
            invoice_number = f"INV-{invoice_num}"
            invoice_num += 1

            # Random date in the past 3 months
            days_ago = random.randint(1, 90)
            issue_date = date.today() - timedelta(days=days_ago)
            due_date = issue_date + timedelta(days=30)

            amount = Decimal(random.randint(250, 800))
            status = random.choice(["paid", "sent", "draft"])
            paid_amount = amount if status == "paid" else Decimal(0)
            paid_date = issue_date + timedelta(days=random.randint(5, 25)) if status == "paid" else None

            try:
                await session.execute(
                    text("""
                        INSERT INTO invoices (
                            id, customer_id, invoice_number, issue_date, due_date,
                            amount, paid_amount, status, paid_date, created_at
                        ) VALUES (
                            :id, :customer_id, :invoice_number, :issue_date, :due_date,
                            :amount, :paid_amount, :status, :paid_date, NOW()
                        )
                    """),
                    {
                        "id": invoice_id,
                        "customer_id": customer_uuid,
                        "invoice_number": invoice_number,
                        "issue_date": issue_date,
                        "due_date": due_date,
                        "amount": amount,
                        "paid_amount": paid_amount,
                        "status": status,
                        "paid_date": paid_date,
                    }
                )
                invoice_count += 1
            except Exception as e:
                print(f"  Warning: Could not create invoice for customer {customer_id}: {e}")

    await session.commit()
    print(f"  Total: {invoice_count} invoices created")


async def main():
    """Main seeding function."""
    print("=" * 60)
    print("ECBTX CRM - Central Texas Seed Data")
    print("=" * 60)
    print(f"\nConnecting to database...")

    try:
        engine = create_async_engine(DATABASE_URL, echo=False)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            # Test connection
            result = await session.execute(text("SELECT 1"))
            print("Database connection successful!")

            # Seed data
            await seed_technicians(session)
            customer_ids = await seed_customers(session)
            await seed_prospects(session)
            await seed_work_orders(session, customer_ids)
            await seed_invoices(session, customer_ids)

        await engine.dispose()

        print("\n" + "=" * 60)
        print("Seeding completed successfully!")
        print("=" * 60)

    except Exception as e:
        print(f"\nERROR: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
