"""Default candidate SMS templates.

Each template is keyed by the destination stage. `{first_name}`,
`{requisition_title}`, `{company_name}` are the available placeholders —
the renderer does a plain ``.format()``.
"""
DEFAULTS: list[dict] = [
    {
        "stage": "screen",
        "body": "Hi {first_name}, thanks for applying for {requisition_title} at {company_name}. "
                "We'd like to schedule a quick screening call. Reply with your best times.",
    },
    {
        "stage": "ride_along",
        "body": "Hi {first_name}, we'd like to have you ride along on a shift. "
                "Reply with dates that work this week.",
    },
    {
        "stage": "offer",
        "body": "Great news {first_name} — we have an offer for {requisition_title}. "
                "Check your email for details and reply here with any questions.",
    },
    {
        "stage": "hired",
        "body": "Welcome to the team, {first_name}! You'll get onboarding paperwork by email shortly.",
    },
    {
        "stage": "rejected",
        "body": "Hi {first_name}, thanks for your interest in {requisition_title}. "
                "We've decided to go with other candidates at this time. Best of luck.",
    },
]
