# AI Inspection Letter Generation — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** AI generates real estate inspection letters in Doug's writing style. Doug reviews/edits in a side-by-side CRM view, approves, and sends as PDF on MAC Septic letterhead.

**Architecture:** New backend service (`inspection_letter_service.py`) calls `ai_gateway.chat_completion()` with few-shot examples of Doug's real letters. Two new endpoints: generate draft + approve/render PDF. New frontend component (`InspectionLetterPanel.tsx`) shows side-by-side editor. Integrates into existing `InspectionChecklist.tsx` for RE inspections.

**Tech Stack:** FastAPI, ai_gateway (Ollama/OpenAI/Anthropic fallback), WeasyPrint PDF, React 19, TanStack Query, Tailwind 4

---

## File Structure

### Backend (react-crm-api)

| File | Action | Responsibility |
|------|--------|---------------|
| `app/services/inspection_letter_service.py` | **Create** | AI prompt assembly, letter generation, PDF rendering |
| `app/api/v2/employee_portal.py` | **Modify** | Add 3 new endpoints for generate/approve/send letter |

### Frontend (ReactCRM)

| File | Action | Responsibility |
|------|--------|---------------|
| `src/api/hooks/useTechPortal.ts` | **Modify** | Add `useGenerateInspectionLetter`, `useApproveInspectionLetter`, `useSendInspectionLetter` hooks |
| `src/features/technician-portal/components/InspectionLetterPanel.tsx` | **Create** | Side-by-side editor: AI draft (editable) + inspection data (reference) |
| `src/features/technician-portal/components/InspectionChecklist.tsx` | **Modify** | Add "Generate AI Letter" button + mount `InspectionLetterPanel` for RE inspections |

---

### Task 1: Backend — Inspection Letter Service

**Files:**
- Create: `app/services/inspection_letter_service.py`

This is the core service. It has two functions: (1) assemble the prompt and call the AI to generate a letter draft, and (2) render an approved letter into a PDF with MAC Septic letterhead.

- [ ] **Step 1: Create `inspection_letter_service.py` with `generate_letter_draft()`**

