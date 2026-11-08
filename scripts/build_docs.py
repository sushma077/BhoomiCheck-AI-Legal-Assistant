"""Build the knowledge-base README and the two-page solution PDF from real evaluation files."""
from __future__ import annotations

import io
import json
import sys
from pathlib import Path

import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

S = json.loads((config.EVAL_DIR / "evaluation_summary.json").read_text())
FIRST = json.loads((config.EVAL_DIR / "first_holdout_run_summary.json").read_text())["holdout_set"]
FRESH = json.loads((config.EVAL_DIR / "fresh_set_first_run_summary.json").read_text())["fresh_set"]
SOURCES = json.loads(config.SOURCES_JSON.read_text())["sources"]
DEV = S["development_set"]
AVAILABLE = [s for s in SOURCES if s["availability"] == "available"]
MISSING = [s for s in SOURCES if s["availability"] != "available"]
MODEL = S["real_model_test"]
STRESS = S["validator_stress"]


def frac(metric: dict) -> str:
    return f"{metric['passed']}/{metric['total']}"


def build_kb_readme() -> None:
    lines = ["# Legal knowledge base", "",
             "Official Indian sources collected by `scripts/collect_sources.py` and indexed by `scripts/build_index.py`.",
             "Every PDF must pass a content check before it counts as collected. `sources.json` holds the URL, date, hash and every failed attempt.",
             "", f"**{len(AVAILABLE)} of {len(SOURCES)} sources indexed, {S['knowledge_base']['chunks']:,} passages.** Search mode: {S['retrieval_mode']}.",
             "", "RAG here means looking up passages at question time. No model has been trained on this material.",
             "", "## Indexed", "", "| Source | Jurisdiction | Status | Host |", "|---|---|---|---|"]
    for s in AVAILABLE:
        host = (s["url"] or "").split("/")[2]
        lines.append(f"| [{s['title']}]({s['url']}) | {s['jurisdiction']} | {s['status']} | {host} |")
    lines += ["", "## Not available when collected", "", "Their contents were not invented. Re-run the collector to try again.", "", "| Source | Last recorded reason |", "|---|---|"]
    for s in MISSING:
        reason = (s["attempts"] or ["unknown"])[-1].replace("|", " ")
        lines.append(f"| {s['title']} | {reason[:150]} |")
    lines += ["", "## How current these texts are", "",
              "Texts are as published on the hosting site when collected. They were not compared line by line against the latest amendments, and no lawyer has reviewed them.", "",
              "- **Indian Stamp Act:** the copy says it is as amended by the Finance Act, 2006, and comes from Puducherry's revenue site. Stamp duty is largely set by states, so check state law for rates.",
              "- **Uttar Pradesh Revenue Code:** this copy is updated to 5 March 2021.",
              "- **Indian Succession Act:** this copy says it is modified to 26 November 2018.",
              "- **Limitation Act, Contract Act, Succession Act, Easements Act:** India Code's old server returned errors, so copies came from a High Court website (thc.nic.in). The file behind the Limitation Act has \"2019\" in its name, but its content is the 1963 Act.",
              "- **Draft Registration Bill, 2025:** a draft for consultation, so it is left out of search unless a question asks about it. Whether it has been enacted was not confirmed from an official source. If it has, Registration Act answers may be out of date.",
              "- **Supreme Court judgments:** the passages on mutation were read in the PDFs: Karam Singh (p.11), Mansoor Saheb (p.20), P. Kishore Kumar (p.10).",
              "- **State coverage:** only Uttar Pradesh and Maharashtra revenue law is indexed. Karnataka's Act could not be collected.",
              "", "State portals that render in the browser (IGRS UP, UP Bhulekh, DoLR home page) return no readable text to a script. No CAPTCHA, login or site protection was bypassed.", ""]
    (config.KB_DIR / "README.md").write_text("\n".join(lines))


CSS = """
body {font-family: sans-serif; font-size: 10pt; line-height: 1.3; color: #1f2937;}
h1 {font-size: 15pt; color: #14213d; margin: 0;}
h2 {font-size: 11pt; color: #0f766e; margin: 7pt 0 2pt 0;}
p {margin: 1.5pt 0;}
ul {margin: 1pt 0 1pt 11pt; padding: 0;}
li {margin: 0.8pt 0;}
.sub {font-size: 8.5pt; color: #4b5563;}
"""


def row(label: str, value: str) -> str:
    return f"<li><b>{label}:</b> {value}</li>"


