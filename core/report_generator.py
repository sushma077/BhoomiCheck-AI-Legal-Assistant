"""Downloadable PDF and DOCX reports built from one analysis result."""
from __future__ import annotations

import html
import io
from datetime import datetime

import pymupdf
from docx import Document
from docx.enum.text import WD_COLOR_INDEX
from docx.shared import Pt, RGBColor

import config
from core.models import HIGH, INFO, WARNING

NEXT_STEPS = [
    "Resolve every High Priority item with the seller, and get the explanation in writing.",
    "Get certified copies of key documents from the Sub-Registrar's office.",
    "Take a current Encumbrance Certificate, and check the land record on the state portal.",
    "Visit the property and confirm its boundaries and who is in possession.",
    "Ask a qualified property lawyer for a written title opinion before you pay or sign.",
]
LAWYER_MATTERS = "Inheritance and family claims, ownership conflicts, court cases, suspected forgery, and any serious title question."
FIELD_LABELS = [
    ("sellers", "Seller / transferor"), ("buyers", "Buyer / transferee"), ("owners", "Owner named"), ("previous_owners", "Previous owner named"),
    ("landlord", "Landlord"), ("tenant", "Tenant"), ("poa_principal", "POA principal"), ("poa_attorney", "POA attorney"),
    ("survey_numbers", "Survey / Khasra"), ("plot_numbers", "Plot / house"), ("khata_numbers", "Khata"),
]
SINGLE_LABELS = [("property_address", "Property address"), ("execution_date", "Execution date"), ("registration_date", "Registration date"),
                 ("sub_registrar", "Sub-Registrar"), ("mutation_order_date", "Mutation order date")]


def _page(item) -> str:
    return f" (p.{item['page']})" if isinstance(item, dict) and item.get("page") else ""


def _readable_date(value: str) -> str:
    try:
        return datetime.strptime(value, "%Y-%m-%d").strftime("%d %B %Y")
    except (TypeError, ValueError):
        return str(value)


def document_facts(doc) -> list[tuple[str, str]]:
    """Label and value rows for one document, each carrying its source page."""
    f = doc.fields
    rows: list[tuple[str, str]] = []
    for key, label in FIELD_LABELS:
        values = f.get(key) or []
        if values:
            rows.append((label, ", ".join(f"{v['value']}{_page(v)}" for v in values)))
    for key, label in SINGLE_LABELS:
        if f.get(key):
            value = _readable_date(f[key]["value"]) if key.endswith("_date") else f[key]["value"]
            rows.append((label, f"{value}{_page(f[key])}"))
    if f.get("area"):
        area = f["area"]["value"]
        extra = f" (about {area['sq_m']} sq. m)" if area.get("sq_m") else ""
        rows.append(("Area", f"{area['text'].rstrip('. ')}{extra}{_page(f['area'])}"))
    if f.get("transaction_amount"):
        rows.append(("Transaction amount", f["transaction_amount"]["value"]["display"] + _page(f["transaction_amount"])))
    if f.get("stamp_duty"):
        rows.append(("Stamp duty", f["stamp_duty"]["value"]["display"] + _page(f["stamp_duty"])))
    reg = f.get("registration") or {}
    if reg.get("document_no"):
        rows.append(("Registration document no.", reg["document_no"]["value"] + _page(reg["document_no"])))
    if f.get("boundaries"):
        rows.append(("Boundaries", "; ".join(f"{k.title()}: {v['value']}" for k, v in f["boundaries"].items())))
    lease = f.get("lease") or {}
    if lease.get("monthly_rent"):
        rows.append(("Monthly rent", lease["monthly_rent"]["value"]["display"] + _page(lease["monthly_rent"])))
    if lease.get("security_deposit"):
        rows.append(("Security deposit", lease["security_deposit"]["value"]["display"] + _page(lease["security_deposit"])))
    if lease.get("term_months"):
        rows.append(("Period", f"{lease['term_months']['value']} months" + _page(lease["term_months"])))
    return rows


def _used_sources(findings) -> list[str]:
    seen, out = set(), []
    for finding in findings:
        for c in finding.citations:
            key = (c.title, c.provision)
            if key not in seen:
                seen.add(key)
                where = f", p.{c.page}" if c.page else ""
                out.append(f"{c.title}, {c.provision}{where}. {c.url or ''}".strip())
    return out


def _counts(findings) -> dict:
    return {s: sum(f.severity == s for f in findings) for s in (HIGH, WARNING, INFO)}