```python
"""AI-powered inspection letter generation in Doug Carter's writing style.

Uses ai_gateway to generate narrative letter body from structured inspection data.
The AI writes only the narrative paragraphs — letterhead, disclaimer, and signature
are handled by the PDF template.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# ── Few-shot examples (real letters from Doug) ──────────────────────────────

EXAMPLE_SIMPLE = """INSPECTION DATA:
- Address: 102 Pascal Dr., Mount Juliet, TN, 37122
- Tank location: right side rear of house, ~15ft from crawl space access door between flower bed and storage structure
- Surface access: covered by large octagonal paver
- Tank depth: ~12 inches
- Permit source: TDEC paperwork, installed 1985, new construction
- System type: standard septic, one tank gravity flow, ~1000 gallons
- Tank condition: good, no visible damage
- Pumped during inspection: no
- Drain field: no leaching, no saturation, functioning properly
- Notable: tank outline and inlet lines marked with marking paint

LETTER:
On the above date and time, an on-site survey of the septic system was conducted by MAC Septic. The septic tank was located in the right side rear of the house approximately 15 feet from the crawl space access door between a flower bed and additional storage structure. The surface access to the tank's inlet manhole was covered by a large octagonal paver. The outline of the tank as well as the inlet lines were marked with marking paint during the inspection. The tank appeared to be approximately 12" deep. TDEC paperwork indicates the system was installed in 1985 as a new construction. This is a standard septic system with one tank gravity flow and an estimated capacity of 1000 gallons. The tank appears to be in good working condition with no visible signs of damage.

The drain field shows no signs of leaching up or super saturation. This system appears to be functioning properly overall."""

EXAMPLE_WITH_PUMPING = """INSPECTION DATA:
- Address: 1376 Panhandle Rd., Manchester, TN 37355
- Tank location: front center of house, ~10ft from foundation
- Tank depth: ~6 inches under surface
- Permit source: TDEC database searched, no documentation found. Homeowner stated installed 1994.
- System type: standard septic, one tank gravity flow, ~1000 gallons
- Tank condition: good, no visible damage
- Pumped during inspection: yes
- Baffles: inlet and outlet observed during pumping, good working order, no visible damage
- Operational test: flushed toilets and ran sinks, normal inflow, no obstruction
- Drain field: no leaching, no saturation, functioning properly
- Notable: tank sits below front porch foundation. Only outlet side accessible for pumping. If inlet baffle/line clogs, porch foundation must be removed for access.

LETTER:
On the above date and time, an on-site survey of the septic system was conducted by MAC Septic. The septic tank is in front center of the house approximately 10' feet from the foundation. The tank top sits approximately 6" under the surface. A search of the TDEC database was conducted and no documentation could be found regarding original permitting and drawings of the septic system. No updated permits or drawings were found. The homeowner stated that the system was originally installed in 1994. This is a standard septic system with one tank gravity flow and an estimated capacity of 1000 gallons. The tank appears to be in good working condition with no visible signs of damage.

Simultaneous to the Septic Inspection, MAC Septic accessed, pumped and cleaned the tank. During the pumping, both inlet and outlet baffles as well as the interior of the tank were observed and inspected. All parts of the tank appeared to be in good working order with no visible signs of damage. At the conclusion of pumping/cleaning the tank an operational test of the system was conducted (flushing toilets and running sinks). Normal inflow to the tank was observed with no signs of obstruction. The system was observed to be in good working order.

It was noted that the tank sits below the foundation of the front porch. As a result, only the outlet side of the tank can be accessed for pumping and/or maintenance. In the result of an Inlet Baffle and/or Inlet Line clog, the foundation of the porch would have to be removed or modified for access.

The drain field shows no signs of leaching up or super saturation. This system appears to be functioning properly overall."""

EXAMPLE_FORCED_FLOW = """INSPECTION DATA:
- Address: 111 Emerald Shores Circle., Chapin, SC 29036
- Tank location: ~6ft off foundation, back right corner
- Tank depth: ~12 inches below surface
- Pump chamber: ~500 gallons, ~12 inches beneath surface, immediately in line with outlet side
- Permit source: homeowner, installed ~39 years ago (1986), new construction
- System type: forced-flow, pumping into deeded drain field at top of hill in cul-de-sac
- Tank capacity: ~1000 gallons septic tank + ~500 gallon pump chamber
- Tank condition: good, no visible damage
- Pumped during inspection: yes
- Baffles: inlet and outlet observed, good working order, no visible damage, no obstruction
- Pump: Goulds WE1512HH series, electrical continuity and amperage testing conducted, operating as designed
- Drain field: not assessed from pump side (deeded drain field at top of hill)
- Notable: homeowner present, permission received. Effluent pump tested.
- Who present: homeowner

LETTER:
On the above date and time, an on-site survey of the septic system was conducted by MAC Septic. Prior to the inspection, MAC Septic received permission to be on-site by the homeowner. The homeowner was present during the time of the inspection.

The system is comprised of an approximately 1000-gallon septic tank and an approximately 500-gallon pump chamber immediately in line with the outlet side of the septic tank. The septic tank is located approximately 6' off the foundation of the house in the back right corner. The tank top sits approximately 12" below the ground surface. The pump chamber appeared to be approximately 12" beneath the soil surface. Information provided by the homeowner indicates the system was installed approximately 39 years ago (1986) as a new construction. This is a standard forced-flow system pumping into a deeded drain field at the top of the hill in the cul-de-sac. The system contains an approximately 500-gallon pump chamber with an effluent pump. The tank and pump appeared to be in good working condition with no visible signs of damage.

Simultaneous to the Septic Inspection, MAC Septic accessed, pumped and cleaned the septic tank. During the pumping, the inlet and outlet baffles as well as the interior of the tank were observed and inspected. Normal inflow to the tank was observed with no signs of obstruction. All parts of the tank appeared to be in good working order with no visible signs of damage. No visible indication was observed that would indicate any malfunction to proper functionality of the septic tank.

The effluent pump in the pump chamber is a Goulds WE1512HH series. Electrical continuity and amperage testing was conducted at the time of the inspection with all components operating as designed. No visible indication was observed that would indicate any malfunction to proper functionality of the pump chamber."""

SYSTEM_PROMPT = """You are writing the narrative body of a septic inspection letter for MAC Septic LLC. You write exactly like the company's leadership — professional, specific, and knowledgeable.

STYLE RULES:
- Write in third person ("MAC Septic" not "we")
- Use specific measurements with "approximately" ("approximately 10' off the foundation", "12\" below the surface")
- Reference spatial landmarks relative to the house (corners, porches, doors, flower beds)
- Reference where permit/install info came from (TDEC database, homeowner, realtor)
- Use professional septic industry terminology (baffles, inlet, outlet, gravity flow, forced-flow, leaching, super saturation)
- Each paragraph covers one topic — don't combine unrelated observations
- If pumping was done simultaneously, describe what was observed (baffles, operational test)
- Note any access limitations or concerns as separate paragraphs
- For the drain field, always assess leaching and super saturation

STRUCTURE (follow this order, skip sections that don't apply):
1. Opening: "On the above date and time, an on-site survey of the septic system was conducted by MAC Septic." Add who was present if applicable.
2. Tank location and physical description
3. Permit/history and system specifications (type, capacity, flow type, install year)
4. Pumping observations (if pumped during inspection): baffles, operational test, results
5. Notable observations: specific equipment details, access concerns, unique conditions
6. Drain field assessment

CRITICAL RULES:
- Do NOT include any greeting, salutation, date header, or "To Whom It May Concern"
- Do NOT include the disclaimer paragraph about subterranean systems
- Do NOT include "Thank you for this opportunity to serve you" or any closing
- Do NOT include any signature block
- Do NOT fabricate measurements or details not provided in the inspection data
- If information is missing, omit that detail — do not guess
- Output ONLY the narrative paragraphs, nothing else

Below are three examples of real inspection letters. Study the tone, structure, and level of detail carefully."""


def _build_inspection_data_text(
    inspection: dict,
    customer_name: str,
    customer_address: str,
    system_type: str | None,
    wo_notes: str | None,
) -> str:
    """Convert structured inspection data into the text format the AI expects."""
    steps = inspection.get("steps", {})
    summary = inspection.get("summary", {})

    # Tank location from step 1
    step1 = steps.get("1", {})
    tank_location = step1.get("notes", "")

    # Visual assessment from step 2
    step2 = steps.get("2", {})
    visual_notes = step2.get("notes", "")

    # Inlet from step 3
    step3 = steps.get("3", {})
    inlet_notes = step3.get("notes", "")

    # Baffles from step 4
    step4 = steps.get("4", {})
    baffle_notes = step4.get("notes", "")

    # Sludge from step 5
    step5 = steps.get("5", {})
    sludge_level = step5.get("sludge_level", "")
    sludge_notes = step5.get("notes", "")

    # Outlet from step 6
    step6 = steps.get("6", {})
    outlet_notes = step6.get("notes", "")
    manufacturer = step6.get("custom_fields", {}).get("aerobic_manufacturer", "")

    # Distribution from step 7
    step7 = steps.get("7", {})
    distribution_notes = step7.get("notes", "")

    # Drain field from step 8
    step8 = steps.get("8", {})
    drainfield_status = step8.get("status", "")
    drainfield_notes = step8.get("notes", "")

    # Risers from step 9
    step9 = steps.get("9", {})
    riser_notes = step9.get("notes", "")

    # Pump tank from step 10
    step10 = steps.get("10", {})
    pumped = step10.get("status", "") == "pass"
    pump_notes = step10.get("notes", "")

    # Final inspection from step 11
    step11 = steps.get("11", {})
    final_notes = step11.get("notes", "")

    # Overall condition
    condition = summary.get("overall_condition", "good")
    recommendations = summary.get("recommendations", [])

    # Determine flow type
    flow_type = "gravity" if system_type != "aerobic" else "aerobic"
    if any("forced" in (s.get("notes", "") or "").lower() for s in steps.values() if isinstance(s, dict)):
        flow_type = "forced-flow"

    lines = [
        "INSPECTION DATA:",
        f"- Address: {customer_address}",
    ]

    if tank_location:
        lines.append(f"- Tank location: {tank_location}")
    if visual_notes:
        lines.append(f"- Visual assessment: {visual_notes}")
    if inlet_notes:
        lines.append(f"- Inlet: {inlet_notes}")
    if baffle_notes:
        lines.append(f"- Baffles: {baffle_notes}")
    if sludge_level:
        lines.append(f"- Sludge level: {sludge_level}")
    if sludge_notes:
        lines.append(f"- Sludge notes: {sludge_notes}")
    if outlet_notes:
        lines.append(f"- Outlet: {outlet_notes}")
    if distribution_notes:
        lines.append(f"- Distribution: {distribution_notes}")

    lines.append(f"- System type: {system_type or 'standard'}, {flow_type}")
    lines.append(f"- Overall condition: {condition}")
    lines.append(f"- Pumped during inspection: {'yes' if pumped else 'no'}")
    if pump_notes:
        lines.append(f"- Pump notes: {pump_notes}")

    lines.append(f"- Drain field status: {drainfield_status}")
    if drainfield_notes:
        lines.append(f"- Drain field notes: {drainfield_notes}")

    if riser_notes:
        lines.append(f"- Risers: {riser_notes}")
    if final_notes:
        lines.append(f"- Final inspection notes: {final_notes}")
    if manufacturer:
        lines.append(f"- Manufacturer: {manufacturer}")
    if wo_notes:
        lines.append(f"- Additional notes: {wo_notes}")
    if recommendations:
        lines.append(f"- Recommendations: {'; '.join(recommendations)}")

    return "\n".join(lines)


async def generate_letter_draft(
    inspection: dict,
    customer_name: str,
    customer_address: str,
    system_type: str | None = None,
    wo_notes: str | None = None,
) -> dict:
    """Generate an AI letter draft from structured inspection data.

    Returns dict with keys: body, generated_at, model, error (if failed).
    """
    from app.services.ai_gateway import ai_gateway

    inspection_text = _build_inspection_data_text(
        inspection, customer_name, customer_address, system_type, wo_notes,
    )

    # Build messages with few-shot examples
    messages = [
        {"role": "user", "content": EXAMPLE_SIMPLE.split("LETTER:")[0].strip()},
        {"role": "assistant", "content": EXAMPLE_SIMPLE.split("LETTER:")[1].strip()},
        {"role": "user", "content": EXAMPLE_WITH_PUMPING.split("LETTER:")[0].strip()},
        {"role": "assistant", "content": EXAMPLE_WITH_PUMPING.split("LETTER:")[1].strip()},
        {"role": "user", "content": EXAMPLE_FORCED_FLOW.split("LETTER:")[0].strip()},
        {"role": "assistant", "content": EXAMPLE_FORCED_FLOW.split("LETTER:")[1].strip()},
        {"role": "user", "content": inspection_text},
    ]

    try:
        result = await ai_gateway.chat_completion(
            messages=messages,
            system_prompt=SYSTEM_PROMPT,
            max_tokens=2048,
            temperature=0.3,
            feature="inspection_letter",
        )

        body = result.get("content", "")
        if not body or body.startswith("[AI"):
            return {
                "body": "",
                "generated_at": datetime.utcnow().isoformat() + "Z",
                "model": result.get("model", "unknown"),
                "error": result.get("error", "Empty response from AI"),
            }

        return {
            "body": body.strip(),
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "model": result.get("model", "unknown"),
            "status": "draft",
        }

    except Exception as e:
        logger.error(f"[INSPECTION-LETTER] AI generation failed: {e}")
        return {
            "body": "",
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "model": "error",
            "error": str(e),
        }
```

