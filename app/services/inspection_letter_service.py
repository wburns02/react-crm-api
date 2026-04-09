"""Inspection Letter Service — AI draft generation + PDF rendering.

Part 1: generate_letter_draft() uses the AI gateway to produce a narrative
inspection letter in Doug Carter's exact writing style.

Part 2: render_letter_pdf() produces a WeasyPrint PDF on MAC Septic letterhead.
"""

import logging
from datetime import datetime
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Signer configuration
# ---------------------------------------------------------------------------

SIGNERS = {
    "matthew_carter": {
        "name": "Matthew Carter",
        "title": "President",
        "licenses": ["TDEC Pumping #972", "TDEC SSDSI #14228"],
    },
    "douglas_carter": {
        "name": "Douglas Carter",
        "title": "Executive Vice President",
        "licenses": ["TDEC Pumping #972", "TDEC SSDSI #14229"],
    },
    "marvin_carter": {
        "name": "Marvin Carter",
        "title": "Founder",
        "licenses": ["SC DHEC License #32-368-32022"],
    },
}

# ---------------------------------------------------------------------------
# Office addresses by state
# ---------------------------------------------------------------------------

OFFICES = {
    "TN": {
        "address": "8011 Brooks Chapel Rd. Unit 457, Brentwood, TN 37027",
        "phone": "(615) 345-2544",
    },
    "SC": {
        "address": "PO Box 722, Chapin, SC 29036",
        "phone": "803-223-9677",
    },
}

# ---------------------------------------------------------------------------
# Static disclaimer (identical on every letter)
# ---------------------------------------------------------------------------

