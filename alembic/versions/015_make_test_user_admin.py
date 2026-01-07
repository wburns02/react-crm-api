"""Make test user an admin for seeding

Revision ID: 015_make_test_user_admin
Revises: 014_seed_journey_steps
Create Date: 2026-01-07
"""
from alembic import op

revision = '015_make_test_user_admin'
down_revision = '014_seed_journey_steps'
branch_labels = None
depends_on = None


def upgrade():
    # Make the test user an admin so they can seed data
    op.execute("""
        UPDATE api_users
        SET is_superuser = true
        WHERE email = 'test@macseptic.com';
    """)


def downgrade():
    op.execute("""
        UPDATE api_users
        SET is_superuser = false
        WHERE email = 'test@macseptic.com';
    """)