def solution_html() -> str:
    fr = FRESH["retrieval"]
    dr = DEV["retrieval"]
    return f"""
<h1>BhoomiCheck: an AI assistant for Indian property documents</h1>
<p class="sub">Kuku placement assignment, Problem 2 (Build an AI Lawyer). Understand Documents. Identify Risks. Verify Before You Invest.</p>

<h2>Problem choice and why</h2>
<p>Buying property is the largest purchase most Indian families make, yet buyers often see the papers only when asked to pay. A lawyer's title search is the right safeguard, but people need to know what to ask first. A general chatbot is dangerous here, because a confident invented section or "the title looks clear" can cost a family its savings. So BhoomiCheck does not try to replace a lawyer. It reads the papers, finds conflicts between them, and prepares a checklist and report the citizen can take to one.</p>

<h2>Assumptions</h2>
<ul>
<li>Users hold copies of their papers and read English, Hindi or Hinglish. Most documents follow common deed and revenue-record patterns.</li>
<li>BhoomiCheck sees only what is uploaded, with no access to court, bank or registry records. A document that was not uploaded may still exist.</li>
<li>No paid service could be required, and no API key was available, so the core had to work without a language model.</li>
</ul>

<h2>How the application works</h2>
<p>Streamlit app, ten pages. Upload PDFs or photos &rarr; read text, using OCR for scans and for Hindi PDFs with broken text layers (Tesseract, English + Hindi) &rarr; classify &rarr; extract names, Khasra and Khata numbers, area, boundaries, amounts, dates and registration details, each with its page &rarr; compare across documents &rarr; raise findings as High Priority, Warning or Information, each with reason, source, page and what to verify &rarr; generate checklists and PDF and Word reports. The assistant answers in English, Hindi and Hinglish.</p>

<h2>AI versus code responsibilities</h2>
<ul>
<li><b>Python rules decide:</b> extraction, name matching (including Hindi against English spelling), area conversion, the ownership chain, date logic, every risk finding, and every section cited on a finding.</li>
<li><b>Embeddings find:</b> a multilingual model helps Hindi and Hinglish questions reach English statutes, alongside keyword search.</li>
<li><b>A language model may only explain:</b> it can reword retrieved law in English, if its reply passes the checks below. It cannot create findings. Requests to certify a property never reach it.</li>
</ul>

<h2>RAG and legal hallucination prevention</h2>
<p><b>Corpus:</b> {len(AVAILABLE)} of {len(SOURCES)} official sources attempted, {S['knowledge_base']['chunks']:,} passages split by legal section, each keeping title, URL, jurisdiction, page and provision. Includes the Transfer of Property, Registration, Stamp, RERA, Contract, Specific Relief, Limitation and succession Acts, UP and Maharashtra revenue law, and three Supreme Court judgments on mutation. {len(MISSING)} sources could not be collected and are recorded as unavailable, with their contents never invented. This is retrieval. No model was trained on legal data.</p>
<p><b>Safeguards:</b> every rule citation is an exact lookup, checked against the index. A model reply is rejected if it lacks a passage tag, names a section outside the retrieved text, uses corrupted or wrong-script text, has sentences unsupported by the sources, or makes a forbidden claim ("100% safe", "mutation proves ownership"). Small local models may answer in English only. If a reply fails, the user sees direct quotes instead, and quotes appear under every accepted reply too.</p>

<h2>Scalability across states and document types</h2>
<p>New sources need one entry in the collector and an incremental index rebuild. State law is tagged by jurisdiction, and it is ranked below central law unless the state is named. Document types are data tables of phrases and fields. Local units such as bigha vary by state, so they are never converted and are flagged for manual checking. The next steps are more state revenue laws, more regional languages for OCR, and testing on real documents with consent.</p>

<h2>Actual test results</h2>
<p>From <b>evaluation/run_evals.py</b>. {S['synthetic_documents']} synthetic documents with fictional people. Answer keys came from the document definitions, not pipeline output. <b>The same AI wrote the rules and the tests, so unseen-set scores are the fairer guide.</b></p>
<ul>
{row("Unseen wording, first run (set 1)", f"fields {frac(FIRST['field_extraction'])} ({FIRST['field_extraction']['pct']}%), scenarios {frac(FIRST['scenarios'])}, classification {frac(FIRST['classification'])}. This exposed overfitting, so general fixes followed.")}
{row("Unseen wording after fixes (set 2, run once)", f"fields {frac(FRESH['field_extraction'])} ({FRESH['field_extraction']['pct']}%), scenarios {frac(FRESH['scenarios'])}, classification {frac(FRESH['classification'])}, legal retrieval in top 3: {fr['top3']}/{fr['total']}.")}
{row("Development set (used to fix bugs, so optimistic)", f"scenarios {frac(DEV['scenarios'])}, fields {frac(DEV['field_extraction'])}, classification {frac(DEV['classification'])}, comparison {frac(DEV['cross_document_comparison'])}, risk detection {frac(DEV['risk_detection'])}, unreadable files refused {frac(DEV['unreadable_handling'])}, retrieval in top 3: {dr['top3']}/{dr['total']}.")}
{row("Assistant", f"{frac(S['assistant'])}, including hallucination resistance {frac(S['hallucination_resistance'])} and lawyer escalation {frac(S['lawyer_escalation'])}, run without a language model.")}
{row("Citations", f"{S['citation_correctness']['citations_checked']} checked, {len(S['citation_correctness']['invalid'])} invalid. This confirms a passage exists, not that a legal reading is right.")}
{row("Validator stress test", f"caught {STRESS['false_statements_caught']} of {STRESS['false_statements']} plausible false statements, and accepted {STRESS['true_statements_accepted']} of {STRESS['true_statements']} true ones.")}
{row("Real local model (" + MODEL['model'].split('/')[-1] + ")", f"produced {MODEL['model_produced_output']} answers in the final run, and {MODEL['accepted_by_validator']} passed the validator.")}
</ul>

<h2>Known failures</h2>
<ul>
<li>Extraction misses unfamiliar wording. In set 2 it missed a registration date, a Sub-Registrar office (since fixed), a holder name and a Khata number, and truncated a boundary at "A. Rao". On set 1 it still picks the father's name as POA principal in one document.</li>
<li>Rules were never tried on a real document, and scan tests used clean, simulated noise. Real results may be lower.</li>
<li>The validator cannot truly check meaning. It missed {len(STRESS['false_statements_missed'])} false statements, such as "{STRESS['false_statements_missed'][1]}" It also rejects some correct answers, which is why quotes are always shown.</li>
<li>No language model runs by default, so Hindi and Hinglish answers use fixed text plus English quotes, and finding text stays in English. The Anthropic and Ollama connectors are written but were never run, as no key or Ollama was available. The local model's accepted answers ran on one Apple Silicon machine only.</li>
<li>Hindi retrieval is weaker: both set 2 misses were Hindi questions. Only Uttar Pradesh and Maharashtra revenue law is indexed. Some Act copies have older amendment dates. Whether the 2025 Registration Bill became law was not confirmed. No lawyer has reviewed this project.</li>
</ul>

<h2>AI tools used</h2>
<p>Claude Code (Claude Opus 5.5) designed and wrote all the code, collected sources and ran the tests, working from my brief. Local model used in testing: Qwen2.5-3B through MLX. Embeddings: paraphrase-multilingual-MiniLM-L12-v2. OCR: Tesseract. My role was the problem choice, product brief and final review. Full log: DEVELOPMENT_LOG.md.</p>

<h2>A genuine AI error, detected and corrected</h2>
<p><b>A model gave dangerous advice, and the AI-written safety check approved it.</b> Asked "Registry karana zaroori hai kya?", the local model replied in garbled Hindi that registration is not necessary. The retrieved law says the opposite: a sale of tangible immovable property worth Rs. 100 or more can be made only by a registered instrument (Transfer of Property Act, s.54). The validator Claude had written returned <i>ok: true</i>, because it only looked for forbidden phrases and invented section numbers. No test flagged it; it was found by reading the raw output. <b>Correction:</b> citation tags became mandatory, grounding and script checks were added, small models were limited to English, source quotes now always appear, and the exact reply became a regression test. Original text: raw_outputs/first_run/E7_original_model_output.txt. Another error: the collector saved a Rajasthan notification as the "RERA Act" and reported success, until page counts revealed it. Every download now passes a content check.</p>
"""


def build_pdf() -> int:
    archive = pymupdf.Archive(str(config.FONT_DIR))
    story = pymupdf.Story(html=solution_html(), user_css=CSS, archive=archive)
    buffer = io.BytesIO()
    writer = pymupdf.DocumentWriter(buffer)
    more, pages = 1, 0
    while more:
        device = writer.begin_page(pymupdf.paper_rect("a4"))
        more, _ = story.place(pymupdf.Rect(36, 30, 559, 815))
        story.draw(device)
        writer.end_page()
        pages += 1
    writer.close()
    config.DELIVERABLES_DIR.mkdir(exist_ok=True)
    (config.DELIVERABLES_DIR / "BhoomiCheck_Solution_Document.pdf").write_bytes(buffer.getvalue())
    return pages


if __name__ == "__main__":
    build_kb_readme()
    print("solution PDF pages:", build_pdf())
