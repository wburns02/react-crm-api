"""add cascade delete customer fks

Revision ID: 076
Revises: 075
Create Date: 2026-02-24

"""
from alembic import op

# revision identifiers, used by Alembic.
revision = '076'
down_revision = '075'
branch_labels = None
depends_on = None


# Tables that should CASCADE (child records deleted with customer)
CASCADE_TABLES = [
    'work_orders',
    'activities',
    'contracts',
    'quotes',
    'invoices',
    'equipment',
    'customer_service_schedules',
    'service_reminders',
    'sms_consent',
    # customer_success tables
    'cs_touchpoints',
    'cs_tasks',
    'cs_escalations',
    'cs_campaign_recipients',
    'cs_survey_responses',
    'cs_survey_invitations',
    'cs_customer_health_scores',
    'cs_health_score_history',
    'cs_customer_journey_enrollments',
    'cs_playbook_enrollments',
    'cs_send_time_preferences',
    'cs_collaboration_notes',
    'cs_collaboration_activities',
    'cs_customer_segments',
]

# Tables that should SET NULL (keep record but clear customer reference)
SET_NULL_TABLES = [
    'call_logs',
    'messages',
    'bookings',
    'payments',
    'tickets',
    'geofence_alerts',
    'inbound_emails',
]


def upgrade():
    for table in CASCADE_TABLES:
        op.execute(f"""
            ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_customer_id_fkey;
            ALTER TABLE {table} ADD CONSTRAINT {table}_customer_id_fkey
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE CASCADE;
        """)

    for table in SET_NULL_TABLES:
        op.execute(f"""
            ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_customer_id_fkey;
            ALTER TABLE {table} ADD CONSTRAINT {table}_customer_id_fkey
                FOREIGN KEY (customer_id) REFERENCES customers(id) ON DELETE SET NULL;
        """)


def downgrade():
    for table in CASCADE_TABLES:
        op.execute(f"""
            ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_customer_id_fkey;
            ALTER TABLE {table} ADD CONSTRAINT {table}_customer_id_fkey
                FOREIGN KEY (customer_id) REFERENCES customers(id);
        """)

    for table in SET_NULL_TABLES:
        op.execute(f"""
            ALTER TABLE {table} DROP CONSTRAINT IF EXISTS {table}_customer_id_fkey;
            ALTER TABLE {table} ADD CONSTRAINT {table}_customer_id_fkey
                FOREIGN KEY (customer_id) REFERENCES customers(id);
        """)