- [ ] **Step 2: Verify the file imports work**

Run: `cd /home/will/react-crm-api && python -c "from app.services.inspection_letter_service import generate_letter_draft; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/will/react-crm-api
git add app/services/inspection_letter_service.py
git commit -m "feat: add inspection letter AI generation service

3 few-shot examples from Doug's real letters, structured prompt assembly
from inspection checklist data, ai_gateway integration."
```

---

### Task 2: Backend — Letter PDF Rendering

**Files:**
- Modify: `app/services/inspection_letter_service.py`

Add `render_letter_pdf()` that takes the approved letter body and renders it on MAC Septic letterhead via WeasyPrint, matching the exact format of Doug's existing letters.

- [ ] **Step 1: Add signer config and `render_letter_pdf()` to `inspection_letter_service.py`**

Append after the `generate_letter_draft` function:

```python
# ── Signer configuration ────────────────────────────────────────────────────

SIGNERS = {
    "matthew_carter": {
        "name": "Matthew Carter",
        "title": "President",
        "permits": "TDEC Pumping Permit #: 972\nTDEC SSDSI Permit #: 14228",
    },
    "douglas_carter": {
        "name": "Douglas Carter",
        "title": "Executive Vice President",
        "permits": "TDEC Pumping Permit #: 972\nTDEC SSDSI Permit #: 14229",
    },
    "marvin_carter": {
        "name": "Marvin A. Carter",
        "title": "Founder",
        "permits": "SC DHEC License #32-368-32022",
    },
}

OFFICE_INFO = {
    "TN": {
        "address": "8011 Brooks Chapel Rd. Unit 457",
        "city_state_zip": "Brentwood, TN 37027",
        "phone": "(615) 345-2544",
    },
    "SC": {
        "address": "PO Box 722",
        "city_state_zip": "Chapin, SC 29036",
        "phone": "803-223-9677",
    },
}

DISCLAIMER_TEXT = (
    "Septic systems are subterranean; therefore, it is not possible to determine "
    "their overall condition. No prediction can be made as to when or if a system "
    "might fail. This letter comments on the working ability of the system on the "
    "day of the evaluation only and is in no way intended to be a warranty. "
    "Workability can be altered by factors such as excessive rainfall, heavy water "
    "usage, faulty plumbing, neglect or physical damage to the system."
)


def _detect_state(address: str) -> str:
    """Detect TN vs SC from address. Defaults to TN."""
    addr_upper = (address or "").upper()
    if ", SC " in addr_upper or addr_upper.endswith(" SC") or "SOUTH CAROLINA" in addr_upper:
        return "SC"
    return "TN"


def render_letter_pdf(
    letter_body: str,
    customer_name: str,
    customer_address: str,
    customer_email: str | None,
    customer_phone: str | None,
    inspection_date: str,
    inspection_time: str,
    signer_key: str = "douglas_carter",
    letter_date: str | None = None,
) -> bytes:
    """Render the full inspection letter as a PDF with MAC Septic letterhead.

    Returns raw PDF bytes.
    """
    from app.services.logos import LOGO_WHITE_DATA_URI

    signer = SIGNERS.get(signer_key, SIGNERS["douglas_carter"])
    state = _detect_state(customer_address)
    office = OFFICE_INFO[state]
    
    if not letter_date:
        letter_date = datetime.now().strftime("%B %d, %Y")

    # Format the letter body paragraphs as HTML
    body_paragraphs = "\n".join(
        f"<p>{para.strip()}</p>"
        for para in letter_body.strip().split("\n\n")
        if para.strip()
    )

    # Permit lines as HTML
    permit_lines = "<br>".join(signer["permits"].split("\n"))

    html = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<style>
    @page {{ margin: 0.75in 1in; size: letter; }}
    body {{ font-family: 'Times New Roman', Times, serif; color: #1a1a1a; font-size: 11.5pt; line-height: 1.6; }}
    .header {{ display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 24px; padding-bottom: 16px; border-bottom: 3px solid #1e3a5f; }}
    .logo {{ height: 70px; }}
    .company-info {{ text-align: right; font-size: 9pt; color: #374151; line-height: 1.5; }}
    .company-info .address {{ font-weight: 600; color: #1e3a5f; font-size: 10pt; }}
    .recipient {{ margin-bottom: 20px; }}
    .recipient .name {{ font-size: 13pt; font-weight: 700; color: #1e3a5f; margin-bottom: 2px; }}
    .recipient .detail {{ font-size: 10pt; color: #374151; }}
    .title-row {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 16px; }}
    .title {{ font-size: 14pt; font-weight: 700; color: #1e3a5f; }}
    .letter-date {{ font-size: 11pt; color: #374151; }}
    .metadata {{ font-size: 10pt; color: #4b5563; margin-bottom: 20px; line-height: 1.4; }}
    .salutation {{ font-weight: 700; margin-bottom: 16px; font-size: 11.5pt; }}
    .body p {{ margin: 0 0 14px 0; text-align: justify; }}
    .disclaimer {{ margin-top: 20px; font-size: 10.5pt; color: #374151; font-style: italic; }}
    .closing {{ margin-top: 24px; }}
    .closing .thanks {{ margin-bottom: 16px; }}
    .closing .sincerely {{ margin-bottom: 40px; }}
    .signature .name {{ font-size: 12pt; font-weight: 700; color: #1e3a5f; }}
    .signature .title-line {{ font-size: 10pt; color: #374151; }}
    .signature .company {{ font-size: 10pt; color: #374151; }}
    .signature .permits {{ font-size: 9.5pt; color: #4b5563; margin-top: 2px; }}
    .footer {{ position: fixed; bottom: 0; left: 0; right: 0; height: 30px; background: #1e3a5f; }}
</style>
</head>
<body>
    <div class="header">
        <img src="{LOGO_WHITE_DATA_URI}" alt="MAC Septic" class="logo">
        <div class="company-info">
            <div class="address">{office['address']}<br>{office['city_state_zip']}</div>
            {office['phone']}<br>
            info@macseptic.com<br>
            www.macseptic.com
        </div>
    </div>

    <div class="recipient">
        <div class="name">{customer_name}</div>
        {"<div class='detail'>" + customer_email + "</div>" if customer_email else ""}
        {"<div class='detail'>" + customer_phone + "</div>" if customer_phone else ""}
    </div>

    <div class="title-row">
        <div class="title">SEPTIC INSPECTION LETTER</div>
        <div class="letter-date">{letter_date}</div>
    </div>

    <div class="metadata">
        Date of Inspection: {inspection_date}<br>
        Time of Inspection: {inspection_time}<br>
        Inspection Address: {customer_address}
    </div>

    <div class="salutation">To Whom It May Concern:</div>

    <div class="body">
        {body_paragraphs}
    </div>

    <div class="disclaimer">
        <p>{DISCLAIMER_TEXT}</p>
    </div>

    <div class="closing">
        <p class="thanks">Thank you for this opportunity to serve you.</p>
        <p class="sincerely">Sincerely,</p>
        <div class="signature">
            <div class="name">{signer['name']}</div>
            <div class="title-line">{signer['title']}</div>
            <div class="company">MAC Septic LLC</div>
            <div class="permits">{permit_lines}</div>
        </div>
    </div>

    <div class="footer"></div>
</body>
</html>"""

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        logger.info(f"[INSPECTION-LETTER] PDF rendered: {len(pdf_bytes)} bytes")
        return pdf_bytes
    except ImportError:
        logger.error("[INSPECTION-LETTER] WeasyPrint not available")
        raise RuntimeError("WeasyPrint required for PDF generation")
    except Exception as e:
        logger.error(f"[INSPECTION-LETTER] PDF render failed: {e}")
        raise
```

