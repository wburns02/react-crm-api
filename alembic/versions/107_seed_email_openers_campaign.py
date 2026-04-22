"""seed Email Openers - Spring Follow-Up campaign

Revision ID: 107
Revises: 106
"""
from datetime import datetime, timezone

import sqlalchemy as sa
from alembic import op


revision = "107"
down_revision = "106"
branch_labels = None
depends_on = None


CAMPAIGN_ID = "email-openers-spring-2026"


# Mirrors the hardcoded contact list that was previously injected client-side
# from src/features/outbound-campaigns/store.ts:109-145 in the frontend repo.
# 37 TN permit owners who opened the Mar 27 spring service email.
CONTACTS = [
    ("Shanna Byrnes", "9313341335", "shanna.hulsey81@gmail.com", "Spring Hill", "164 Oak Valley Dr", 8),
    ("Deborah Bohannon", "6159675144", "dinonerd1981@gmail.com", "Columbia", "612 Delk Ln", 6),
    ("Christine Browm", "4075519693", "doug@macseptic.com", "Ashland City", "404 Patricia Dr", 6),
    ("Chris Guthrie", "8475071120", "chrisguthrie143@gmail.com", "Columbia", "2298 Hermitage Cir", 5),
    ("Amerispec", "9314103003", "contact@amerispecmidtn.net", "Spring Hill", "2465 Lake Shore Dr", 5),
    ("Jack Hartley", "4193039476", "j.hartley.bhs@gmail.com", "Columbia", "2846 Pulaski Hwy", 5),
    ("Melinda Hanes", "9314864677", "mhanes@hawkston.com", "Columbia", "2410 Park Plus Dr", 4),
    ("Secilia Wagnor", "6157177267", "seciliabryce2023@gmail.com", "Columbia", "1508 Potter Dr", 3),
    ("Lina Wagoner", "6158046383", "lina8809@gmail.com", "Columbia", "1399 Standing Stone Circle", 3),
    ("Smotherman Excavation", "6154891015", "smothermanexcavation@gmail.com", "Columbia", "", 3),
    ("Keith Barnhill", "6154957989", "keith.barnhill@erm.com", "Spring Hill", "2472 Lewisburg Pike", 3),
    ("Dj Gillit", "8063924352", "dgillit@gmail.com", "Columbia", "1926 Bryant Road", 3),
    ("Lowell Brown", "8202884114", "atlasbuildtn@gmail.com", "Culleoka", "2952 Valley Creek Rd", 2),
    ("Samantha Sierra", "6616168583", "mike_sam@att.net", "Spring Hill", "405 Billy Ln", 2),
    ("Kirk Hennig", "6154966459", "kirkhennig@gmail.com", "Spring Hill", "3688 Stone Creek Dr", 2),
    ("Felix Pena", "9312158029", "generalemaildumping@gmail.com", "Culleoka", "2629 Demastus Rd", 2),
    ("Brittney King", "6157109159", "kbrittney106@gmail.com", "Columbia", "1103 Haley St", 2),
    ("Allison Epps", "2142293589", "epps.ali@gmail.com", "Spring Hill", "59 Oak Valley Dr", 2),
    ("Natalie Wagner", "9164128643", "natalie@libertytransactions.com", "Columbia", "2380 Beasley Lane", 2),
    ("Chris Cocilovo", "8058891833", "chriscocilovo@gmail.com", "Chapel Hill", "4012 Caney Creek Ln", 2),
    ("Bill Spradley", "9319815033", "williamasberry64@gmail.com", "Columbia", "909 Everyman Ct", 2),
    ("Vanessa Medrano", "6195193931", "vmedrano@firstwatch.com", "Columbia", "202 S James Campbell", 2),
    ("Jeremy Smith", "6155062797", "jeremybsmith@gmail.com", "Columbia", "1157 Roseland Dr", 2),
    ("Mark Leatherman", "9312557429", "markleatherman10@gmail.com", "Columbia", "3034 Glenstone Dr", 2),
    ("Briana Betker", "9319818789", "brianabetker739@gmail.com", "Columbia", "2624 Bristow Rd", 2),
    ("Carla Gibbs", "9312427123", "carlapfernandez@yahoo.com", "Columbia", "3514 Tobe Robertson Rd", 2),
    ("Shea Heeney", "6154964191", "sheaandbecca@gmail.com", "Columbia", "903 Carters Creek Pike", 1),
    ("Dillon Nab", "3072775547", "dillon.nab@gmail.com", "Mount Pleasant", "4461 W Point Road", 1),
    ("Wilbur Alvarez", "8083439032", "wilburalvarez0148@gmail.com", "Columbia", "2854 Greens Mill Rd", 1),
    ("Paul Rivera", "7142232557", "paul.rivera59@icloud.com", "Columbia", "1151 Old Hwy 99", 1),
    ("Peri Chinoda", "6154389095", "pchinoda2@yahoo.com", "Spring Hill", "2219 Twin Peaks Ct", 1),
    ("Debra Setera", "6153977764", "abennett@scoutrealty.com", "Columbia", "5317 Tobe Robertson Rd", 1),
    ("Loretta Lovett", "2817734844", "lorettaanngilbert@gmail.com", "Lewisburg", "1352 Webb Road", 1),
    ("Floyd White", "6152683557", "fwhite0725@gmail.com", "Columbia", "414 Lake Circle", 1),
    ("Wesley Baird", "4693446395", "asclafani423@gmail.com", "Columbia", "215 Elliott Ct", 1),
    ("Adam Busch", "5638456577", "acbusch52@gmail.com", "Columbia", "3687 Perry Cemetery Road", 1),
    ("Jeff Lamb", "6155049533", "jplambsr@gmail.com", "Columbia", "3907 Kelley Farris Rd", 1),
]


