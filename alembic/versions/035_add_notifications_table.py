"""Add notifications table for in-app notifications

Revision ID: 035_add_notifications
Revises: 034_add_service_intervals
Create Date: 2026-01-29

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision = '035_add_notifications'
down_revision = '034_add_service_intervals'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'notifications',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('user_id', sa.Integer, sa.ForeignKey('api_users.id'), nullable=False, index=True),
        sa.Column('type', sa.String(50), nullable=False, index=True),
        sa.Column('title', sa.String(255), nullable=False),
        sa.Column('message', sa.Text, nullable=False),
        sa.Column('read', sa.Boolean, default=False, index=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('link', sa.String(500), nullable=True),
        sa.Column('metadata', postgresql.JSON, nullable=True),
        sa.Column('source', sa.String(50), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), index=True),
    )

    # Create composite index for common queries
    op.create_index(
        'ix_notifications_user_unread',
        'notifications',
        ['user_id', 'read'],
        postgresql_where=sa.text('read = false')
    )


def downgrade():
    op.drop_index('ix_notifications_user_unread', table_name='notifications')
    op.drop_table('notifications')