REPORT_CSS = """
@font-face {font-family: hindi; src: url(NotoSansDevanagari-Regular.ttf);}
body {font-family: sans-serif, hindi; font-size: 10pt; line-height: 1.35; color: #1f2937;}
h1 {font-size: 19pt; color: #14213d; margin: 0 0 2pt 0;}
h2 {font-size: 12.5pt; color: #0f766e; margin: 13pt 0 4pt 0;}
h3 {font-size: 10.5pt; color: #14213d; margin: 8pt 0 2pt 0;}
p {margin: 2pt 0;}
li {margin: 2pt 0;}
.notice {color: #7c2d12;}
.small {font-size: 8.5pt; color: #4b5563;}
.high {color: #b91c1c; font-weight: bold;}
.warning {color: #b45309; font-weight: bold;}
.information {color: #1d4ed8; font-weight: bold;}
"""


def _e(value) -> str:
    return html.escape(str(value))


def _sources_text(finding) -> str:
    parts = []
    for s in finding.sources:
        parts.append(f"{s.document}, page {s.page}" if s.page else s.document)
    return "; ".join(dict.fromkeys(parts))


def build_pdf(result: dict) -> bytes:
    docs, findings, comparisons = result["documents"], result["findings"], result["comparisons"]
    counts = _counts(findings)
    b: list[str] = [f"<h1>{config.APP_NAME} property analysis report</h1>",
                    f"<p class='small'>Generated {datetime.now():%d %B %Y, %H:%M}. Analysis engine: {_e(result['model']['model'])}.</p>",
                    f"<p class='notice'>{_e(config.LEGAL_NOTICE)}</p>",
                    "<h2>Property overview</h2>",
                    f"<p>{len(docs)} document(s) reviewed. Findings: {counts[HIGH]} High Priority, {counts[WARNING]} Warning, {counts[INFO]} Information.</p>"]
    for d in docs:
        b.append(f"<p><b>{_e(d.name)}</b>: {_e(d.doc_type_label)}, {len(d.pages)} page(s), status {d.status}.</p>")
    b.append("<h2>Extracted details and transaction information</h2><p class='small'>What each document states, with its page. This is not verified ownership.</p>")
    for d in docs:
        b.append(f"<h3>{_e(d.name)}</h3>")
        rows = document_facts(d)
        if not rows:
            b.append("<p>No details could be extracted from this document.</p>")
        b.extend(f"<p><b>{_e(label)}:</b> {_e(value)}</p>" for label, value in rows)
    b.append("<h2>Comparison findings</h2>")
    b.extend(f"<p><b>{_e(c.status.replace('_', ' ').title())}:</b> {_e(c.summary)}</p>" for c in comparisons)
    b.append("<h2>Potential risks</h2>")
    if not findings:
        b.append("<p>No rule-based findings. That does not mean the property is free of problems.</p>")
    for f in findings:
        css = f.severity.split()[0].lower()
        b.append(f"<h3>{_e(f.title)}</h3><p class='{css}'>{_e(f.severity)}</p><p>{_e(f.reason)}</p>")
        where = _sources_text(f)
        if where:
            b.append(f"<p class='small'><b>Source:</b> {_e(where)}</p>")
        b.append(f"<p><b>Verify:</b> {_e(f.recommended_verification)}</p>")
        if f.citations:
            b.append("<p class='small'><b>Legal reference:</b> " + _e("; ".join(f"{c.title}, {c.provision}" for c in f.citations)) + "</p>")
    missing = [f for f in findings if f.code == "MISSING_DOCUMENT" or f.code == "CHAIN_INCOMPLETE"]
    b.append("<h2>Missing information</h2>")
    b.extend(f"<p>{_e(f.reason)}</p>" for f in missing)
    if not missing:
        b.append("<p>No expected document type was missing from the uploads.</p>")
    b.append("<h2>Due-diligence checklist</h2>")
    for context, items in result["checklists"].items():
        b.append(f"<h3>{_e(context)}</h3><ul>")
        b.extend(f"<li><b>{_e(i['task'])}</b> ({_e(i['status'])}). {_e(i['why'])} Where: {_e(i['where'])}.</li>" for i in items)
        b.append("</ul>")
    b.append("<h2>Recommended next steps</h2><ol>")
    b.extend(f"<li>{_e(s)}</li>" for s in NEXT_STEPS)
    b.append("</ol><h2>Official source references</h2><ul>")
    b.extend(f"<li>{_e(s)}</li>" for s in _used_sources(findings))
    if not _used_sources(findings):
        b.append("<li>No legal provisions were needed for these findings.</li>")
    b.append("</ul><h2>Matters requiring lawyer verification</h2>")
    referred = [f.title for f in findings if f.lawyer_referral]
    b.append(f"<p>{_e(LAWYER_MATTERS)}</p>")
    b.extend(f"<p>This report: {_e(t)}.</p>" for t in referred)
    b.append("<h2>Limits of this report</h2><ul>")
    b.extend(f"<li>{_e(n)}</li>" for n in result["safety_notes"])
    b.append("</ul>")

    archive = pymupdf.Archive(str(config.FONT_DIR))
    story = pymupdf.Story(html="".join(b), user_css=REPORT_CSS, archive=archive)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    more = 1
    while more:
        device = writer.begin_page(pymupdf.paper_rect("a4"))
        more, _ = story.place(pymupdf.Rect(48, 46, 547, 800))
        story.draw(device)
        writer.end_page()
    writer.close()
    return buffer.getvalue()


