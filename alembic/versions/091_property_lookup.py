"""property_lookup table for tank size estimation

Revision ID: 091
Revises: 090
Create Date: 2026-03-06
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "091"
down_revision = "090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "property_lookups",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("address_normalized", sa.String(500), nullable=False),
        sa.Column("address_raw", sa.String(500)),
        sa.Column("city", sa.String(100)),
        sa.Column("state", sa.String(2), server_default="TN"),
        sa.Column("zip_code", sa.String(10)),
        sa.Column("county", sa.String(100), nullable=False),
        sa.Column("sqft", sa.Integer),
        sa.Column("acres", sa.Float),
        sa.Column("improvement_value", sa.Integer),
        sa.Column("total_value", sa.Integer),
        sa.Column("year_built", sa.Integer),
        sa.Column("land_use", sa.String(100)),
        sa.Column("bedrooms", sa.Integer),
        sa.Column("system_type", sa.String(200)),
        sa.Column("designation", sa.String(100)),
        sa.Column("estimated_tank_gallons", sa.Integer, nullable=False, server_default="1000"),
        sa.Column("estimation_confidence", sa.String(20), server_default="medium"),
        sa.Column("estimation_source", sa.String(50)),
        sa.Column("data_source", sa.String(100), nullable=False),
        sa.Column("source_id", sa.String(100)),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )
    op.create_index("idx_property_lookup_addr_city", "property_lookups", ["address_normalized", "city"])
    op.create_index("idx_property_lookup_county", "property_lookups", ["county"])
    op.create_index("idx_property_lookup_zip", "property_lookups", ["zip_code"])
    # Trigram index for fuzzy matching
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute("CREATE INDEX idx_property_lookup_addr_trgm ON property_lookups USING gin (address_normalized gin_trgm_ops)")


def downgrade() -> None:
    op.drop_index("idx_property_lookup_addr_trgm", table_name="property_lookups")
    op.drop_index("idx_property_lookup_zip", table_name="property_lookups")
    op.drop_index("idx_property_lookup_county", table_name="property_lookups")
    op.drop_index("idx_property_lookup_addr_city", table_name="property_lookups")
    op.drop_table("property_lookups")
