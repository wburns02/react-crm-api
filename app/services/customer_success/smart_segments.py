"""
Smart Segments Service for Enterprise Customer Success Platform

Defines pre-built smart segments for customer segmentation:
- Lifecycle Segments: New, Loyal, Dormant, At-Risk, Churned
- Value Segments: VIP, High Value, Medium Value, Low Value
- Service Segments: Aerobic, Conventional, Contract, One-Time, Service Due, Overdue
- Engagement Segments: Email Engaged/Unengaged, NPS Promoters/Passives/Detractors
- Geographic Segments: By city, county, service area
"""

from typing import Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.customer_success import Segment


class SmartSegmentCategory:
    """Segment category constants."""
    LIFECYCLE = "lifecycle"
    VALUE = "value"
    SERVICE = "service"
    ENGAGEMENT = "engagement"
    GEOGRAPHIC = "geographic"


# Smart segment definitions
# Each definition includes: name, description, category, rules, ai_insight, recommended_actions, priority, color

SMART_SEGMENTS = [
    # =============================================================================
    # LIFECYCLE SEGMENTS
    # =============================================================================
    {
        "name": "New Customers",
        "description": "Customers created within the last 30 days",
        "category": SmartSegmentCategory.LIFECYCLE,
        "color": "#22C55E",  # Green
        "priority": 90,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "created_at", "operator": "gte", "value": "NOW - INTERVAL '30 days'"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "New customers are in their critical onboarding phase. First impressions matter - ensure excellent service delivery and proactive communication to build loyalty.",
        "recommended_actions": [
            {"action": "send_welcome_email", "label": "Send Welcome Email", "priority": "high"},
            {"action": "schedule_onboarding_call", "label": "Schedule Onboarding Call", "priority": "high"},
            {"action": "assign_csm", "label": "Assign Customer Success Manager", "priority": "medium"},
            {"action": "setup_service_reminders", "label": "Set Up Service Reminders", "priority": "medium"}
        ]
    },
    {
        "name": "Loyal Customers",
        "description": "Customers with 3+ years tenure and good health score (70+)",
        "category": SmartSegmentCategory.LIFECYCLE,
        "color": "#3B82F6",  # Blue
        "priority": 85,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "created_at", "operator": "lte", "value": "NOW - INTERVAL '3 years'"},
                {"field": "health_score", "operator": "gte", "value": 70},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "These long-term customers are your brand advocates. They've demonstrated loyalty and satisfaction. Nurture these relationships for referrals and case studies.",
        "recommended_actions": [
            {"action": "request_referral", "label": "Request Referral", "priority": "high"},
            {"action": "offer_loyalty_discount", "label": "Offer Loyalty Discount", "priority": "medium"},
            {"action": "invite_to_loyalty_program", "label": "Invite to VIP Program", "priority": "medium"},
            {"action": "request_testimonial", "label": "Request Testimonial", "priority": "low"}
        ]
    },
    {
        "name": "Dormant Customers",
        "description": "Active customers with no service in the last 12 months",
        "category": SmartSegmentCategory.LIFECYCLE,
        "color": "#F59E0B",  # Amber
        "priority": 80,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "last_service_date", "operator": "lte", "value": "NOW - INTERVAL '12 months'"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Dormant customers haven't engaged in over a year. They may have found alternative services or forgotten about regular maintenance. Re-engage before they churn.",
        "recommended_actions": [
            {"action": "send_reengagement_campaign", "label": "Send Re-engagement Campaign", "priority": "high"},
            {"action": "offer_service_discount", "label": "Offer Service Discount", "priority": "high"},
            {"action": "call_to_check_in", "label": "Call to Check In", "priority": "medium"},
            {"action": "send_maintenance_reminder", "label": "Send Maintenance Reminder", "priority": "medium"}
        ]
    },
    {
        "name": "At-Risk Customers",
        "description": "Customers with health score below 50",
        "category": SmartSegmentCategory.LIFECYCLE,
        "color": "#EF4444",  # Red
        "priority": 95,  # High priority for attention
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "health_score", "operator": "lt", "value": 50},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "At-risk customers show warning signs of potential churn. Immediate intervention is needed to address concerns, resolve issues, and restore satisfaction.",
        "recommended_actions": [
            {"action": "create_escalation", "label": "Create Escalation", "priority": "critical"},
            {"action": "schedule_urgent_call", "label": "Schedule Urgent Call", "priority": "critical"},
            {"action": "review_recent_interactions", "label": "Review Recent Interactions", "priority": "high"},
            {"action": "offer_service_recovery", "label": "Offer Service Recovery", "priority": "high"},
            {"action": "assign_senior_csm", "label": "Assign Senior CSM", "priority": "medium"}
        ]
    },
    {
        "name": "Churned Customers",
        "description": "Customers marked as inactive/churned",
        "category": SmartSegmentCategory.LIFECYCLE,
        "color": "#6B7280",  # Gray
        "priority": 70,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "is_active", "operator": "eq", "value": False}
            ]
        },
        "ai_insight": "Churned customers have ended their relationship. Analyze churn reasons to improve retention and consider win-back campaigns for recoverable accounts.",
        "recommended_actions": [
            {"action": "analyze_churn_reason", "label": "Analyze Churn Reason", "priority": "high"},
            {"action": "send_win_back_campaign", "label": "Send Win-Back Campaign", "priority": "medium"},
            {"action": "request_exit_feedback", "label": "Request Exit Feedback", "priority": "medium"},
            {"action": "add_to_nurture_sequence", "label": "Add to Nurture Sequence", "priority": "low"}
        ]
    },

    # =============================================================================
    # VALUE SEGMENTS
    # =============================================================================
    {
        "name": "VIP Customers",
        "description": "Customers with $5,000+ lifetime value",
        "category": SmartSegmentCategory.VALUE,
        "color": "#8B5CF6",  # Purple
        "priority": 100,  # Highest priority
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "lifetime_value", "operator": "gte", "value": 5000},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "VIP customers are your most valuable accounts, contributing significantly to revenue. They deserve white-glove service and exclusive benefits to maintain their loyalty.",
        "recommended_actions": [
            {"action": "assign_dedicated_csm", "label": "Assign Dedicated CSM", "priority": "high"},
            {"action": "offer_vip_benefits", "label": "Offer VIP Benefits", "priority": "high"},
            {"action": "priority_scheduling", "label": "Enable Priority Scheduling", "priority": "high"},
            {"action": "quarterly_business_review", "label": "Schedule QBR", "priority": "medium"},
            {"action": "executive_sponsor", "label": "Assign Executive Sponsor", "priority": "medium"}
        ]
    },
    {
        "name": "High Value Customers",
        "description": "Customers with $2,000-$5,000 lifetime value",
        "category": SmartSegmentCategory.VALUE,
        "color": "#6366F1",  # Indigo
        "priority": 88,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "lifetime_value", "operator": "gte", "value": 2000},
                {"field": "lifetime_value", "operator": "lt", "value": 5000},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "High-value customers have strong spending history. Focus on expanding their service portfolio and nurturing them toward VIP status through excellent experiences.",
        "recommended_actions": [
            {"action": "upsell_contract", "label": "Upsell Service Contract", "priority": "high"},
            {"action": "cross_sell_services", "label": "Cross-Sell Additional Services", "priority": "medium"},
            {"action": "loyalty_program_invite", "label": "Invite to Loyalty Program", "priority": "medium"},
            {"action": "referral_request", "label": "Request Referrals", "priority": "low"}
        ]
    },
    {
        "name": "Medium Value Customers",
        "description": "Customers with $500-$2,000 lifetime value",
        "category": SmartSegmentCategory.VALUE,
        "color": "#14B8A6",  # Teal
        "priority": 75,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "lifetime_value", "operator": "gte", "value": 500},
                {"field": "lifetime_value", "operator": "lt", "value": 2000},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Medium-value customers represent growth opportunities. Understand their needs better and identify ways to increase engagement and service adoption.",
        "recommended_actions": [
            {"action": "promote_service_bundles", "label": "Promote Service Bundles", "priority": "medium"},
            {"action": "schedule_checkup", "label": "Schedule System Checkup", "priority": "medium"},
            {"action": "send_educational_content", "label": "Send Educational Content", "priority": "low"},
            {"action": "offer_contract_upgrade", "label": "Offer Contract Upgrade", "priority": "low"}
        ]
    },
    {
        "name": "Low Value Customers",
        "description": "Customers with less than $500 lifetime value",
        "category": SmartSegmentCategory.VALUE,
        "color": "#94A3B8",  # Slate
        "priority": 60,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "lifetime_value", "operator": "lt", "value": 500},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Low-value customers may be new or have limited service needs. Use automated engagement to cost-effectively nurture them toward higher value.",
        "recommended_actions": [
            {"action": "automated_nurture", "label": "Add to Automated Nurture", "priority": "medium"},
            {"action": "send_service_education", "label": "Send Service Education", "priority": "low"},
            {"action": "offer_first_time_discount", "label": "Offer First-Time Discount", "priority": "low"}
        ]
    },

    # =============================================================================
    # SERVICE SEGMENTS
    # =============================================================================
    {
        "name": "Aerobic System Owners",
        "description": "Customers with aerobic septic systems",
        "category": SmartSegmentCategory.SERVICE,
        "color": "#10B981",  # Emerald
        "priority": 82,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "system_type", "operator": "eq", "value": "aerobic"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Aerobic systems require more frequent maintenance than conventional systems. These customers need quarterly inspections and regular maintenance reminders.",
        "recommended_actions": [
            {"action": "setup_quarterly_maintenance", "label": "Set Up Quarterly Maintenance", "priority": "high"},
            {"action": "send_aerobic_tips", "label": "Send Aerobic System Tips", "priority": "medium"},
            {"action": "schedule_inspection", "label": "Schedule Inspection", "priority": "medium"},
            {"action": "offer_maintenance_contract", "label": "Offer Maintenance Contract", "priority": "high"}
        ]
    },
    {
        "name": "Conventional System Owners",
        "description": "Customers with conventional septic systems",
        "category": SmartSegmentCategory.SERVICE,
        "color": "#0EA5E9",  # Sky
        "priority": 78,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "system_type", "operator": "in", "value": ["conventional", "standard", "gravity"]},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Conventional systems typically need pumping every 3-5 years. Educate these customers on proper maintenance to extend system life.",
        "recommended_actions": [
            {"action": "schedule_pumping_reminder", "label": "Schedule Pumping Reminder", "priority": "medium"},
            {"action": "send_maintenance_guide", "label": "Send Maintenance Guide", "priority": "low"},
            {"action": "offer_inspection", "label": "Offer System Inspection", "priority": "medium"}
        ]
    },
    {
        "name": "Contract Customers",
        "description": "Customers with active service contracts",
        "category": SmartSegmentCategory.SERVICE,
        "color": "#7C3AED",  # Violet
        "priority": 92,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "has_active_contract", "operator": "eq", "value": True},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Contract customers provide predictable recurring revenue. Ensure contract obligations are met and identify opportunities for contract upgrades at renewal.",
        "recommended_actions": [
            {"action": "review_contract_compliance", "label": "Review Contract Compliance", "priority": "high"},
            {"action": "schedule_contracted_services", "label": "Schedule Contracted Services", "priority": "high"},
            {"action": "prepare_renewal_offer", "label": "Prepare Renewal Offer", "priority": "medium"},
            {"action": "upsell_contract_tier", "label": "Upsell Contract Tier", "priority": "low"}
        ]
    },
    {
        "name": "One-Time Customers",
        "description": "Customers without active service contracts",
        "category": SmartSegmentCategory.SERVICE,
        "color": "#64748B",  # Slate
        "priority": 65,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "has_active_contract", "operator": "eq", "value": False},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "One-time customers represent untapped recurring revenue. Focus on demonstrating the value of service contracts for peace of mind and cost savings.",
        "recommended_actions": [
            {"action": "promote_contracts", "label": "Promote Service Contracts", "priority": "high"},
            {"action": "send_contract_benefits", "label": "Send Contract Benefits Info", "priority": "medium"},
            {"action": "offer_contract_trial", "label": "Offer Contract Trial", "priority": "medium"},
            {"action": "calculate_savings_analysis", "label": "Calculate Savings Analysis", "priority": "low"}
        ]
    },
    {
        "name": "Service Due This Month",
        "description": "Customers with service scheduled or due this month",
        "category": SmartSegmentCategory.SERVICE,
        "color": "#F97316",  # Orange
        "priority": 93,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "next_service_date", "operator": "gte", "value": "FIRST_DAY_OF_MONTH"},
                {"field": "next_service_date", "operator": "lte", "value": "LAST_DAY_OF_MONTH"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "These customers need service attention this month. Ensure timely scheduling and communication to maintain service intervals and satisfaction.",
        "recommended_actions": [
            {"action": "confirm_appointment", "label": "Confirm Appointment", "priority": "high"},
            {"action": "send_service_reminder", "label": "Send Service Reminder", "priority": "high"},
            {"action": "optimize_route", "label": "Optimize Routing", "priority": "medium"},
            {"action": "prepare_service_checklist", "label": "Prepare Service Checklist", "priority": "medium"}
        ]
    },
    {
        "name": "Service Overdue",
        "description": "Customers whose last service exceeds their service interval",
        "category": SmartSegmentCategory.SERVICE,
        "color": "#DC2626",  # Red
        "priority": 96,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "service_overdue", "operator": "eq", "value": True},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Overdue customers are past their recommended service interval. This increases risk of system issues and potential health score decline. Urgent outreach needed.",
        "recommended_actions": [
            {"action": "urgent_scheduling_call", "label": "Urgent Scheduling Call", "priority": "critical"},
            {"action": "send_overdue_notice", "label": "Send Overdue Notice", "priority": "high"},
            {"action": "offer_priority_scheduling", "label": "Offer Priority Scheduling", "priority": "high"},
            {"action": "flag_for_csm_review", "label": "Flag for CSM Review", "priority": "medium"}
        ]
    },

    # =============================================================================
    # ENGAGEMENT SEGMENTS
    # =============================================================================
    {
        "name": "Email Engaged",
        "description": "Customers who opened an email in the last 90 days",
        "category": SmartSegmentCategory.ENGAGEMENT,
        "color": "#22D3EE",  # Cyan
        "priority": 72,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "last_email_open", "operator": "gte", "value": "NOW - INTERVAL '90 days'"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Engaged email subscribers are receptive to communication. They're good candidates for promotions, educational content, and surveys.",
        "recommended_actions": [
            {"action": "include_in_campaigns", "label": "Include in Campaigns", "priority": "high"},
            {"action": "send_exclusive_offers", "label": "Send Exclusive Offers", "priority": "medium"},
            {"action": "request_survey_feedback", "label": "Request Survey Feedback", "priority": "medium"},
            {"action": "share_educational_content", "label": "Share Educational Content", "priority": "low"}
        ]
    },
    {
        "name": "Email Unengaged",
        "description": "Customers with no email opens in 90+ days",
        "category": SmartSegmentCategory.ENGAGEMENT,
        "color": "#78716C",  # Stone
        "priority": 68,
        "rules": {
            "logic": "or",
            "rules": [
                {"field": "last_email_open", "operator": "lte", "value": "NOW - INTERVAL '90 days'"},
                {"field": "last_email_open", "operator": "is_null", "value": None}
            ]
        },
        "ai_insight": "Unengaged subscribers may have email deliverability issues or simply ignore emails. Consider alternative channels like SMS or phone for important communications.",
        "recommended_actions": [
            {"action": "verify_email_address", "label": "Verify Email Address", "priority": "high"},
            {"action": "try_alternative_channels", "label": "Try Alternative Channels", "priority": "high"},
            {"action": "send_reengagement_email", "label": "Send Re-engagement Email", "priority": "medium"},
            {"action": "consider_email_sunset", "label": "Consider Email Sunset", "priority": "low"}
        ]
    },
    {
        "name": "NPS Promoters",
        "description": "Customers with NPS score of 9-10 (promoters)",
        "category": SmartSegmentCategory.ENGAGEMENT,
        "color": "#16A34A",  # Green
        "priority": 84,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "nps_score", "operator": "gte", "value": 9},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Promoters are highly satisfied customers likely to recommend your services. Leverage their enthusiasm for referrals, reviews, and case studies.",
        "recommended_actions": [
            {"action": "request_online_review", "label": "Request Online Review", "priority": "high"},
            {"action": "request_referral", "label": "Request Referral", "priority": "high"},
            {"action": "invite_to_referral_program", "label": "Invite to Referral Program", "priority": "medium"},
            {"action": "feature_in_case_study", "label": "Feature in Case Study", "priority": "low"}
        ]
    },
    {
        "name": "NPS Passives",
        "description": "Customers with NPS score of 7-8 (passives)",
        "category": SmartSegmentCategory.ENGAGEMENT,
        "color": "#EAB308",  # Yellow
        "priority": 76,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "nps_score", "operator": "gte", "value": 7},
                {"field": "nps_score", "operator": "lte", "value": 8},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Passive customers are satisfied but not enthusiastic. They're vulnerable to competitive offers. Focus on delighting them to convert to promoters.",
        "recommended_actions": [
            {"action": "understand_gaps", "label": "Understand Experience Gaps", "priority": "high"},
            {"action": "offer_surprise_delight", "label": "Offer Surprise & Delight", "priority": "medium"},
            {"action": "personalized_followup", "label": "Personalized Follow-up", "priority": "medium"},
            {"action": "invite_feedback", "label": "Invite Feedback", "priority": "low"}
        ]
    },
    {
        "name": "NPS Detractors",
        "description": "Customers with NPS score of 0-6 (detractors)",
        "category": SmartSegmentCategory.ENGAGEMENT,
        "color": "#B91C1C",  # Dark Red
        "priority": 94,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "nps_score", "operator": "lte", "value": 6},
                {"field": "nps_score", "operator": "is_not_null", "value": None},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Detractors are unhappy and may spread negative word-of-mouth. Prioritize resolving their issues to prevent churn and reputation damage.",
        "recommended_actions": [
            {"action": "immediate_outreach", "label": "Immediate Outreach", "priority": "critical"},
            {"action": "create_escalation", "label": "Create Escalation", "priority": "critical"},
            {"action": "document_issues", "label": "Document Issues", "priority": "high"},
            {"action": "service_recovery", "label": "Initiate Service Recovery", "priority": "high"},
            {"action": "manager_followup", "label": "Manager Follow-up", "priority": "medium"}
        ]
    },

    # =============================================================================
    # GEOGRAPHIC SEGMENTS
    # =============================================================================
    {
        "name": "San Marcos Customers",
        "description": "Customers located in San Marcos, TX",
        "category": SmartSegmentCategory.GEOGRAPHIC,
        "color": "#A855F7",  # Purple
        "priority": 50,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "city", "operator": "eq", "value": "San Marcos"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "San Marcos customers form a concentrated service area. Optimize routing and consider area-specific promotions to maximize efficiency.",
        "recommended_actions": [
            {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
            {"action": "local_event_invite", "label": "Invite to Local Events", "priority": "low"},
            {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
        ]
    },
    {
        "name": "Wimberley Customers",
        "description": "Customers located in Wimberley, TX",
        "category": SmartSegmentCategory.GEOGRAPHIC,
        "color": "#EC4899",  # Pink
        "priority": 50,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "city", "operator": "eq", "value": "Wimberley"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Wimberley area customers often have unique septic needs due to local geology. Consider specialized service offerings.",
        "recommended_actions": [
            {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
            {"action": "terrain_specific_tips", "label": "Send Terrain-Specific Tips", "priority": "low"},
            {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
        ]
    },
    {
        "name": "New Braunfels Customers",
        "description": "Customers located in New Braunfels, TX",
        "category": SmartSegmentCategory.GEOGRAPHIC,
        "color": "#F472B6",  # Light Pink
        "priority": 50,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "city", "operator": "eq", "value": "New Braunfels"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "New Braunfels is a growing market. Focus on capturing referrals from satisfied customers to expand presence.",
        "recommended_actions": [
            {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
            {"action": "referral_program_focus", "label": "Focus Referral Program", "priority": "medium"},
            {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
        ]
    },
    {
        "name": "Comal County Customers",
        "description": "Customers in Comal County service area",
        "category": SmartSegmentCategory.GEOGRAPHIC,
        "color": "#FB923C",  # Orange
        "priority": 52,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "county", "operator": "eq", "value": "Comal"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Comal County customers span a wide geographic area. Consider dedicated service days for efficiency.",
        "recommended_actions": [
            {"action": "dedicated_service_day", "label": "Schedule Dedicated Service Day", "priority": "medium"},
            {"action": "county_regulations_update", "label": "Send Regulations Update", "priority": "low"},
            {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"}
        ]
    },
    {
        "name": "Kyle Customers",
        "description": "Customers located in Kyle, TX",
        "category": SmartSegmentCategory.GEOGRAPHIC,
        "color": "#84CC16",  # Lime
        "priority": 50,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "city", "operator": "eq", "value": "Kyle"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Kyle is a rapidly growing area with new construction. Good opportunity for new customer acquisition through builder partnerships.",
        "recommended_actions": [
            {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
            {"action": "new_construction_outreach", "label": "New Construction Outreach", "priority": "medium"},
            {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
        ]
    },
    {
        "name": "Buda Customers",
        "description": "Customers located in Buda, TX",
        "category": SmartSegmentCategory.GEOGRAPHIC,
        "color": "#06B6D4",  # Cyan
        "priority": 50,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "city", "operator": "eq", "value": "Buda"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Buda is experiencing significant growth. Establish strong presence with excellent service to capture market share.",
        "recommended_actions": [
            {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
            {"action": "growth_market_strategy", "label": "Implement Growth Market Strategy", "priority": "medium"},
            {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
        ]
    },
    {
        "name": "Dripping Springs Customers",
        "description": "Customers located in Dripping Springs, TX",
        "category": SmartSegmentCategory.GEOGRAPHIC,
        "color": "#2DD4BF",  # Teal
        "priority": 50,
        "rules": {
            "logic": "and",
            "rules": [
                {"field": "city", "operator": "eq", "value": "Dripping Springs"},
                {"field": "is_active", "operator": "eq", "value": True}
            ]
        },
        "ai_insight": "Dripping Springs customers often have larger properties with unique septic requirements. Consider premium service offerings.",
        "recommended_actions": [
            {"action": "route_optimization", "label": "Optimize Service Routes", "priority": "medium"},
            {"action": "premium_service_offer", "label": "Offer Premium Services", "priority": "medium"},
            {"action": "area_specific_promotion", "label": "Send Area-Specific Promotion", "priority": "low"}
        ]
    },
]


class SmartSegmentService:
    """
    Service for managing pre-built smart segments.

    Handles creation, seeding, and management of system-defined segments.
    """

    def __init__(self, db: AsyncSession):
        """Initialize with database session."""
        self.db = db

    async def seed_smart_segments(self) -> dict:
        """
        Seed all pre-built smart segments into the database.

        Returns dict with counts of created/updated/skipped segments.
        """
        created = 0
        updated = 0
        skipped = 0

        for segment_def in SMART_SEGMENTS:
            result = await self._create_or_update_segment(segment_def)
            if result == "created":
                created += 1
            elif result == "updated":
                updated += 1
            else:
                skipped += 1

        await self.db.commit()

        return {
            "created": created,
            "updated": updated,
            "skipped": skipped,
            "total": len(SMART_SEGMENTS)
        }

    async def _create_or_update_segment(self, segment_def: dict) -> str:
        """
        Create or update a single smart segment.

        Returns: 'created', 'updated', or 'skipped'
        """
        # Check if segment already exists
        result = await self.db.execute(
            select(Segment).where(
                Segment.name == segment_def["name"],
                Segment.is_system == True
            )
        )
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing segment
            existing.description = segment_def["description"]
            existing.category = segment_def["category"]
            existing.color = segment_def["color"]
            existing.priority = segment_def["priority"]
            existing.rules = segment_def["rules"]
            existing.ai_insight = segment_def["ai_insight"]
            existing.recommended_actions = segment_def["recommended_actions"]
            return "updated"
        else:
            # Create new segment
            segment = Segment(
                name=segment_def["name"],
                description=segment_def["description"],
                segment_type="dynamic",
                category=segment_def["category"],
                color=segment_def["color"],
                priority=segment_def["priority"],
                rules=segment_def["rules"],
                ai_insight=segment_def["ai_insight"],
                recommended_actions=segment_def["recommended_actions"],
                is_system=True,
                is_active=True,
                auto_refresh=True,
                refresh_interval_hours=24
            )
            self.db.add(segment)
            return "created"

    async def get_smart_segments(self, category: Optional[str] = None) -> list[Segment]:
        """
        Get all smart segments, optionally filtered by category.
        """
        query = select(Segment).where(Segment.is_system == True)

        if category:
            query = query.where(Segment.category == category)

        query = query.order_by(Segment.priority.desc(), Segment.name)

        result = await self.db.execute(query)
        return result.scalars().all()

    async def get_segment_by_name(self, name: str) -> Optional[Segment]:
        """Get a smart segment by name."""
        result = await self.db.execute(
            select(Segment).where(
                Segment.name == name,
                Segment.is_system == True
            )
        )
        return result.scalar_one_or_none()

    async def get_segment_categories(self) -> list[dict]:
        """
        Get list of segment categories with counts.
        """
        categories = [
            {"code": SmartSegmentCategory.LIFECYCLE, "label": "Lifecycle", "description": "Based on customer journey stage"},
            {"code": SmartSegmentCategory.VALUE, "label": "Value", "description": "Based on customer lifetime value"},
            {"code": SmartSegmentCategory.SERVICE, "label": "Service", "description": "Based on service type and status"},
            {"code": SmartSegmentCategory.ENGAGEMENT, "label": "Engagement", "description": "Based on communication engagement"},
            {"code": SmartSegmentCategory.GEOGRAPHIC, "label": "Geographic", "description": "Based on customer location"},
        ]

        # Get counts per category
        for cat in categories:
            result = await self.db.execute(
                select(Segment).where(
                    Segment.is_system == True,
                    Segment.category == cat["code"]
                )
            )
            cat["count"] = len(result.scalars().all())

        return categories

    async def reset_smart_segments(self) -> dict:
        """
        Reset all smart segments to default definitions.

        This will recreate all system segments with default settings.
        """
        # Delete all existing system segments
        result = await self.db.execute(
            select(Segment).where(Segment.is_system == True)
        )
        existing = result.scalars().all()

        for segment in existing:
            await self.db.delete(segment)

        await self.db.commit()

        # Re-seed
        return await self.seed_smart_segments()


# Convenience function for seeding
async def seed_smart_segments(db: AsyncSession) -> dict:
    """Seed smart segments - convenience function."""
    service = SmartSegmentService(db)
    return await service.seed_smart_segments()
