#!/usr/bin/env python3
"""Convert call log CSV to CRM call_logs import CSV.

Source: ~/OneDrive/Documents/Call_Logs(Last_13_days)-20250114 (1).csv
- 46 rows with 49 columns from phone system export
- Key fields: external_number, date_started, talk_duration, direction, name
"""

import csv
from pathlib import Path
from datetime import datetime

SOURCE = Path.home() / "OneDrive/Documents/Call_Logs(Last_13_days)-20250114 (1).csv"
OUTPUT = Path(__file__).parent / "call_logs_import.csv"


def main():
    print(f"Reading {SOURCE}...")

    rows_written = 0

    with open(SOURCE, "r") as infile, open(OUTPUT, "w", newline="") as outfile:
        reader = csv.DictReader(infile)
        writer = csv.writer(outfile)
        writer.writerow([
            "caller_number", "called_number", "direction",
            "call_date", "call_time", "duration_seconds", "notes"
        ])

        for row in reader:
            direction = (row.get("direction") or "").strip().lower()
            external = (row.get("external_number") or "").strip()
            internal = (row.get("internal_number") or "").strip()

            if direction in ("outbound", "outgoing"):
                caller_number = internal
                called_number = external
                crm_direction = "outbound"
            else:
                caller_number = external
                called_number = internal
                crm_direction = "inbound"

            # Parse date_started
            date_started = (row.get("date_started") or "").strip()
            call_date = ""
            call_time = ""
            if date_started:
                try:
                    dt = datetime.fromisoformat(date_started.replace("Z", "+00:00"))
                    call_date = dt.strftime("%Y-%m-%d")
                    call_time = dt.strftime("%H:%M:%S")
                except Exception:
                    call_date = date_started[:10] if len(date_started) >= 10 else date_started

            # talk_duration is in minutes (float)
            talk_dur = row.get("talk_duration") or "0"
            try:
                duration_seconds = int(float(talk_dur) * 60)
            except (ValueError, TypeError):
                duration_seconds = 0

            agent_name = (row.get("name") or "").strip()
            notes_parts = []
            if agent_name:
                notes_parts.append(f"Agent: {agent_name}")
            voicemail = (row.get("voicemail") or "").strip()
            if voicemail and voicemail.lower() not in ("false", "0", ""):
                notes_parts.append("Voicemail")

            writer.writerow([
                caller_number,
                called_number,
                crm_direction,
                call_date,
                call_time,
                duration_seconds,
                "; ".join(notes_parts)
            ])
            rows_written += 1

    print(f"Done! Wrote {rows_written} call logs to {OUTPUT}")


if __name__ == "__main__":
    main()
