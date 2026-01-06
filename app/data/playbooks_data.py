"""
World-Class Customer Success Playbooks Data (2025-2026 Best Practices)

This module contains enterprise-grade playbook definitions based on research from:
- Gainsight, ChurnZero, Totango best practices
- 2025-2026 Customer Success trends
- Enterprise SaaS onboarding frameworks

Used by both the API seed endpoint and standalone seed scripts.
"""


def get_world_class_playbooks(segment_ids: list[int] = None) -> list[dict]:
    """
    Returns world-class playbook definitions.

    Args:
        segment_ids: Optional list of segment IDs to reference. If None, segment references will be None.

    Returns:
        List of playbook dictionaries with steps.
    """
    # Default segment ID for new customers segment
    new_customers_segment = segment_ids[3] if segment_ids and len(segment_ids) > 3 else None

    return [
        # ============================================================
        # PLAYBOOK 1: ENTERPRISE ONBOARDING (90-Day Time-to-Value)
        # ============================================================
        {
            "name": "Enterprise Customer Onboarding",
            "description": "90-day comprehensive onboarding program optimized for time-to-value. Incorporates 2025 best practices: digital-first approach, AI-powered insights, proactive touchpoints, and milestone-based success tracking.",
            "category": "onboarding",
            "trigger_type": "segment_entry",
            "trigger_segment_id": new_customers_segment,
            "priority": "high",
            "target_completion_days": 90,
            "estimated_hours": 12.0,
            "success_criteria": {"feature_adoption": 70, "health_score": 75, "first_value_achieved": True},
            "steps": [
                {
                    "name": "Pre-Kickoff Internal Prep",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Review sales handoff notes, research customer company, prepare kickoff deck, provision accounts",
                    "instructions": "1. Review CRM notes from sales\n2. Research company size, industry, recent news\n3. Identify key stakeholders and their goals\n4. Customize kickoff presentation\n5. Ensure all user accounts are provisioned",
                    "required_outcomes": ["handoff_reviewed", "stakeholders_identified", "accounts_provisioned"]
                },
                {
                    "name": "Welcome Email & Success Plan",
                    "step_type": "email",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Send personalized welcome email with success plan, meeting invite, and resource links",
                    "email_subject": "Welcome to ECBTX - Your Success Journey Begins",
                    "email_body_template": "Welcome {customer_name}! I'm {csm_name}, your dedicated Customer Success Manager. Let's schedule your kickoff call to align on your goals and set you up for success.",
                    "instructions": "Personalize with customer's specific goals from sales handoff. Include calendar link for kickoff scheduling."
                },
                {
                    "name": "Kickoff Call - Goal Alignment",
                    "step_type": "meeting",
                    "days_from_start": 3,
                    "due_days": 5,
                    "description": "60-minute strategic kickoff to establish goals, success criteria, and communication preferences",
                    "meeting_agenda_template": "1. Introductions (10 min)\n2. Customer Goals & Success Criteria (15 min)\n3. Solution Overview & How We Help (10 min)\n4. Onboarding Timeline & Milestones (10 min)\n5. Technical Requirements (10 min)\n6. Q&A & Next Steps (5 min)",
                    "talk_track": "What does success look like in 90 days? 6 months? What metrics will you use to measure our impact? What's the biggest pain point we need to solve first?",
                    "required_outcomes": ["goals_documented", "success_metrics_defined", "timeline_agreed"]
                },
                {
                    "name": "Technical Setup & Configuration",
                    "step_type": "internal_task",
                    "days_from_start": 5,
                    "due_days": 5,
                    "description": "Complete environment setup, data migration, integrations, and system configuration",
                    "instructions": "1. Configure customer environment\n2. Complete data import/migration\n3. Set up integrations with existing tools\n4. Configure user permissions and roles\n5. Verify all systems operational"
                },
                {
                    "name": "Admin Training Session",
                    "step_type": "training",
                    "days_from_start": 10,
                    "due_days": 3,
                    "description": "90-minute deep dive training for admin users on system configuration and management",
                    "meeting_agenda_template": "1. Admin Dashboard Overview (15 min)\n2. User Management (15 min)\n3. System Configuration (20 min)\n4. Reporting & Analytics (20 min)\n5. Best Practices & Tips (15 min)\n6. Q&A (5 min)"
                },
                {
                    "name": "End User Training",
                    "step_type": "training",
                    "days_from_start": 14,
                    "due_days": 5,
                    "description": "60-minute core training session for all users on daily workflows",
                    "instructions": "Focus on the 3-5 most critical features for their use case. Provide recorded session for future reference."
                },
                {
                    "name": "Week 2 Check-in Call",
                    "step_type": "call",
                    "days_from_start": 14,
                    "due_days": 3,
                    "description": "Quick pulse check on adoption progress, address questions, remove blockers",
                    "talk_track": "How is the team finding the platform? Any questions from training? What's working well? What challenges are you facing?"
                },
                {
                    "name": "First Value Milestone Review",
                    "step_type": "review",
                    "days_from_start": 21,
                    "due_days": 3,
                    "description": "Review first value achievement - has customer completed their first key workflow?",
                    "instructions": "Check if customer has: 1) Logged first service call 2) Generated first invoice 3) Completed first scheduled job. Document the 'aha moment'."
                },
                {
                    "name": "30-Day Success Review Meeting",
                    "step_type": "meeting",
                    "days_from_start": 28,
                    "due_days": 5,
                    "description": "Formal 30-day review of progress, adoption metrics, and goal tracking",
                    "meeting_agenda_template": "1. Progress Review vs Goals (15 min)\n2. Adoption Metrics Analysis (10 min)\n3. Feature Usage Deep Dive (10 min)\n4. Roadmap & Next 60 Days (10 min)\n5. Action Items & Commitments (5 min)",
                    "talk_track": "Let's review your progress toward the goals we set. Here's what the data shows about your team's adoption..."
                },
                {
                    "name": "Champion Enablement Session",
                    "step_type": "training",
                    "days_from_start": 35,
                    "due_days": 5,
                    "description": "Advanced training for power users/champions to drive internal adoption",
                    "instructions": "Identify 1-2 champions. Provide advanced features training, internal advocacy toolkit, and escalation path direct to CSM."
                },
                {
                    "name": "60-Day Health Check",
                    "step_type": "call",
                    "days_from_start": 60,
                    "due_days": 5,
                    "description": "Mid-point check-in focusing on adoption acceleration and expansion opportunities",
                    "talk_track": "We're 2/3 through onboarding. Let's assess where you are vs. goals and identify any gaps to address in the final 30 days."
                },
                {
                    "name": "90-Day Graduation Review",
                    "step_type": "meeting",
                    "days_from_start": 85,
                    "due_days": 7,
                    "description": "Formal onboarding completion meeting - transition to ongoing success relationship",
                    "meeting_agenda_template": "1. Goals Achievement Summary (15 min)\n2. ROI & Value Delivered (10 min)\n3. Ongoing Cadence & Support (10 min)\n4. Expansion Opportunities (10 min)\n5. NPS Survey & Testimonial Request (5 min)",
                    "required_outcomes": ["onboarding_complete", "health_score_green", "cadence_established"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 2: CRITICAL CHURN PREVENTION (14-Day Rapid Response)
        # ============================================================
        {
            "name": "Critical At-Risk Intervention",
            "description": "14-day rapid response playbook for customers showing churn signals. AI-triggered when health score drops below threshold. Focuses on immediate stabilization, root cause analysis, and recovery plan execution.",
            "category": "churn_risk",
            "trigger_type": "health_threshold",
            "trigger_health_threshold": 50,
            "trigger_health_direction": "below",
            "priority": "critical",
            "target_completion_days": 14,
            "estimated_hours": 8.0,
            "success_criteria": {"health_score_increase": 20, "engagement_restored": True, "risk_mitigated": True},
            "steps": [
                {
                    "name": "Immediate Risk Assessment",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Analyze all risk signals: usage decline, support tickets, payment issues, champion changes",
                    "instructions": "Pull 30/60/90 day usage data. Review support history. Check billing status. Identify what triggered the health drop. Document findings.",
                    "required_outcomes": ["risk_factors_identified", "root_cause_hypothesis"]
                },
                {
                    "name": "Urgent Customer Outreach",
                    "step_type": "call",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Same-day call to primary contact. Show concern, not alarm. Seek to understand.",
                    "talk_track": "I noticed some changes in your account and wanted to check in personally. How are things going? Is there anything concerning you that I should know about? What challenges are you facing right now?",
                    "instructions": "Be empathetic, not defensive. Listen more than talk. Don't make promises yet - gather information."
                },
                {
                    "name": "Internal Escalation Brief",
                    "step_type": "internal_task",
                    "days_from_start": 1,
                    "due_days": 1,
                    "description": "Create escalation brief for CS leadership. High-value accounts require VP notification.",
                    "instructions": "Document: Customer value, risk level, root cause, proposed recovery actions, resources needed. Submit to CS Manager for review."
                },
                {
                    "name": "Executive Sponsor Engagement",
                    "step_type": "email",
                    "days_from_start": 2,
                    "due_days": 1,
                    "description": "Reach out to executive sponsor or secondary contact if primary unresponsive",
                    "email_subject": "Partnership Review Request - {company_name}",
                    "email_body_template": "I'm reaching out to schedule a brief discussion about your team's experience with our platform. We value your partnership and want to ensure we're meeting your needs.",
                    "instructions": "For high-value accounts, have your VP co-sign or send directly. Multi-thread the account."
                },
                {
                    "name": "Recovery Plan Development",
                    "step_type": "documentation",
                    "days_from_start": 3,
                    "due_days": 2,
                    "description": "Create detailed recovery plan with specific actions, owners, and success criteria",
                    "instructions": "Include: Root cause summary, specific recovery actions with owners and dates, customer commitments needed, success metrics, escalation triggers, check-in schedule."
                },
                {
                    "name": "Recovery Plan Presentation",
                    "step_type": "meeting",
                    "days_from_start": 5,
                    "due_days": 2,
                    "description": "Present recovery plan to customer. Get buy-in on mutual commitments.",
                    "meeting_agenda_template": "1. Acknowledge the Situation (5 min)\n2. Root Cause Discussion (10 min)\n3. Our Commitment & Recovery Plan (15 min)\n4. Your Commitments Needed (10 min)\n5. Success Metrics & Timeline (5 min)\n6. Next Steps (5 min)",
                    "talk_track": "We've identified what went wrong and here's our plan to fix it. We're committed to your success, but we need your partnership on a few things..."
                },
                {
                    "name": "Day 7 Progress Check",
                    "step_type": "call",
                    "days_from_start": 7,
                    "due_days": 1,
                    "description": "Weekly check-in on recovery progress. Address new blockers immediately.",
                    "talk_track": "Let's review our progress this week. What's improved? What's still challenging? How can I help accelerate the recovery?"
                },
                {
                    "name": "Support & Training Intervention",
                    "step_type": "training",
                    "days_from_start": 8,
                    "due_days": 3,
                    "description": "If adoption is the issue, provide intensive re-training or support intervention",
                    "instructions": "Schedule hands-on working session. Focus on their specific pain points. Leave them with clear next steps they can execute immediately."
                },
                {
                    "name": "Executive Business Review (if needed)",
                    "step_type": "meeting",
                    "days_from_start": 10,
                    "due_days": 3,
                    "description": "For high-value accounts, involve executive sponsors on both sides",
                    "instructions": "Only for strategic accounts or if recovery isn't progressing. Bring your CS Director or VP. Focus on partnership value and mutual investment."
                },
                {
                    "name": "Day 14 Recovery Assessment",
                    "step_type": "review",
                    "days_from_start": 14,
                    "due_days": 1,
                    "description": "Final assessment: Is customer stabilized? Health score improving? Engagement restored?",
                    "instructions": "Review all metrics. If recovery successful, transition to monitoring. If not, escalate for retention offer consideration or accept loss.",
                    "required_outcomes": ["recovery_assessed", "next_steps_determined", "health_score_updated"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 3: STRATEGIC RENEWAL PROGRAM (90-Day)
        # ============================================================
        {
            "name": "Strategic Renewal Program",
            "description": "90-day renewal excellence program. Begins 90 days before contract end. Combines value realization, executive alignment, and expansion opportunity identification.",
            "category": "renewal",
            "trigger_type": "days_to_renewal",
            "trigger_days_to_renewal": 90,
            "priority": "high",
            "target_completion_days": 90,
            "estimated_hours": 10.0,
            "success_criteria": {"renewal_closed": True, "expansion_identified": True, "multi_year_consideration": True},
            "steps": [
                {
                    "name": "Renewal Readiness Assessment",
                    "step_type": "review",
                    "days_from_start": 0,
                    "due_days": 3,
                    "description": "Internal assessment of renewal likelihood, expansion potential, and risk factors",
                    "instructions": "Score 1-5 on: Health Score Trend, Goal Achievement, Usage/Adoption, Relationship Strength, Support Experience, NPS, Champion Stability, Competitive Threat. Total 32+ = High confidence, 24-31 = Attention needed, <24 = At risk."
                },
                {
                    "name": "Value Delivered Documentation",
                    "step_type": "documentation",
                    "days_from_start": 3,
                    "due_days": 7,
                    "description": "Compile comprehensive value delivered summary with ROI metrics",
                    "instructions": "Document: Original goals vs achievement, quantified ROI, usage highlights, key wins with metrics, cost savings, efficiency gains. Prepare visual one-pager."
                },
                {
                    "name": "Expansion Opportunity Analysis",
                    "step_type": "internal_task",
                    "days_from_start": 7,
                    "due_days": 5,
                    "description": "Identify all expansion opportunities: additional services, more tanks, new locations, premium features",
                    "instructions": "Review usage patterns for capacity signals. Check for new department interest. Identify feature requests matching premium tier. Calculate potential expansion value."
                },
                {
                    "name": "Value Review Meeting",
                    "step_type": "meeting",
                    "days_from_start": 15,
                    "due_days": 5,
                    "description": "Present value delivered summary to customer. Confirm ROI and gather feedback.",
                    "meeting_agenda_template": "1. Relationship Check-in (5 min)\n2. Value Delivered Review (15 min)\n3. Goals Achievement Discussion (10 min)\n4. Future Goals & Needs (10 min)\n5. Next Steps (5 min)",
                    "talk_track": "Over the past year, here's the value we've delivered together... [ROI data]. Looking ahead, what are your goals for the next 12 months?"
                },
                {
                    "name": "Stakeholder Mapping & Multi-threading",
                    "step_type": "internal_task",
                    "days_from_start": 20,
                    "due_days": 5,
                    "description": "Identify all stakeholders involved in renewal decision. Ensure relationships at multiple levels.",
                    "instructions": "Map: Decision maker, Budget holder, Champion, Users, Detractors. Ensure you have relationships at 3+ levels. Schedule touchpoints with any gaps."
                },
                {
                    "name": "Executive Sponsor Touch-base",
                    "step_type": "call",
                    "days_from_start": 30,
                    "due_days": 5,
                    "description": "Connect with executive sponsor to ensure strategic alignment and surface any concerns",
                    "talk_track": "As we approach renewal, I wanted to check in at the strategic level. How does our partnership fit into your priorities for the coming year? Any concerns I should be aware of?"
                },
                {
                    "name": "Renewal Proposal Preparation",
                    "step_type": "documentation",
                    "days_from_start": 40,
                    "due_days": 5,
                    "description": "Prepare renewal proposal with options: same terms, multi-year, expansion",
                    "instructions": "Create 3 options: 1) Same terms renewal, 2) Multi-year with discount, 3) Expansion bundle. Include value summary, pricing, and ROI projections for each."
                },
                {
                    "name": "Renewal Discussion Meeting",
                    "step_type": "meeting",
                    "days_from_start": 50,
                    "due_days": 5,
                    "description": "Present renewal proposal, discuss options, handle objections",
                    "meeting_agenda_template": "1. Value Summary Recap (5 min)\n2. Future Vision Alignment (10 min)\n3. Renewal Options Presentation (15 min)\n4. Q&A and Objection Handling (15 min)\n5. Next Steps & Timeline (5 min)",
                    "talk_track": "Based on your goals and the value we've delivered, here are three options for moving forward..."
                },
                {
                    "name": "Negotiation & Objection Handling",
                    "step_type": "call",
                    "days_from_start": 60,
                    "due_days": 10,
                    "description": "Handle any negotiations, objections, or procurement requirements",
                    "instructions": "Common objections: Price too high (cite ROI), Need to evaluate options (offer comparison support), Not using enough (offer adoption sprint), Leadership approval needed (offer exec alignment call)."
                },
                {
                    "name": "Contract Finalization",
                    "step_type": "documentation",
                    "days_from_start": 75,
                    "due_days": 10,
                    "description": "Finalize contract, process signature, update billing",
                    "instructions": "Coordinate with legal/procurement. Ensure clean handoff to billing. Update CRM with new contract details."
                },
                {
                    "name": "Renewal Celebration & Next Year Kickoff",
                    "step_type": "email",
                    "days_from_start": 85,
                    "due_days": 5,
                    "description": "Thank you communication and kickoff of new contract term success plan",
                    "email_subject": "Thank You for Your Continued Partnership - Year 2 Success Plan",
                    "email_body_template": "Thank you for renewing! Here's what to expect in Year 2, including new features, your dedicated support resources, and our first check-in date...",
                    "required_outcomes": ["renewal_closed", "success_plan_created", "health_score_updated"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 4: EXPANSION & UPSELL ACCELERATION
        # ============================================================
        {
            "name": "Expansion Opportunity Accelerator",
            "description": "Structured program for identified expansion opportunities. Combines value-based selling, multi-stakeholder engagement, and ROI documentation. Best practice: Only pursue when health score > 70 and initial goals achieved.",
            "category": "expansion",
            "trigger_type": "manual",
            "priority": "high",
            "target_completion_days": 45,
            "estimated_hours": 8.0,
            "success_criteria": {"opportunity_qualified": True, "proposal_presented": True, "decision_made": True},
            "steps": [
                {
                    "name": "Expansion Readiness Check",
                    "step_type": "review",
                    "days_from_start": 0,
                    "due_days": 2,
                    "description": "Verify customer is ready for expansion: Health score > 70, goals achieved, relationship strong",
                    "instructions": "Check: Health score (must be >70), Goal achievement (>80%), Champion relationship (strong), No open escalations. If any fail, pause playbook and address first."
                },
                {
                    "name": "Opportunity Qualification (BANT)",
                    "step_type": "internal_task",
                    "days_from_start": 2,
                    "due_days": 2,
                    "description": "Qualify the opportunity: Budget, Authority, Need, Timeline",
                    "instructions": "Document: Do they have budget? Who approves? What problem does expansion solve? When do they need it? Score opportunity 1-4 on each dimension."
                },
                {
                    "name": "Value-Based Discovery Call",
                    "step_type": "call",
                    "days_from_start": 5,
                    "due_days": 3,
                    "description": "Deep discovery on expanded needs, pain points, and business impact",
                    "talk_track": "You've been so successful with [current use]. Tell me about [expanded need]. What would it mean for your business if you could [desired outcome]? What's the cost of not solving this?",
                    "instructions": "Focus 80% on their needs, 20% on solution. Quantify the pain. Get them to articulate the value."
                },
                {
                    "name": "Internal Deal Review",
                    "step_type": "internal_task",
                    "days_from_start": 10,
                    "due_days": 2,
                    "description": "Review opportunity with sales/account team. Align on approach and pricing.",
                    "instructions": "Present: Customer situation, expansion opportunity, qualification score, proposed solution, pricing recommendation, timeline. Get alignment on deal strategy."
                },
                {
                    "name": "ROI Business Case Development",
                    "step_type": "documentation",
                    "days_from_start": 12,
                    "due_days": 5,
                    "description": "Build compelling ROI business case with customer-specific data",
                    "instructions": "Calculate: Investment amount, Expected benefits (quantified), ROI %, Payback period. Use customer's own data where possible. Include case studies from similar customers."
                },
                {
                    "name": "Champion Alignment",
                    "step_type": "call",
                    "days_from_start": 18,
                    "due_days": 3,
                    "description": "Preview proposal with champion. Get feedback and buy-in before formal presentation.",
                    "talk_track": "Before I present to the broader team, I wanted to get your input on our proposal. Does this address your needs? What concerns might others have?",
                    "instructions": "Champions can preview objections and help you tailor the presentation. Their buy-in is critical."
                },
                {
                    "name": "Expansion Proposal Presentation",
                    "step_type": "meeting",
                    "days_from_start": 22,
                    "due_days": 5,
                    "description": "Present expansion proposal to decision-makers",
                    "meeting_agenda_template": "1. Current Success Recap (5 min)\n2. Identified Opportunity (10 min)\n3. Proposed Solution & Benefits (15 min)\n4. ROI & Business Case (10 min)\n5. Investment & Options (5 min)\n6. Q&A & Next Steps (10 min)",
                    "instructions": "Have champion introduce you if possible. Lead with their pain, not your product. Let ROI do the convincing."
                },
                {
                    "name": "Negotiation & Closing",
                    "step_type": "call",
                    "days_from_start": 30,
                    "due_days": 10,
                    "description": "Handle objections, negotiate terms, close the expansion",
                    "instructions": "Common stalls: Need more time (offer trial), Too expensive (emphasize ROI), Not right now (anchor to their timeline/pain). Don't discount without getting something in return."
                },
                {
                    "name": "Expansion Handoff & Kickoff",
                    "step_type": "internal_task",
                    "days_from_start": 42,
                    "due_days": 5,
                    "description": "Hand off to implementation, schedule expansion kickoff, update health score",
                    "instructions": "Document: Expansion details, customer expectations, timeline, success criteria. Trigger expansion onboarding playbook if applicable.",
                    "required_outcomes": ["expansion_closed", "implementation_scheduled", "health_updated"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 5: EXECUTIVE BUSINESS REVIEW (QBR/EBR)
        # ============================================================
        {
            "name": "Executive Business Review",
            "description": "Comprehensive EBR program that transforms QBRs from status updates to strategic partnership discussions. Focuses on value demonstration, executive alignment, and strategic planning.",
            "category": "qbr",
            "trigger_type": "scheduled",
            "priority": "medium",
            "target_completion_days": 21,
            "estimated_hours": 6.0,
            "success_criteria": {"ebr_completed": True, "next_quarter_plan": True, "executive_engaged": True},
            "steps": [
                {
                    "name": "EBR Prep - Data Analysis",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 5,
                    "description": "Analyze all customer data: usage, health score trends, support tickets, NPS, goal progress",
                    "instructions": "Pull: Usage trends (up/down), Feature adoption by team, Support ticket themes, NPS score and verbatims, Health score trend, Goal achievement %. Create visual dashboard."
                },
                {
                    "name": "Internal Strategy Session",
                    "step_type": "internal_task",
                    "days_from_start": 5,
                    "due_days": 2,
                    "description": "Align internal team on EBR objectives, opportunities, and risks",
                    "instructions": "Review with: Account Executive (expansion opps), Support Lead (ticket trends), Product (roadmap items). Define: 3 wins to highlight, 1 area for improvement, 1 expansion discussion."
                },
                {
                    "name": "EBR Deck Preparation",
                    "step_type": "documentation",
                    "days_from_start": 7,
                    "due_days": 3,
                    "description": "Create executive-level presentation deck",
                    "instructions": "Structure: Executive Summary (1 slide), Value Delivered (2-3 slides), Looking Ahead (2 slides), Strategic Discussion (1 slide). Keep to 10 slides max. Lead with insights, not data dumps."
                },
                {
                    "name": "Pre-EBR Champion Sync",
                    "step_type": "call",
                    "days_from_start": 10,
                    "due_days": 2,
                    "description": "Preview EBR content with champion, gather intel on executive priorities",
                    "talk_track": "I'm preparing for our EBR with [exec]. What's top of mind for them right now? Any sensitive topics I should be aware of? What would make this meeting most valuable for you?",
                    "instructions": "Champions provide invaluable intel. Adjust presentation based on their feedback."
                },
                {
                    "name": "Executive Business Review Meeting",
                    "step_type": "meeting",
                    "days_from_start": 14,
                    "due_days": 3,
                    "description": "Conduct strategic EBR with executive stakeholders",
                    "meeting_agenda_template": "1. Executive Summary & Key Outcomes (5 min)\n2. Value Delivered This Quarter (10 min)\n3. Strategic Alignment Discussion (15 min)\n4. Roadmap & Innovation Preview (10 min)\n5. Next Quarter Success Plan (10 min)\n6. Partnership Feedback (5 min)",
                    "talk_track": "The goal today is to ensure we're aligned on the strategic value we're delivering and your priorities for the next quarter. Let's start with the key wins..."
                },
                {
                    "name": "EBR Follow-up & Action Items",
                    "step_type": "email",
                    "days_from_start": 15,
                    "due_days": 2,
                    "description": "Send EBR summary, action items, and next quarter success plan",
                    "email_subject": "EBR Summary & Q[X] Success Plan - {company_name}",
                    "email_body_template": "Thank you for the strategic discussion today. Attached is our EBR summary and the success plan for next quarter. Key action items: [list]. Our next check-in is scheduled for [date]."
                },
                {
                    "name": "Internal EBR Debrief",
                    "step_type": "internal_task",
                    "days_from_start": 16,
                    "due_days": 2,
                    "description": "Debrief with internal team, update account strategy, create action items",
                    "instructions": "Document: Key takeaways, new information learned, risks identified, expansion signals, required internal actions. Update account plan."
                },
                {
                    "name": "Action Item Execution Kickoff",
                    "step_type": "internal_task",
                    "days_from_start": 18,
                    "due_days": 3,
                    "description": "Begin executing on committed action items from EBR",
                    "instructions": "Assign owners to each action item. Set deadlines. Schedule follow-up with customer if action items require their involvement.",
                    "required_outcomes": ["ebr_completed", "action_items_assigned", "next_ebr_scheduled"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 6: ESCALATION RESPONSE & RECOVERY
        # ============================================================
        {
            "name": "Escalation Response & Recovery",
            "description": "Structured escalation handling process for critical customer issues. Ensures rapid response, thorough resolution, and relationship recovery. Best practice: Turn escalations into opportunities to deepen trust.",
            "category": "churn_risk",
            "trigger_type": "manual",
            "priority": "critical",
            "target_completion_days": 7,
            "estimated_hours": 5.0,
            "success_criteria": {"issue_resolved": True, "customer_satisfied": True, "relationship_recovered": True},
            "steps": [
                {
                    "name": "Immediate Acknowledgment",
                    "step_type": "call",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Call customer within 1 hour of escalation. Acknowledge, empathize, commit to resolution.",
                    "talk_track": "I understand you're experiencing [issue] and I want you to know this is my top priority. I'm personally taking ownership of this. Let me understand exactly what happened...",
                    "instructions": "No excuses, no deflection. Own it. Get full details. Commit to a follow-up timeline."
                },
                {
                    "name": "Internal Escalation & War Room",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Assemble cross-functional team, brief leadership, begin root cause analysis",
                    "instructions": "Notify: CS Manager, Support Lead, Engineering (if technical), Executive sponsor (if high value). Create war room channel. Document timeline, impact, customer sentiment."
                },
                {
                    "name": "Root Cause Analysis",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Conduct thorough root cause analysis with all relevant teams",
                    "instructions": "5 Whys analysis. Document: What happened, When, How it was discovered, Impact scope, Root cause, Contributing factors. No blame - focus on systems and processes."
                },
                {
                    "name": "Resolution Plan Development",
                    "step_type": "internal_task",
                    "days_from_start": 1,
                    "due_days": 1,
                    "description": "Create comprehensive resolution plan with preventive measures",
                    "instructions": "Include: Immediate fix, Short-term workaround (if needed), Permanent solution with timeline, Preventive measures, Customer communication plan. Get sign-off from all stakeholders."
                },
                {
                    "name": "Customer Resolution Call",
                    "step_type": "call",
                    "days_from_start": 2,
                    "due_days": 1,
                    "description": "Present root cause and resolution plan to customer",
                    "talk_track": "I want to share what we learned and our plan to make this right. Here's what happened... Here's why it happened... Here's what we're doing to fix it and ensure it never happens again...",
                    "instructions": "Be transparent. Own the failure. Show concrete actions. Ask for their feedback on the plan."
                },
                {
                    "name": "Resolution Implementation",
                    "step_type": "internal_task",
                    "days_from_start": 2,
                    "due_days": 3,
                    "description": "Execute resolution plan, keep customer updated on progress",
                    "instructions": "Daily internal stand-ups. Customer updates every 24 hours minimum. Document all actions taken. Verify fix with customer before closing."
                },
                {
                    "name": "Customer Verification & Sign-off",
                    "step_type": "call",
                    "days_from_start": 5,
                    "due_days": 1,
                    "description": "Confirm resolution with customer, verify they're satisfied",
                    "talk_track": "I believe we've resolved the issue. Can you confirm everything is working as expected? Is there anything else we should address? How are you feeling about our partnership?",
                    "instructions": "Don't close until customer explicitly confirms satisfaction. Address any lingering concerns."
                },
                {
                    "name": "Internal Post-Mortem",
                    "step_type": "internal_task",
                    "days_from_start": 6,
                    "due_days": 1,
                    "description": "Conduct blameless post-mortem, document learnings, update processes",
                    "instructions": "Document: Timeline, Impact, Root cause, Actions taken, Lessons learned, Process improvements. Share with relevant teams. Update runbooks/playbooks as needed."
                },
                {
                    "name": "Relationship Recovery Follow-up",
                    "step_type": "call",
                    "days_from_start": 7,
                    "due_days": 2,
                    "description": "One week follow-up to ensure issue remains resolved and relationship is recovering",
                    "talk_track": "I wanted to check in one week after our escalation. Is everything still working well? How is the team feeling? Is there anything more we can do?",
                    "instructions": "Consider goodwill gesture if appropriate (credit, extended support, executive call). Update health score based on recovery.",
                    "required_outcomes": ["issue_resolved", "customer_satisfied", "post_mortem_complete", "health_updated"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 7: CHAMPION CHANGE MANAGEMENT
        # ============================================================
        {
            "name": "Champion Change Management",
            "description": "Proactive playbook for managing customer champion transitions. Maintains account stability and identifies new champions when primary contacts leave or change roles.",
            "category": "churn_risk",
            "trigger_type": "manual",
            "priority": "high",
            "target_completion_days": 30,
            "estimated_hours": 5.0,
            "success_criteria": {"new_champion_identified": True, "relationships_maintained": True, "health_stable": True},
            "steps": [
                {
                    "name": "Transition Risk Assessment",
                    "step_type": "internal_task",
                    "days_from_start": 0,
                    "due_days": 1,
                    "description": "Assess impact of champion change on account health and stability",
                    "instructions": "Evaluate: Account health score, Other relationships in account, New champion's attitude toward us, Previous champion's departure circumstances, Competitive risk, Contract timeline."
                },
                {
                    "name": "Departing Champion Conversation",
                    "step_type": "call",
                    "days_from_start": 1,
                    "due_days": 2,
                    "description": "Connect with departing champion to understand transition, get introductions",
                    "talk_track": "I heard about your transition. Congratulations on [new role/opportunity]. Before you go, could you help me ensure a smooth transition? Who should I be working with going forward? Would you be able to make an introduction?",
                    "instructions": "Get: Recommended contacts, Context on their perspective, Introduction email or call, Their new contact info for future networking."
                },
                {
                    "name": "New Champion Research",
                    "step_type": "internal_task",
                    "days_from_start": 2,
                    "due_days": 2,
                    "description": "Research new contact's background, priorities, and communication preferences",
                    "instructions": "LinkedIn research: Background, tenure, priorities, communication style. Check internal notes for any previous interactions. Prepare tailored approach."
                },
                {
                    "name": "New Champion Introduction",
                    "step_type": "call",
                    "days_from_start": 5,
                    "due_days": 3,
                    "description": "Initial introduction call with new champion",
                    "talk_track": "I'm reaching out as your Customer Success Manager. I'd love to learn about your priorities and how we can best support you. Could you tell me about your goals in this role?",
                    "instructions": "Listen mode. Understand their priorities, concerns, and decision-making style. Don't assume they have same goals as predecessor."
                },
                {
                    "name": "Value Re-Demonstration",
                    "step_type": "meeting",
                    "days_from_start": 10,
                    "due_days": 5,
                    "description": "Present tailored value overview to new champion",
                    "meeting_agenda_template": "1. Your Priorities & Goals (15 min)\n2. Current Value We're Delivering (10 min)\n3. Quick Platform Overview (10 min)\n4. How We Can Help You Succeed (10 min)\n5. Next Steps (5 min)",
                    "instructions": "This is essentially a mini-sales presentation. New champions may not know what we do or the value we provide."
                },
                {
                    "name": "Multi-Threading Assessment",
                    "step_type": "internal_task",
                    "days_from_start": 15,
                    "due_days": 3,
                    "description": "Ensure relationships exist at multiple levels to reduce single-point-of-failure risk",
                    "instructions": "Map all contacts. Identify gaps at: Executive level, Technical level, End user level, Finance/procurement. Schedule touchpoints to fill gaps."
                },
                {
                    "name": "30-Day Check-in",
                    "step_type": "call",
                    "days_from_start": 28,
                    "due_days": 3,
                    "description": "One month check-in with new champion to assess relationship strength",
                    "talk_track": "It's been about a month since we started working together. How are you feeling about the partnership? Is there anything we could be doing better? What are your goals for the next quarter?",
                    "instructions": "Gauge: Are they engaged? Becoming an advocate? Any concerns? Update health score and champion strength rating.",
                    "required_outcomes": ["new_champion_established", "relationship_assessed", "multi_threaded", "health_updated"]
                }
            ]
        },
        # ============================================================
        # PLAYBOOK 8: IMPLEMENTATION SUCCESS PROGRAM
        # ============================================================
        {
            "name": "Implementation Success Program",
            "description": "Ensures successful implementation for customers with complex technical requirements. Bridges the gap between sales and ongoing success. Critical for enterprise customers with integration needs.",
            "category": "onboarding",
            "trigger_type": "segment_entry",
            "priority": "high",
            "target_completion_days": 45,
            "estimated_hours": 15.0,
            "success_criteria": {"implementation_complete": True, "integrations_working": True, "users_trained": True, "go_live_successful": True},
            "steps": [
                {
                    "name": "Technical Discovery & Scoping",
                    "step_type": "meeting",
                    "days_from_start": 0,
                    "due_days": 3,
                    "description": "Deep-dive technical discovery to scope implementation requirements",
                    "meeting_agenda_template": "1. Current Technology Stack (10 min)\n2. Integration Requirements (20 min)\n3. Data Migration Needs (15 min)\n4. Security & Compliance (10 min)\n5. Timeline & Milestones (10 min)\n6. Resource Requirements (5 min)",
                    "instructions": "Involve technical team. Document all requirements. Identify potential blockers early. Set realistic timeline expectations."
                },
                {
                    "name": "Implementation Plan Development",
                    "step_type": "documentation",
                    "days_from_start": 3,
                    "due_days": 3,
                    "description": "Create detailed implementation project plan with milestones",
                    "instructions": "Include: Project phases, Milestones with dates, Resource requirements (both sides), Risk register, Communication plan, Go-live criteria, Rollback plan."
                },
                {
                    "name": "Implementation Kickoff",
                    "step_type": "meeting",
                    "days_from_start": 7,
                    "due_days": 2,
                    "description": "Formal implementation kickoff with all stakeholders",
                    "meeting_agenda_template": "1. Project Overview & Goals (10 min)\n2. Team Introductions (10 min)\n3. Implementation Plan Review (20 min)\n4. Roles & Responsibilities (10 min)\n5. Communication & Escalation (5 min)\n6. Q&A & Next Steps (5 min)"
                },
                {
                    "name": "Environment Setup & Configuration",
                    "step_type": "internal_task",
                    "days_from_start": 10,
                    "due_days": 7,
                    "description": "Complete technical environment setup, configuration, and security hardening",
                    "instructions": "Setup checklist: Provision environment, Configure security settings, Set up SSO/authentication, Configure roles and permissions, Complete security review."
                },
                {
                    "name": "Integration Development",
                    "step_type": "internal_task",
                    "days_from_start": 14,
                    "due_days": 10,
                    "description": "Build and test required integrations with customer systems",
                    "instructions": "For each integration: Build connection, Test in sandbox, Document any limitations, Create monitoring alerts, Prepare rollback procedure."
                },
                {
                    "name": "Data Migration",
                    "step_type": "internal_task",
                    "days_from_start": 21,
                    "due_days": 7,
                    "description": "Execute data migration and validation",
                    "instructions": "Steps: Data extraction, Transformation mapping, Test migration (sample), Full migration, Validation with customer, Sign-off on data accuracy."
                },
                {
                    "name": "User Acceptance Testing",
                    "step_type": "meeting",
                    "days_from_start": 30,
                    "due_days": 5,
                    "description": "Conduct UAT with customer team, document and resolve issues",
                    "instructions": "Prepare UAT scripts. Walk through critical workflows. Document all issues. Prioritize fixes. Get written sign-off before proceeding to training."
                },
                {
                    "name": "End User Training",
                    "step_type": "training",
                    "days_from_start": 35,
                    "due_days": 5,
                    "description": "Comprehensive training program for all user groups",
                    "instructions": "Train: Admin users (deep dive), Power users (full training), End users (core workflows). Provide: Documentation, Video recordings, Quick reference guides."
                },
                {
                    "name": "Go-Live Execution",
                    "step_type": "internal_task",
                    "days_from_start": 42,
                    "due_days": 2,
                    "description": "Execute go-live with hypercare support",
                    "instructions": "Go-live checklist: Final system check, Cutover execution, Data freeze and final sync, Go-live announcement, Hypercare support activated, War room for issues."
                },
                {
                    "name": "Post-Implementation Review",
                    "step_type": "meeting",
                    "days_from_start": 45,
                    "due_days": 3,
                    "description": "Review implementation success, transition to ongoing support",
                    "meeting_agenda_template": "1. Implementation Summary (10 min)\n2. Goals Achieved (10 min)\n3. Open Items & Timeline (10 min)\n4. Support Model & Escalation (10 min)\n5. Transition to CSM (10 min)\n6. Feedback & Next Steps (5 min)",
                    "required_outcomes": ["implementation_complete", "customer_signed_off", "transitioned_to_csm", "health_score_set"]
                }
            ]
        }
    ]
