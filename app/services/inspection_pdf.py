"""Server-side inspection report PDF generation using WeasyPrint.

Generates a professional PDF from inspection data stored in work_orders.checklist.
This eliminates the fragile base64 transfer from frontend → backend.
"""

import base64
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)


def generate_inspection_pdf(
    customer_name: str,
    customer_address: str,
    inspection_data: dict,
    work_order_id: str,
    job_type: str = "Inspection",
    scheduled_date: Optional[str] = None,
) -> bytes:
    """Generate a PDF inspection report and return raw bytes.

    Uses WeasyPrint to render HTML → PDF. Falls back to a simple
    text-based PDF if WeasyPrint is unavailable.
    """
    summary = inspection_data.get("summary", {})
    condition = summary.get("overall_condition", "N/A")
    issues = summary.get("total_issues", 0)
    critical = summary.get("critical_issues", 0)
    recs = summary.get("recommendations", [])

    # AI analysis
    ai = inspection_data.get("ai_analysis", {})
    ai_assessment = ai.get("overall_assessment", "")

    # Weather
    weather = inspection_data.get("weather", {})
    weather_text = ""
    if weather:
        current = weather.get("current", {})
        if current:
            weather_text = f"Temperature: {current.get('temperature', 'N/A')}°F, {current.get('condition', 'N/A')}"

    # Steps data
    steps = inspection_data.get("steps", {})

    # Build condition badge
    cond_color = "#22c55e" if condition == "good" else "#f59e0b" if condition == "fair" else "#ef4444"
    cond_label = "Good" if condition == "good" else "Needs Attention" if condition == "fair" else "Needs Repair" if condition in ("poor", "critical") else condition.title()

    # Format date
    report_date = scheduled_date or datetime.now().strftime("%Y-%m-%d")
    try:
        dt = datetime.fromisoformat(report_date.replace("Z", "+00:00"))
        report_date_formatted = dt.strftime("%B %d, %Y")
    except Exception:
        report_date_formatted = report_date

    # Build recommendations HTML
    recs_html = ""
    if recs:
        items = "".join(f"<li>{r}</li>" for r in recs)
        recs_html = f"<h3>Key Findings &amp; Recommendations</h3><ul>{items}</ul>"

    # Build step details
    steps_html = ""
    step_labels = {
        "1": "Locate System", "2": "Visual Assessment", "3": "Check Inlet",
        "4": "Check Baffles", "5": "Measure Sludge", "6": "Check Outlet",
        "7": "Check Distribution", "8": "Check Drainfield", "9": "Check Risers",
        "10": "Pump Tank", "11": "Final Inspection", "12": "Aerobic - Air Pump",
        "13": "Aerobic - Chlorinator", "14": "Aerobic - Spray Heads",
        "15": "Aerobic - Control Panel", "16": "Aerobic - Manufacturer"
    }
    for step_key in sorted(steps.keys(), key=lambda x: int(x) if x.isdigit() else 999):
        step = steps[step_key]
        if isinstance(step, dict):
            step_status = step.get("status", "not_started")
            notes = step.get("notes", "")
            label = step_labels.get(step_key, f"Step {step_key}")
            status_icon = "✅" if step_status == "pass" else "⚠️" if step_status == "flag" else "❌" if step_status == "fail" else "⏭️" if step_status == "skip" else "—"
            notes_html = f"<p class='step-notes'>{notes}</p>" if notes else ""
            steps_html += f"""
            <div class="step-row">
                <span class="step-icon">{status_icon}</span>
                <span class="step-label">{label}</span>
                <span class="step-status">{step_status.replace('_', ' ').title()}</span>
            </div>
            {notes_html}
            """

    # AI section
    ai_html = ""
    if ai_assessment:
        ai_html = f"""
        <div class="ai-section">
            <h3>Expert Analysis</h3>
            <p>{ai_assessment}</p>
        </div>
        """

    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <meta charset="utf-8">
        <style>
            @page {{ margin: 0.75in; size: letter; }}
            body {{ font-family: Arial, Helvetica, sans-serif; color: #1f2937; font-size: 11pt; line-height: 1.5; }}
            .header {{ background: linear-gradient(135deg, #1e3a5f, #2563eb); color: white; padding: 24px; text-align: center; border-radius: 8px; margin-bottom: 20px; }}
            .header h1 {{ margin: 0; font-size: 22pt; letter-spacing: 1px; }}
            .header p {{ margin: 4px 0 0; color: #93c5fd; font-size: 11pt; }}
            .info-grid {{ display: flex; gap: 16px; margin-bottom: 20px; }}
            .info-box {{ flex: 1; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; padding: 12px; }}
            .info-box label {{ font-size: 9pt; color: #6b7280; text-transform: uppercase; letter-spacing: 0.5px; display: block; margin-bottom: 4px; }}
            .info-box span {{ font-size: 11pt; font-weight: 600; color: #1f2937; }}
            .condition-banner {{ background: {cond_color}; color: white; padding: 16px; border-radius: 8px; text-align: center; margin: 20px 0; }}
            .condition-banner strong {{ font-size: 18pt; }}
            .condition-banner span {{ display: block; font-size: 10pt; opacity: 0.9; margin-top: 4px; }}
            h3 {{ color: #1e3a5f; font-size: 13pt; margin: 20px 0 10px; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px; }}
            ul {{ padding-left: 20px; }}
            li {{ margin-bottom: 6px; }}
            .step-row {{ display: flex; align-items: center; gap: 8px; padding: 6px 0; border-bottom: 1px solid #f3f4f6; }}
            .step-icon {{ font-size: 14pt; width: 24px; text-align: center; }}
            .step-label {{ flex: 1; font-weight: 500; }}
            .step-status {{ font-size: 9pt; color: #6b7280; text-transform: uppercase; }}
            .step-notes {{ margin: 2px 0 8px 32px; font-size: 10pt; color: #4b5563; font-style: italic; }}
            .ai-section {{ background: #f0f4ff; border-left: 4px solid #2563eb; padding: 12px 16px; border-radius: 0 8px 8px 0; margin: 20px 0; }}
            .ai-section h3 {{ border: none; margin-top: 0; padding-bottom: 0; }}
            .footer {{ margin-top: 30px; text-align: center; padding: 16px; background: #f9fafb; border-radius: 8px; }}
            .footer p {{ margin: 2px 0; font-size: 10pt; color: #6b7280; }}
            .footer .phone {{ font-size: 13pt; font-weight: 600; color: #1e3a5f; }}
        </style>
    </head>
    <body>
        <div class="header">
            <h1>MAC SEPTIC SERVICES</h1>
            <p>Septic System Inspection Report</p>
        </div>

        <div class="info-grid">
            <div class="info-box">
                <label>Customer</label>
                <span>{customer_name}</span>
            </div>
            <div class="info-box">
                <label>Date</label>
                <span>{report_date_formatted}</span>
            </div>
            <div class="info-box">
                <label>Service Type</label>
                <span>{job_type}</span>
            </div>
        </div>

        {f'<div class="info-box" style="margin-bottom:20px"><label>Address</label><span>{customer_address}</span></div>' if customer_address else ''}

        <div class="condition-banner">
            <strong>Overall Condition: {cond_label}</strong>
            <span>{issues} item(s) noted during inspection{f" ({critical} critical)" if critical else ""}</span>
        </div>

        {recs_html}

        {f'<h3>Inspection Steps</h3>{steps_html}' if steps_html else ''}

        {ai_html}

        {f'<div class="info-box" style="margin-top:20px"><label>Weather Conditions</label><span>{weather_text}</span></div>' if weather_text else ''}

        <div class="footer">
            <p class="phone">(512) 392-1232 &nbsp;|&nbsp; macseptic.com</p>
            <p>MAC Septic Services — San Marcos, TX</p>
            <p>Report ID: {work_order_id[:8] if work_order_id else 'N/A'}</p>
        </div>
    </body>
    </html>
    """

    try:
        from weasyprint import HTML
        pdf_bytes = HTML(string=html).write_pdf()
        logger.info(f"[INSPECTION-PDF] Generated PDF: {len(pdf_bytes)} bytes via WeasyPrint")
        return pdf_bytes
    except ImportError:
        logger.error("[INSPECTION-PDF] WeasyPrint not available, falling back to simple PDF")
        # Fallback: generate a minimal valid PDF without WeasyPrint
        return _generate_simple_pdf(customer_name, condition, cond_label, issues, recs, report_date_formatted, work_order_id)
    except Exception as e:
        logger.error(f"[INSPECTION-PDF] WeasyPrint failed: {e}, falling back to simple PDF")
        return _generate_simple_pdf(customer_name, condition, cond_label, issues, recs, report_date_formatted, work_order_id)


def _generate_simple_pdf(customer_name, condition, cond_label, issues, recs, date_str, wo_id):
    """Generate a minimal valid PDF without external dependencies."""
    # Build text content
    lines = [
        "MAC SEPTIC SERVICES",
        "Septic System Inspection Report",
        "",
        f"Customer: {customer_name}",
        f"Date: {date_str}",
        f"Report ID: {wo_id[:8] if wo_id else 'N/A'}",
        "",
        f"Overall Condition: {cond_label}",
        f"Issues Noted: {issues}",
        "",
    ]
    if recs:
        lines.append("Key Findings:")
        for r in recs:
            lines.append(f"  - {r}")
        lines.append("")
    lines.append("Thank you for choosing MAC Septic Services!")
    lines.append("(512) 392-1232 | macseptic.com")

    text = "\n".join(lines)

    # Construct a minimal valid PDF manually
    # This is a bare-bones PDF 1.4 with a single page of text
    content_stream = f"BT /F1 12 Tf 72 720 Td "
    y = 720
    for line in lines:
        # Escape special PDF characters
        safe_line = line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
        content_stream += f"({safe_line}) Tj 0 -16 Td "
        y -= 16
    content_stream += "ET"

    stream_bytes = content_stream.encode("latin-1")
    stream_len = len(stream_bytes)

    pdf = (
        b"%PDF-1.4\n"
        b"1 0 obj <</Type /Catalog /Pages 2 0 R>> endobj\n"
        b"2 0 obj <</Type /Pages /Kids [3 0 R] /Count 1>> endobj\n"
        b"3 0 obj <</Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
        b"/Contents 4 0 R /Resources <</Font <</F1 5 0 R>>>>>> endobj\n"
        b"4 0 obj <</Length " + str(stream_len).encode() + b">>\nstream\n"
        + stream_bytes +
        b"\nendstream\nendobj\n"
        b"5 0 obj <</Type /Font /Subtype /Type1 /BaseFont /Helvetica>> endobj\n"
        b"xref\n0 6\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"0000000115 00000 n \n"
        b"0000000266 00000 n \n"
        b"0000000" + str(317 + stream_len).encode() + b" 00000 n \n"
        b"trailer <</Size 6 /Root 1 0 R>>\n"
        b"startxref\n0\n%%EOF"
    )

    logger.info(f"[INSPECTION-PDF] Generated simple PDF: {len(pdf)} bytes")
    return pdf


def pdf_to_base64(pdf_bytes: bytes) -> str:
    """Convert PDF bytes to base64 string for Brevo attachment."""
    return base64.b64encode(pdf_bytes).decode("ascii")
