"""
Populate database with test call data for Call Intelligence testing
"""
import asyncio
import asyncpg
import os
from datetime import datetime, timedelta, date, time
import random

# Database connection
DATABASE_URL = os.environ.get("DATABASE_URL", "")

async def populate_calls():
    """Create realistic call log entries for testing."""
    if not DATABASE_URL:
        print("ERROR: DATABASE_URL environment variable not set")
        return

    # Connect to database
    conn = await asyncpg.connect(DATABASE_URL)

    try:
        # Sample data for realistic calls
        phone_numbers = [
            "+12145550101", "+12145550102", "+12145550103",
            "+12145550104", "+12145550105", "+15555551234",
            "+15555559876", "+18005551234", "+19725550987"
        ]

        company_number = "+12145550100"  # Main company number

        dispositions = [
            "completed", "answered", "missed", "busy",
            "no_answer", "voicemail", "transferred"
        ]

        # Generate calls for the last 7 days
        calls_created = 0

        for days_ago in range(7):
            call_date = (datetime.utcnow() - timedelta(days=days_ago)).date()

            # Generate 3-8 calls per day
            calls_per_day = random.randint(3, 8)

            for i in range(calls_per_day):
                # Random call time during business hours
                hour = random.randint(8, 17)
                minute = random.randint(0, 59)
                call_time = time(hour, minute)

                # Random direction and numbers
                direction = random.choice(["inbound", "outbound"])

                if direction == "inbound":
                    caller = random.choice(phone_numbers)
                    called = company_number
                else:
                    caller = company_number
                    called = random.choice(phone_numbers)

                # Random duration (30 seconds to 10 minutes)
                duration = random.randint(30, 600)

                # Random disposition
                disposition = random.choice(dispositions)

                # Some calls have recordings
                has_recording = random.random() > 0.3  # 70% have recordings
                recording_url = None
                if has_recording:
                    recording_url = f"https://platform.ringcentral.com/restapi/v1.0/account/899705035/recording/fake-{random.randint(1000, 9999)}/content"

                # Insert call record
                query = """
                INSERT INTO call_logs (
                    call_date, call_time, direction, caller_number, called_number,
                    duration_seconds, call_disposition, assigned_to, recording_url,
                    ringcentral_call_id, created_at
                ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11)
                """

                await conn.execute(
                    query,
                    call_date,
                    call_time,
                    direction,
                    caller,
                    called,
                    duration,
                    disposition,
                    "test-user",
                    recording_url,
                    f"fake-call-{random.randint(100000, 999999)}",
                    datetime.utcnow()
                )

                calls_created += 1

        print(f"SUCCESS: Created {calls_created} test call records")

        # Verify the data
        count = await conn.fetchval("SELECT COUNT(*) FROM call_logs")
        print(f"Total calls in database: {count}")

        # Show sample of recent calls
        recent = await conn.fetch("""
            SELECT call_date, direction, caller_number, called_number, duration_seconds, call_disposition
            FROM call_logs
            ORDER BY call_date DESC, call_time DESC
            LIMIT 5
        """)

        print("\nSample recent calls:")
        for call in recent:
            print(f"  {call['call_date']} {call['direction']} {call['caller_number']} -> {call['called_number']} ({call['duration_seconds']}s) [{call['call_disposition']}]")

    except Exception as e:
        print(f"ERROR: {e}")

    finally:
        await conn.close()

if __name__ == "__main__":
    asyncio.run(populate_calls())