- [ ] **Step 2: Verify import**

Run: `cd /home/will/react-crm-api && python -c "from app.services.inspection_letter_service import render_letter_pdf; print('OK')"`
Expected: `OK`

- [ ] **Step 3: Commit**

```bash
cd /home/will/react-crm-api
git add app/services/inspection_letter_service.py
git commit -m "feat: add letter PDF rendering with MAC Septic letterhead

Supports TN/SC office addresses, 3 signers (Matthew, Douglas, Marvin),
static disclaimer boilerplate, WeasyPrint HTML-to-PDF."
```

---

### Task 3: Backend — API Endpoints

**Files:**
- Modify: `app/api/v2/employee_portal.py` (add 3 endpoints after the existing inspection endpoints ~line 2374)

- [ ] **Step 1: Add the generate-letter endpoint**

Add after the `complete_inspection` endpoint (around line 2460 — after the last inspection-related endpoint):

```python
# ── AI Inspection Letter Generation ─────────────────────────────────────────

class ApproveLetterRequest(BaseModel):
    edited_body: str
    signer: str = "douglas_carter"


@router.post("/jobs/{job_id}/inspection/generate-letter")
async def generate_inspection_letter(
    job_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Generate an AI draft of the inspection letter in Doug's writing style."""
    result = await db.execute(
        select(WorkOrder).options(selectinload(WorkOrder.customer)).where(WorkOrder.id == job_id)
    )
    wo = result.scalars().first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    checklist = wo.checklist or {}
    inspection = checklist.get("inspection", {})
    if not inspection:
        raise HTTPException(status_code=400, detail="No inspection data found")

    # Get customer info
    customer_name = "Valued Customer"
    customer_address = ""
    if wo.customer:
        cust = wo.customer
        customer_name = f"{cust.first_name or ''} {cust.last_name or ''}".strip() or "Valued Customer"
        addr_parts = [cust.address_line1, cust.city, cust.state, cust.postal_code]
        customer_address = ", ".join(p for p in addr_parts if p)

    # Use service address if available
    if wo.service_address_line1:
        svc_parts = [wo.service_address_line1, wo.service_city, wo.service_state, wo.service_postal_code]
        customer_address = ", ".join(p for p in svc_parts if p)

    from app.services.inspection_letter_service import generate_letter_draft

    draft = await generate_letter_draft(
        inspection=inspection,
        customer_name=customer_name,
        customer_address=customer_address,
        system_type=getattr(wo, "system_type", None),
        wo_notes=wo.notes,
    )

    # Store draft in checklist
    inspection["ai_letter"] = draft
    checklist["inspection"] = inspection
    wo.checklist = checklist
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(wo, "checklist")
    await db.commit()

    return draft


@router.post("/jobs/{job_id}/inspection/approve-letter")
async def approve_inspection_letter(
    job_id: str,
    body: ApproveLetterRequest,
    db: DbSession,
    current_user: CurrentUser,
):
    """Approve the edited letter and generate the final PDF."""
    result = await db.execute(
        select(WorkOrder).options(selectinload(WorkOrder.customer)).where(WorkOrder.id == job_id)
    )
    wo = result.scalars().first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    checklist = wo.checklist or {}
    inspection = checklist.get("inspection", {})

    # Get customer info for PDF
    customer_name = "Valued Customer"
    customer_address = ""
    customer_email = None
    customer_phone = None
    if wo.customer:
        cust = wo.customer
        customer_name = f"{cust.first_name or ''} {cust.last_name or ''}".strip() or "Valued Customer"
        addr_parts = [cust.address_line1, cust.city, cust.state, cust.postal_code]
        customer_address = ", ".join(p for p in addr_parts if p)
        customer_email = cust.email
        customer_phone = cust.phone

    if wo.service_address_line1:
        svc_parts = [wo.service_address_line1, wo.service_city, wo.service_state, wo.service_postal_code]
        customer_address = ", ".join(p for p in svc_parts if p)

    # Format date/time
    insp_date = str(wo.scheduled_date) if wo.scheduled_date else datetime.utcnow().strftime("%m/%d/%Y")
    insp_time = "12:00 PM CST"  # Default if not stored

    from app.services.inspection_letter_service import render_letter_pdf
    import base64

    pdf_bytes = render_letter_pdf(
        letter_body=body.edited_body,
        customer_name=customer_name,
        customer_address=customer_address,
        customer_email=customer_email,
        customer_phone=customer_phone,
        inspection_date=insp_date,
        inspection_time=insp_time,
        signer_key=body.signer,
    )

    # Store PDF in documents table
    from app.models.document import Document
    doc = Document(
        entity_id=wo.entity_id if hasattr(wo, "entity_id") else None,
        document_type="inspection_letter",
        reference_id=wo.id,
        customer_id=wo.customer_id,
        file_name=f"Inspection-Letter-{str(wo.id)[:8]}.pdf",
        pdf_data=pdf_bytes,
        status="draft",
    )
    db.add(doc)

    # Update checklist
    inspection.setdefault("ai_letter", {})
    inspection["ai_letter"]["status"] = "approved"
    inspection["ai_letter"]["approved_body"] = body.edited_body
    inspection["ai_letter"]["signer"] = body.signer
    inspection["ai_letter"]["document_id"] = str(doc.id)
    inspection["ai_letter"]["approved_at"] = datetime.utcnow().isoformat() + "Z"
    checklist["inspection"] = inspection
    wo.checklist = checklist
    from sqlalchemy.orm.attributes import flag_modified
    flag_modified(wo, "checklist")
    await db.commit()

    return {
        "document_id": str(doc.id),
        "pdf_base64": base64.b64encode(pdf_bytes).decode("ascii"),
        "status": "approved",
    }


@router.post("/jobs/{job_id}/inspection/send-letter")
async def send_inspection_letter(
    job_id: str,
    db: DbSession,
    current_user: CurrentUser,
):
    """Send the approved inspection letter PDF to the buyer via email."""
    result = await db.execute(
        select(WorkOrder).options(selectinload(WorkOrder.customer)).where(WorkOrder.id == job_id)
    )
    wo = result.scalars().first()
    if not wo:
        raise HTTPException(status_code=404, detail="Work order not found")

    checklist = wo.checklist or {}
    inspection = checklist.get("inspection", {})
    ai_letter = inspection.get("ai_letter", {})

    if ai_letter.get("status") != "approved":
        raise HTTPException(status_code=400, detail="Letter must be approved before sending")

    doc_id = ai_letter.get("document_id")
    if not doc_id:
        raise HTTPException(status_code=400, detail="No approved letter document found")

    # Fetch the PDF
    from app.models.document import Document
    doc_result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = doc_result.scalars().first()
    if not doc or not doc.pdf_data:
        raise HTTPException(status_code=404, detail="Letter PDF not found")

    # Get recipient email (buyer)
    to_email = None
    customer_name = "Valued Customer"
    if wo.customer:
        to_email = wo.customer.email
        customer_name = f"{wo.customer.first_name or ''} {wo.customer.last_name or ''}".strip() or "Valued Customer"

    if not to_email:
        raise HTTPException(status_code=400, detail="No email address on file for customer")

    import base64
    from app.services.email_service import EmailService

    email_svc = EmailService()
    if not email_svc.is_configured:
        raise HTTPException(status_code=503, detail="Email service not configured")

    pdf_b64 = base64.b64encode(doc.pdf_data).decode("ascii")
    wo_number = wo.work_order_number or str(wo.id)[:8]

    email_result = await email_svc.send_email(
        to=to_email,
        subject=f"Septic Inspection Letter — {customer_name}",
        body=f"Please find attached the septic inspection letter for the property inspection completed by MAC Septic.\n\nThank you for choosing MAC Septic Services.\n(615) 345-2544 | macseptic.com",
        html_body=f"""<div style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto">
<div style="background:#1e3a5f;color:white;padding:20px;text-align:center;border-radius:8px 8px 0 0">
<h2 style="margin:0;font-size:18px">Septic Inspection Letter</h2>
</div>
<div style="padding:20px;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px">
<p>Hi {customer_name},</p>
<p>Please find attached the septic inspection letter for the recent property inspection completed by MAC Septic.</p>
<p style="padding:12px;background:#eff6ff;border-radius:6px;text-align:center"><strong>Your inspection letter is attached as a PDF.</strong></p>
<p>Questions? Call us at <strong>(615) 345-2544</strong></p>
<p>Thank you,<br><strong>MAC Septic Services</strong></p>
</div></div>""",
        attachments=[{
            "content": pdf_b64,
            "name": f"MAC-Septic-Inspection-Letter-{wo_number}.pdf",
        }],
    )

    if email_result.get("success"):
        # Update status
        inspection["ai_letter"]["status"] = "sent"
        inspection["ai_letter"]["sent_at"] = datetime.utcnow().isoformat() + "Z"
        inspection["ai_letter"]["sent_to"] = to_email
        checklist["inspection"] = inspection
        wo.checklist = checklist
        from sqlalchemy.orm.attributes import flag_modified
        flag_modified(wo, "checklist")

        doc.status = "sent"
        doc.sent_at = datetime.utcnow()
        await db.commit()

        return {"success": True, "sent_to": to_email}
    else:
        raise HTTPException(status_code=500, detail=f"Email failed: {email_result.get('error')}")
```