DISCLAIMER = (
    "Septic systems are subterranean; therefore, it is not possible to "
    "determine their overall condition. No prediction can be made as to when "
    "or if a system might fail. This letter comments on the working ability "
    "of the system on the day of the evaluation only and is in no way "
    "intended to be a warranty. Workability can be altered by factors such "
    "as excessive rainfall, heavy water usage, faulty plumbing, neglect or "
    "physical damage to the system."
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _detect_state(address: str) -> str:
    """Return 'TN' or 'SC' based on the address string.  Defaults to TN."""
    if not address:
        return "TN"
    upper = address.upper()
    # Check for SC indicators
    for marker in [", SC ", " SC ", "SOUTH CAROLINA"]:
        if marker in upper:
            return "SC"
    return "TN"


def _build_inspection_text(checklist: dict) -> str:
    """Build a structured text representation of inspection data from the
    checklist steps so the AI can convert it into a narrative letter."""

    parts: list[str] = []
    steps = checklist.get("steps", {})

    # Step 1: Property / address info
    s1 = steps.get("1", {})
    addr_parts = []
    for f in ["address", "city", "state", "zip"]:
        v = s1.get(f) or checklist.get(f)
        if v:
            addr_parts.append(str(v))
    if addr_parts:
        parts.append(f"Address: {', '.join(addr_parts)}")

    # Step 2: Tank location
    s2 = steps.get("2", {})
    if s2.get("tank_location"):
        parts.append(f"Tank located {s2['tank_location']}")
    if s2.get("tank_depth"):
        parts.append(f"Tank ~{s2['tank_depth']} deep")
    if s2.get("surface_access"):
        parts.append(f"Surface access: {s2['surface_access']}")

    # Step 3: Permit / history
    s3 = steps.get("3", {})
    if s3.get("permit_info"):
        parts.append(f"Permit/history: {s3['permit_info']}")
    if s3.get("installation_year"):
        parts.append(f"Installed: {s3['installation_year']}")

    # Step 4: System type
    s4 = steps.get("4", {})
    if s4.get("system_type"):
        parts.append(f"System type: {s4['system_type']}")
    if s4.get("tank_capacity"):
        parts.append(f"Estimated capacity: {s4['tank_capacity']}")
    if s4.get("condition"):
        parts.append(f"Condition: {s4['condition']}")

    # Step 5: Pumping
    s5 = steps.get("5", {})
    pumped = s5.get("pumped") or s5.get("pumped_during_inspection")
    if pumped:
        parts.append(f"Pumped during inspection: {pumped}")
    if s5.get("baffles"):
        parts.append(f"Baffles: {s5['baffles']}")
    if s5.get("operational_test"):
        parts.append(f"Operational test: {s5['operational_test']}")

    # Step 6: Notable observations / aerobic / pump info
    s6 = steps.get("6", {})
    if s6.get("notable_observations"):
        parts.append(f"Notable: {s6['notable_observations']}")
    if s6.get("pump_info"):
        parts.append(f"Pump: {s6['pump_info']}")
    if s6.get("pump_chamber"):
        parts.append(f"Pump chamber: {s6['pump_chamber']}")

    # Step 7: Drain field
    s7 = steps.get("7", {})
    if s7.get("drain_field"):
        parts.append(f"Drain field: {s7['drain_field']}")

    # Additional custom fields
    custom = checklist.get("customFields", {})
    if custom.get("homeowner_present"):
        parts.append("Homeowner present during inspection, permission received.")
    for key in ["additional_notes", "extra_observations"]:
        if custom.get(key):
            parts.append(custom[key])

    return ". ".join(parts) if parts else ""


# ---------------------------------------------------------------------------
# System prompt for AI letter generation
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a professional writer for MAC Septic Services. Your job is to convert structured inspection data into a polished narrative inspection letter body written in Douglas Carter's exact style.

STYLE RULES:
- Always third person ("MAC Septic", never "I" or "we")
- Use specific measurements with "approximately" (e.g., "approximately 15 feet", "approximately 12\" deep")
- Use spatial landmarks to describe tank location (e.g., "right side rear of the house", "6' off the foundation in the back right corner")
- Reference TDEC (Tennessee) or DHEC (South Carolina) databases/paperwork when permit info is available
- Formal, factual tone — no opinions beyond "appears to be in good working condition"
- Each major topic gets its own paragraph

STRUCTURE (follow this order):
1. Opening: "On the above date and time, an on-site survey of the septic system was conducted by MAC Septic."
   - If homeowner was present, add: "Prior to the inspection, MAC Septic received permission to be on-site by the homeowner. The homeowner was present during the time of the inspection."
2. Tank location and physical description (depth, surface access, markings)
3. Permit/history (TDEC/DHEC search results, homeowner statements about installation year)
4. System type, capacity, and condition assessment
5. Pumping paragraph (only if pumped): "Simultaneous to the Septic Inspection, MAC Septic accessed, pumped and cleaned the tank..."
   - Include baffle inspection, operational test results
6. Notable observations (access issues, structural concerns, pump details)
7. Closing: "The drain field shows no signs of leaching up or super saturation. This system appears to be functioning properly overall."

CRITICAL RULES:
- Output ONLY the narrative body paragraphs
- NO greeting (no "Dear..." or "Hello")
- NO disclaimer paragraph
- NO closing/sign-off (no "Sincerely", "Best regards", etc.)
- NO signature block
- Start directly with "On the above date and time..."
- End with the drain field / overall assessment paragraph"""

# ---------------------------------------------------------------------------
# Few-shot examples
# ---------------------------------------------------------------------------

_FEW_SHOT_EXAMPLES = [
    # Example 1 — simple, no pumping
    {
        "role": "user",
        "content": (
            "INSPECTION DATA: Address: 102 Pascal Dr., Mount Juliet, TN, 37122. "
            "Tank located right side rear of house, ~15ft from crawl space access door between flower bed and storage structure. "
            "Surface access covered by large octagonal paver. Tank ~12\" deep. "
            "TDEC paperwork indicates installed 1985 as new construction. "
            "Standard septic, one tank gravity flow, ~1000 gallons. Good condition, no damage. "
            "No pumping. Drain field: no leaching, no saturation. "
            "Tank outline and inlet lines marked with marking paint."
        ),
    },
    {
        "role": "assistant",
        "content": (
            "On the above date and time, an on-site survey of the septic system was conducted by MAC Septic. "
            "The septic tank was located in the right side rear of the house approximately 15 feet from the crawl space access door "
            "between a flower bed and additional storage structure. The surface access to the tank's inlet manhole was covered by a large octagonal paver. "
            "The outline of the tank as well as the inlet lines were marked with marking paint during the inspection. "
            "The tank appeared to be approximately 12\" deep. "
            "TDEC paperwork indicates the system was installed in 1985 as a new construction. "
            "This is a standard septic system with one tank gravity flow and an estimated capacity of 1000 gallons. "
            "The tank appears to be in good working condition with no visible signs of damage.\n\n"
            "The drain field shows no signs of leaching up or super saturation. "
            "This system appears to be functioning properly overall."
        ),
    },
    # Example 2 — with pumping + notable observations
    {
        "role": "user",
        "content": (
            "INSPECTION DATA: Address: 1376 Panhandle Rd., Manchester, TN 37355. "
            "Tank front center of house, ~10ft from foundation. Tank ~6\" under surface. "
            "TDEC database searched — no documentation found. Homeowner said installed 1994. "
            "Standard septic, one tank gravity flow, ~1000 gallons. Good condition. "
            "Pumped during inspection: yes. Inlet and outlet baffles observed, good working order. "
            "Operational test: flushed toilets/ran sinks, normal inflow, no obstruction. "
            "Notable: tank sits below front porch foundation, only outlet side accessible. "
            "If inlet clogs, porch foundation must be removed."
        ),
    },
    {
        "role": "assistant",
        "content": (
            "On the above date and time, an on-site survey of the septic system was conducted by MAC Septic. "
            "The septic tank is in front center of the house approximately 10' feet from the foundation. "
            "The tank top sits approximately 6\" under the surface. "
            "A search of the TDEC database was conducted and no documentation could be found regarding original permitting and drawings of the septic system. "
            "No updated permits or drawings were found. "
            "The homeowner stated that the system was originally installed in 1994. "
            "This is a standard septic system with one tank gravity flow and an estimated capacity of 1000 gallons. "
            "The tank appears to be in good working condition with no visible signs of damage.\n\n"
            "Simultaneous to the Septic Inspection, MAC Septic accessed, pumped and cleaned the tank. "
            "During the pumping, both inlet and outlet baffles as well as the interior of the tank were observed and inspected. "
            "All parts of the tank appeared to be in good working order with no visible signs of damage. "
            "At the conclusion of pumping/cleaning the tank an operational test of the system was conducted (flushing toilets and running sinks). "
            "Normal inflow to the tank was observed with no signs of obstruction. "
            "The system was observed to be in good working order.\n\n"
            "It was noted that the tank sits below the foundation of the front porch. "
            "As a result, only the outlet side of the tank can be accessed for pumping and/or maintenance. "
            "In the result of an Inlet Baffle and/or Inlet Line clog, the foundation of the porch would have to be removed or modified for access.\n\n"
            "The drain field shows no signs of leaching up or super saturation. "
            "This system appears to be functioning properly overall."
        ),
    },
    # Example 3 — forced-flow with pump chamber
    {
        "role": "user",
        "content": (
            "INSPECTION DATA: Address: 111 Emerald Shores Circle., Chapin, SC 29036. "
            "Tank ~6ft off foundation, back right corner, ~12\" below surface. "
            "Pump chamber: ~500 gallons, ~12\" beneath surface, in line with outlet. "
            "Homeowner said installed ~39 years ago (1986), new construction. "
            "Forced-flow system pumping into deeded drain field at top of hill. "
            "~1000 gal tank + ~500 gal pump chamber. Good condition. "
            "Pumped: yes. Baffles good, no obstruction. "
            "Pump: Goulds WE1512HH, electrical continuity and amperage tested, operating as designed. "
            "Homeowner present, permission received."
        ),
    },
    {
        "role": "assistant",
        "content": (
            "On the above date and time, an on-site survey of the septic system was conducted by MAC Septic. "
            "Prior to the inspection, MAC Septic received permission to be on-site by the homeowner. "
            "The homeowner was present during the time of the inspection.\n\n"
            "The system is comprised of an approximately 1000-gallon septic tank and an approximately 500-gallon pump chamber "
            "immediately in line with the outlet side of the septic tank. "
            "The septic tank is located approximately 6' off the foundation of the house in the back right corner. "
            "The tank top sits approximately 12\" below the ground surface. "
            "The pump chamber appeared to be approximately 12\" beneath the soil surface. "
            "Information provided by the homeowner indicates the system was installed approximately 39 years ago (1986) as a new construction. "
            "This is a standard forced-flow system pumping into a deeded drain field at the top of the hill in the cul-de-sac. "
            "The system contains an approximately 500-gallon pump chamber with an effluent pump. "
            "The tank and pump appeared to be in good working condition with no visible signs of damage.\n\n"
            "Simultaneous to the Septic Inspection, MAC Septic accessed, pumped and cleaned the septic tank. "
            "During the pumping, the inlet and outlet baffles as well as the interior of the tank were observed and inspected. "
            "Normal inflow to the tank was observed with no signs of obstruction. "
            "All parts of the tank appeared to be in good working order with no visible signs of damage. "
            "No visible indication was observed that would indicate any malfunction to proper functionality of the septic tank.\n\n"
            "The effluent pump in the pump chamber is a Goulds WE1512HH series. "
            "Electrical continuity and amperage testing was conducted at the time of the inspection with all components operating as designed. "
            "No visible indication was observed that would indicate any malfunction to proper functionality of the pump chamber."
        ),
    },
]


# ---------------------------------------------------------------------------
# Part 1: AI letter draft generation
# ---------------------------------------------------------------------------


async def generate_letter_draft(checklist: dict) -> Dict[str, Any]:
    """Generate a narrative inspection letter body using the AI gateway.

    Args:
        checklist: The work order checklist dict containing inspection steps.

    Returns:
        Dict with keys: body, generated_at, model, status, and optionally error.
    """
    from app.services.ai_gateway import ai_gateway

    inspection_text = _build_inspection_text(checklist)
    if not inspection_text:
        return {
            "body": "",
            "generated_at": datetime.utcnow().isoformat(),
            "model": None,
            "status": "error",
            "error": "No inspection data found in checklist.",
        }

    # Build messages: few-shot examples + the real request
    messages = list(_FEW_SHOT_EXAMPLES) + [
        {"role": "user", "content": f"INSPECTION DATA: {inspection_text}"},
    ]

    try:
        result = await ai_gateway.chat_completion(
            messages=messages,
            system_prompt=_SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.3,
            feature="inspection_letter",
        )

        body = (result.get("content") or "").strip()
        return {
            "body": body,
            "generated_at": datetime.utcnow().isoformat(),
            "model": result.get("model"),
            "status": "draft" if body else "error",
            "error": None if body else "AI returned empty content.",
        }
    except Exception as exc:
        logger.exception("Failed to generate inspection letter draft")
        return {
            "body": "",
            "generated_at": datetime.utcnow().isoformat(),
            "model": None,
            "status": "error",
            "error": str(exc),
        }


# ---------------------------------------------------------------------------
# Part 2: PDF rendering
# ---------------------------------------------------------------------------


def render_letter_pdf(
    letter_body: str,
    customer_name: str,
    customer_address: str,
    customer_email: str = "",
    customer_phone: str = "",
    inspection_date: str = "",
    inspection_time: str = "",
    signer_key: str = "douglas_carter",
    letter_date: Optional[str] = None,
) -> bytes:
    """Render an approved inspection letter body into a PDF on MAC Septic
    letterhead using WeasyPrint.

    Returns raw PDF bytes.
    """
    from weasyprint import HTML
    from app.services.logos import LOGO_WHITE_DATA_URI

    signer = SIGNERS.get(signer_key, SIGNERS["douglas_carter"])
    state = _detect_state(customer_address)
    office = OFFICES.get(state, OFFICES["TN"])

    if not letter_date:
        letter_date = datetime.utcnow().strftime("%B %d, %Y")

    # Format body paragraphs as HTML <p> tags
    body_html = "\n".join(
        f"<p>{para.strip()}</p>"
        for para in letter_body.strip().split("\n\n")
        if para.strip()
    )

    # Licenses as comma-separated string
    licenses_str = " | ".join(signer["licenses"])

    html_content = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{
        size: letter;
        margin: 0.75in 1in 0.75in 1in;
    }}
    body {{
        font-family: "Times New Roman", Times, serif;
        font-size: 11pt;
        line-height: 1.5;
        color: #1a1a1a;
        margin: 0;
        padding: 0;
    }}
    .header {{
        display: flex;
        align-items: center;
        justify-content: space-between;
        border-bottom: 2px solid #1a3a5c;
        padding-bottom: 12px;
        margin-bottom: 24px;
    }}
    .header-logo img {{
        height: 60px;
    }}
    .header-info {{
        text-align: right;
        font-size: 9pt;
        color: #333;
        line-height: 1.4;
    }}
    .recipient-block {{
        margin-bottom: 20px;
        font-size: 11pt;
    }}
    .recipient-block p {{
        margin: 0;
        padding: 0;
    }}
    .letter-title {{
        text-align: center;
        font-size: 14pt;
        font-weight: bold;
        text-decoration: underline;
        margin: 24px 0 16px 0;
        color: #1a3a5c;
    }}
    .metadata {{
        margin-bottom: 16px;
        font-size: 10pt;
    }}
    .metadata table {{
        border-collapse: collapse;
    }}
    .metadata td {{
        padding: 2px 12px 2px 0;
    }}
    .metadata td.label {{
        font-weight: bold;
    }}
    .salutation {{
        margin-bottom: 12px;
    }}
    .body p {{
        text-indent: 0;
        margin: 0 0 12px 0;
        text-align: justify;
    }}
    .disclaimer {{
        margin-top: 24px;
        padding: 12px;
        border: 1px solid #999;
        background: #f9f9f9;
        font-size: 9pt;
        font-style: italic;
        color: #444;
        text-align: justify;
    }}
    .closing {{
        margin-top: 32px;
    }}
    .closing .regards {{
        margin-bottom: 40px;
    }}
    .closing .signer-name {{
        font-weight: bold;
    }}
    .closing .signer-title {{
        font-size: 10pt;
        color: #555;
    }}
    .closing .signer-licenses {{
        font-size: 9pt;
        color: #666;
    }}
</style>
</head>
<body>
    <!-- Header -->
    <div class="header">
        <div class="header-logo">
            <img src="{LOGO_WHITE_DATA_URI}" alt="MAC Septic">
        </div>
        <div class="header-info">
            <strong>MAC Septic Services</strong><br>
            {office['address']}<br>
            {office['phone']}
        </div>
    </div>

    <!-- Date -->
    <p>{letter_date}</p>

    <!-- Recipient block -->
    <div class="recipient-block">
        <p>{customer_name}</p>
        <p>{customer_address}</p>
        {"<p>" + customer_email + "</p>" if customer_email else ""}
        {"<p>" + customer_phone + "</p>" if customer_phone else ""}
    </div>

    <!-- Title -->
    <div class="letter-title">SEPTIC INSPECTION LETTER</div>

    <!-- Metadata -->
    <div class="metadata">
        <table>
            <tr><td class="label">Inspection Date:</td><td>{inspection_date}</td></tr>
            <tr><td class="label">Inspection Time:</td><td>{inspection_time}</td></tr>
            <tr><td class="label">Property Address:</td><td>{customer_address}</td></tr>
        </table>
    </div>

    <!-- Salutation -->
    <p class="salutation">To Whom It May Concern:</p>

    <!-- Body -->
    <div class="body">
        {body_html}
    </div>

    <!-- Disclaimer -->
    <div class="disclaimer">
        {DISCLAIMER}
    </div>

    <!-- Closing -->
    <div class="closing">
        <p class="regards">Respectfully,</p>
        <p class="signer-name">{signer['name']}</p>
        <p class="signer-title">{signer['title']}, MAC Septic Services</p>
        <p class="signer-licenses">{licenses_str}</p>
    </div>
</body>
</html>"""

    pdf_bytes = HTML(string=html_content).write_pdf()
    return pdf_bytes
