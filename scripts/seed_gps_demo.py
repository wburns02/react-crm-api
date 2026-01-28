#!/usr/bin/env python3
"""
Seed GPS demo data for testing the tracking page.

This script generates:
- TechnicianLocation records for active technicians
- Work orders scheduled for today (if none exist)

This allows the GPS tracking page to display technicians and jobs on the map.
"""

import asyncio
import os
import sys
import random
from datetime import datetime, timedelta

# Add the app directory to the path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker


# Configuration
DATABASE_URL = os.environ.get("DATABASE_URL", "")
if DATABASE_URL.startswith("postgresql://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Central Texas coordinates for demo locations
# These are real locations around Austin/San Antonio area
TEXAS_LOCATIONS = [
    {"name": "Austin Downtown", "lat": 30.2672, "lng": -97.7431},
    {"name": "Round Rock", "lat": 30.5083, "lng": -97.6789},
    {"name": "Georgetown", "lat": 30.6327, "lng": -97.6773},
    {"name": "Pflugerville", "lat": 30.4393, "lng": -97.6200},
    {"name": "Cedar Park", "lat": 30.5052, "lng": -97.8203},
    {"name": "Lakeway", "lat": 30.3632, "lng": -97.9795},
    {"name": "Dripping Springs", "lat": 30.1902, "lng": -98.0867},
    {"name": "Kyle", "lat": 29.9891, "lng": -97.8772},
    {"name": "Buda", "lat": 30.0852, "lng": -97.8403},
    {"name": "San Marcos", "lat": 29.8833, "lng": -97.9414},
]

# Technician statuses
STATUSES = ["available", "en_route", "on_site", "break"]


async def get_active_technicians(session):
    """Get all active technicians."""
    result = await session.execute(
        text("""
            SELECT id, first_name, last_name
            FROM technicians
            WHERE is_active = true
            ORDER BY id
        """)
    )
    return result.fetchall()


async def get_existing_locations(session):
    """Get technician IDs that already have locations."""
    result = await session.execute(
        text("SELECT technician_id FROM technician_locations")
    )
    return {row[0] for row in result.fetchall()}


async def get_todays_work_orders(session):
    """Get work orders scheduled for today."""
    today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)

    result = await session.execute(
        text("""
            SELECT COUNT(*) FROM work_orders
            WHERE scheduled_date >= :today_start
              AND scheduled_date < :today_end
              AND status != 'completed'
        """),
        {"today_start": today_start, "today_end": today_end}
    )
    return result.scalar()


async def get_customers_with_coords(session):
    """Get customers that have coordinates."""
    result = await session.execute(
        text("""
            SELECT id, first_name, last_name,
                   COALESCE(latitude, 30.2672) as latitude,
                   COALESCE(longitude, -97.7431) as longitude
            FROM customers
            WHERE is_active = true
            LIMIT 20
        """)
    )
    return result.fetchall()


async def create_technician_location(session, tech_id, tech_name, location):
    """Create or update a technician location."""
    now = datetime.utcnow()

    # Add some randomness to the exact position (within ~500m)
    lat = location["lat"] + random.uniform(-0.005, 0.005)
    lng = location["lng"] + random.uniform(-0.005, 0.005)

    # Random status
    status = random.choice(STATUSES)

    # Random battery level 40-100%
    battery = random.randint(40, 100)

    # Random speed 0-45 mph (0 if on_site or break)
    speed = 0 if status in ("on_site", "break") else random.uniform(0, 45)

    # Random heading 0-360
    heading = random.uniform(0, 360)

    # Check if exists
    result = await session.execute(
        text("SELECT id FROM technician_locations WHERE technician_id = :tech_id"),
        {"tech_id": tech_id}
    )
    existing = result.fetchone()

    if existing:
        # Update existing
        await session.execute(
            text("""
                UPDATE technician_locations SET
                    latitude = :lat,
                    longitude = :lng,
                    accuracy = :accuracy,
                    speed = :speed,
                    heading = :heading,
                    is_online = true,
                    battery_level = :battery,
                    captured_at = :captured_at,
                    received_at = :received_at,
                    current_status = :status
                WHERE technician_id = :tech_id
            """),
            {
                "tech_id": tech_id,
                "lat": lat,
                "lng": lng,
                "accuracy": random.uniform(5, 25),
                "speed": speed,
                "heading": heading,
                "battery": battery,
                "captured_at": now,
                "received_at": now,
                "status": status,
            }
        )
        print(f"  Updated location for {tech_name}: {location['name']} ({status})")
    else:
        # Insert new
        await session.execute(
            text("""
                INSERT INTO technician_locations (
                    technician_id, latitude, longitude, accuracy,
                    speed, heading, is_online, battery_level,
                    captured_at, received_at, current_status
                ) VALUES (
                    :tech_id, :lat, :lng, :accuracy,
                    :speed, :heading, true, :battery,
                    :captured_at, :received_at, :status
                )
            """),
            {
                "tech_id": tech_id,
                "lat": lat,
                "lng": lng,
                "accuracy": random.uniform(5, 25),
                "speed": speed,
                "heading": heading,
                "battery": battery,
                "captured_at": now,
                "received_at": now,
                "status": status,
            }
        )
        print(f"  Created location for {tech_name}: {location['name']} ({status})")


