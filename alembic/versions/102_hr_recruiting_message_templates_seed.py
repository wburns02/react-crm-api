"""seed default recruiting message templates

Revision ID: 102
Revises: 101
"""
import uuid

from alembic import op
from sqlalchemy import text


revision = "102"
down_revision = "101"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Import lazily so alembic's initial module scan doesn't need the app
    # package on sys.path.
    from app.hr.recruiting.message_templates import DEFAULTS

    bind = op.get_bind()
    existing = {
        row[0]
        for row in bind.execute(
            text("SELECT stage FROM hr_recruiting_message_templates")
        ).fetchall()
    }
    insert = text(
        "INSERT INTO hr_recruiting_message_templates "
        "(id, stage, channel, body, active) "
        "VALUES (CAST(:id AS uuid), :stage, 'sms', :body, true)"
    )
    for t in DEFAULTS:
        if t["stage"] in existing:
            continue
        bind.execute(insert, {"id": str(uuid.uuid4()), "stage": t["stage"], "body": t["body"]})


def downgrade() -> None:
    op.execute(
        "DELETE FROM hr_recruiting_message_templates WHERE stage IN ("
        "'screen','ride_along','offer','hired','rejected')"
    )
