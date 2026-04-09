# AI Inspection Letter Generation — Design Spec

**Date:** 2026-04-09
**Goal:** AI writes real estate inspection letters in Doug's exact style, saving hours/week of manual letter writing.
**Scope:** RE inspections only. Side-by-side editor in CRM. PDF on MAC Septic letterhead.

## Background

Doug Carter (EVP) currently hand-writes narrative inspection letters for every real estate inspection. These are formal letters on MAC Septic letterhead sent to homeowners/buyers, often shared with realtors and title companies. Each letter takes ~20-30 minutes to write.

The tech fills out a structured inspection form (previously MS Forms, now CRM checklist). Doug reads the structured data and writes a narrative letter following a consistent structure he's developed over years of experience.

**Training corpus:** 83 real letters archived at `/mnt/data6tb/home-offload/Downloads/Septic Inspection letters/` (150+ TN, 18 SC).

## Doug's Letter Structure (reverse-engineered from 7 letters)

Every letter follows this order:

1. **Letterhead** — MAC Septic logo, office address (TN or SC), phone, email, website
2. **Recipient block** — Client name, email, phone
3. **Title** — "SEPTIC INSPECTION LETTER" + date
4. **Inspection metadata** — Date, time, address
5. **Salutation** — "To Whom It May Concern:"
6. **Opening** — "On the above date and time, an on-site survey of the septic system was conducted by MAC Septic."
7. **Tank location** — Position relative to house (distance, landmarks, depth below surface)
8. **Permit/history** — TDEC database search results, install year, system type (gravity/forced-flow), capacity, who provided the info (homeowner, realtor, TDEC)
9. **Pumping paragraph** (if done simultaneously) — Baffles observed, operational test (flush toilets, run sinks), results
10. **Notable observations** — Specific callouts (tank under porch, electrical box replacement needed, pump brand/HP, field line layout, marking paint applied)
11. **Drain field** — "The drain field shows no signs of leaching up or super saturation. This system appears to be functioning properly overall." (or issues if found)
12. **Disclaimer** — Always identical boilerplate about subterranean systems, no warranty, workability factors
13. **Closing** — "Thank you for this opportunity to serve you." / Sincerely
14. **Signature block** — Signer name, title, company, permit numbers
15. **Photos** — Attached as additional pages (marking paint, excavation, field lines)

