#!/usr/bin/env python3
"""Convert 'all contracts.xlsx' to CRM customer import CSV.

Source: ~/OneDrive/Documents/all contracts.xlsx
- Sheet "All Contracts 1030": 13,712 rows
- Row 1: blank, Row 2: headers (3 named cols), Data starts row 3
- Col 1: Account Name, Col 2: Account Email, Col 3-7: fragmented billing address
"""

import csv
import sys
from pathlib import Path
import openpyxl

SOURCE = Path.home() / "OneDrive/Documents/all contracts.xlsx"
OUTPUT = Path(__file__).parent / "customers_import.csv"


def parse_address(row_vals):
    """Parse fragmented address from cols 3-7 (0-indexed: 2-6).

    Pattern observed: col2=street, col3=city, col4=#VALUE! or blank, col6=state+zip
    Example: '1227 Lake Drive', ' Spring Branch', '#VALUE!', None, ' TX 78070'
    """
    street = str(row_vals[2] or "").strip()
    city = str(row_vals[3] or "").strip().strip(",")
    # col4 often has #VALUE! formula error - skip
    # col5 often None
    state_zip = str(row_vals[6] or "").strip() if len(row_vals) > 6 else ""

    # Parse state and zip from combined field like "TX 78070"
    state = ""
    postal_code = ""
    if state_zip:
        parts = state_zip.strip().split()
        if len(parts) >= 2:
            state = parts[0]
            postal_code = parts[1]
        elif len(parts) == 1:
            if parts[0].isdigit():
                postal_code = parts[0]
            else:
                state = parts[0]

    return street, city, state, postal_code


def split_name(full_name):
    """Split 'First Last' into (first_name, last_name)."""
    parts = full_name.strip().split(None, 1)
    if len(parts) == 2:
        return parts[0], parts[1]
    return full_name.strip(), ""


def main():
    print(f"Reading {SOURCE}...")
    wb = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    ws = wb["All Contracts 1030"]

    rows_written = 0
    seen_emails = set()
    skipped_dup = 0
    skipped_empty = 0

    with open(OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "name", "email", "phone", "address", "city", "state",
            "zip_code", "customer_type", "tags", "notes"
        ])

        for i, row in enumerate(ws.iter_rows(min_row=3, values_only=True), start=3):
            name = str(row[0] or "").strip()
            if not name:
                skipped_empty += 1
                continue

            email = str(row[1] or "").strip()
            if email.lower() in ("none", "unknown", "#value!", ""):
                email = ""

            # Dedup by email
            if email:
                email_lower = email.lower()
                if email_lower in seen_emails:
                    skipped_dup += 1
                    continue
                seen_emails.add(email_lower)

            street, city, state, postal_code = parse_address(list(row))

            writer.writerow([
                name,           # name (will be split by importer)
                email,
                "",             # phone (not in source)
                street,         # address
                city,
                state,
                postal_code,
                "residential",
                "imported",
                "Imported from OneDrive contracts"
            ])
            rows_written += 1

    wb.close()
    print(f"Done! Wrote {rows_written} rows to {OUTPUT}")
    print(f"  Skipped {skipped_dup} duplicate emails, {skipped_empty} empty names")


if __name__ == "__main__":
    main()
