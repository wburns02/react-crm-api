"""Seed data for the two lifecycle workflow templates.

Shape matches `app.hr.workflow.schemas.TemplateIn` so callers can pass these
dicts straight into `create_template` if they want.  Migration 104 uses the
raw values and writes via raw SQL to avoid circular imports at alembic boot.
"""
from typing import Any


ONBOARDING_TEMPLATE: dict[str, Any] = {
    "name": "New Field Tech Onboarding",
    "category": "onboarding",
    "tasks": [
        # Pre-Day 1
        {"position": 1, "stage": "pre_day_one", "name": "Sign Employment Agreement",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "employment_agreement_2026"}},
        {"position": 2, "stage": "pre_day_one", "name": "Sign I-9 Section 1",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "i9"}},
        {"position": 3, "stage": "pre_day_one", "name": "Sign W-4 2026",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "w4_2026"}},
        {"position": 4, "stage": "pre_day_one", "name": "Complete ADP Employee Information Form",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "adp_info"}},
        {"position": 5, "stage": "pre_day_one", "name": "Elect AFA health plan",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "benefits_election"}},
        {"position": 6, "stage": "pre_day_one", "name": "Submit direct deposit authorization",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"document_template_kind": "adp_info"}},
        {"position": 7, "stage": "pre_day_one", "name": "Upload copy of driver's license",
         "kind": "document_upload", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"doc_kind": "license"}},
        {"position": 8, "stage": "pre_day_one", "name": "Upload DOT medical card",
         "kind": "document_upload", "assignee_role": "hire", "due_offset_days": 0,
         "config": {"doc_kind": "dot_med_card"}},
        {"position": 9, "stage": "pre_day_one", "name": "Upload CDL (if applicable)",
         "kind": "document_upload", "assignee_role": "hire", "due_offset_days": 0,
         "required": False, "config": {"doc_kind": "cdl"}},
        {"position": 10, "stage": "pre_day_one", "name": "Verify I-9 Section 2",
         "kind": "verify", "assignee_role": "hr", "due_offset_days": 0,
         "depends_on": [2, 7]},
        {"position": 11, "stage": "pre_day_one", "name": "Run background check",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 0},
        {"position": 12, "stage": "pre_day_one", "name": "Schedule drug test",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 0},
        # Day 1
        {"position": 13, "stage": "day_1", "name": "Uniform + PPE fitting",
         "kind": "manual", "assignee_role": "manager", "due_offset_days": 1},
        {"position": 14, "stage": "day_1", "name": "Create CRM account",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 1,
         "config": {"system": "crm"}},
        {"position": 15, "stage": "day_1", "name": "Issue company phone + Google Workspace account",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 1,
         "config": {"system": "google_workspace"}},
        {"position": 16, "stage": "day_1", "name": "Assign truck",
         "kind": "assignment", "assignee_role": "manager", "due_offset_days": 1,
         "depends_on": [7], "config": {"asset_type": "vehicle"}},
        {"position": 17, "stage": "day_1", "name": "Issue fuel card",
         "kind": "assignment", "assignee_role": "manager", "due_offset_days": 1,
         "config": {"asset_type": "fuel_card"}},
        {"position": 18, "stage": "day_1", "name": "Sign Employee Handbook Acknowledgement",
         "kind": "form_sign", "assignee_role": "hire", "due_offset_days": 1,
         "config": {"document_template_kind": "adp_info"}},
        {"position": 19, "stage": "day_1", "name": "Watch safety training videos",
         "kind": "training_video", "assignee_role": "hire", "due_offset_days": 1,
         "config": {"video_count": 4}},
        # Week 1
        {"position": 20, "stage": "week_1", "name": "3-day ride-along check-in",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 3},
        {"position": 21, "stage": "week_1", "name": "Complete TCEQ OS-0 study materials",
         "kind": "training_video", "assignee_role": "hire", "due_offset_days": 7},
        # Month 1
        {"position": 22, "stage": "month_1", "name": "30-day review",
         "kind": "manual", "assignee_role": "manager", "due_offset_days": 30},
        {"position": 23, "stage": "month_1", "name": "Confirm all certs logged",
         "kind": "verify", "assignee_role": "hr", "due_offset_days": 30,
         "depends_on": [8, 9]},
    ],
}


OFFBOARDING_TEMPLATE: dict[str, Any] = {
    "name": "Tech Separation",
    "category": "offboarding",
    "tasks": [
        {"position": 1, "name": "Record separation reason + last day",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 0},
        {"position": 2, "name": "Exit interview",
         "kind": "form_sign", "assignee_role": "employee", "due_offset_days": 0},
        {"position": 3, "name": "Return company truck",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 0,
         "config": {"close": "hr_truck_assignments"}},
        {"position": 4, "name": "Return company phone",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 0},
        {"position": 5, "name": "Return uniforms + PPE",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 0},
        {"position": 6, "name": "Inventory audit of truck stock",
         "kind": "verify", "assignee_role": "manager", "due_offset_days": 0,
         "depends_on": [3]},
        {"position": 7, "name": "Kill fuel card",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"close": "hr_fuel_card_assignments"}},
        {"position": 8, "name": "Revoke CRM access",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"system": "crm", "close_grant": True}},
        {"position": 9, "name": "Revoke Google Workspace",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"system": "google_workspace", "close_grant": True}},
        {"position": 10, "name": "Revoke RingCentral",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"system": "ringcentral", "close_grant": True}},
        {"position": 11, "name": "Revoke Samsara",
         "kind": "assignment", "assignee_role": "it", "due_offset_days": 0,
         "config": {"system": "samsara", "close_grant": True}},
        {"position": 12, "name": "Final paycheck cut in ADP",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 1},
        {"position": 13, "name": "Send COBRA notification",
         "kind": "form_sign", "assignee_role": "hr", "due_offset_days": 1},
        {"position": 14, "name": "Terminate in ADP + mark inactive in CRM",
         "kind": "manual", "assignee_role": "hr", "due_offset_days": 2,
         "depends_on": [12]},
    ],
}


def _template_payload(template: dict[str, Any]) -> dict[str, Any]:
    return template


LIFECYCLE_TEMPLATES: list[dict[str, Any]] = [ONBOARDING_TEMPLATE, OFFBOARDING_TEMPLATE]
