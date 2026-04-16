"""Indeed-compatible XML feed builder.

Spec: https://docs.indeed.com/indeed-apply/xml-feed

Only emits open requisitions.  Published-date is "now" for every item in
Plan 1; swap to the requisition's `opened_at` if Indeed starts rejecting
feeds that re-stamp dates each poll.
"""
from datetime import datetime, timezone
from xml.sax.saxutils import escape as xml_escape

from app.hr.recruiting.models import HrRequisition


_JOB_TYPE_MAP = {
    "full_time": "fulltime",
    "part_time": "parttime",
    "contract": "contract",
}


def _fmt(v: str | None) -> str:
    return xml_escape(v or "")


def build_indeed_xml(base_url: str, reqs: list[HrRequisition]) -> str:
    now = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S GMT")
    items: list[str] = []
    for r in reqs:
        url = f"{base_url}/careers/{r.slug}"
        desc_parts = [
            r.description_md or "",
            ("\n\n**Requirements**\n" + r.requirements_md) if r.requirements_md else "",
            ("\n\n**Benefits**\n" + r.benefits_md) if r.benefits_md else "",
        ]
        description = "".join(desc_parts).strip()
        job_type = _JOB_TYPE_MAP.get(r.employment_type, "fulltime")
        items.append(
            f"""
    <job>
      <title><![CDATA[{r.title}]]></title>
      <date>{now}</date>
      <referencenumber>{_fmt(r.slug)}</referencenumber>
      <url>{_fmt(url)}</url>
      <company><![CDATA[Mac Septic]]></company>
      <city>{_fmt(r.location_city)}</city>
      <state>{_fmt(r.location_state)}</state>
      <country>US</country>
      <description><![CDATA[{description}]]></description>
      <salary><![CDATA[{r.compensation_display or ''}]]></salary>
      <jobtype>{job_type}</jobtype>
    </job>"""
        )
    body = "".join(items)
    return (
        "<?xml version='1.0' encoding='utf-8'?>\n"
        "<source>\n"
        "  <publisher>Mac Septic</publisher>\n"
        f"  <publisherurl>{_fmt(base_url)}</publisherurl>\n"
        f"  <lastbuilddate>{now}</lastbuilddate>"
        f"{body}\n"
        "</source>\n"
    )
