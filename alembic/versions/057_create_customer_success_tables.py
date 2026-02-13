"""Create all Customer Success platform tables.

Creates 41 cs_* tables for the Enterprise Customer Success platform including:
- Health scores and events
- Segments, rules, memberships, snapshots
- Journeys, steps, enrollments
- Playbooks, steps, executions
- Tasks, touchpoints
- Surveys, questions, responses, answers, analyses, actions
- Campaigns, steps, enrollments
- Escalations, notes, activities
- Collaboration resources, likes, comments, team notes
- Send time optimization profiles
- A/B tests

Uses metadata.create_all with checkfirst=True so it's safe to re-run.

Revision ID: 057
Revises: 056
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision = "057"
down_revision = "056"
branch_labels = None
depends_on = None


def upgrade():
    """Create all CS tables using SQLAlchemy model metadata."""
    # Import all CS models to register them with Base.metadata
    from app.models.customer_success import (
        HealthScore,
        HealthScoreEvent,
        Segment,
        CustomerSegment,
        SegmentRule,
        SegmentMembership,
        SegmentSnapshot,
        Journey,
        JourneyStep,
        JourneyEnrollment,
        JourneyStepExecution,
        Playbook,
        PlaybookStep,
        PlaybookExecution,
        CSTask,
        Touchpoint,
        Survey,
        SurveyQuestion,
        SurveyResponse,
        SurveyAnswer,
        SurveyAnalysis,
        SurveyAction,
        Campaign,
        CampaignStep,
        CampaignEnrollment,
        CampaignStepExecution,
        Escalation,
        EscalationNote,
        EscalationActivity,
        CSResource,
        CSResourceLike,
        CSResourceComment,
        CSTeamNote,
        CSTeamNoteComment,
        CSActivity,
        CustomerSendTimeProfile,
        CampaignSendTimeAnalysis,
        ABTest,
    )
    from app.database import Base

    # Get the connection from the Alembic context
    bind = op.get_bind()

    # Get list of existing tables
    inspector = inspect(bind)
    existing_tables = set(inspector.get_table_names())

    # All CS table names (in dependency order)
    cs_tables = [
        # Independent tables first
        "cs_health_scores",
        "cs_segments",
        "cs_journeys",
        "cs_playbooks",
        "cs_tasks",
        "cs_touchpoints",
        "cs_surveys",
        "cs_campaigns",
        "cs_escalations",
        "cs_resources",
        "cs_team_notes",
        "cs_activities",
        "cs_customer_send_profiles",
        "cs_campaign_send_analysis",
        "cs_ab_tests",
        # Dependent tables
        "cs_health_score_events",
        "cs_segment_rules",
        "cs_segment_memberships",
        "cs_segment_snapshots",
        "cs_customer_segments",
        "cs_journey_steps",
        "cs_journey_enrollments",
        "cs_journey_step_executions",
        "cs_playbook_steps",
        "cs_playbook_executions",
        "cs_survey_questions",
        "cs_survey_responses",
        "cs_survey_answers",
        "cs_survey_analyses",
        "cs_survey_actions",
        "cs_campaign_steps",
        "cs_campaign_enrollments",
        "cs_campaign_step_executions",
        "cs_escalation_notes",
        "cs_escalation_activities",
        "cs_resource_likes",
        "cs_resource_comments",
        "cs_team_note_comments",
    ]

    # Filter to only tables that need to be created
    tables_to_create = [t for t in cs_tables if t not in existing_tables]

    if not tables_to_create:
        print("All CS tables already exist. Nothing to do.")
        return

    print(f"Creating {len(tables_to_create)} CS tables: {', '.join(tables_to_create)}")

    # Create only CS tables using metadata
    cs_table_objects = [
        table for name, table in Base.metadata.tables.items()
        if name.startswith("cs_") and name in tables_to_create
    ]

    if cs_table_objects:
        Base.metadata.create_all(bind=bind, tables=cs_table_objects, checkfirst=True)
        print(f"Successfully created {len(cs_table_objects)} CS tables.")
    else:
        print("No CS table objects found in metadata.")


def downgrade():
    """Drop all CS tables in reverse dependency order."""
    cs_tables_reverse = [
        # Dependent tables first (reverse order)
        "cs_team_note_comments",
        "cs_resource_comments",
        "cs_resource_likes",
        "cs_escalation_activities",
        "cs_escalation_notes",
        "cs_campaign_step_executions",
        "cs_campaign_enrollments",
        "cs_campaign_steps",
        "cs_survey_actions",
        "cs_survey_analyses",
        "cs_survey_answers",
        "cs_survey_responses",
        "cs_survey_questions",
        "cs_playbook_executions",
        "cs_playbook_steps",
        "cs_journey_step_executions",
        "cs_journey_enrollments",
        "cs_journey_steps",
        "cs_customer_segments",
        "cs_segment_snapshots",
        "cs_segment_memberships",
        "cs_segment_rules",
        "cs_health_score_events",
        # Independent tables last
        "cs_ab_tests",
        "cs_campaign_send_analysis",
        "cs_customer_send_profiles",
        "cs_activities",
        "cs_team_notes",
        "cs_resources",
        "cs_escalations",
        "cs_campaigns",
        "cs_surveys",
        "cs_touchpoints",
        "cs_tasks",
        "cs_playbooks",
        "cs_journeys",
        "cs_segments",
        "cs_health_scores",
    ]

    # Also drop ENUM types
    cs_enums = [
        "cs_health_status_enum",
        "cs_score_trend_enum",
        "cs_health_event_type_enum",
        "cs_segment_type_enum",
        "cs_rule_mode_enum",
        "cs_rule_logic_enum",
        "cs_rule_operator_enum",
        "cs_snapshot_type_enum",
    ]

    for table_name in cs_tables_reverse:
        op.execute(f"DROP TABLE IF EXISTS {table_name} CASCADE")

    for enum_name in cs_enums:
        op.execute(f"DROP TYPE IF EXISTS {enum_name}")
