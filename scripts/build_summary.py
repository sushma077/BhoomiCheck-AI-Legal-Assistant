"""Build the project summary PDF for reviewers. Scores are read from the saved evaluation files."""
from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import KeepTogether, ListFlowable, ListItem, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

S = json.loads((config.EVAL_DIR / "evaluation_summary.json").read_text())
SET1 = json.loads((config.EVAL_DIR / "first_holdout_run_summary.json").read_text())["holdout_set"]
SET2 = json.loads((config.EVAL_DIR / "fresh_set_first_run_summary.json").read_text())["fresh_set"]
SOURCES = json.loads(config.SOURCES_JSON.read_text())["sources"]
DEV = S["development_set"]
STRESS = S["validator_stress"]
MODEL = S["real_model_test"]
INDEXED = sum(s["availability"] == "available" for s in SOURCES)

NAVY, TEAL, LINE, SOFT = colors.HexColor("#14213d"), colors.HexColor("#0f766e"), colors.HexColor("#d9e0e8"), colors.HexColor("#f1f6f6")
BODY = ParagraphStyle("body", fontName="Helvetica", fontSize=9.7, leading=12.8, textColor=colors.HexColor("#1f2937"), alignment=TA_LEFT, spaceAfter=4)
CELL = ParagraphStyle("cell", parent=BODY, fontSize=8.9, leading=11.4, spaceAfter=0)
HEAD = ParagraphStyle("head", parent=CELL, fontName="Helvetica-Bold", textColor=colors.white)
H1 = ParagraphStyle("h1", parent=BODY, fontName="Helvetica-Bold", fontSize=20, leading=24, textColor=NAVY, spaceAfter=2)
SUB = ParagraphStyle("sub", parent=BODY, fontSize=9.5, textColor=colors.HexColor("#5b6b82"), spaceAfter=8)
H2 = ParagraphStyle("h2", parent=BODY, fontName="Helvetica-Bold", fontSize=12.5, leading=15, textColor=TEAL, spaceBefore=7, spaceAfter=3, keepWithNext=1)
H3 = ParagraphStyle("h3", parent=BODY, fontName="Helvetica-Bold", fontSize=10, textColor=NAVY, spaceBefore=4, spaceAfter=2, keepWithNext=1)
WIDTH = A4[0] - 36 * mm


def frac(metric: dict) -> str:
    return f"{metric['passed']}/{metric['total']}"


def retrieval(metric: dict) -> str:
    return f"{metric['top3']}/{metric['total']}"


def para(text: str) -> Paragraph:
    return Paragraph(text, BODY)


def bullets(items: list[str]) -> ListFlowable:
    return ListFlowable([ListItem(Paragraph(i, BODY), leftIndent=11) for i in items], bulletType="bullet", start="•", leftIndent=11, bulletFontSize=8)


def table(rows: list[list[str]], widths: list[float]) -> Table:
    data = [[Paragraph(c, HEAD) for c in rows[0]]] + [[Paragraph(c, CELL) for c in row] for row in rows[1:]]
    t = Table(data, colWidths=[w * WIDTH for w in widths], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), NAVY), ("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.5, LINE),
        ("TOPPADDING", (0, 0), (-1, -1), 3), ("BOTTOMPADDING", (0, 0), (-1, -1), 4), ("LEFTPADDING", (0, 0), (-1, -1), 5), ("RIGHTPADDING", (0, 0), (-1, -1), 5),
    ]))
    return t


def footer(canvas, doc) -> None:
    canvas.saveState()
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(colors.HexColor("#5b6b82"))
    canvas.drawString(18 * mm, 10 * mm, "BhoomiCheck project summary. All test documents are synthetic.")
    canvas.drawRightString(A4[0] - 18 * mm, 10 * mm, f"Page {doc.page}")
    canvas.restoreState()