- [ ] **Step 2: Add necessary imports at top of employee_portal.py**

Check that these imports exist at the top of the file (add any missing ones):
- `from sqlalchemy.orm import selectinload` (likely already there)
- `from pydantic import BaseModel` (likely already there)
- `from datetime import datetime` (likely already there)

- [ ] **Step 3: Test endpoints load**

Run: `cd /home/will/react-crm-api && python -c "from app.api.v2.employee_portal import router; print('Routes:', len(router.routes))"`
Expected: prints route count without import errors

- [ ] **Step 4: Commit**

```bash
cd /home/will/react-crm-api
git add app/api/v2/employee_portal.py
git commit -m "feat: add AI letter generate/approve/send endpoints

POST /employee/jobs/{id}/inspection/generate-letter
POST /employee/jobs/{id}/inspection/approve-letter
POST /employee/jobs/{id}/inspection/send-letter"
```

---

### Task 4: Frontend — API Hooks

**Files:**
- Modify: `src/api/hooks/useTechPortal.ts` (add 3 new hooks after the existing inspection hooks ~line 770)

- [ ] **Step 1: Add the letter hooks**

Add after `useFetchInspectionWeather` (around line 775):

```typescript
// ── AI Inspection Letter ───────────────────────────────────────────────────

export interface AILetterDraft {
  body: string;
  generated_at: string;
  model: string;
  status?: string;
  error?: string;
}

export interface ApprovedLetter {
  document_id: string;
  pdf_base64: string;
  status: string;
}

export interface SentLetter {
  success: boolean;
  sent_to: string;
}

export function useGenerateInspectionLetter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string): Promise<AILetterDraft> => {
      const { data } = await apiClient.post(`/employee/jobs/${jobId}/inspection/generate-letter`);
      return data;
    },
    onSuccess: (_data, jobId) => {
      qc.invalidateQueries({ queryKey: ["tech-portal", "jobs", jobId, "inspection"] });
    },
    onError: () => toastError("Failed to generate AI letter — try again"),
  });
}

export function useApproveInspectionLetter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async ({
      jobId,
      editedBody,
      signer,
    }: {
      jobId: string;
      editedBody: string;
      signer: string;
    }): Promise<ApprovedLetter> => {
      const { data } = await apiClient.post(`/employee/jobs/${jobId}/inspection/approve-letter`, {
        edited_body: editedBody,
        signer,
      });
      return data;
    },
    onSuccess: (_data, vars) => {
      qc.invalidateQueries({ queryKey: ["tech-portal", "jobs", vars.jobId, "inspection"] });
      toastSuccess("Letter approved and PDF generated!");
    },
    onError: () => toastError("Failed to generate letter PDF"),
  });
}

export function useSendInspectionLetter() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: async (jobId: string): Promise<SentLetter> => {
      const { data } = await apiClient.post(`/employee/jobs/${jobId}/inspection/send-letter`);
      return data;
    },
    onSuccess: (data, jobId) => {
      qc.invalidateQueries({ queryKey: ["tech-portal", "jobs", jobId, "inspection"] });
      toastSuccess(`Letter emailed to ${data.sent_to}!`);
    },
    onError: () => toastError("Failed to send letter"),
  });
}
```