async def create_demo_work_order(session, customer, technician, scheduled_time):
    """Create a demo work order for today."""
    import uuid

    customer_id, first_name, last_name, lat, lng = customer
    tech_id, tech_first, tech_last = technician

    wo_id = str(uuid.uuid4())
    customer_name = f"{first_name} {last_name}"
    tech_name = f"{tech_first} {tech_last}"

    await session.execute(
        text("""
            INSERT INTO work_orders (
                id, customer_id, technician_id, assigned_technician,
                job_type, status, scheduled_date,
                notes, created_at, updated_at
            ) VALUES (
                :id, :customer_id, :tech_id, :tech_name,
                :job_type, :status, :scheduled_date,
                :notes, :created_at, :updated_at
            )
        """),
        {
            "id": wo_id,
            "customer_id": customer_id,
            "tech_id": tech_id,
            "tech_name": tech_name,
            "job_type": random.choice(["pumping", "inspection", "maintenance"]),
            "status": random.choice(["scheduled", "in_progress"]),
            "scheduled_date": scheduled_time,
            "notes": "[GPS DEMO] Test work order for GPS tracking demo",
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
        }
    )

    print(f"  Created work order for {customer_name} assigned to {tech_name}")
    return wo_id


async def main():
    """Main function to seed GPS demo data."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        sys.exit(1)

    print("=" * 60)
    print("GPS Demo Data Seeder")
    print("=" * 60)
    print(f"Database: {DATABASE_URL[:50]}...")
    print()

    # Create engine and session
    engine = create_async_engine(DATABASE_URL, echo=False)
    async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async with async_session() as session:
        # Get active technicians
        technicians = await get_active_technicians(session)
        if not technicians:
            print("No active technicians found.")
            return

        print(f"Found {len(technicians)} active technicians")

        # Create/update locations for each technician
        print("\nCreating technician locations:")
        for i, tech in enumerate(technicians):
            tech_id, first_name, last_name = tech
            tech_name = f"{first_name} {last_name}"
            location = TEXAS_LOCATIONS[i % len(TEXAS_LOCATIONS)]
            await create_technician_location(session, tech_id, tech_name, location)

        await session.commit()

        # Check for today's work orders
        todays_count = await get_todays_work_orders(session)
        print(f"\nFound {todays_count} uncompleted work orders for today")

        if todays_count == 0:
            print("\nCreating demo work orders for today:")
            customers = await get_customers_with_coords(session)

            if customers:
                # Create 3-5 work orders for today
                num_orders = min(5, len(customers), len(technicians))
                today = datetime.utcnow().replace(hour=8, minute=0, second=0, microsecond=0)

                for i in range(num_orders):
                    scheduled_time = today + timedelta(hours=random.randint(0, 8))
                    await create_demo_work_order(
                        session,
                        customers[i],
                        technicians[i % len(technicians)],
                        scheduled_time
                    )

                await session.commit()
                print(f"\nCreated {num_orders} demo work orders")
            else:
                print("No customers found to create work orders")

        # Summary
        print("\n" + "=" * 60)
        print("GPS Demo Data Seeding Complete!")
        print("=" * 60)
        print("\nNext steps:")
        print("1. Visit https://react.ecbtx.com/tracking")
        print("2. You should now see technicians on the map")
        print("3. Online/Offline/Jobs counts should be non-zero")
        print("\nNote: Location data will become 'stale' after 5 minutes")
        print("Run this script again to refresh demo locations")


if __name__ == "__main__":
    asyncio.run(main())
