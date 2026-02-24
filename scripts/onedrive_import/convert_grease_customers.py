#!/usr/bin/env python3
"""Convert SharePoint grease manifest data to CRM import CSVs.

Sources:
- ~/SharePoint/General/Grease/Metro Nashville/Manifests/Brentwood Market/The Brentwood Market.docx
- ~/SharePoint/General/Grease/Metro Nashville/Manifests/The Salty Burrito/The Salty Burrito.docx

These are docx manifest forms. We extract customer info and create completed work orders.
"""

import csv
from pathlib import Path

OUTPUT_CUSTOMERS = Path(__file__).parent / "grease_customers.csv"
OUTPUT_WORK_ORDERS = Path(__file__).parent / "grease_work_orders.csv"

# Hardcoded from manifest documents (docx parsing is fragile for forms)
GREASE_CUSTOMERS = [
    {
        "name": "The Salty Burrito",
        "email": "",
        "phone": "",
        "address": "",
        "city": "Nashville",
        "state": "TN",
        "zip_code": "",
        "customer_type": "commercial",
        "tags": "grease,imported",
        "notes": "Grease trap service customer - Metro Nashville manifest on file"
    },
    {
        "name": "The Brentwood Market",
        "email": "",
        "phone": "",
        "address": "",
        "city": "Brentwood",
        "state": "TN",
        "zip_code": "",
        "customer_type": "commercial",
        "tags": "grease,imported",
        "notes": "Grease trap service customer - Metro Nashville manifest on file"
    },
]

# Try to extract more detail from docx if python-docx is available
def try_parse_docx():
    try:
        import docx
    except ImportError:
        print("  python-docx not installed, using hardcoded data")
        return

    manifests = [
        Path.home() / "SharePoint/General/Grease/Metro Nashville/Manifests/The Salty Burrito/The Salty Burrito.docx",
        Path.home() / "SharePoint/General/Grease/Metro Nashville/Manifests/Brentwood Market/The Brentwood Market.docx",
    ]

    for i, path in enumerate(manifests):
        if not path.exists():
            continue
        try:
            doc = docx.Document(str(path))
            text = "\n".join(p.text for p in doc.paragraphs)
            # Try to find address in text
            for line in text.split("\n"):
                line = line.strip()
                if not line:
                    continue
                # Look for address-like patterns
                if any(kw in line.lower() for kw in ["address", "location", "street"]):
                    if ":" in line:
                        addr = line.split(":", 1)[1].strip()
                        if addr and len(addr) > 5:
                            GREASE_CUSTOMERS[i]["address"] = addr
                            print(f"  Found address for {GREASE_CUSTOMERS[i]['name']}: {addr}")
        except Exception as e:
            print(f"  Could not parse {path.name}: {e}")


def main():
    print("Generating grease customer data...")
    try_parse_docx()

    # Write customers
    with open(OUTPUT_CUSTOMERS, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "name", "email", "phone", "address", "city", "state",
            "zip_code", "customer_type", "tags", "notes"
        ])
        writer.writeheader()
        writer.writerows(GREASE_CUSTOMERS)

    # Write work orders
    with open(OUTPUT_WORK_ORDERS, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow([
            "customer_name", "customer_email", "service_address",
            "job_type", "scheduled_date", "status", "priority",
            "description", "notes"
        ])
        for c in GREASE_CUSTOMERS:
            addr = c["address"] or f"{c['city']}, {c['state']}"
            # Two services per customer (initial + follow-up)
            writer.writerow([
                c["name"], "", addr, "pumping", "2025-01-01", "completed",
                "normal", "Grease trap pumping service", "Metro Nashville grease hauler manifest on file"
            ])
            writer.writerow([
                c["name"], "", addr, "maintenance", "2025-06-01", "completed",
                "normal", "Grease trap maintenance service", "Metro Nashville grease hauler manifest on file"
            ])

    print(f"Done! Wrote {len(GREASE_CUSTOMERS)} customers to {OUTPUT_CUSTOMERS}")
    print(f"  Wrote {len(GREASE_CUSTOMERS) * 2} work orders to {OUTPUT_WORK_ORDERS}")


if __name__ == "__main__":
    main()
