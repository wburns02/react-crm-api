"""HTML→PDF document template engine using Jinja2 + WeasyPrint.

Generates professional branded PDFs for invoices, quotes, work orders, and inspection reports.
"""

import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

# Company branding defaults
COMPANY_NAME = "MAC Septic Services"
COMPANY_ADDRESS = "Central Texas"
COMPANY_PHONE = "(512) 555-0123"
COMPANY_EMAIL = "info@macseptic.com"
TAX_RATE = 0.0825


def _base_styles() -> str:
    return """
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body { font-family: Arial, Helvetica, sans-serif; font-size: 12px; color: #334155; line-height: 1.5; }
        .header { background: #1e293b; color: white; padding: 24px 32px; display: flex; justify-content: space-between; align-items: center; }
        .header-left { display: flex; align-items: center; gap: 16px; }
        .header-left img { height: 40px; }
        .header-left h1 { font-size: 18px; font-weight: 700; }
        .header-right { text-align: right; }
        .header-right .doc-type { font-size: 20px; font-weight: 700; text-transform: uppercase; }
        .header-right .doc-number { font-size: 13px; opacity: 0.85; margin-top: 2px; }
        .content { padding: 32px; }
        .meta-grid { display: flex; gap: 32px; margin-bottom: 24px; }
        .meta-box { flex: 1; }
        .meta-box h3 { font-size: 10px; text-transform: uppercase; color: #94a3b8; letter-spacing: 0.5px; margin-bottom: 6px; }
        .meta-box p { font-size: 12px; color: #1e293b; }
        table.items { width: 100%; border-collapse: collapse; margin: 20px 0; }
        table.items th { background: #f1f5f9; color: #475569; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; padding: 8px 12px; text-align: left; border-bottom: 2px solid #e2e8f0; }
        table.items td { padding: 10px 12px; border-bottom: 1px solid #e2e8f0; font-size: 12px; }
        table.items tr:last-child td { border-bottom: none; }
        .totals { margin-left: auto; width: 260px; margin-top: 16px; }
        .totals tr td { padding: 6px 12px; font-size: 12px; }
        .totals tr td:first-child { color: #64748b; text-align: right; }
        .totals tr td:last-child { text-align: right; font-weight: 600; }
        .totals .grand-total td { font-size: 16px; font-weight: 700; color: #1e293b; border-top: 2px solid #1e293b; padding-top: 10px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: 10px; font-weight: 600; }
        .badge-pass { background: #dcfce7; color: #166534; }
        .badge-fail { background: #fef2f2; color: #991b1b; }
        .badge-na { background: #f1f5f9; color: #64748b; }
        .badge-optional { background: #eff6ff; color: #1d4ed8; }
        .section { margin: 20px 0; }
        .section h2 { font-size: 14px; color: #1e293b; border-bottom: 2px solid #2563eb; padding-bottom: 6px; margin-bottom: 12px; }
        .footer { background: #f8fafc; border-top: 1px solid #e2e8f0; padding: 16px 32px; text-align: center; font-size: 11px; color: #94a3b8; margin-top: 32px; }
        .card { border: 1px solid #e2e8f0; border-radius: 8px; padding: 16px; margin-bottom: 12px; }
        .card h4 { font-size: 12px; color: #2563eb; margin-bottom: 8px; }
        @page { size: letter; margin: 0; }
    </style>
    """


def _header_html(doc_type: str, doc_number: str, logo_data_uri: str = "") -> str:
    logo_html = f'<img src="{logo_data_uri}" alt="Logo" />' if logo_data_uri else ""
    return f"""
    <div class="header">
        <div class="header-left">
            {logo_html}
            <div>
                <h1>{COMPANY_NAME}</h1>
                <div style="font-size: 11px; opacity: 0.7;">{COMPANY_ADDRESS}</div>
            </div>
        </div>
        <div class="header-right">
            <div class="doc-type">{doc_type}</div>
            <div class="doc-number">{doc_number}</div>
        </div>
    </div>
    """


