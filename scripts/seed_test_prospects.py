"""
Seed 10 test prospects with sent quotes for outbound agent testing.
All use the same phone number (Will's cell) for testing.

Usage: cd /home/will/react-crm-api && python scripts/seed_test_prospects.py
"""

import asyncio
import uuid
from datetime import datetime, timedelta, timezone

from app.database import async_session_maker
from app.models.customer import Customer
from app.models.quote import Quote


TEST_PHONE = "+19792361958"

PROSPECTS = [
    {"first": "Mike", "last": "Johnson", "addr": "123 Oak Lane", "city": "Nashville", "state": "TN", "service": "Septic Tank Pumping", "amount": 625},
    {"first": "Lisa", "last": "Williams", "addr": "456 Cedar Dr", "city": "Columbia", "state": "SC", "service": "Septic Inspection", "amount": 825},
    {"first": "David", "last": "Brown", "addr": "789 Maple Ave", "city": "Nashville", "state": "TN", "service": "Septic Tank Pumping", "amount": 595},
    {"first": "Sarah", "last": "Davis", "addr": "321 Pine St", "city": "Franklin", "state": "TN", "service": "Grease Trap Cleaning", "amount": 450},
    {"first": "James", "last": "Wilson", "addr": "654 Elm Rd", "city": "Brentwood", "state": "TN", "service": "Septic Repair", "amount": 1200},
    {"first": "Jennifer", "last": "Taylor", "addr": "987 Birch Blvd", "city": "Columbia", "state": "SC", "service": "Septic Tank Pumping", "amount": 625},
    {"first": "Robert", "last": "Anderson", "addr": "147 Walnut Ct", "city": "Nashville", "state": "TN", "service": "Real Estate Inspection", "amount": 825},
    {"first": "Emily", "last": "Thomas", "addr": "258 Spruce Way", "city": "Murfreesboro", "state": "TN", "service": "Aerobic System Service", "amount": 745},
    {"first": "Chris", "last": "Martinez", "addr": "369 Ash Ln", "city": "Columbia", "state": "SC", "service": "Septic Tank Pumping", "amount": 595},
    {"first": "Amanda", "last": "Garcia", "addr": "741 Hickory Dr", "city": "Nashville", "state": "TN", "service": "Septic Inspection", "amount": 825},
]


async def main():
    async with async_session_maker() as db:
        created = 0
        for i, p in enumerate(PROSPECTS):
            # Create customer
            customer = Customer(
                id=uuid.uuid4(),
                first_name=p["first"],
                last_name=p["last"],
                phone=TEST_PHONE,
                email=f"test{i+1}@macseptic.com",
                address_line1=p["addr"],
                city=p["city"],
                state=p["state"],
                postal_code="37000",
                customer_type="residential",
                is_active=True,
            )
            db.add(customer)
            await db.flush()

            # Create sent quote (5-10 days old)
            days_ago = 5 + i % 6
            sent_at = datetime.now(timezone.utc) - timedelta(days=days_ago)

            quote = Quote(
                id=uuid.uuid4(),
                quote_number=f"TEST-{1000 + i}",
                customer_id=customer.id,
                title=f"{p['service']} - {p['addr']}",
                line_items=[{
                    "service": p["service"],
                    "description": f"{p['service']} at {p['addr']}",
                    "quantity": 1,
                    "rate": p["amount"],
                    "amount": p["amount"],
                }],
                subtotal=p["amount"],
                total=p["amount"],
                status="sent",
                sent_at=sent_at,
                notes=f"Test quote for outbound agent testing",
            )
            db.add(quote)
            created += 1
            print(f"  [{created}] {p['first']} {p['last']} — {p['service']} ${p['amount']} (sent {days_ago}d ago)")

        await db.commit()
        print(f"\nCreated {created} test prospects with quotes. Phone: {TEST_PHONE}")


if __name__ == "__main__":
    asyncio.run(main())
