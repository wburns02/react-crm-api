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
    # Seed journey steps for existing journeys
    op.execute("""
        -- Onboarding Journey Steps
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, condition_rules, action_config, is_required, is_active, created_at, updated_at)
        SELECT
            j.id,
            step_data.name,
            step_data.description,
            step_data.step_type::cs_journey_step_type_enum,
            step_data.step_order,
            step_data.wait_duration_hours,
            step_data.condition_rules::jsonb,
            step_data.action_config::jsonb,
            true,
            true,
            NOW(),
            NOW()
        FROM cs_journeys j
        CROSS JOIN (VALUES
            ('Welcome Email', 'Send personalized welcome email with next steps', 'email', 1, NULL, NULL, '{"template": "welcome", "subject": "Welcome to Mac-Septic!"}'),
            ('Wait 24 Hours', 'Allow customer time to explore', 'wait', 2, 24, NULL, NULL),
            ('Account Setup Reminder', 'Remind customer to complete profile', 'email', 3, NULL, NULL, '{"template": "setup_reminder"}'),
            ('CSM Introduction Call', 'Schedule introductory call with assigned CSM', 'task', 4, NULL, NULL, '{"task_type": "call", "assignee_role": "csm"}'),
            ('Check Profile Complete', 'Verify customer has completed their profile', 'condition', 5, NULL, '{"field": "profile_complete", "operator": "eq", "value": true}', NULL),
            ('Schedule First Service', 'Help customer schedule their first service', 'task', 6, NULL, NULL, '{"task_type": "meeting", "title": "Schedule First Service"}'),
            ('Wait for Service', 'Wait for first service to be completed', 'wait', 7, 168, NULL, NULL),
            ('Post-Service Follow-up', 'Send satisfaction survey after first service', 'email', 8, NULL, NULL, '{"template": "post_service_survey"}'),
            ('NPS Survey', 'Request Net Promoter Score feedback', 'email', 9, NULL, NULL, '{"template": "nps_survey"}'),
            ('Graduation Check', 'Verify customer is fully onboarded', 'health_check', 10, NULL, NULL, '{"min_health_score": 70}')
        ) AS step_data(name, description, step_type, step_order, wait_duration_hours, condition_rules, action_config)
        WHERE LOWER(j.name) LIKE '%onboarding%'
        AND NOT EXISTS (SELECT 1 FROM cs_journey_steps WHERE journey_id = j.id);

        -- Risk Mitigation Journey Steps
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, condition_rules, action_config, is_required, is_active, created_at, updated_at)
        SELECT
            j.id,
            step_data.name,
            step_data.description,
            step_data.step_type::cs_journey_step_type_enum,
            step_data.step_order,
            step_data.wait_duration_hours,
            step_data.condition_rules::jsonb,
            step_data.action_config::jsonb,
            true,
            true,
            NOW(),
            NOW()
        FROM cs_journeys j
        CROSS JOIN (VALUES
            ('Risk Alert', 'Notify CSM of at-risk customer', 'custom', 1, NULL, NULL, '{"channel": "slack", "priority": "high"}'),
            ('Health Score Review', 'Analyze health score components', 'health_check', 2, NULL, NULL, '{"review_type": "detailed"}'),
            ('Immediate Outreach', 'CSM calls customer within 24 hours', 'task', 3, NULL, NULL, '{"task_type": "call", "priority": "critical", "due_hours": 24}'),
            ('Concern Documentation', 'Document customer concerns and issues', 'task', 4, NULL, NULL, '{"task_type": "documentation"}'),
            ('Recovery Plan Creation', 'Create action plan to address issues', 'task', 5, NULL, NULL, '{"task_type": "internal", "title": "Create Recovery Plan"}'),
            ('Executive Escalation Check', 'Determine if executive involvement needed', 'condition', 6, NULL, '{"field": "health_score", "operator": "lt", "value": 30}', NULL),
            ('Recovery Actions', 'Execute recovery plan actions', 'task', 7, NULL, NULL, '{"task_type": "follow_up"}'),
            ('Wait 7 Days', 'Allow time for recovery actions to take effect', 'wait', 8, 168, NULL, NULL),
            ('Progress Check-in', 'Follow up call to assess progress', 'task', 9, NULL, NULL, '{"task_type": "call", "title": "Recovery Progress Check"}'),
            ('Health Re-evaluation', 'Re-calculate health score after intervention', 'health_check', 10, NULL, NULL, '{"target_score": 60}')
        ) AS step_data(name, description, step_type, step_order, wait_duration_hours, condition_rules, action_config)
        WHERE LOWER(j.name) LIKE '%risk%' OR LOWER(j.name) LIKE '%mitigation%'
        AND NOT EXISTS (SELECT 1 FROM cs_journey_steps WHERE journey_id = j.id);

        -- Advocacy Development Journey Steps
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_duration_hours, condition_rules, action_config, is_required, is_active, created_at, updated_at)
        SELECT
            j.id,
            step_data.name,
            step_data.description,
            step_data.step_type::cs_journey_step_type_enum,
            step_data.step_order,
            step_data.wait_duration_hours,
            step_data.condition_rules::jsonb,
            step_data.action_config::jsonb,
            true,
            true,
            NOW(),
            NOW()
        FROM cs_journeys j
        CROSS JOIN (VALUES
            ('Promoter Identification', 'Confirm customer is a promoter (NPS 9-10)', 'condition', 1, NULL, '{"field": "nps_score", "operator": "gte", "value": 9}', NULL),
            ('Thank You Email', 'Send personalized thank you for high NPS', 'email', 2, NULL, NULL, '{"template": "promoter_thanks"}'),
            ('Case Study Invitation', 'Invite customer to participate in case study', 'email', 3, NULL, NULL, '{"template": "case_study_invite"}'),
            ('Wait for Response', 'Allow time to consider case study', 'wait', 4, 72, NULL, NULL),
            ('Referral Program Introduction', 'Introduce referral rewards program', 'email', 5, NULL, NULL, '{"template": "referral_program"}'),
            ('Review Request', 'Request online review', 'email', 6, NULL, NULL, '{"template": "review_request"}'),
            ('Social Media Engagement', 'Invite to follow and engage on social', 'in_app_message', 7, NULL, NULL, '{"message_type": "banner"}'),
            ('Advocacy Program Enrollment', 'Enroll in formal advocacy program', 'custom', 8, NULL, NULL, '{"field": "is_advocate", "value": true}')
        ) AS step_data(name, description, step_type, step_order, wait_duration_hours, condition_rules, action_config)
        WHERE LOWER(j.name) LIKE '%advocacy%'
        AND NOT EXISTS (SELECT 1 FROM cs_journey_steps WHERE journey_id = j.id);
    """)


def downgrade():
    # Remove seeded journey steps
    op.execute("""
        DELETE FROM cs_journey_steps
        WHERE name IN (
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
