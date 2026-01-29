"""Create bookings table for direct book & pay

Revision ID: 029_create_bookings
Revises: 028_create_dump_sites_standalone
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '029_create_bookings'
down_revision = '028_create_dump_sites_standalone'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'bookings',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('customer_id', sa.Integer, sa.ForeignKey('customers.id'), nullable=True),

        # Customer info
        sa.Column('customer_first_name', sa.String(100), nullable=False),
        sa.Column('customer_last_name', sa.String(100), nullable=False),
        sa.Column('customer_email', sa.String(255), nullable=True),
        sa.Column('customer_phone', sa.String(20), nullable=False),
        sa.Column('service_address', sa.Text, nullable=True),

        # Service details
        sa.Column('service_type', sa.String(50), nullable=False, server_default='pumping'),
        sa.Column('scheduled_date', sa.Date, nullable=False),
        sa.Column('time_window_start', sa.Time, nullable=True),
        sa.Column('time_window_end', sa.Time, nullable=True),
        sa.Column('time_slot', sa.String(20), nullable=True),

        # Pricing
        sa.Column('base_price', sa.Numeric(10, 2), nullable=False),
        sa.Column('included_gallons', sa.Integer, nullable=False, server_default='1750'),
        sa.Column('overage_rate', sa.Numeric(10, 4), nullable=False, server_default='0.45'),

        # Actual service
        sa.Column('actual_gallons', sa.Integer, nullable=True),
        sa.Column('overage_gallons', sa.Integer, nullable=True),
        sa.Column('overage_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('final_amount', sa.Numeric(10, 2), nullable=True),

        # Payment
        sa.Column('clover_charge_id', sa.String(100), nullable=True),
        sa.Column('preauth_amount', sa.Numeric(10, 2), nullable=True),
        sa.Column('payment_status', sa.String(20), nullable=True, server_default='pending'),
        sa.Column('captured_at', sa.DateTime(timezone=True), nullable=True),

        # Test mode
        sa.Column('is_test', sa.Boolean, nullable=False, server_default='false'),

        # Status
        sa.Column('status', sa.String(20), nullable=True, server_default='confirmed'),

        # Consent
        sa.Column('overage_acknowledged', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('sms_consent', sa.Boolean, nullable=False, server_default='false'),

        # Notes
        sa.Column('customer_notes', sa.Text, nullable=True),
        sa.Column('internal_notes', sa.Text, nullable=True),

        # Timestamps
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
    )

    # Create indexes
    op.create_index('ix_bookings_scheduled_date', 'bookings', ['scheduled_date'])
    op.create_index('ix_bookings_customer_phone', 'bookings', ['customer_phone'])
    op.create_index('ix_bookings_payment_status', 'bookings', ['payment_status'])
    op.create_index('ix_bookings_status', 'bookings', ['status'])


def downgrade() -> None:
    op.drop_index('ix_bookings_status')
    op.drop_index('ix_bookings_payment_status')
    op.drop_index('ix_bookings_customer_phone')
    op.drop_index('ix_bookings_scheduled_date')
    op.drop_table('bookings')
