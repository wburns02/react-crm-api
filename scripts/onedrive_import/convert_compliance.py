#!/usr/bin/env python3
"""Convert Annual Requirements to compliance contacts and reminders.

Source: ~/SharePoint/General/Annual Requirements.xlsx
- Headers: Requirement, Permit #, Date Issued, Expiration, Business/Org., PoC, Title, Phone, Email, Address, Site, Fees
"""

import csv
from pathlib import Path
import openpyxl

SOURCE = Path.home() / "SharePoint/General/Annual Requirements.xlsx"
CONTACTS_OUTPUT = Path(__file__).parent / "compliance_contacts.csv"
REMINDERS_OUTPUT = Path(__file__).parent / "compliance_reminders.txt"


def main():
    print(f"Reading {SOURCE}...")
    wb = openpyxl.load_workbook(SOURCE, read_only=True, data_only=True)
    ws = wb.active

    rows = list(ws.iter_rows(values_only=True))
    headers = [str(c or "").strip() for c in rows[0]]
    print(f"  Headers: {headers}")

    contacts_written = 0
    reminders = []
    seen_orgs = set()

    with open(CONTACTS_OUTPUT, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "name", "email", "phone", "address", "city", "state",
            "zip_code", "customer_type", "tags", "notes"
        ])

        for row in rows[1:]:
            vals = dict(zip(headers, row))

            requirement = str(vals.get("Requirement", "") or "").strip()
            permit = str(vals.get("Permit #", "") or "").strip()
            expiration = str(vals.get("Expiration", "") or "").strip()
            org = str(vals.get("Business/Org.", "") or "").strip()
            poc = str(vals.get("PoC", "") or "").strip()
            title = str(vals.get("Title", "") or "").strip()
            phone = str(vals.get("Phone", "") or "").strip()
            email = str(vals.get("Email", "") or "").strip()
            address = str(vals.get("Address", "") or "").strip()
            site = str(vals.get("Site", "") or "").strip()
            fees = str(vals.get("Fees", "") or "").strip()

            # Build reminder entry
            if requirement and expiration:
                reminders.append(f"{requirement} | Permit: {permit} | Expires: {expiration} | Org: {org} | Fees: {fees}")

            # Create contact for unique organizations with contact info
            if org and org.lower() not in seen_orgs and (phone or email):
                seen_orgs.add(org.lower())

                notes_parts = [f"Compliance contact"]
                if poc:
                    notes_parts.append(f"PoC: {poc}")
                if title:
                    notes_parts.append(f"Title: {title}")
                if site:
                    notes_parts.append(f"Site: {site}")
                if permit:
                    notes_parts.append(f"Permit: {permit}")

                writer.writerow([
                    org,
                    email,
                    phone,
                    address,
                    "",    # city
                    "",    # state
                    "",    # zip
                    "vendor",
                    "compliance,imported",
                    "; ".join(notes_parts)
                ])
                contacts_written += 1

    # Write reminders to stdout and file
    with open(REMINDERS_OUTPUT, "w") as f:
        f.write("=== COMPLIANCE REMINDERS (for manual task creation) ===\n\n")
        for r in reminders:
            f.write(r + "\n")
            print(f"  REMINDER: {r}")

    wb.close()
    print(f"\nDone! Wrote {contacts_written} contacts to {CONTACTS_OUTPUT}")
    print(f"  Wrote {len(reminders)} reminders to {REMINDERS_OUTPUT}")


if __name__ == "__main__":
    main()
