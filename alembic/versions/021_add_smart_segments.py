"""Add Smart Segments Support

Adds fields for pre-built smart segments:
- is_system: Boolean flag for system segments (cannot be deleted)
- category: Segment category (lifecycle, value, service, engagement, geographic)
- ai_insight: AI-generated insight message for the segment
- recommended_actions: JSON list of recommended actions

Also seeds the initial set of smart segments.

Revision ID: 021_add_smart_segments
Revises: 020_survey_enhancements
Create Date: 2026-01-08 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '021_add_smart_segments'
down_revision = '020_survey_enhancements'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add new columns to cs_segments table
    op.add_column('cs_segments', sa.Column('is_system', sa.Boolean(), nullable=True, server_default='false'))
    op.add_column('cs_segments', sa.Column('category', sa.String(50), nullable=True))
    op.add_column('cs_segments', sa.Column('ai_insight', sa.Text(), nullable=True))
    op.add_column('cs_segments', sa.Column('recommended_actions', postgresql.JSON(astext_type=sa.Text()), nullable=True))

    # Create index on is_system for faster queries
    op.create_index('ix_cs_segments_is_system', 'cs_segments', ['is_system'], unique=False)
    op.create_index('ix_cs_segments_category', 'cs_segments', ['category'], unique=False)

    # Seed the smart segments
    seed_smart_segments()


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_cs_segments_category', table_name='cs_segments')
    op.drop_index('ix_cs_segments_is_system', table_name='cs_segments')

    # Remove system segments first
    op.execute("DELETE FROM cs_segments WHERE is_system = true")

    # Drop columns
    op.drop_column('cs_segments', 'recommended_actions')
    op.drop_column('cs_segments', 'ai_insight')
    op.drop_column('cs_segments', 'category')
    op.drop_column('cs_segments', 'is_system')


def seed_smart_segments():
    """Seed the pre-built smart segments."""
    import json
    from datetime import datetime

    # Smart segment definitions
    segments = [
        # LIFECYCLE SEGMENTS
        {
            "name": "New Customers",
            "description": "Customers created within the last 30 days",
            "category": "lifecycle",
            "color": "#22C55E",
            "priority": 90,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "created_at", "operator": "gte", "value": "NOW - INTERVAL '30 days'"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "New customers are in their critical onboarding phase. First impressions matter - ensure excellent service delivery and proactive communication to build loyalty.",
            "recommended_actions": json.dumps([
                {"action": "send_welcome_email", "label": "Send Welcome Email", "priority": "high"},
                {"action": "schedule_onboarding_call", "label": "Schedule Onboarding Call", "priority": "high"},
                {"action": "assign_csm", "label": "Assign Customer Success Manager", "priority": "medium"},
                {"action": "setup_service_reminders", "label": "Set Up Service Reminders", "priority": "medium"}
            ])
        },
        {
            "name": "Loyal Customers",
            "description": "Customers with 3+ years tenure and good health score (70+)",
            "category": "lifecycle",
            "color": "#3B82F6",
            "priority": 85,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "created_at", "operator": "lte", "value": "NOW - INTERVAL '3 years'"},
                    {"field": "health_score", "operator": "gte", "value": 70},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "These long-term customers are your brand advocates. They've demonstrated loyalty and satisfaction. Nurture these relationships for referrals and case studies.",
            "recommended_actions": json.dumps([
                {"action": "request_referral", "label": "Request Referral", "priority": "high"},
                {"action": "offer_loyalty_discount", "label": "Offer Loyalty Discount", "priority": "medium"},
                {"action": "invite_to_loyalty_program", "label": "Invite to VIP Program", "priority": "medium"},
                {"action": "request_testimonial", "label": "Request Testimonial", "priority": "low"}
            ])
        },
        {
            "name": "Dormant Customers",
            "description": "Active customers with no service in the last 12 months",
            "category": "lifecycle",
            "color": "#F59E0B",
            "priority": 80,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "last_service_date", "operator": "lte", "value": "NOW - INTERVAL '12 months'"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Dormant customers haven't engaged in over a year. They may have found alternative services or forgotten about regular maintenance. Re-engage before they churn.",
            "recommended_actions": json.dumps([
                {"action": "send_reengagement_campaign", "label": "Send Re-engagement Campaign", "priority": "high"},
                {"action": "offer_service_discount", "label": "Offer Service Discount", "priority": "high"},
                {"action": "call_to_check_in", "label": "Call to Check In", "priority": "medium"},
                {"action": "send_maintenance_reminder", "label": "Send Maintenance Reminder", "priority": "medium"}
            ])
        },
        {
            "name": "At-Risk Customers",
            "description": "Customers with health score below 50",
            "category": "lifecycle",
            "color": "#EF4444",
            "priority": 95,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "health_score", "operator": "lt", "value": 50},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "At-risk customers show warning signs of potential churn. Immediate intervention is needed to address concerns, resolve issues, and restore satisfaction.",
            "recommended_actions": json.dumps([
                {"action": "create_escalation", "label": "Create Escalation", "priority": "critical"},
                {"action": "schedule_urgent_call", "label": "Schedule Urgent Call", "priority": "critical"},
                {"action": "review_recent_interactions", "label": "Review Recent Interactions", "priority": "high"},
                {"action": "offer_service_recovery", "label": "Offer Service Recovery", "priority": "high"},
                {"action": "assign_senior_csm", "label": "Assign Senior CSM", "priority": "medium"}
            ])
        },
        {
            "name": "Churned Customers",
            "description": "Customers marked as inactive/churned",
            "category": "lifecycle",
            "color": "#6B7280",
            "priority": 70,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "is_active", "operator": "eq", "value": False}
                ]
            }),
            "ai_insight": "Churned customers have ended their relationship. Analyze churn reasons to improve retention and consider win-back campaigns for recoverable accounts.",
            "recommended_actions": json.dumps([
                {"action": "analyze_churn_reason", "label": "Analyze Churn Reason", "priority": "high"},
                {"action": "send_win_back_campaign", "label": "Send Win-Back Campaign", "priority": "medium"},
                {"action": "request_exit_feedback", "label": "Request Exit Feedback", "priority": "medium"},
                {"action": "add_to_nurture_sequence", "label": "Add to Nurture Sequence", "priority": "low"}
            ])
        },
        # VALUE SEGMENTS
        {
            "name": "VIP Customers",
            "description": "Customers with $5,000+ lifetime value",
            "category": "value",
            "color": "#8B5CF6",
            "priority": 100,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "lifetime_value", "operator": "gte", "value": 5000},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "VIP customers are your most valuable accounts, contributing significantly to revenue. They deserve white-glove service and exclusive benefits to maintain their loyalty.",
            "recommended_actions": json.dumps([
                {"action": "assign_dedicated_csm", "label": "Assign Dedicated CSM", "priority": "high"},
                {"action": "offer_vip_benefits", "label": "Offer VIP Benefits", "priority": "high"},
                {"action": "priority_scheduling", "label": "Enable Priority Scheduling", "priority": "high"},
                {"action": "quarterly_business_review", "label": "Schedule QBR", "priority": "medium"},
                {"action": "executive_sponsor", "label": "Assign Executive Sponsor", "priority": "medium"}
            ])
        },
        {
            "name": "High Value Customers",
            "description": "Customers with $2,000-$5,000 lifetime value",
            "category": "value",
            "color": "#6366F1",
            "priority": 88,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "lifetime_value", "operator": "gte", "value": 2000},
                    {"field": "lifetime_value", "operator": "lt", "value": 5000},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "High-value customers have strong spending history. Focus on expanding their service portfolio and nurturing them toward VIP status through excellent experiences.",
            "recommended_actions": json.dumps([
                {"action": "upsell_contract", "label": "Upsell Service Contract", "priority": "high"},
                {"action": "cross_sell_services", "label": "Cross-Sell Additional Services", "priority": "medium"},
                {"action": "loyalty_program_invite", "label": "Invite to Loyalty Program", "priority": "medium"},
                {"action": "referral_request", "label": "Request Referrals", "priority": "low"}
            ])
        },
        {
            "name": "Medium Value Customers",
            "description": "Customers with $500-$2,000 lifetime value",
            "category": "value",
            "color": "#14B8A6",
            "priority": 75,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "lifetime_value", "operator": "gte", "value": 500},
                    {"field": "lifetime_value", "operator": "lt", "value": 2000},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Medium-value customers represent growth opportunities. Understand their needs better and identify ways to increase engagement and service adoption.",
            "recommended_actions": json.dumps([
                {"action": "promote_service_bundles", "label": "Promote Service Bundles", "priority": "medium"},
                {"action": "schedule_checkup", "label": "Schedule System Checkup", "priority": "medium"},
                {"action": "send_educational_content", "label": "Send Educational Content", "priority": "low"},
                {"action": "offer_contract_upgrade", "label": "Offer Contract Upgrade", "priority": "low"}
            ])
        },
        {
            "name": "Low Value Customers",
            "description": "Customers with less than $500 lifetime value",
            "category": "value",
            "color": "#94A3B8",
            "priority": 60,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "lifetime_value", "operator": "lt", "value": 500},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Low-value customers may be new or have limited service needs. Use automated engagement to cost-effectively nurture them toward higher value.",
            "recommended_actions": json.dumps([
                {"action": "automated_nurture", "label": "Add to Automated Nurture", "priority": "medium"},
                {"action": "send_service_education", "label": "Send Service Education", "priority": "low"},
                {"action": "offer_first_time_discount", "label": "Offer First-Time Discount", "priority": "low"}
            ])
        },
        # SERVICE SEGMENTS
        {
            "name": "Aerobic System Owners",
            "description": "Customers with aerobic septic systems",
            "category": "service",
            "color": "#10B981",
            "priority": 82,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "system_type", "operator": "eq", "value": "aerobic"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Aerobic systems require more frequent maintenance than conventional systems. These customers need quarterly inspections and regular maintenance reminders.",
            "recommended_actions": json.dumps([
                {"action": "setup_quarterly_maintenance", "label": "Set Up Quarterly Maintenance", "priority": "high"},
                {"action": "send_aerobic_tips", "label": "Send Aerobic System Tips", "priority": "medium"},
                {"action": "schedule_inspection", "label": "Schedule Inspection", "priority": "medium"},
                {"action": "offer_maintenance_contract", "label": "Offer Maintenance Contract", "priority": "high"}
            ])
        },
        {
            "name": "Conventional System Owners",
            "description": "Customers with conventional septic systems",
            "category": "service",
            "color": "#0EA5E9",
            "priority": 78,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "system_type", "operator": "in", "value": ["conventional", "standard", "gravity"]},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Conventional systems typically need pumping every 3-5 years. Educate these customers on proper maintenance to extend system life.",
            "recommended_actions": json.dumps([
                {"action": "schedule_pumping_reminder", "label": "Schedule Pumping Reminder", "priority": "medium"},
                {"action": "send_maintenance_guide", "label": "Send Maintenance Guide", "priority": "low"},
                {"action": "offer_inspection", "label": "Offer System Inspection", "priority": "medium"}
            ])
        },
        {
            "name": "Contract Customers",
            "description": "Customers with active service contracts",
            "category": "service",
            "color": "#7C3AED",
            "priority": 92,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "has_active_contract", "operator": "eq", "value": True},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Contract customers provide predictable recurring revenue. Ensure contract obligations are met and identify opportunities for contract upgrades at renewal.",
            "recommended_actions": json.dumps([
                {"action": "review_contract_compliance", "label": "Review Contract Compliance", "priority": "high"},
                {"action": "schedule_contracted_services", "label": "Schedule Contracted Services", "priority": "high"},
                {"action": "prepare_renewal_offer", "label": "Prepare Renewal Offer", "priority": "medium"},
                {"action": "upsell_contract_tier", "label": "Upsell Contract Tier", "priority": "low"}
            ])
        },
        {
            "name": "One-Time Customers",
            "description": "Customers without active service contracts",
            "category": "service",
            "color": "#64748B",
            "priority": 65,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "has_active_contract", "operator": "eq", "value": False},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "One-time customers represent untapped recurring revenue. Focus on demonstrating the value of service contracts for peace of mind and cost savings.",
            "recommended_actions": json.dumps([
                {"action": "promote_contracts", "label": "Promote Service Contracts", "priority": "high"},
                {"action": "send_contract_benefits", "label": "Send Contract Benefits Info", "priority": "medium"},
                {"action": "offer_contract_trial", "label": "Offer Contract Trial", "priority": "medium"},
                {"action": "calculate_savings_analysis", "label": "Calculate Savings Analysis", "priority": "low"}
            ])
        },
        {
            "name": "Service Due This Month",
            "description": "Customers with service scheduled or due this month",
            "category": "service",
            "color": "#F97316",
            "priority": 93,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "next_service_date", "operator": "gte", "value": "FIRST_DAY_OF_MONTH"},
                    {"field": "next_service_date", "operator": "lte", "value": "LAST_DAY_OF_MONTH"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "These customers need service attention this month. Ensure timely scheduling and communication to maintain service intervals and satisfaction.",
            "recommended_actions": json.dumps([
                {"action": "confirm_appointment", "label": "Confirm Appointment", "priority": "high"},
                {"action": "send_service_reminder", "label": "Send Service Reminder", "priority": "high"},
                {"action": "optimize_route", "label": "Optimize Routing", "priority": "medium"},
                {"action": "prepare_service_checklist", "label": "Prepare Service Checklist", "priority": "medium"}
            ])
        },
        {
            "name": "Service Overdue",
            "description": "Customers whose last service exceeds their service interval",
            "category": "service",
            "color": "#DC2626",
            "priority": 96,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "service_overdue", "operator": "eq", "value": True},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Overdue customers are past their recommended service interval. This increases risk of system issues and potential health score decline. Urgent outreach needed.",
            "recommended_actions": json.dumps([
                {"action": "urgent_scheduling_call", "label": "Urgent Scheduling Call", "priority": "critical"},
                {"action": "send_overdue_notice", "label": "Send Overdue Notice", "priority": "high"},
                {"action": "offer_priority_scheduling", "label": "Offer Priority Scheduling", "priority": "high"},
                {"action": "flag_for_csm_review", "label": "Flag for CSM Review", "priority": "medium"}
            ])
        },
        # ENGAGEMENT SEGMENTS
        {
            "name": "Email Engaged",
            "description": "Customers who opened an email in the last 90 days",
            "category": "engagement",
            "color": "#22D3EE",
            "priority": 72,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "last_email_open", "operator": "gte", "value": "NOW - INTERVAL '90 days'"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Engaged email subscribers are receptive to communication. They're good candidates for promotions, educational content, and surveys.",
            "recommended_actions": json.dumps([
                {"action": "include_in_campaigns", "label": "Include in Campaigns", "priority": "high"},
                {"action": "send_exclusive_offers", "label": "Send Exclusive Offers", "priority": "medium"},
                {"action": "request_survey_feedback", "label": "Request Survey Feedback", "priority": "medium"},
                {"action": "share_educational_content", "label": "Share Educational Content", "priority": "low"}
            ])
        },
        {
            "name": "Email Unengaged",
            "description": "Customers with no email opens in 90+ days",
            "category": "engagement",
            "color": "#78716C",
            "priority": 68,
            "rules": json.dumps({
                "logic": "or",
                "rules": [
                    {"field": "last_email_open", "operator": "lte", "value": "NOW - INTERVAL '90 days'"},
                    {"field": "last_email_open", "operator": "is_null", "value": None}
                ]
            }),
            "ai_insight": "Unengaged subscribers may have email deliverability issues or simply ignore emails. Consider alternative channels like SMS or phone for important communications.",
            "recommended_actions": json.dumps([
                {"action": "verify_email_address", "label": "Verify Email Address", "priority": "high"},
                {"action": "try_alternative_channels", "label": "Try Alternative Channels", "priority": "high"},
                {"action": "send_reengagement_email", "label": "Send Re-engagement Email", "priority": "medium"},
                {"action": "consider_email_sunset", "label": "Consider Email Sunset", "priority": "low"}
            ])
        },
        {
            "name": "NPS Promoters",
            "description": "Customers with NPS score of 9-10 (promoters)",
            "category": "engagement",
            "color": "#16A34A",
            "priority": 84,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "nps_score", "operator": "gte", "value": 9},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Promoters are highly satisfied customers likely to recommend your services. Leverage their enthusiasm for referrals, reviews, and case studies.",
            "recommended_actions": json.dumps([
                {"action": "request_online_review", "label": "Request Online Review", "priority": "high"},
                {"action": "request_referral", "label": "Request Referral", "priority": "high"},
                {"action": "invite_to_referral_program", "label": "Invite to Referral Program", "priority": "medium"},
                {"action": "feature_in_case_study", "label": "Feature in Case Study", "priority": "low"}
            ])
        },
        {
            "name": "NPS Passives",
            "description": "Customers with NPS score of 7-8 (passives)",
            "category": "engagement",
            "color": "#EAB308",
            "priority": 76,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "nps_score", "operator": "gte", "value": 7},
                    {"field": "nps_score", "operator": "lte", "value": 8},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Passive customers are satisfied but not enthusiastic. They're vulnerable to competitive offers. Focus on delighting them to convert to promoters.",
            "recommended_actions": json.dumps([
                {"action": "understand_gaps", "label": "Understand Experience Gaps", "priority": "high"},
                {"action": "offer_surprise_delight", "label": "Offer Surprise & Delight", "priority": "medium"},
                {"action": "personalized_followup", "label": "Personalized Follow-up", "priority": "medium"},
                {"action": "invite_feedback", "label": "Invite Feedback", "priority": "low"}
            ])
        },
        {
            "name": "NPS Detractors",
            "description": "Customers with NPS score of 0-6 (detractors)",
            "category": "engagement",
            "color": "#B91C1C",
            "priority": 94,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "nps_score", "operator": "lte", "value": 6},
                    {"field": "nps_score", "operator": "is_not_null", "value": None},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Detractors are unhappy and may spread negative word-of-mouth. Prioritize resolving their issues to prevent churn and reputation damage.",
            "recommended_actions": json.dumps([
                {"action": "immediate_outreach", "label": "Immediate Outreach", "priority": "critical"},
                {"action": "create_escalation", "label": "Create Escalation", "priority": "critical"},
                {"action": "document_issues", "label": "Document Issues", "priority": "high"},
                {"action": "service_recovery", "label": "Initiate Service Recovery", "priority": "high"},
                {"action": "manager_followup", "label": "Manager Follow-up", "priority": "medium"}
            ])
        },
        # GEOGRAPHIC SEGMENTS
        {
            "name": "San Marcos Customers",
            "description": "Customers located in San Marcos, TX",
            "category": "geographic",
            "color": "#A855F7",
            "priority": 50,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "city", "operator": "eq", "value": "San Marcos"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "San Marcos customers form a concentrated service area. Optimize routing and consider area-specific promotions to maximize efficiency.",
            "recommended_actions": json.dumps([
                {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
                {"action": "local_event_invite", "label": "Invite to Local Events", "priority": "low"},
                {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
            ])
        },
        {
            "name": "Wimberley Customers",
            "description": "Customers located in Wimberley, TX",
            "category": "geographic",
            "color": "#EC4899",
            "priority": 50,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "city", "operator": "eq", "value": "Wimberley"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Wimberley area customers often have unique septic needs due to local geology. Consider specialized service offerings.",
            "recommended_actions": json.dumps([
                {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
                {"action": "terrain_specific_tips", "label": "Send Terrain-Specific Tips", "priority": "low"},
                {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
            ])
        },
        {
            "name": "New Braunfels Customers",
            "description": "Customers located in New Braunfels, TX",
            "category": "geographic",
            "color": "#F472B6",
            "priority": 50,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "city", "operator": "eq", "value": "New Braunfels"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "New Braunfels is a growing market. Focus on capturing referrals from satisfied customers to expand presence.",
            "recommended_actions": json.dumps([
                {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
                {"action": "referral_program_focus", "label": "Focus Referral Program", "priority": "medium"},
                {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
            ])
        },
        {
            "name": "Comal County Customers",
            "description": "Customers in Comal County service area",
            "category": "geographic",
            "color": "#FB923C",
            "priority": 52,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "county", "operator": "eq", "value": "Comal"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Comal County customers span a wide geographic area. Consider dedicated service days for efficiency.",
            "recommended_actions": json.dumps([
                {"action": "dedicated_service_day", "label": "Schedule Dedicated Service Day", "priority": "medium"},
                {"action": "county_regulations_update", "label": "Send Regulations Update", "priority": "low"},
                {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"}
            ])
        },
        {
            "name": "Kyle Customers",
            "description": "Customers located in Kyle, TX",
            "category": "geographic",
            "color": "#84CC16",
            "priority": 50,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "city", "operator": "eq", "value": "Kyle"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Kyle is a rapidly growing area with new construction. Good opportunity for new customer acquisition through builder partnerships.",
            "recommended_actions": json.dumps([
                {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
                {"action": "new_construction_outreach", "label": "New Construction Outreach", "priority": "medium"},
                {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
            ])
        },
        {
            "name": "Buda Customers",
            "description": "Customers located in Buda, TX",
            "category": "geographic",
            "color": "#06B6D4",
            "priority": 50,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "city", "operator": "eq", "value": "Buda"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Buda is experiencing significant growth. Establish strong presence with excellent service to capture market share.",
            "recommended_actions": json.dumps([
                {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
                {"action": "growth_market_strategy", "label": "Implement Growth Market Strategy", "priority": "medium"},
                {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
            ])
        },
        {
            "name": "Dripping Springs Customers",
            "description": "Customers located in Dripping Springs, TX",
            "category": "geographic",
            "color": "#2DD4BF",
            "priority": 50,
            "rules": json.dumps({
                "logic": "and",
                "rules": [
                    {"field": "city", "operator": "eq", "value": "Dripping Springs"},
                    {"field": "is_active", "operator": "eq", "value": True}
                ]
            }),
            "ai_insight": "Dripping Springs customers often have larger properties with unique septic requirements. Consider premium service offerings.",
            "recommended_actions": json.dumps([
                {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
                {"action": "premium_service_offer", "label": "Offer Premium Services", "priority": "medium"},
                {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
            ])
        },
    ]

    # Build and execute INSERT statements
    for seg in segments:
        op.execute(f"""
            INSERT INTO cs_segments (
                name, description, segment_type, category, color, priority,
                rules, ai_insight, recommended_actions, is_system, is_active,
                auto_refresh, refresh_interval_hours, created_at
            ) VALUES (
                '{seg["name"]}',
                '{seg["description"].replace("'", "''")}',
                'dynamic',
                '{seg["category"]}',
                '{seg["color"]}',
                {seg["priority"]},
                '{seg["rules"].replace("'", "''")}',
                '{seg["ai_insight"].replace("'", "''")}',
                '{seg["recommended_actions"].replace("'", "''")}',
                true,
                true,
                true,
                24,
                NOW()
            )
            ON CONFLICT DO NOTHING
        """)