- [ ] **Step 2: Verify build**

Run: `cd /home/will/ReactCRM && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors related to the new hooks

- [ ] **Step 3: Commit**

```bash
cd /home/will/ReactCRM
git add src/api/hooks/useTechPortal.ts
git commit -m "feat: add AI inspection letter hooks

useGenerateInspectionLetter, useApproveInspectionLetter, useSendInspectionLetter"
```

---

### Task 5: Frontend — InspectionLetterPanel Component

**Files:**
- Create: `src/features/technician-portal/components/InspectionLetterPanel.tsx`

Side-by-side layout: editable AI draft on the left, inspection data reference on the right. Action buttons for generate, approve, and send.

- [ ] **Step 1: Create `InspectionLetterPanel.tsx`**

```tsx
import { useState, useEffect } from "react";
import {
  useGenerateInspectionLetter,
  useApproveInspectionLetter,
  useSendInspectionLetter,
  type AILetterDraft,
} from "@/api/hooks/useTechPortal.ts";
import { toastSuccess, toastInfo } from "@/components/ui/Toast.tsx";

interface Props {
  jobId: string;
  inspection: Record<string, unknown>;
  customerName?: string;
  customerEmail?: string;
  existingLetter?: AILetterDraft & { approved_body?: string; document_id?: string; sent_to?: string; sent_at?: string };
}

const SIGNERS = [
  { key: "douglas_carter", label: "Douglas Carter — EVP" },
  { key: "matthew_carter", label: "Matthew Carter — President" },
  { key: "marvin_carter", label: "Marvin A. Carter — Founder" },
];