def _footer_html() -> str:
    return f"""
    <div class="footer">
        Thank you for your business! &middot; {COMPANY_NAME} &middot; {COMPANY_PHONE} &middot; {COMPANY_EMAIL}
    </div>
    """


def _customer_meta(customer: dict, extra_fields: dict | None = None) -> str:
    fields = extra_fields or {}
    extra_html = "".join(f"<p><strong>{k}:</strong> {v}</p>" for k, v in fields.items())
    return f"""
    <div class="meta-grid">
        <div class="meta-box">
            <h3>Bill To</h3>
            <p><strong>{customer.get('name', customer.get('first_name', '') + ' ' + customer.get('last_name', ''))}</strong></p>
            <p>{customer.get('address', 'N/A')}</p>
            <p>{customer.get('phone', '')} &middot; {customer.get('email', '')}</p>
        </div>
        <div class="meta-box">
            <h3>Details</h3>
            {extra_html}
        </div>
    </div>
    """


def _format_money(amount) -> str:
    try:
        return f"${float(amount):,.2f}"
    except (TypeError, ValueError):
        return "$0.00"


def render_invoice_html(data: dict) -> str:
    """Render an invoice to HTML."""
    from app.services.logos import LOGO_WHITE_DATA_URI
    invoice = data.get("invoice", {})
    customer = data.get("customer", {})
    items = data.get("line_items", invoice.get("line_items", []))

    ref_num = invoice.get("invoice_number", "N/A")
    date_str = invoice.get("invoice_date", invoice.get("created_at", ""))[:10] if invoice.get("invoice_date") or invoice.get("created_at") else ""
    due_date = invoice.get("due_date", "")[:10] if invoice.get("due_date") else "Upon receipt"

    rows_html = ""
    subtotal = 0.0
    for item in items:
        desc = item.get("description", item.get("service", "Service"))
        qty = item.get("quantity", 1)
        rate = float(item.get("rate", item.get("unit_price", item.get("amount", 0))))
        amount = float(qty) * rate
        subtotal += amount
        rows_html += f"<tr><td>{desc}</td><td>{qty}</td><td>{_format_money(rate)}</td><td style='text-align:right'>{_format_money(amount)}</td></tr>"

    tax = subtotal * TAX_RATE
    total = subtotal + tax

    return f"""<!DOCTYPE html><html><head>{_base_styles()}</head><body>
    {_header_html("Invoice", ref_num, LOGO_WHITE_DATA_URI)}
    <div class="content">
        {_customer_meta(customer, {"Date": date_str, "Due Date": due_date, "Status": invoice.get("status", "draft").title()})}
        <table class="items">
            <thead><tr><th>Description</th><th>Qty</th><th>Rate</th><th style="text-align:right">Amount</th></tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        <table class="totals">
            <tr><td>Subtotal</td><td>{_format_money(subtotal)}</td></tr>
            <tr><td>Tax ({TAX_RATE*100:.2f}%)</td><td>{_format_money(tax)}</td></tr>
            <tr class="grand-total"><td>Total</td><td>{_format_money(total)}</td></tr>
        </table>
        {f'<div class="section"><p style="color:#64748b; font-size:11px;">Notes: {invoice.get("notes", "")}</p></div>' if invoice.get("notes") else ""}
    </div>
    {_footer_html()}
    </body></html>"""