def build_docx(result: dict) -> bytes:
    docs, findings, comparisons = result["documents"], result["findings"], result["comparisons"]
    counts = _counts(findings)
    document = Document()
    document.styles["Normal"].font.name = "Calibri"
    document.styles["Normal"].font.size = Pt(10.5)
    document.add_heading(f"{config.APP_NAME} property analysis report", 0)
    document.add_paragraph(f"Generated {datetime.now():%d %B %Y, %H:%M}. Analysis engine: {result['model']['model']}.")
    notice = document.add_paragraph().add_run(config.LEGAL_NOTICE)
    notice.font.highlight_color = WD_COLOR_INDEX.YELLOW
    document.add_heading("Property overview", 1)
    document.add_paragraph(f"{len(docs)} document(s) reviewed. Findings: {counts[HIGH]} High Priority, {counts[WARNING]} Warning, {counts[INFO]} Information.")
    for d in docs:
        document.add_paragraph(f"{d.name}: {d.doc_type_label}, {len(d.pages)} page(s), status {d.status}.", style="List Bullet")
    document.add_heading("Extracted details and transaction information", 1)
    document.add_paragraph("What each document states, with its page. This is not verified ownership.")
    for d in docs:
        document.add_heading(d.name, 2)
        rows = document_facts(d)
        if not rows:
            document.add_paragraph("No details could be extracted from this document.")
            continue
        table = document.add_table(rows=0, cols=2)
        table.style = "Light Grid Accent 1"
        for label, value in rows:
            cells = table.add_row().cells
            cells[0].text, cells[1].text = label, value
    document.add_heading("Comparison findings", 1)
    for c in comparisons:
        document.add_paragraph(f"{c.status.replace('_', ' ').title()}: {c.summary}", style="List Bullet")
    document.add_heading("Potential risks", 1)
    if not findings:
        document.add_paragraph("No rule-based findings. That does not mean the property is free of problems.")
    colours = {HIGH: RGBColor(0xB9, 0x1C, 0x1C), WARNING: RGBColor(0xB4, 0x53, 0x09), INFO: RGBColor(0x1D, 0x4E, 0xD8)}
    for f in findings:
        document.add_heading(f.title, 2)
        run = document.add_paragraph().add_run(f.severity)
        run.bold = True
        run.font.color.rgb = colours[f.severity]
        document.add_paragraph(f.reason)
        where = _sources_text(f)
        if where:
            document.add_paragraph(f"Source: {where}")
        document.add_paragraph(f"Verify: {f.recommended_verification}")
        if f.citations:
            document.add_paragraph("Legal reference: " + "; ".join(f"{c.title}, {c.provision}" for c in f.citations))
    document.add_heading("Missing information", 1)
    missing = [f for f in findings if f.code in ("MISSING_DOCUMENT", "CHAIN_INCOMPLETE")]
    for f in missing:
        document.add_paragraph(f.reason, style="List Bullet")
    if not missing:
        document.add_paragraph("No expected document type was missing from the uploads.")
    document.add_heading("Due-diligence checklist", 1)
    for context, items in result["checklists"].items():
        document.add_heading(context, 2)
        for i in items:
            document.add_paragraph(f"{i['task']} ({i['status']}). {i['why']} Where: {i['where']}.", style="List Bullet")
    document.add_heading("Recommended next steps", 1)
    for step in NEXT_STEPS:
        document.add_paragraph(step, style="List Number")
    document.add_heading("Official source references", 1)
    for source in _used_sources(findings) or ["No legal provisions were needed for these findings."]:
        document.add_paragraph(source, style="List Bullet")
    document.add_heading("Matters requiring lawyer verification", 1)
    document.add_paragraph(LAWYER_MATTERS)
    for f in findings:
        if f.lawyer_referral:
            document.add_paragraph(f"This report: {f.title}.", style="List Bullet")
    document.add_heading("Limits of this report", 1)
    for note in result["safety_notes"]:
        document.add_paragraph(note, style="List Bullet")
    buffer = io.BytesIO()
    document.save(buffer)
    return buffer.getvalue()