export function InspectionLetterPanel({ jobId, inspection, customerName, customerEmail, existingLetter }: Props) {
  const [letterBody, setLetterBody] = useState("");
  const [signer, setSigner] = useState("douglas_carter");
  const [pdfBase64, setPdfBase64] = useState<string | null>(null);

  const generateMutation = useGenerateInspectionLetter();
  const approveMutation = useApproveInspectionLetter();
  const sendMutation = useSendInspectionLetter();

  // Load existing letter if present
  useEffect(() => {
    if (existingLetter?.body && !letterBody) {
      setLetterBody(existingLetter.approved_body || existingLetter.body);
    }
    if (existingLetter?.signer) {
      setSigner(existingLetter.signer as string);
    }
  }, [existingLetter]);

  const status = existingLetter?.status || "none";
  const isGenerating = generateMutation.isPending;
  const isApproving = approveMutation.isPending;
  const isSending = sendMutation.isPending;

  const handleGenerate = async () => {
    const result = await generateMutation.mutateAsync(jobId);
    if (result.error) {
      return;
    }
    setLetterBody(result.body);
    toastInfo("AI letter draft generated — review and edit before approving");
  };

  const handleApprove = async () => {
    const result = await approveMutation.mutateAsync({
      jobId,
      editedBody: letterBody,
      signer,
    });
    setPdfBase64(result.pdf_base64);
  };

  const handleSend = async () => {
    await sendMutation.mutateAsync(jobId);
  };

  const handleDownloadPDF = () => {
    if (!pdfBase64) return;
    const binary = atob(pdfBase64);
    const bytes = new Uint8Array(binary.length);
    for (let i = 0; i < binary.length; i++) bytes[i] = binary.charCodeAt(i);
    const blob = new Blob([bytes], { type: "application/pdf" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `MAC-Septic-Inspection-Letter-${jobId.slice(0, 8)}.pdf`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // Build inspection reference data
  const steps = (inspection.steps || {}) as Record<string, { status?: string; notes?: string; findings?: string }>;
  const summary = (inspection.summary || {}) as Record<string, unknown>;
  const condition = (summary.overall_condition as string) || "N/A";
  const recommendations = (summary.recommendations as string[]) || [];

  const stepLabels: Record<string, string> = {
    "1": "Locate System", "2": "Visual Assessment", "3": "Check Inlet",
    "4": "Check Baffles", "5": "Measure Sludge", "6": "Check Outlet",
    "7": "Check Distribution", "8": "Check Drainfield", "9": "Check Risers",
    "10": "Pump Tank", "11": "Final Inspection",
  };

  return (
    <div className="border-2 border-blue-300 bg-gradient-to-br from-blue-50 to-indigo-50 dark:from-blue-900/20 dark:to-indigo-900/20 dark:border-blue-700 rounded-xl p-4 mt-4">
      <div className="text-center mb-3">
        <span className="text-3xl">AI</span>
        <h4 className="font-bold text-text-primary text-lg mt-1">AI Inspection Letter</h4>
        <p className="text-xs text-text-secondary mt-1">
          {status === "none" && "Generate a professional inspection letter from the inspection data"}
          {status === "draft" && "Review and edit the AI draft, then approve to generate PDF"}
          {status === "approved" && "Letter approved — ready to send or download"}
          {status === "sent" && `Letter sent to ${existingLetter?.sent_to || customerEmail}`}
        </p>
      </div>

      {/* Side-by-side layout */}
      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3">
        {/* Left: Letter editor (3/5) */}
        <div className="lg:col-span-3">
          <div className="flex items-center justify-between mb-2">
            <label className="text-xs font-bold text-text-secondary uppercase tracking-wide">Letter Body</label>
            {letterBody && (
              <span className="text-xs text-text-secondary">{letterBody.split(/\s+/).length} words</span>
            )}
          </div>
          <textarea
            value={letterBody}
            onChange={(e) => setLetterBody(e.target.value)}
            placeholder={isGenerating ? "Generating AI letter..." : "Click 'Generate AI Letter' to create a draft from the inspection data..."}
            disabled={isGenerating || status === "sent"}
            rows={18}
            className="w-full rounded-lg border border-border bg-white dark:bg-bg-secondary p-3 text-sm text-text-primary leading-relaxed resize-y focus:ring-2 focus:ring-primary focus:border-primary disabled:opacity-60"
          />

          {/* Signer selection */}
          <div className="mt-2 flex items-center gap-2">
            <label className="text-xs font-medium text-text-secondary">Signer:</label>
            <select
              value={signer}
              onChange={(e) => setSigner(e.target.value)}
              disabled={status === "sent"}
              className="text-xs rounded-md border border-border bg-white dark:bg-bg-secondary px-2 py-1 text-text-primary"
            >
              {SIGNERS.map((s) => (
                <option key={s.key} value={s.key}>{s.label}</option>
              ))}
            </select>
          </div>
        </div>

        {/* Right: Inspection data reference (2/5) */}
        <div className="lg:col-span-2">
          <label className="text-xs font-bold text-text-secondary uppercase tracking-wide block mb-2">Inspection Data</label>
          <div className="rounded-lg border border-border bg-white dark:bg-bg-secondary p-3 text-xs space-y-3 max-h-[460px] overflow-y-auto">
            {/* Condition */}
            <div>
              <div className="font-bold text-text-primary mb-1">Overall Condition</div>
              <span className={`inline-block px-2 py-0.5 rounded-full text-white text-xs font-bold ${
                condition === "good" ? "bg-green-500" : condition === "fair" ? "bg-yellow-500" : "bg-red-500"
              }`}>
                {condition.charAt(0).toUpperCase() + condition.slice(1)}
              </span>
            </div>

            {/* Steps with notes */}
            <div>
              <div className="font-bold text-text-primary mb-1">Inspection Steps</div>
              {Object.entries(steps)
                .filter(([, s]) => s && typeof s === "object" && s.status && s.status !== "not_started")
                .sort(([a], [b]) => Number(a) - Number(b))
                .map(([key, step]) => (
                  <div key={key} className="mb-2 border-b border-border/50 pb-1.5 last:border-0">
                    <div className="flex items-center gap-1.5">
                      <span className={`w-2 h-2 rounded-full flex-shrink-0 ${
                        step.status === "pass" ? "bg-green-500" :
                        step.status === "flag" ? "bg-yellow-500" :
                        step.status === "fail" ? "bg-red-500" : "bg-gray-400"
                      }`} />
                      <span className="font-medium text-text-primary">{stepLabels[key] || `Step ${key}`}</span>
                      <span className="text-text-secondary ml-auto capitalize">{step.status}</span>
                    </div>
                    {step.notes && (
                      <p className="text-text-secondary mt-0.5 pl-3.5 italic">{step.notes}</p>
                    )}
                  </div>
                ))}
            </div>

            {/* Recommendations */}
            {recommendations.length > 0 && (
              <div>
                <div className="font-bold text-text-primary mb-1">Recommendations</div>
                <ul className="list-disc pl-4 space-y-1 text-text-secondary">
                  {recommendations.map((rec, i) => <li key={i}>{rec}</li>)}
                </ul>
              </div>
            )}

            {/* Customer */}
            <div>
              <div className="font-bold text-text-primary mb-1">Recipient</div>
              <div className="text-text-secondary">{customerName || "N/A"}</div>
              <div className="text-text-secondary">{customerEmail || "No email on file"}</div>
            </div>
          </div>
        </div>
      </div>

      {/* Action buttons */}
      <div className="mt-3 space-y-2">
        {status === "none" || status === "draft" ? (
          <>
            {!letterBody ? (
              <button
                onClick={handleGenerate}
                disabled={isGenerating}
                className="w-full py-3 rounded-xl bg-blue-600 text-white font-bold text-sm hover:bg-blue-700 active:scale-[0.98] transition-all disabled:opacity-50"
              >
                {isGenerating ? (
                  <span className="flex items-center justify-center gap-2"><span className="animate-spin">&#9881;</span> Generating AI Letter...</span>
                ) : (
                  "Generate AI Letter"
                )}
              </button>
            ) : (
              <div className="grid grid-cols-2 gap-2">
                <button
                  onClick={handleGenerate}
                  disabled={isGenerating}
                  className="py-3 rounded-xl border-2 border-blue-300 bg-blue-50 text-sm font-bold text-blue-700 hover:bg-blue-100 active:scale-[0.98] transition-all disabled:opacity-50 dark:bg-blue-900/20 dark:border-blue-700 dark:text-blue-300"
                >
                  {isGenerating ? "Regenerating..." : "Regenerate"}
                </button>
                <button
                  onClick={handleApprove}
                  disabled={isApproving || !letterBody.trim()}
                  className="py-3 rounded-xl bg-green-600 text-white font-bold text-sm hover:bg-green-700 active:scale-[0.98] transition-all disabled:opacity-50"
                >
                  {isApproving ? "Generating PDF..." : "Approve & Generate PDF"}
                </button>
              </div>
            )}
          </>
        ) : status === "approved" ? (
          <div className="grid grid-cols-2 gap-2">
            <button
              onClick={handleDownloadPDF}
              disabled={!pdfBase64}
              className="py-3 rounded-xl border-2 border-border text-sm font-bold text-text-primary hover:bg-bg-hover active:scale-[0.98] transition-all disabled:opacity-50"
            >
              Download PDF
            </button>
            <button
              onClick={handleSend}
              disabled={isSending || !customerEmail}
              className="py-3 rounded-xl bg-primary text-white font-bold text-sm hover:bg-primary/90 active:scale-[0.98] transition-all disabled:opacity-50"
            >
              {isSending ? "Sending..." : `Send to ${customerEmail || "No Email"}`}
            </button>
          </div>
        ) : status === "sent" ? (
          <div className="p-3 bg-green-100 dark:bg-green-900/30 rounded-lg text-center">
            <p className="text-sm text-green-700 dark:text-green-300 font-medium">
              Letter sent to {existingLetter?.sent_to} at {existingLetter?.sent_at ? new Date(existingLetter.sent_at).toLocaleString() : ""}
            </p>
          </div>
        ) : null}
      </div>
    </div>
  );
}
```

- [ ] **Step 2: Verify build**

Run: `cd /home/will/ReactCRM && npx tsc --noEmit --pretty 2>&1 | head -20`
Expected: No errors

- [ ] **Step 3: Commit**

```bash
cd /home/will/ReactCRM
git add src/features/technician-portal/components/InspectionLetterPanel.tsx
git commit -m "feat: add InspectionLetterPanel side-by-side editor

AI draft on left (editable textarea), inspection data reference on right.
Generate/regenerate/approve/send workflow with signer selection."
```

---

### Task 6: Frontend — Integrate into InspectionChecklist

**Files:**
- Modify: `src/features/technician-portal/components/InspectionChecklist.tsx`

Mount `InspectionLetterPanel` for RE inspections, appearing after the "Send Report" section in the summary view.

- [ ] **Step 1: Add import at top of InspectionChecklist.tsx**

Add after the other imports (around line 31):

```typescript
import { InspectionLetterPanel } from "./InspectionLetterPanel.tsx";
```

- [ ] **Step 2: Mount the panel in the summary section**

Find the section after the "Send Report" hero section (around line 2362, after the closing `</div>` of the green send-report border div). Add the letter panel **before** the "Review Steps" button:

Replace:
```tsx
        <button
          onClick={() => { setShowSummary(false); setCurrentStep(1); }}
          className="w-full py-3 rounded-lg text-sm font-medium border border-border text-text-secondary"
        >
          ← Review Steps
        </button>
```

With:
```tsx
        {/* AI Inspection Letter — RE inspections only */}
        {isRealEstateInspection && (
          <InspectionLetterPanel
            jobId={jobId}
            inspection={localState}
            customerName={customerName}
            customerEmail={customerEmail}
            existingLetter={localState.ai_letter}
          />
        )}

        <button
          onClick={() => { setShowSummary(false); setCurrentStep(1); }}
          className="w-full py-3 rounded-lg text-sm font-medium border border-border text-text-secondary"
        >
          ← Review Steps
        </button>
```

- [ ] **Step 3: Verify build**

Run: `cd /home/will/ReactCRM && npm run build 2>&1 | tail -5`
Expected: Build succeeds

- [ ] **Step 4: Commit**

```bash
cd /home/will/ReactCRM
git add src/features/technician-portal/components/InspectionChecklist.tsx
git commit -m "feat: mount AI letter panel in InspectionChecklist for RE inspections

Shows below Send Report section in summary view when job_type is real_estate_inspection."
```

---

### Task 7: Push & Deploy

**Files:** None (git operations only)

- [ ] **Step 1: Push backend**

```bash
cd /home/will/react-crm-api && git push origin master
```

- [ ] **Step 2: Push frontend**

```bash
cd /home/will/ReactCRM && npm run build && git push origin master
```

- [ ] **Step 3: Verify backend deployment**

Wait ~2 minutes, then check:
```bash
curl -s https://react-crm-api-production.up.railway.app/health | head -5
```
Expected: 200 OK

- [ ] **Step 4: Verify frontend deployment**

Wait ~2 minutes, then check that https://react.ecbtx.com loads without errors.

---

### Task 8: Playwright Verification

**Files:** None (testing only)

- [ ] **Step 1: Test the AI letter panel appears for RE inspections**

Use Playwright to:
1. Log in to the CRM
2. Navigate to a real_estate_inspection work order (or create one)
3. Complete the inspection checklist
4. Verify the "AI Inspection Letter" panel appears in the summary view
5. Click "Generate AI Letter" and verify the textarea populates
6. Verify the signer dropdown has all 3 options
7. Verify "Approve & Generate PDF" button works

- [ ] **Step 2: If any failures, fix and retest**

Follow the Sacred Loop: fix → build → push → Playwright → repeat until all pass.