def render_quote_html(data: dict) -> str:
    """Render a quote/estimate to HTML."""
    from app.services.logos import LOGO_WHITE_DATA_URI
    quote = data.get("quote", {})
    customer = data.get("customer", {})
    items = data.get("line_items", quote.get("line_items", []))

    ref_num = quote.get("quote_number", f"QUO-{str(quote.get('id', ''))[:8]}")
    date_str = str(quote.get("created_at", ""))[:10]
    expires = str(quote.get("valid_until", quote.get("expiry_date", "")))[:10] or "30 days"

    rows_html = ""
    subtotal = 0.0
    for item in items:
        desc = item.get("description", "Service")
        qty = item.get("quantity", 1)
        rate = float(item.get("rate", item.get("unit_price", item.get("amount", 0))))
        amount = float(qty) * rate
        optional = item.get("optional", False)
        badge = ' <span class="badge badge-optional">Optional</span>' if optional else ""
        subtotal += amount
        rows_html += f"<tr><td>{desc}{badge}</td><td>{qty}</td><td>{_format_money(rate)}</td><td style='text-align:right'>{_format_money(amount)}</td></tr>"

    tax = subtotal * TAX_RATE
    total = subtotal + tax

    return f"""<!DOCTYPE html><html><head>{_base_styles()}</head><body>
    {_header_html("Estimate", ref_num, LOGO_WHITE_DATA_URI)}
    <div class="content">
        {_customer_meta(customer, {"Date": date_str, "Valid Until": expires, "Status": quote.get("status", "draft").title()})}
        <table class="items">
            <thead><tr><th>Description</th><th>Qty</th><th>Rate</th><th style="text-align:right">Amount</th></tr></thead>
            <tbody>{rows_html}</tbody>
        </table>
        <table class="totals">
            <tr><td>Subtotal</td><td>{_format_money(subtotal)}</td></tr>
            <tr><td>Tax ({TAX_RATE*100:.2f}%)</td><td>{_format_money(tax)}</td></tr>
            <tr class="grand-total"><td>Total</td><td>{_format_money(total)}</td></tr>
        </table>
        <div class="section" style="margin-top: 32px; border-top: 1px dashed #e2e8f0; padding-top: 16px;">
            <p style="font-size: 11px; color: #64748b;">By accepting this estimate, you agree to the terms and conditions of {COMPANY_NAME}.</p>
            <div style="margin-top: 24px; display: flex; gap: 48px;">
                <div><p style="font-size: 10px; color: #94a3b8;">Customer Signature</p><div style="border-bottom: 1px solid #334155; width: 200px; height: 32px;"></div></div>
                <div><p style="font-size: 10px; color: #94a3b8;">Date</p><div style="border-bottom: 1px solid #334155; width: 120px; height: 32px;"></div></div>
            </div>
        </div>
    </div>
    {_footer_html()}
    </body></html>"""


def render_work_order_html(data: dict) -> str:
    """Render a work order to HTML."""
    from app.services.logos import LOGO_WHITE_DATA_URI
    wo = data.get("work_order", {})
    customer = data.get("customer", {})
    technician = data.get("technician", {})

    ref_num = f"WO-{str(wo.get('id', ''))[:8].upper()}"
    job_type = wo.get("job_type", wo.get("type", "Service"))
    status = wo.get("status", "scheduled").title()
    scheduled = str(wo.get("scheduled_date", ""))[:10]
    priority = wo.get("priority", "normal").title()

    tech_name = f"{technician.get('first_name', '')} {technician.get('last_name', '')}".strip() or wo.get("assigned_technician", "Unassigned")
    notes = wo.get("notes", wo.get("description", ""))

    checklist_html = ""
    checklist = wo.get("checklist", {})
    if isinstance(checklist, dict) and checklist:
        items_list = checklist.get("items", [])
        if items_list:
            checklist_html = '<div class="section"><h2>Checklist</h2><ul style="padding-left: 20px;">'
            for item in items_list:
                label = item if isinstance(item, str) else item.get("label", str(item))
                checklist_html += f"<li>{label}</li>"
            checklist_html += "</ul></div>"

    return f"""<!DOCTYPE html><html><head>{_base_styles()}</head><body>
    {_header_html("Work Order", ref_num, LOGO_WHITE_DATA_URI)}
    <div class="content">
        <div class="meta-grid">
            <div class="meta-box">
                <h3>Customer</h3>
                <p><strong>{customer.get('name', customer.get('first_name', '') + ' ' + customer.get('last_name', ''))}</strong></p>
                <p>{customer.get('address', 'N/A')}</p>
                <p>{customer.get('phone', '')}</p>
            </div>
            <div class="meta-box">
                <h3>Job Details</h3>
                <p><strong>Type:</strong> {job_type}</p>
                <p><strong>Status:</strong> {status}</p>
                <p><strong>Scheduled:</strong> {scheduled}</p>
                <p><strong>Priority:</strong> {priority}</p>
            </div>
            <div class="meta-box">
                <h3>Assigned Technician</h3>
                <p><strong>{tech_name}</strong></p>
            </div>
        </div>
        {f'<div class="section"><h2>Notes</h2><p>{notes}</p></div>' if notes else ""}
        {checklist_html}
    </div>
    {_footer_html()}
    </body></html>"""


