"""seed hr document templates

Revision ID: 100_hr_seed_document_templates
Revises: 099_hr_esign_tables
"""
import asyncio


revision = "100_hr_seed_document_templates"
down_revision = "099_hr_esign_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    from app.database import async_session_maker
    from app.hr.esign.seed_templates import seed_document_templates

    async def _run() -> None:
        async with async_session_maker() as db:
            await seed_document_templates(db)
            await db.commit()

    asyncio.run(_run())


def downgrade() -> None:
    from alembic import op
    from sqlalchemy import text

    op.execute(
        text(
            "DELETE FROM hr_document_templates WHERE kind IN ("
            "'employment_agreement_2026','w4_2026','i9','adp_info','benefits_election'"
            ")"
        )
    )
