#!/usr/bin/env python3
"""Convert Septic_Service_Form to CRM work order import CSV.

Source: ~/OneDrive/Septic_Service_Form_with_Commission Structure.xlsx
- Sheet "Sheet2": headers at row 12, data rows 13-773 (~757 records)
- Columns: Office, Operator, Date, Customer Name, Lift Station, Price,
           Other Name, Street Address, Email, System, Service Type,
           Tank Access, Symptoms, Service(s) Provided, Total Price,
           Post Service Notes, Follow-up
"""

import csv
import sys
from pathlib import Path
from datetime import datetime
import openpyxl

SOURCE = Path.home() / "OneDrive/Septic_Service_Form_with_Commission Structure.xlsx"
OUTPUT = Path(__file__).parent / "work_orders_import.csv"

# Map service types to CRM job types
SERVICE_TYPE_MAP = {
    "pump/clean": "pumping",
    "pumping": "pumping",
    "emergency service": "emergency",
    "emergency": "emergency",
    "inspection": "inspection",
    "repair": "repair",
    "installation": "installation",
    "maintenance": "maintenance",
    "annual service": "maintenance",
}


def map_job_type(service_type):
    if not service_type:
        return "pumping"
    key = service_type.strip().lower()
    # Check direct match
    if key in SERVICE_TYPE_MAP:
        return SERVICE_TYPE_MAP[key]
    # Check partial match
    for k, v in SERVICE_TYPE_MAP.items():
        if k in key:
            return v
    return "pumping"  # default


def format_date(val):
    if val is None:
        return ""
    if isinstance(val, datetime):
        return val.strftime("%Y-%m-%d")
    try:
        return str(val)
    except Exception:
        return ""


def main():
    print(f"Reading {SOURCE}...")
    wb = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    ws = wb["Sheet2"]

    rows_written = 0
    skipped = 0

    with open(OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "customer_name", "customer_email", "service_address",
            "job_type", "scheduled_date", "status", "priority",
            "description", "notes"
        ])

        for i, row in enumerate(ws.iter_rows(min_row=13, values_only=True), start=13):
            # Col indices (0-based): 2=Date, 3=Customer Name, 6=Other Name,
            # 7=Street Address, 8=Email, 9=System, 10=Service Type,
            # 13=Services Provided, 14=Total Price, 15=Post Service Notes

            customer_name = str(row[3] or row[6] or "").strip()
            if not customer_name:
                skipped += 1
                continue

            street = str(row[7] or "").strip()
            if not street:
                # Try lift station address col 4
                street = str(row[4] or "").strip()
            if not street:
                skipped += 1
                continue

            email = str(row[8] or "").strip()
            if email.lower() in ("unknown", "none", ""):
                email = ""

            scheduled_date = format_date(row[2])
            service_type = str(row[10] or "").strip()
            job_type = map_job_type(service_type)

            services_provided = str(row[13] or "").strip()
            system_type = str(row[9] or "").strip()
            symptoms = str(row[12] or "").strip()
            total_price = row[14]
            post_notes = str(row[15] or "").strip()

            description_parts = []
            if system_type:
                description_parts.append(f"System: {system_type}")
            if symptoms:
                description_parts.append(f"Symptoms: {symptoms}")
            if services_provided:
                description_parts.append(f"Services: {services_provided}")
            if total_price:
                description_parts.append(f"Total: ${total_price}")

            writer.writerow([
                customer_name,
                email,
                street,
                job_type,
                scheduled_date,
                "completed",
                "normal",
                "; ".join(description_parts),
                post_notes
            ])
            rows_written += 1

    wb.close()
    print(f"Done! Wrote {rows_written} rows to {OUTPUT}")
    print(f"  Skipped {skipped} rows (no name or address)")


if __name__ == "__main__":
    main()
