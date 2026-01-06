"""Add OAuth2 tables for public API

Revision ID: 011_add_oauth_tables
Revises: 010_add_job_costs
Create Date: 2026-01-04

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '011_add_oauth_tables'
down_revision = '010_add_job_costs'
branch_labels = None
depends_on = None


def upgrade():
    # API Clients table
    op.create_table(
        'api_clients',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('client_id', sa.String(64), unique=True, nullable=False, index=True),
        sa.Column('client_secret_hash', sa.String(255), nullable=False),
        sa.Column('name', sa.String(255), nullable=False),
        sa.Column('description', sa.Text, nullable=True),
        sa.Column('scopes', sa.String(500), server_default='read'),
        sa.Column('rate_limit_per_minute', sa.Integer, server_default='100'),
        sa.Column('rate_limit_per_hour', sa.Integer, server_default='1000'),
        sa.Column('is_active', sa.Boolean, server_default='true'),
        sa.Column('owner_user_id', sa.Integer, sa.ForeignKey('api_users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), onupdate=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    )

    # API Tokens table
    op.create_table(
        'api_tokens',
        sa.Column('id', sa.Integer, primary_key=True, autoincrement=True),
        sa.Column('token_hash', sa.String(255), unique=True, nullable=False, index=True),
        sa.Column('token_type', sa.String(20), server_default='Bearer'),
        sa.Column('client_id', sa.Integer, sa.ForeignKey('api_clients.id', ondelete='CASCADE'), nullable=False),
        sa.Column('scopes', sa.String(500), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('refresh_token_hash', sa.String(255), unique=True, nullable=True, index=True),
        sa.Column('refresh_expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_revoked', sa.Boolean, server_default='false'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column('last_used_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create index on client_id for faster token lookups
    op.create_index('ix_api_tokens_client_id', 'api_tokens', ['client_id'])


def downgrade():
    op.drop_index('ix_api_tokens_client_id', table_name='api_tokens')
    op.drop_table('api_tokens')
    op.drop_table('api_clients')