def upgrade() -> None:
    conn = op.get_bind()
    existing = conn.execute(
        sa.text("SELECT 1 FROM outbound_campaigns WHERE id = :id"),
        {"id": CAMPAIGN_ID},
    ).first()
    if existing is not None:
        return

    now = datetime.now(timezone.utc)
    conn.execute(
        sa.text(
            """
            INSERT INTO outbound_campaigns
              (id, name, description, status, source_file, created_by, created_at, updated_at)
            VALUES
              (:id, :name, :description, :status, :source_file, NULL, :now, :now)
            """
        ),
        {
            "id": CAMPAIGN_ID,
            "name": "Email Openers - Spring Follow-Up",
            "description": "TN permit owners who opened the Mar 27 spring service email (1-8x opens). Warm leads for outbound calls.",
            "status": "active",
            "source_file": "Brevo Transactional Export",
            "now": now,
        },
    )

    for i, (name, phone, email, city, address, opens) in enumerate(CONTACTS, start=1):
        cid = f"email-opener-{i}"
        priority = 5 if opens >= 4 else 3 if opens >= 2 else 1
        label = "High" if opens >= 4 else "Medium" if opens >= 2 else "Low"
        conn.execute(
            sa.text(
                """
                INSERT INTO outbound_campaign_contacts
                  (id, campaign_id, account_name, phone, email, address, city, state,
                   system_type, customer_type, call_priority_label, call_status,
                   call_attempts, notes, priority, opens, created_at, updated_at)
                VALUES
                  (:id, :cid, :name, :phone, :email, :address, :city, 'TN',
                   'Residential Septic', 'Residential', :label, 'pending',
                   0, :notes, :priority, :opens, :now, :now)
                """
            ),
            {
                "id": cid,
                "cid": CAMPAIGN_ID,
                "name": name,
                "phone": phone,
                "email": email,
                "address": address or None,
                "city": city,
                "label": label,
                "notes": f"Opened spring service email {opens}x. TN septic permit owner — warm lead.",
                "priority": priority,
                "opens": opens,
                "now": now,
            },
        )


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text("DELETE FROM outbound_campaign_contacts WHERE campaign_id = :id"),
        {"id": CAMPAIGN_ID},
    )
    conn.execute(
        sa.text("DELETE FROM outbound_campaigns WHERE id = :id"),
        {"id": CAMPAIGN_ID},
    )
