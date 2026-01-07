"""Seed world-class journey templates for field service CRM

Revision ID: 015_seed_world_class_journeys
Revises: 014_seed_journey_steps
Create Date: 2026-01-07
"""
from alembic import op
import sqlalchemy as sa

revision = '015_seed_world_class_journeys'
down_revision = '014_seed_journey_steps'
branch_labels = None
depends_on = None


def upgrade():
    # First, clean up old test journeys and their steps
    op.execute("""
        DELETE FROM cs_journey_steps WHERE journey_id IN (
            SELECT id FROM cs_journeys WHERE name IN (
                'Onboarding Journey', 'Risk Mitigation Journey', 'Advocacy Development'
            )
        );
        DELETE FROM cs_journeys WHERE name IN (
            'Onboarding Journey', 'Risk Mitigation Journey', 'Advocacy Development'
        );
    """)

    # ========================================
    # JOURNEY 1: New Customer Welcome (Residential)
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'New Customer Welcome (Residential)',
            'Comprehensive onboarding journey for new residential customers. Builds trust, educates on services, and sets expectations for ongoing maintenance.',
            'onboarding',
            'event',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Welcome Email', 'Personalized welcome with thank you and service confirmation', 'email', 1, NULL,
            '{"template": "residential_welcome", "subject": "Welcome to Mac-Septic! Your Service is Confirmed", "personalization": ["first_name", "service_date", "technician_name"]}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'SMS Confirmation', 'Text message with appointment details and technician info', 'sms', 2, NULL,
            '{"template": "appointment_confirm_sms", "include_tech_photo": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Wait for Service', 'Wait until service is completed', 'wait', 3, 48,
            NULL, true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Post-Service Survey', 'Request feedback on service quality', 'email', 4, 2,
            '{"template": "nps_survey", "subject": "How did we do? Quick 30-second survey", "survey_type": "nps"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Check NPS Score', 'Branch based on customer satisfaction', 'condition', 5, 24,
            '{"field": "nps_score", "operator": "gte", "value": 8, "true_branch": 6, "false_branch": 8}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Request Review (Happy Path)', 'Ask satisfied customers for Google/Yelp review', 'email', 6, 48,
            '{"template": "review_request", "subject": "Share your experience - it means the world to us!", "platforms": ["google", "yelp"]}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Maintenance Education', 'Educational content about septic care', 'email', 7, 168,
            '{"template": "septic_care_tips", "subject": "5 Tips to Keep Your Septic System Healthy"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'CSM Follow-up Call (Unhappy Path)', 'Personal outreach to address concerns', 'task', 8, 4,
            '{"task_type": "call", "priority": "high", "assignee_role": "csm", "script": "service_recovery"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Schedule Maintenance Reminder', 'Set up recurring maintenance schedule', 'email', 9, 720,
            '{"template": "maintenance_schedule", "subject": "Time to schedule your annual maintenance!"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Referral Program Intro', 'Introduce referral rewards program', 'email', 10, 1440,
            '{"template": "referral_program", "subject": "Earn $50 for every friend you refer!", "reward_amount": 50}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Customer Welcome (Residential)';
    """)

    # ========================================
    # JOURNEY 2: Emergency Service Flow
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'Emergency Service Response',
            'Rapid response journey for emergency septic issues. Prioritizes speed, communication, and customer reassurance during stressful situations.',
            'custom',
            'event',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Immediate Confirmation', 'Instant SMS confirming emergency dispatch', 'sms', 1, NULL,
            '{"template": "emergency_dispatch", "priority": "critical", "include_eta": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Emergency Service Response';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Dispatch Alert', 'Notify on-call technician immediately', 'webhook', 2, NULL,
            '{"endpoint": "/dispatch/emergency", "method": "POST", "include_customer_info": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Emergency Service Response';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Technician En Route SMS', 'Notify customer when tech is on the way', 'sms', 3, NULL,
            '{"template": "tech_en_route", "include_live_tracking": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Emergency Service Response';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Service Completion Check', 'Verify service was completed successfully', 'condition', 4, 4,
            '{"field": "service_status", "operator": "eq", "value": "completed"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Emergency Service Response';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Emergency Follow-up Call', 'Personal check-in after emergency service', 'task', 5, 24,
            '{"task_type": "call", "priority": "high", "script": "emergency_followup"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Emergency Service Response';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Prevention Tips Email', 'Educate on preventing future emergencies', 'email', 6, 72,
            '{"template": "emergency_prevention", "subject": "How to Prevent Future Septic Emergencies"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Emergency Service Response';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Maintenance Plan Offer', 'Offer preventive maintenance plan', 'email', 7, 168,
            '{"template": "maintenance_plan_offer", "subject": "Never worry about emergencies again - Special offer inside"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Emergency Service Response';
    """)

    # ========================================
    # JOURNEY 3: At-Risk Customer Recovery
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'At-Risk Customer Recovery',
            'Proactive intervention journey for customers showing signs of churn. Uses health score triggers and personalized outreach to rebuild relationship.',
            'risk_mitigation',
            'health_change',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Health Score Alert', 'Internal notification when customer becomes at-risk', 'custom', 1, NULL,
            '{"notification_type": "slack", "channel": "#cs-alerts", "priority": "high"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'At-Risk Customer Recovery';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Assign CSM Owner', 'Assign dedicated success manager', 'task', 2, NULL,
            '{"task_type": "internal", "auto_assign": true, "criteria": "workload_balanced"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'At-Risk Customer Recovery';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Personal Outreach Call', 'CSM calls to understand concerns', 'task', 3, 4,
            '{"task_type": "call", "priority": "critical", "script": "at_risk_discovery", "due_hours": 24}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'At-Risk Customer Recovery';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Document Concerns', 'Log customer feedback and issues', 'task', 4, NULL,
            '{"task_type": "documentation", "required_fields": ["concerns", "resolution_plan"]}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'At-Risk Customer Recovery';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Special Offer Email', 'Send retention offer based on concerns', 'email', 5, 24,
            '{"template": "retention_offer", "subject": "A special thank you for being our customer", "offer_type": "dynamic"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'At-Risk Customer Recovery';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Wait for Response', 'Allow time for customer to respond', 'wait', 6, 168,
            NULL, true, NOW(), NOW() FROM cs_journeys WHERE name = 'At-Risk Customer Recovery';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Check Engagement', 'Evaluate if customer re-engaged', 'condition', 7, NULL,
            '{"field": "last_interaction_days", "operator": "lte", "value": 7}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'At-Risk Customer Recovery';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Executive Escalation', 'Escalate to management if still at-risk', 'task', 8, 24,
            '{"task_type": "escalation", "escalate_to": "manager", "reason": "persistent_risk"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'At-Risk Customer Recovery';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Health Score Re-check', 'Measure improvement after intervention', 'health_check', 9, 336,
            '{"target_improvement": 15, "success_threshold": 60}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'At-Risk Customer Recovery';
    """)

    # ========================================
    # JOURNEY 4: Referral & Advocacy Program
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'Referral & Advocacy Program',
            'Turn happy customers into brand advocates. Multi-touch journey to encourage referrals, reviews, and social sharing.',
            'advocacy',
            'event',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Identify Promoters', 'Check NPS score qualifies for advocacy', 'condition', 1, NULL,
            '{"field": "nps_score", "operator": "gte", "value": 9}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Referral & Advocacy Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Thank You Email', 'Personal thank you for high rating', 'email', 2, NULL,
            '{"template": "promoter_thanks", "subject": "Thank you for the amazing feedback!"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Referral & Advocacy Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Referral Program Invite', 'Introduce referral rewards', 'email', 3, 72,
            '{"template": "referral_invite", "subject": "Share the love - Earn $50 per referral!", "reward": 50}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Referral & Advocacy Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Review Request', 'Ask for Google/Yelp review', 'email', 4, 168,
            '{"template": "review_request", "subject": "Would you recommend us? Leave a quick review", "platforms": ["google", "yelp", "facebook"]}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Referral & Advocacy Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Social Share Prompt', 'Encourage social media sharing', 'in_app_message', 5, 336,
            '{"message_type": "banner", "cta": "Share your experience on Facebook"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Referral & Advocacy Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Case Study Invitation', 'Invite to participate in case study', 'email', 6, 720,
            '{"template": "case_study_invite", "subject": "We would love to feature your story!"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Referral & Advocacy Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'VIP Status Upgrade', 'Enroll in VIP customer program', 'custom', 7, NULL,
            '{"action": "update_segment", "segment": "vip_customers", "benefits": ["priority_scheduling", "discount_10"]}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Referral & Advocacy Program';
    """)

    # ========================================
    # JOURNEY 5: Seasonal Maintenance Campaign
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'Seasonal Maintenance Campaign',
            'Proactive seasonal outreach to schedule preventive maintenance. Reduces emergencies and builds recurring revenue.',
            'custom',
            'scheduled',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Season Start Email', 'Initial seasonal reminder', 'email', 1, NULL,
            '{"template": "seasonal_reminder", "subject": "Spring is here! Time for your septic check-up"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Seasonal Maintenance Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Check Last Service', 'Verify if maintenance is due', 'condition', 2, 72,
            '{"field": "months_since_service", "operator": "gte", "value": 10}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Seasonal Maintenance Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Early Bird Offer', 'Special pricing for early booking', 'email', 3, NULL,
            '{"template": "early_bird_offer", "subject": "Book now and save 15% on spring maintenance", "discount": 15}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Seasonal Maintenance Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'SMS Reminder', 'Text reminder for non-responders', 'sms', 4, 168,
            '{"template": "seasonal_sms", "message": "Dont miss our spring special! Book your septic maintenance today."}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Seasonal Maintenance Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Outbound Call', 'Phone call for high-value customers', 'task', 5, 336,
            '{"task_type": "call", "priority": "medium", "script": "seasonal_booking"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Seasonal Maintenance Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Last Chance Email', 'Final reminder before season ends', 'email', 6, 504,
            '{"template": "last_chance", "subject": "Last chance for spring pricing - ends this week!"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Seasonal Maintenance Campaign';
    """)

    # ========================================
    # JOURNEY 6: Win-Back Campaign
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'Win-Back Campaign',
            'Re-engage lapsed customers who havent booked service in 18+ months. Personalized offers and reminders to reactivate relationship.',
            'win_back',
            'scheduled',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'We Miss You Email', 'Warm re-engagement message', 'email', 1, NULL,
            '{"template": "win_back_intro", "subject": "We miss you! Heres a special welcome back offer"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Win-Back Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Special Offer', 'Exclusive discount for returning', 'email', 2, 168,
            '{"template": "win_back_offer", "subject": "25% off your next service - just for you", "discount": 25, "expiry_days": 30}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Win-Back Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Check Response', 'See if customer engaged', 'condition', 3, 336,
            '{"field": "email_opened", "operator": "eq", "value": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Win-Back Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Personal Call', 'Phone outreach for engaged leads', 'task', 4, 24,
            '{"task_type": "call", "priority": "medium", "script": "win_back_call"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Win-Back Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Final Reminder', 'Last attempt before marking inactive', 'email', 5, 504,
            '{"template": "win_back_final", "subject": "Your offer expires soon - dont miss out!"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Win-Back Campaign';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Mark Inactive', 'Update customer status if no response', 'custom', 6, 720,
            '{"action": "update_status", "status": "inactive", "reason": "win_back_failed"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Win-Back Campaign';
    """)

    # ========================================
    # JOURNEY 7: Commercial Customer Onboarding
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'Commercial Customer Onboarding',
            'Comprehensive onboarding for commercial/business customers with dedicated account management and custom service agreements.',
            'onboarding',
            'event',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Welcome Package', 'Send commercial welcome kit', 'email', 1, NULL,
            '{"template": "commercial_welcome", "subject": "Welcome to Mac-Septic Commercial Services", "attachments": ["service_agreement", "maintenance_schedule"]}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Commercial Customer Onboarding';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Assign Account Manager', 'Dedicated AM assignment', 'task', 2, NULL,
            '{"task_type": "internal", "role": "account_manager", "criteria": "industry_expertise"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Commercial Customer Onboarding';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Kickoff Call', 'Schedule onboarding call with AM', 'task', 3, 24,
            '{"task_type": "meeting", "duration_minutes": 60, "agenda": "needs_assessment"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Commercial Customer Onboarding';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Site Assessment', 'Schedule on-site facility review', 'task', 4, 72,
            '{"task_type": "site_visit", "checklist": "commercial_assessment"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Commercial Customer Onboarding';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Custom Service Plan', 'Deliver tailored service proposal', 'email', 5, 168,
            '{"template": "commercial_proposal", "subject": "Your Custom Service Plan is Ready"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Commercial Customer Onboarding';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Contract Signature', 'Send contract for e-signature', 'webhook', 6, 72,
            '{"endpoint": "/contracts/send", "method": "POST", "document_type": "service_agreement"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Commercial Customer Onboarding';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Portal Training', 'Train on customer portal usage', 'email', 7, 168,
            '{"template": "portal_training", "subject": "Get started with your Mac-Septic Portal", "video_link": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Commercial Customer Onboarding';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, '30-Day Check-in', 'First month success review', 'task', 8, 720,
            '{"task_type": "call", "agenda": "30_day_review", "survey": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Commercial Customer Onboarding';
    """)

    # ========================================
    # JOURNEY 8: Annual Contract Renewal
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'Annual Contract Renewal',
            'Proactive renewal journey starting 90 days before contract expiration. Focus on value demonstration and retention.',
            'renewal',
            'renewal_window',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, '90-Day Notice', 'Initial renewal reminder', 'email', 1, NULL,
            '{"template": "renewal_90_day", "subject": "Your service agreement renews in 90 days"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Annual Contract Renewal';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Value Report', 'Send annual service summary', 'email', 2, 168,
            '{"template": "annual_value_report", "subject": "Your Year in Review with Mac-Septic", "include_savings": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Annual Contract Renewal';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Renewal Call', 'Personal outreach to discuss renewal', 'task', 3, 504,
            '{"task_type": "call", "priority": "high", "script": "renewal_discussion"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Annual Contract Renewal';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Check Renewal Status', 'Verify if renewed', 'condition', 4, 336,
            '{"field": "contract_status", "operator": "eq", "value": "renewed"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Annual Contract Renewal';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Loyalty Discount', 'Offer retention discount if hesitant', 'email', 5, 72,
            '{"template": "loyalty_discount", "subject": "Thank you for your loyalty - Special renewal offer", "discount": 10}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Annual Contract Renewal';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Manager Escalation', 'Escalate at-risk renewals', 'task', 6, 168,
            '{"task_type": "escalation", "escalate_to": "sales_manager"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Annual Contract Renewal';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Final Notice', 'Last renewal reminder', 'email', 7, 336,
            '{"template": "renewal_final", "subject": "Your service agreement expires in 7 days"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Annual Contract Renewal';
    """)

    # ========================================
    # JOURNEY 9: Post-Service Excellence
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'Post-Service Excellence',
            'Comprehensive post-service follow-up to ensure satisfaction, gather feedback, and identify upsell opportunities.',
            'custom',
            'event',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Thank You SMS', 'Immediate thank you message', 'sms', 1, NULL,
            '{"template": "service_thanks_sms", "include_tech_name": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Post-Service Excellence';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Invoice & Receipt', 'Send digital invoice', 'email', 2, 1,
            '{"template": "invoice_receipt", "subject": "Your Mac-Septic Service Invoice", "include_pdf": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Post-Service Excellence';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Satisfaction Survey', 'Request service feedback', 'email', 3, 24,
            '{"template": "satisfaction_survey", "subject": "How was your service today?", "survey_type": "csat"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Post-Service Excellence';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Check Satisfaction', 'Evaluate survey response', 'condition', 4, 48,
            '{"field": "csat_score", "operator": "gte", "value": 4}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Post-Service Excellence';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Service Recovery', 'Immediate outreach for unhappy customers', 'task', 5, 2,
            '{"task_type": "call", "priority": "critical", "script": "service_recovery"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Post-Service Excellence';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Maintenance Tips', 'Educational follow-up content', 'email', 6, 168,
            '{"template": "maintenance_tips", "subject": "Tips to extend the life of your septic system"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Post-Service Excellence';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Upsell Opportunity', 'Recommend additional services', 'email', 7, 336,
            '{"template": "upsell_recommendation", "subject": "Services that complement your recent work", "ai_recommendations": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Post-Service Excellence';
    """)

    # ========================================
    # JOURNEY 10: VIP Customer Program
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'VIP Customer Program',
            'Exclusive program for top-tier customers. Premium benefits, priority service, and personalized attention to maximize lifetime value.',
            'expansion',
            'segment_entry',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'VIP Welcome', 'Welcome to VIP program', 'email', 1, NULL,
            '{"template": "vip_welcome", "subject": "Welcome to Mac-Septic VIP - Exclusive Benefits Inside"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'VIP Customer Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Assign VIP Manager', 'Dedicated success manager assignment', 'task', 2, NULL,
            '{"task_type": "internal", "role": "vip_manager", "intro_call": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'VIP Customer Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Benefits Overview Call', 'Personal call to explain VIP benefits', 'task', 3, 72,
            '{"task_type": "call", "script": "vip_benefits", "duration_minutes": 30}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'VIP Customer Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Priority Scheduling Setup', 'Configure priority booking', 'custom', 4, NULL,
            '{"action": "enable_priority_booking", "priority_level": "vip"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'VIP Customer Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Quarterly Check-in', 'Regular relationship touchpoint', 'task', 5, 2160,
            '{"task_type": "call", "recurring": true, "frequency": "quarterly"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'VIP Customer Program';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Exclusive Offer', 'VIP-only seasonal promotion', 'email', 6, 4320,
            '{"template": "vip_exclusive", "subject": "VIP Exclusive: Early access to our spring special"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'VIP Customer Program';
    """)

    # ========================================
    # JOURNEY 11: New Homeowner Acquisition
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'New Homeowner Acquisition',
            'Target new homeowners in service area with educational content and special first-time customer offers.',
            'custom',
            'manual',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Welcome to Neighborhood', 'Introduction mailer/email', 'email', 1, NULL,
            '{"template": "new_homeowner_welcome", "subject": "Welcome to the neighborhood! Important info about your septic system"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Homeowner Acquisition';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Septic 101 Guide', 'Educational content for new owners', 'email', 2, 168,
            '{"template": "septic_101", "subject": "Your Complete Guide to Septic System Care", "include_pdf": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Homeowner Acquisition';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'First Service Offer', 'Special new customer discount', 'email', 3, 336,
            '{"template": "new_customer_offer", "subject": "New homeowner special: 20% off your first inspection", "discount": 20}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Homeowner Acquisition';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Check Engagement', 'Monitor email opens/clicks', 'condition', 4, 504,
            '{"field": "email_clicked", "operator": "eq", "value": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Homeowner Acquisition';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Phone Outreach', 'Personal call to engaged leads', 'task', 5, 24,
            '{"task_type": "call", "script": "new_homeowner_intro"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Homeowner Acquisition';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Reminder Postcard', 'Physical mail touchpoint', 'custom', 6, 720,
            '{"action": "send_postcard", "template": "new_homeowner_postcard"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'New Homeowner Acquisition';
    """)

    # ========================================
    # JOURNEY 12: Property Manager Partnership
    # ========================================
    op.execute("""
        INSERT INTO cs_journeys (name, description, journey_type, trigger_type, is_active, created_at, updated_at)
        VALUES (
            'Property Manager Partnership',
            'B2B journey for property management companies. Focus on volume pricing, simplified billing, and multi-property coordination.',
            'onboarding',
            'manual',
            true,
            NOW(),
            NOW()
        );
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Partnership Inquiry', 'Initial response to inquiry', 'email', 1, NULL,
            '{"template": "pm_inquiry_response", "subject": "Mac-Septic Property Management Partnership Program"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Property Manager Partnership';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Schedule Discovery Call', 'Book needs assessment meeting', 'task', 2, 24,
            '{"task_type": "meeting", "duration_minutes": 45, "agenda": "pm_discovery"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Property Manager Partnership';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Volume Pricing Proposal', 'Custom pricing based on portfolio', 'email', 3, 168,
            '{"template": "pm_proposal", "subject": "Your Custom Property Management Pricing", "include_pdf": true}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Property Manager Partnership';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Follow-up Call', 'Discuss proposal and answer questions', 'task', 4, 336,
            '{"task_type": "call", "script": "pm_proposal_followup"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Property Manager Partnership';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Contract & Onboarding', 'Send partnership agreement', 'webhook', 5, 168,
            '{"endpoint": "/contracts/pm-agreement", "method": "POST"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Property Manager Partnership';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Property Import', 'Bulk upload property list', 'task', 6, 72,
            '{"task_type": "internal", "action": "property_import_setup"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Property Manager Partnership';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Portal Training', 'Train on multi-property dashboard', 'task', 7, 168,
            '{"task_type": "meeting", "duration_minutes": 60, "agenda": "pm_portal_training"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Property Manager Partnership';
    """)
    op.execute("""
        INSERT INTO cs_journey_steps (journey_id, name, description, step_type, step_order, wait_hours, config, is_active, created_at, updated_at)
        SELECT id, 'Quarterly Business Review', 'Schedule ongoing QBR', 'task', 8, 2160,
            '{"task_type": "meeting", "recurring": true, "frequency": "quarterly", "agenda": "pm_qbr"}',
            true, NOW(), NOW() FROM cs_journeys WHERE name = 'Property Manager Partnership';
    """)


def downgrade():
    # Delete all world-class journeys and their steps
    op.execute("""
        DELETE FROM cs_journey_steps WHERE journey_id IN (
            SELECT id FROM cs_journeys WHERE name IN (
                'New Customer Welcome (Residential)',
                'Emergency Service Response',
                'At-Risk Customer Recovery',
                'Referral & Advocacy Program',
                'Seasonal Maintenance Campaign',
                'Win-Back Campaign',
                'Commercial Customer Onboarding',
                'Annual Contract Renewal',
                'Post-Service Excellence',
                'VIP Customer Program',
                'New Homeowner Acquisition',
                'Property Manager Partnership'
            )
        );
        DELETE FROM cs_journeys WHERE name IN (
            'New Customer Welcome (Residential)',
            'Emergency Service Response',
            'At-Risk Customer Recovery',
            'Referral & Advocacy Program',
            'Seasonal Maintenance Campaign',
            'Win-Back Campaign',
            'Commercial Customer Onboarding',
            'Annual Contract Renewal',
            'Post-Service Excellence',
            'VIP Customer Program',
            'New Homeowner Acquisition',
            'Property Manager Partnership'
        );
    """)
