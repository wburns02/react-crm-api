"""Seed journey steps for existing journeys

Revision ID: 014_seed_journey_steps
Revises: 013_fix_journey_schema
Create Date: 2026-01-07

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '014_seed_journey_steps'
down_revision = '013_fix_journey_schema'
branch_labels = None
depends_on = None


def upgrade():
    # Seed Onboarding Journey Steps
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Welcome Email', 'Send personalized welcome email with next steps', 'email', 1, NULL, '{"template": "welcome", "subject": "Welcome to Mac-Septic!"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%' AND NOT EXISTS (SELECT 1 FROM cs_journey_steps WHERE journey_id = cs_journeys.id);
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Wait 24 Hours', 'Allow customer time to explore', 'wait', 2, 24, NULL, true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Account Setup Reminder', 'Remind customer to complete profile', 'email', 3, NULL, '{"template": "setup_reminder"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'CSM Introduction Call', 'Schedule introductory call with assigned CSM', 'task', 4, NULL, '{"task_type": "call", "assignee_role": "csm"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, condition_rules, is_required, is_active, created_at, updated_at)
        SELECT id, 'Check Profile Complete', 'Verify customer has completed their profile', 'condition', 5, NULL, '{"field": "profile_complete", "operator": "eq", "value": true}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Schedule First Service', 'Help customer schedule their first service', 'task', 6, NULL, '{"task_type": "meeting", "title": "Schedule First Service"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Wait for Service', 'Wait for first service to be completed', 'wait', 7, 168, NULL, true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Post-Service Follow-up', 'Send satisfaction survey after first service', 'email', 8, NULL, '{"template": "post_service_survey"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'NPS Survey', 'Request Net Promoter Score feedback', 'email', 9, NULL, '{"template": "nps_survey"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Graduation Check', 'Verify customer is fully onboarded', 'health_check', 10, NULL, '{"min_health_score": 70}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%onboarding%';
    """)

    # Seed Risk Mitigation Journey Steps
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Risk Alert', 'Notify CSM of at-risk customer', 'custom', 1, NULL, '{"channel": "slack", "priority": "high"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%' AND NOT EXISTS (SELECT 1 FROM cs_journey_steps WHERE journey_id = cs_journeys.id);
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Health Score Review', 'Analyze health score components', 'health_check', 2, NULL, '{"review_type": "detailed"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Immediate Outreach', 'CSM calls customer within 24 hours', 'task', 3, NULL, '{"task_type": "call", "priority": "critical", "due_hours": 24}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Concern Documentation', 'Document customer concerns and issues', 'task', 4, NULL, '{"task_type": "documentation"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Recovery Plan Creation', 'Create action plan to address issues', 'task', 5, NULL, '{"task_type": "internal", "title": "Create Recovery Plan"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, condition_rules, is_required, is_active, created_at, updated_at)
        SELECT id, 'Executive Escalation Check', 'Determine if executive involvement needed', 'condition', 6, NULL, '{"field": "health_score", "operator": "lt", "value": 30}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Recovery Actions', 'Execute recovery plan actions', 'task', 7, NULL, '{"task_type": "follow_up"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Wait 7 Days', 'Allow time for recovery actions to take effect', 'wait', 8, 168, NULL, true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Progress Check-in', 'Follow up call to assess progress', 'task', 9, NULL, '{"task_type": "call", "title": "Recovery Progress Check"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Health Re-evaluation', 'Re-calculate health score after intervention', 'health_check', 10, NULL, '{"target_score": 60}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%risk%';
    """)

    # Seed Advocacy Journey Steps
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, condition_rules, is_required, is_active, created_at, updated_at)
        SELECT id, 'Promoter Identification', 'Confirm customer is a promoter (NPS 9-10)', 'condition', 1, NULL, '{"field": "nps_score", "operator": "gte", "value": 9}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%advocacy%' AND NOT EXISTS (SELECT 1 FROM cs_journey_steps WHERE journey_id = cs_journeys.id);
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Thank You Email', 'Send personalized thank you for high NPS', 'email', 2, NULL, '{"template": "promoter_thanks"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%advocacy%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Case Study Invitation', 'Invite customer to participate in case study', 'email', 3, NULL, '{"template": "case_study_invite"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%advocacy%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Wait for Response', 'Allow time to consider case study', 'wait', 4, 72, NULL, true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%advocacy%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Referral Program Introduction', 'Introduce referral rewards program', 'email', 5, NULL, '{"template": "referral_program"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%advocacy%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Review Request', 'Request online review', 'email', 6, NULL, '{"template": "review_request"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%advocacy%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Social Media Engagement', 'Invite to follow and engage on social', 'in_app_message', 7, NULL, '{"message_type": "banner"}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%advocacy%';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, action_config, is_required, is_active, created_at, updated_at)
        SELECT id, 'Advocacy Program Enrollment', 'Enroll in formal advocacy program', 'custom', 8, NULL, '{"field": "is_advocate", "value": true}', true, true, NOW(), NOW()
        FROM cs_journeys WHERE LOWER(name) LIKE '%advocacy%';
    """)


def downgrade():
    op.execute("""
        DELETE FROM cs_journey_steps WHERE name IN (
            'Welcome Email', 'Wait 24 Hours', 'Account Setup Reminder', 'CSM Introduction Call',
            'Check Profile Complete', 'Schedule First Service', 'Wait for Service',
            'Post-Service Follow-up', 'NPS Survey', 'Graduation Check',
            'Risk Alert', 'Health Score Review', 'Immediate Outreach', 'Concern Documentation',
            'Recovery Plan Creation', 'Executive Escalation Check', 'Recovery Actions',
            'Wait 7 Days', 'Progress Check-in', 'Health Re-evaluation',
            'Promoter Identification', 'Thank You Email', 'Case Study Invitation',
            'Wait for Response', 'Referral Program Introduction', 'Review Request',
            'Social Media Engagement', 'Advocacy Program Enrollment'
        );
    """)
