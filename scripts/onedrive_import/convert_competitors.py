#!/usr/bin/env python3
"""Convert competitor data to CRM customer import CSV.

Source: ~/OneDrive/Merged_Septic_Companies_with_Contacts.xlsx
- Sheet "Work on this": 131 rows
- Headers: LICENSEE, COUNTY, STATE, Phone Number, Email, Address, Website, Facebook, Google Rating, Notes
"""

import csv
from pathlib import Path
import openpyxl

SOURCE = Path.home() / "OneDrive/Merged_Septic_Companies_with_Contacts.xlsx"
OUTPUT = Path(__file__).parent / "competitors_import.csv"


def main():
    print(f"Reading {SOURCE}...")
    wb = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    ws = wb["Work on this"]

    rows = list(ws.iter_rows(values_only=True))
    headers = [str(c or "").strip() for c in rows[0]]
    print(f"  Headers: {headers}")

    rows_written = 0

    with open(OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "name", "email", "phone", "address", "city", "state",
            "zip_code", "customer_type", "tags", "notes"
        ])

        for row in rows[1:]:
            vals = dict(zip(headers, row))

            name = str(vals.get("LICENSEE", "") or "").strip()
            if not name:
                continue

            phone = str(vals.get("Phone Number", "") or "").strip()
            email = str(vals.get("Email", "") or "").strip()
            address = str(vals.get("Address", "") or "").strip()
            county = str(vals.get("COUNTY", "") or "").strip()
            state = str(vals.get("STATE", "") or "").strip()
            website = str(vals.get("Website", "") or "").strip()
            rating = str(vals.get("Google Rating", "") or "").strip()
            notes_val = str(vals.get("Notes", "") or "").strip()
            facebook = str(vals.get("Facebook", "") or "").strip()

            notes_parts = ["Competitor"]
            if website:
                notes_parts.append(f"Website: {website}")
            if facebook:
                notes_parts.append(f"Facebook: {facebook}")
            if rating:
                notes_parts.append(f"Google Rating: {rating}")
            if notes_val:
                notes_parts.append(notes_val)

            writer.writerow([
                name,
                email,
                phone,
                address,
                county,   # city = county
                state,
                "",       # zip
                "commercial",
                "competitor,imported",
                "; ".join(notes_parts)
            ])
            rows_written += 1

    wb.close()
    print(f"Done! Wrote {rows_written} competitors to {OUTPUT}")


if __name__ == "__main__":
    main()