def render_inspection_html(data: dict) -> str:
    """Render an inspection report to HTML. Delegates to existing inspection_pdf module for data extraction."""
    from app.services.logos import LOGO_WHITE_DATA_URI
    wo = data.get("work_order", {})
    customer = data.get("customer", {})
    inspection = wo.get("checklist", {}).get("inspection", wo.get("checklist", {}))

    ref_num = f"INSP-{str(wo.get('id', ''))[:8].upper()}"
    summary = inspection.get("summary", {})
    condition = summary.get("overall_condition", "N/A")
    issues = summary.get("total_issues", 0)

    steps_html = ""
    steps = inspection.get("steps", {})
    if isinstance(steps, dict):
        for step_key, step_data in steps.items():
            if not isinstance(step_data, dict):
                continue
            label = step_data.get("label", step_key.replace("_", " ").title())
            status = step_data.get("status", "N/A")
            badge_cls = "badge-pass" if status.lower() == "pass" else "badge-fail" if status.lower() == "fail" else "badge-na"
            notes = step_data.get("notes", "")
            steps_html += f"""
            <div class="card">
                <h4>{label} <span class="badge {badge_cls}">{status.upper()}</span></h4>
                {f"<p>{notes}</p>" if notes else ""}
            </div>
            """

    weather_html = ""
    weather = inspection.get("weather", {})
    if weather:
        current = weather.get("current", {})
        if current:
            weather_html = f"""
            <div class="section"><h2>Weather Conditions</h2>
                <p>Temperature: {current.get('temperature', 'N/A')}&deg;F &middot; {current.get('condition', 'N/A')} &middot; Wind: {current.get('wind_speed', 'N/A')} mph</p>
            </div>
            """

    return f"""<!DOCTYPE html><html><head>{_base_styles()}</head><body>
    {_header_html("Inspection Report", ref_num, LOGO_WHITE_DATA_URI)}
    <div class="content">
        <div class="meta-grid">
            <div class="meta-box">
                <h3>Customer</h3>
                <p><strong>{customer.get('name', customer.get('first_name', '') + ' ' + customer.get('last_name', ''))}</strong></p>
                <p>{customer.get('address', 'N/A')}</p>
            </div>
            <div class="meta-box">
                <h3>Assessment</h3>
                <p><strong>Overall Condition:</strong> {condition}</p>
                <p><strong>Issues Found:</strong> {issues}</p>
                <p><strong>Date:</strong> {str(wo.get('scheduled_date', ''))[:10]}</p>
            </div>
        </div>
        {weather_html}
        <div class="section"><h2>Inspection Steps</h2>{steps_html or "<p>No step data available.</p>"}</div>
    </div>
    {_footer_html()}
    </body></html>"""


TEMPLATE_RENDERERS = {
    "invoice": render_invoice_html,
    "quote": render_quote_html,
    "work_order": render_work_order_html,
    "inspection_report": render_inspection_html,
}


async def render_document_html(doc_type: str, data: dict, entity_id: str = "") -> str:
    """Render a document to HTML string."""
    renderer = TEMPLATE_RENDERERS.get(doc_type)
    if not renderer:
        raise ValueError(f"Unknown document type: {doc_type}")
    return renderer(data)


async def render_document_pdf(doc_type: str, data: dict, entity_id: str = "") -> bytes:
    """Render a document to PDF bytes via WeasyPrint."""
    html = await render_document_html(doc_type, data, entity_id)
    try:
        from weasyprint import HTML
        return HTML(string=html).write_pdf()
    except ImportError:
        logger.warning("WeasyPrint not available, returning HTML as fallback")
        return html.encode("utf-8")