### Key style notes:
- Professional but reads like a knowledgeable person explaining what they saw
- Specific measurements and spatial references ("approximately 10' off the foundation", "12" below surface")
- References TDEC/DHEC database searches
- Paragraph count varies by complexity (simple 1-page vs. detailed multi-page)
- Three signers: Matthew Carter (President, TN), Douglas Carter (EVP, TN), Marvin A. Carter (Founder, SC)
- TN letters use TDEC permits #972 / #14228 or #14229
- SC letters use SC DHEC License #32-368-32022
- Office addresses differ by state: TN = 8011 Brooks Chapel Rd Unit 457, Brentwood, TN 37027; SC = PO Box 722, Chapin, SC 29036

## Architecture

### What the AI writes vs. what the template handles

| Component | AI writes? | Template handles? |
|-----------|-----------|-------------------|
| Letterhead (logo, address, phone) | No | Yes |
| Recipient block | No | Yes |
| Title + date + metadata | No | Yes |
| Salutation | No | Yes (always "To Whom It May Concern:") |
| Narrative body (paragraphs 6-11) | **Yes** | No |
| Disclaimer boilerplate | No | Yes (static text) |
| Closing + signature | No | Yes |
| Photos | No | Yes (from inspection photos) |

The AI only generates the **narrative body** — the 3-6 paragraphs between "To Whom It May Concern:" and the disclaimer. Everything else is deterministic.

### Data flow

```
Tech completes RE inspection → clicks "Generate AI Letter"
    ↓
POST /employee/jobs/{id}/inspection/generate-letter
    ↓
Backend gathers:
  - wo.checklist.inspection (steps, notes, summary, ai_analysis)
  - Customer info (name, address, phone, email)
  - Work order metadata (date, time, job_type, system_type)
  - Signer info (determined by state: TN vs SC)
    ↓
ai_gateway.chat_completion() with:
  - System prompt with 3 few-shot examples
  - Structured inspection data as user message
  - temperature=0.3 (low creativity, high consistency)
  - max_tokens=2048
    ↓
Response stored in wo.checklist.inspection.ai_letter = {
  "body": "On the above date and time...",
  "generated_at": "2026-04-09T14:30:00Z",
  "model": "claude-sonnet-4-6",
  "status": "draft"  // draft | approved | sent
}
    ↓
Frontend shows side-by-side editor
    ↓
Doug edits → "Approve & Generate PDF"
    ↓
POST /employee/jobs/{id}/inspection/approve-letter
  body: { edited_body: "...", signer: "douglas_carter" }
    ↓
Backend renders full letter PDF (WeasyPrint) with:
  - Letterhead template
  - Recipient block from customer data
  - AI-written (Doug-edited) narrative body
  - Static disclaimer
  - Signature block
  - Inspection photos appended
    ↓
PDF stored in documents table + wo.checklist.inspection.ai_letter.status = "approved"
    ↓
Doug clicks "Send" → existing email flow sends PDF to buyer
```

## Backend Changes

### New file: `app/services/inspection_letter_service.py`

Core service with two functions:

1. **`generate_letter_draft(wo, customer, db)`** — Assembles prompt, calls AI gateway, returns draft text
2. **`render_letter_pdf(wo, customer, letter_body, signer, photos)`** — Renders full letter PDF with letterhead via WeasyPrint

### New endpoints in `app/api/v2/employee_portal.py`

1. **`POST /employee/jobs/{id}/inspection/generate-letter`**
   - Gathers inspection data + customer info
   - Calls `generate_letter_draft()`
   - Stores draft in `wo.checklist.inspection.ai_letter`
   - Returns `{ body, generated_at, model }`

2. **`POST /employee/jobs/{id}/inspection/approve-letter`**
   - Accepts `{ edited_body, signer }`
   - Calls `render_letter_pdf()`
   - Stores PDF in documents table
   - Updates `ai_letter.status = "approved"`
   - Returns `{ document_id, pdf_url }`

3. **`POST /employee/jobs/{id}/inspection/send-letter`**
   - Sends the approved letter PDF to the buyer via existing email service
   - Updates `ai_letter.status = "sent"`

### AI Prompt Design

**System prompt** includes:
- Role: "You are writing a septic inspection letter for MAC Septic LLC"
- Style guide: professional, specific measurements, spatial references, TDEC/DHEC references
- Structure guide: opening → tank location → permit/history → pumping (if applicable) → notable observations → drain field assessment
- 3 few-shot examples: one simple (102 Pascal Dr), one with pumping (1376 Panhandle Rd), one complex with pump chamber (111 Emerald Shores)
- Rules: no disclaimer (template adds it), no greeting/closing (template adds them), no fabricated measurements, use "approximately" for estimates

**User message** is a structured JSON of the inspection data:
```json
{
  "customer_name": "Spring Eisenzimmer",
  "address": "102 Pascal Dr., Mount Juliet, TN 37122",
  "inspection_date": "08/09/2024",
  "inspection_time": "08:30 AM CST",
  "system_type": "standard",
  "flow_type": "gravity",
  "tank_capacity_gallons": 1000,
  "install_year": 1985,
  "permit_source": "TDEC paperwork",
  "tank_location": "right side rear of house, ~15ft from crawl space access door",
  "tank_depth": "~12 inches",
  "tank_condition": "good",
  "pumped_during_inspection": false,
  "baffles_inspected": false,
  "drain_field_leaching": false,
  "drain_field_saturation": false,
  "overall_functioning": true,
  "notable_observations": "Surface access covered by large octagonal paver. Tank outline and inlet lines marked with marking paint.",
  "who_present": ["none"],
  "steps": { ... }
}
```

## Frontend Changes

### New component: `InspectionLetterPanel.tsx`

Located in `src/features/technician-portal/components/` (or possibly a new location Doug accesses — TBD based on where Doug works in the CRM).

**Side-by-side layout:**
- **Left panel (60%):** Editable text area with the AI-generated letter body. Rich text not needed — this is plain narrative text. Textarea with good typography.
- **Right panel (40%):** Read-only inspection data summary — step results, notes, measurements, photos thumbnails. Acts as a reference while editing.

**Action buttons:**
- "Generate AI Letter" — calls generate endpoint, shows loading state
- "Regenerate" — re-calls AI if first draft was off
- "Approve & Generate PDF" — locks text, generates PDF, shows preview
- "Send to Buyer" — emails the PDF
- Signer dropdown (Matthew Carter / Douglas Carter / Marvin A. Carter)

### Integration point

This panel appears on the work order detail page when:
- `job_type === "real_estate_inspection"`
- Inspection is completed (has summary data)

It could be a new tab alongside the existing inspection checklist, or a section below the "Send Report" area in `InspectionChecklist.tsx`.

## PDF Template

The letter PDF uses the same MAC Septic letterhead as the existing letters (logo, address block, phone/email/website). The template adapts based on state:

- **TN:** 8011 Brooks Chapel Rd Unit 457, Brentwood, TN 37027 | (615) 345-2544
- **SC:** PO Box 722, Chapin, SC 29036 | 803-223-9677

Signers and their titles/permits:
- **Matthew Carter** — President, TDEC Pumping #972, TDEC SSDSI #14228
- **Douglas Carter** — Executive Vice President, TDEC Pumping #972, TDEC SSDSI #14229
- **Marvin A. Carter** — Founder, SC DHEC License #32-368-32022

The disclaimer boilerplate is always:
> "Septic systems are subterranean; therefore, it is not possible to determine their overall condition. No prediction can be made as to when or if a system might fail. This letter comments on the working ability of the system on the day of the evaluation only and is in no way intended to be a warranty. Workability can be altered by factors such as excessive rainfall, heavy water usage, faulty plumbing, neglect or physical damage to the system."

## What's NOT in scope (future phases)

- **TDEC permit auto-lookup:** Matching property address to permit database for install date, system specs, permit numbers. The TN permits are on the T430 — this requires connecting to that data source. For now, the AI uses whatever the tech entered in the inspection checklist.
- **Fine-tuned local model:** Approach B from brainstorming — OCR all 83 letters, build training pairs, fine-tune on R730.
- **Auto-generation on inspection complete:** For now, Doug clicks a button. Later, could auto-generate when inspection status changes to complete.
- **SC-specific letter flow:** SC letters have slightly different formatting. Start with TN (majority of volume), add SC adaptation later.
- **Photo attachment in letter PDF:** The existing letters include photos as additional pages. For v1, photos are handled separately (existing photo flow). Future: auto-append inspection photos to letter PDF.

## Success Criteria

1. AI generates a letter body that matches Doug's style (tone, structure, specificity)
2. Doug can review and edit inline before approving
3. PDF renders on correct MAC Septic letterhead with proper signer
4. Letter can be emailed to buyer from the CRM
5. Doug reports meaningful time savings (target: 20+ min → 5 min review/edit)