def build() -> Path:
    glance = Table([[Paragraph(
        f"<b>In short:</b> I picked Problem 2, Build an AI Lawyer, and built BhoomiCheck, a working app that reads Indian property documents, finds conflicts between them, "
        f"and tells a citizen what to verify before paying. On document wording it had not seen, it extracted <b>{SET2['field_extraction']['pct']}%</b> of details correctly, after scoring "
        f"<b>{SET1['field_extraction']['pct']}%</b> on its first unseen test. It has only been tested on synthetic documents, and it does not replace a lawyer.", BODY)]], colWidths=[WIDTH])
    glance.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, -1), SOFT), ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9), ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 3)]))

    story = [
        Paragraph("BhoomiCheck: project summary", H1),
        Paragraph("Kuku placement assignment, Problem 2: Build an AI Lawyer", SUB),
        glance,

        Paragraph("1. The problem I picked, and why", H2),
        para("Buying property is the largest purchase most Indian families make, yet many buyers cannot read the papers they are asked to rely on. "
             "A lawyer's title search is the right safeguard, but people need help knowing what to ask, and a family can lose its savings by missing one conflict between two papers."),
        para("I narrowed \"AI Lawyer\" to property documents for three reasons:"),
        bullets([
            "<b>The harm is real and easy to understand.</b> A wrong name or an unreleased mortgage has direct financial consequences.",
            "<b>Much of the work can be checked by code.</b> Whether two Khasra numbers match needs no AI judgment, so the riskiest decisions can be kept away from a language model.",
            "<b>A general legal chatbot is the wrong product.</b> A confident invented section is the failure that matters most in law, so I wanted a design that could be tested against it.",
        ]),

        Paragraph("2. Assumptions", H2),
        bullets([
            "Users hold copies of their papers, and read English, Hindi or Hinglish.",
            "Most documents follow common Indian deed and revenue-record wording. <b>This is untested on real documents.</b>",
            "BhoomiCheck sees only what is uploaded, with no access to court, bank or registry records. A document that was not uploaded may still exist.",
            "The core had to work free, with no API key, as none was available.",
        ]),

        Paragraph("3. How the solution works", H2),
        table([
            ["Step", "What happens", "Done by"],
            ["Read", "Takes PDFs and photos, using OCR for scans and for Hindi PDFs whose text extracts as junk", "Tesseract OCR, PyMuPDF"],
            ["Understand", "Identifies the document type, then extracts names, Khasra and Khata numbers, area, boundaries, amounts and dates, each with its page", "Python rules"],
            ["Compare", "Checks names, property identity, area, dates, amounts and the chain of ownership across documents", "Python rules"],
            ["Flag", "Raises High Priority, Warning and Information findings, with reason, source page and what to verify", "Python rules"],
            ["Answer", f"Answers questions in three languages, citing document pages and {INDEXED} official legal sources ({S['knowledge_base']['chunks']:,} searchable passages)", "Rules, plus keyword and embedding search"],
            ["Explain (optional)", "A connected language model may reword retrieved law. Its reply is shown only if it passes a validator, and always with the source quote", "Language model, off by default"],
            ["Report", "Produces due-diligence checklists, and PDF and Word reports to take to a lawyer", "Python"],
        ], [0.17, 0.58, 0.25]),
        Spacer(1, 6),
        Paragraph("Choices I made, and why", H3),
        table([
            ["Choice", "Why"],
            ["Rules decide, and AI may only explain", "The same input always gives the same finding, each finding can be traced to a page, and a model cannot invent a conflict."],
            ["It refuses to certify a property", "Nobody can promise clear title from uploaded papers. Requests like \"guarantee this is safe\" never reach a model."],
            ["Official sources only, each one checked on download", "A wrong source gives wrong answers with real-looking citations. Unavailable sources are recorded as unavailable, not filled in."],
            ["Keyword plus multilingual search", "Citizens ask in Hindi and Hinglish, while statutes are in English."],
            ["Test sets kept unseen until measured", "The same AI wrote the rules and the test documents, so scores on those documents alone would flatter it."],
        ], [0.38, 0.62]),

        Paragraph("4. Problems we faced", H2),
        para("All of these were real, and the full record is in DEVELOPMENT_LOG.md."),
        table([
            ["Problem", "How it was found", "What changed"],
            ["<b>A local AI model said registration was not necessary, and the safety check approved it.</b> The law says the opposite.", "Reading the raw output. No test flagged it.", "Citations became mandatory, more checks were added, small models were limited to English, and quotes now always appear."],
            ["<b>Rules were overfitted.</b> 99.6% on my own documents, but 64.3% on unseen wording.", "An unseen test set", "General fixes, then a second new test set: 81.5%."],
            ["<b>The wrong legal documents were saved.</b> A Rajasthan notification was stored as the \"RERA Act\", and the collector reported success.", "Checking page counts before indexing", "Every download must now pass a content check."],
            ["<b>Government sites were hard to reach.</b> India Code had moved hosts, its old server returned errors, and some portals gave scripts no readable text.", "Reading the responses, not only the status codes", "Used other official hosts. 8 of 28 sources stayed unavailable, and no site protection was bypassed."],
            ["<b>Hindi PDFs looked right but extracted as junk.</b>", "A rendering test", "These pages are detected and sent to OCR."],
            ["<b>No API key or local AI was available.</b>", "Checking the machine at the start", "Built the core to work with no language model, then tested a small local one."],
        ], [0.46, 0.2, 0.34]),

        Paragraph("5. How it would scale", H2),
        Paragraph("Across states and document types (built today)", H3),
        bullets([
            "A new legal source needs one entry in the collector, then an incremental index rebuild. State law is tagged, and it ranks below central law unless that state is named.",
            "Adding documents costs no new rules. Adding a new <i>format</i> does, and that is the real scaling limit of a rule-based extractor, as the unseen tests showed.",
            "Speed is not the constraint so far: 4 documents, one a Hindi scan, took about 2 seconds in one run on an 8 GB laptop. This was not load-tested.",
        ]),
        KeepTogether([
        Paragraph("To every show Kuku makes (a proposal: nothing here is built or tested)", H3),
        para("BhoomiCheck reviews property documents, not shows. It does not read show contracts today, so it would not work on them as it stands. "
             "The same approach could carry over, because each show also rests on a chain of papers, such as author to adapter to platform:"),
        table([
            ["What carries over", "What would be new"],
            ["Page-level extraction, comparing documents, chain checking, severity-ranked findings, the citation validator, refusing to certify", "Rights and licence document types. Checks for term, territory, expiry and gaps in the chain of rights. Copyright law in the index (not there today). Test documents based on real contracts. Review by a media lawyer."],
        ], [0.5, 0.5]),
        ]),
        Spacer(1, 4),
        para("Rules would belong to contract <i>formats</i>, not individual shows, so a new show in a known format should need no new work. Each new format would need new rules or a capable language model, plus its own test set. "
             "I have no data on the volume or variety of Kuku's contracts, so I can't estimate effort or accuracy."),

        Paragraph("6. How I know it's good", H2),
        para(f"An automated evaluation ran on {S['synthetic_documents']} synthetic documents, with answer keys written from each document's definition, not from pipeline output. All raw outputs are saved. <b>The unseen columns are the fair guide</b>, and each is the set's first run:"),
        KeepTogether(table([
            ["Measure", "My own test documents (optimistic)", "Unseen set 1", "Unseen set 2, after fixes"],
            ["Details extracted correctly", f"{frac(DEV['field_extraction'])} ({DEV['field_extraction']['pct']}%)", f"{frac(SET1['field_extraction'])} ({SET1['field_extraction']['pct']}%)", f"<b>{frac(SET2['field_extraction'])} ({SET2['field_extraction']['pct']}%)</b>"],
            ["Scenarios passed", frac(DEV["scenarios"]), frac(SET1["scenarios"]), frac(SET2["scenarios"])],
            ["Document type correct", frac(DEV["classification"]), frac(SET1["classification"]), frac(SET2["classification"])],
            ["Correct law in top 3 results", retrieval(DEV["retrieval"]), retrieval(SET1["retrieval"]), retrieval(SET2["retrieval"])],
        ], [0.31, 0.27, 0.19, 0.23])),
        Spacer(1, 6),
        bullets([
            f"<b>Assistant:</b> {frac(S['assistant'])} tests passed with no language model, including refusing to certify ({frac(S['hallucination_resistance'])} hallucination-resistance tests) and referring to a lawyer ({frac(S['lawyer_escalation'])}).",
            f"<b>Citations:</b> {S['citation_correctness']['citations_checked']} checked, {len(S['citation_correctness']['invalid'])} invalid. This shows each passage exists, not that a legal reading is right.",
            "<b>Automated tests:</b> 157 Pytest tests passed, including from a clean install. I also ran the full user flow in a real browser.",
        ]),
        Paragraph("Set sizes are small, at 6 documents each, so treat these scores as indications only.", BODY),

        Paragraph("7. Where it fails", H2),
        bullets([
            "<b>Real documents:</b> it has never seen one. Expect lower accuracy than these results, especially on poor scans.",
            "<b>Unfamiliar wording:</b> unseen set 2 missed a registration date, a Sub-Registrar office (since fixed), a holder name and a Khata number, and cut a boundary short. A missed detail can also trigger a false warning.",
            f"<b>The AI safety check cannot truly verify meaning:</b> it caught {STRESS['false_statements_caught']} of {STRESS['false_statements']} plausible false statements. It missed \"{STRESS['false_statements_missed'][3].replace(' [L1].', '')}\". It also rejects correct answers.",
            f"<b>The local AI model isn't useful yet:</b> in the final run it produced {MODEL['model_produced_output']} answers and {MODEL['accepted_by_validator']} passed. The Anthropic and Ollama connections are written but have never been run.",
            "<b>Hindi and Hinglish are limited:</b> answers use fixed text plus English quotes, findings stay in English, and both retrieval misses in unseen set 2 were Hindi questions.",
            "<b>Coverage and currency:</b> only UP and Maharashtra revenue law is indexed. Some Act copies carry older amendment dates, and I could not confirm whether the 2025 Registration Bill became law.",
            "<b>What it can't see:</b> court, bank and registry records. It can't detect forgery. <b>No lawyer has reviewed this project.</b>",
        ]),

        Paragraph("8. What I'd do next, and how it was built", H2),
        para("<b>Next:</b> test on real documents with consent, have a property lawyer review the rules and citations, connect a capable language model for Hindi and for unfamiliar wording while keeping the checks, and add more states."),
        para("<b>How it was built:</b> Claude Code (Claude Opus 5.5) designed and wrote the code, collected the sources and ran the tests, working from my brief. I chose the problem and set the requirements."),
    ]
    out = config.DELIVERABLES_DIR / "BhoomiCheck_Project_Summary.pdf"
    SimpleDocTemplate(str(out), pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=13 * mm, bottomMargin=16 * mm,
                      title="BhoomiCheck: project summary", author="BhoomiCheck").build(story, onFirstPage=footer, onLaterPages=footer)
    return out


if __name__ == "__main__":
    print(build())
