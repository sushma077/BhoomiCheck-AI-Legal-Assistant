"""The ten pages. Each reads from st.session_state and leaves the analysis itself to core/."""
from __future__ import annotations

import datetime
import json

import pymupdf
import streamlit as st

import config
from core.ai_engine import status as llm_status
from core.assistant import answer
from core.checklist_generator import CHECKLISTS, generate as generate_checklist
from core.legal_retrieval import get_retriever
from core.models import HIGH, INFO, WARNING
from core.pipeline import SAFETY_NOTES, analyse, load_bytes, serialisable
from core.report_generator import build_docx, build_pdf, document_facts
from ui import theme

PURPOSES = {"Buying a property": "purchase", "Renting a property": "rental", "Agricultural land": "agricultural"}
STATUS_PILL = {"match": ("Matches", "ok"), "mismatch": ("Conflict", "high"), "variation": ("Check name", "warning"), "missing": ("Not uploaded", "warning"), "not_comparable": ("Could not compare", "neutral")}
CHECK_LABELS = {
    "owner_name": "Owner names", "survey_numbers": "Survey / Khasra numbers", "khata_numbers": "Khata numbers", "area": "Property area", "boundaries": "Boundaries",
    "ownership_chain": "Ownership chain", "dates": "Dates", "amounts": "Transaction amounts", "registration_refs": "Registration numbers",
}
EXAMPLES = ["Who is the seller?", "Is deed mein area kitna hai?", "इस दस्तावेज़ में मालिक कौन है?", "Do the owner names match?", "What is mutation?", "Kya is property par loan hai?"]


def _needs_documents() -> bool:
    if st.session_state.documents:
        return False
    theme.empty("Upload your documents first, then come back to this page.")
    return True


def _go(page: str) -> None:
    st.session_state.nav = page


def home() -> None:
    st.markdown(f'<div class="hero"><h1>{config.APP_NAME}</h1><p>{config.TAGLINE}</p></div>', unsafe_allow_html=True)
    st.markdown("Upload property papers. BhoomiCheck reads them, compares them against each other, and points out what to verify before you pay or sign.")
    cols = st.columns(3)
    cards = [("1. Read", "Reads PDFs and photos, including scanned and Hindi documents, and finds names, numbers, dates and amounts with their page."),
             ("2. Compare", "Checks whether names, Khasra numbers, area, boundaries, dates and the chain of ownership agree across documents."),
             ("3. Verify", "Lists what needs checking, where to check it, the law behind it, and when a lawyer is needed.")]
    for col, (title, text) in zip(cols, cards):
        col.markdown(theme.card(title, text), unsafe_allow_html=True)
    st.button("Start: upload documents", type="primary", on_click=_go, args=("Upload Documents",))
    st.markdown('<div class="notice"><b>What BhoomiCheck is not:</b> it does not certify ownership or say a property is safe. It works from your uploaded papers, not government or court records. Please use a qualified lawyer for the final decision.</div>', unsafe_allow_html=True)
    st.markdown("### Works with")
    st.markdown("Sale Deeds · Agreements to Sell · Rent and Lease Agreements · Gift and Partition Deeds · Mutation Records · Khasra, Khatauni and Jamabandi · Encumbrance Certificates · Property Tax Receipts · Power of Attorney · NOCs · RERA documents")


def upload() -> None:
    theme.intro("Upload Documents", "Add all the papers you have for one property. PDF, JPG, JPEG and PNG are supported. More documents allow more cross-checks.")
    purpose = st.radio("What are you doing?", list(PURPOSES), horizontal=True)
    files = st.file_uploader("Choose files", type=["pdf", "jpg", "jpeg", "png"], accept_multiple_files=True, help="Files stay in this browser session and are not added to any database.")
    if st.button("Analyse documents", type="primary", disabled=not files):
        documents = []
        progress = st.progress(0.0, "Reading documents. Scanned pages take longer.")
        for i, file in enumerate(files, start=1):
            progress.progress((i - 0.5) / len(files), f"Reading {file.name}")
            blob = file.getvalue()
            doc = load_bytes(blob, file.name)
            documents.append(doc)
            st.session_state.setdefault("files", {})[file.name] = blob
        progress.progress(1.0, "Comparing documents")
        st.session_state.documents = documents
        st.session_state.purpose = PURPOSES[purpose]
        st.session_state.result = analyse(documents, PURPOSES[purpose])
        st.session_state.chat = []
        progress.empty()
    documents = st.session_state.documents
    if not documents:
        st.caption("Want to try it first? Sample files with fictional people and properties are in data/synthetic_documents.")
        return
    result = st.session_state.result
    counts = {s: sum(f.severity == s for f in result["findings"]) for s in (HIGH, WARNING, INFO)}
    st.markdown("### Results")
    cols = st.columns(4)
    cols[0].markdown(theme.metric(len(documents), "documents uploaded"), unsafe_allow_html=True)
    cols[1].markdown(theme.metric(counts[HIGH], "High Priority", "var(--high)"), unsafe_allow_html=True)
    cols[2].markdown(theme.metric(counts[WARNING], "Warnings", "var(--warn)"), unsafe_allow_html=True)
    cols[3].markdown(theme.metric(counts[INFO], "Information", "var(--info)"), unsafe_allow_html=True)
    st.write("")
    for doc in documents:
        status_cls = {"ok": "ok", "partial": "warning", "unreadable": "high", "error": "high"}[doc.status]
        status_text = {"ok": "Read", "partial": "Partly read", "unreadable": "Could not read", "error": "Could not open"}[doc.status]
        st.markdown(f'<div class="card"><h4>{theme.e(doc.name)}</h4><p>{theme.pill(status_text, status_cls)} {theme.pill(doc.doc_type_label, "teal")} {len(doc.pages)} page(s)</p></div>', unsafe_allow_html=True)
        for warning in doc.warnings:
            st.warning(warning)
    st.button("See the risks", type="primary", on_click=_go, args=("Risk Analysis",))


def _preview(doc) -> None:
    blob = st.session_state.get("files", {}).get(doc.name)
    if not blob:
        return
    try:
        if doc.name.lower().endswith(".pdf"):
            pdf = pymupdf.open(stream=blob, filetype="pdf")
            if len(pdf):
                st.image(pdf[0].get_pixmap(dpi=70).tobytes("png"), caption="Page 1 preview", width="stretch")
        else:
            st.image(blob, caption="Preview", width="stretch")
    except Exception:  # a preview must never break the page
        st.caption("Preview not available.")


def document_analysis() -> None:
    theme.intro("Document Analysis", "What BhoomiCheck read in each document, with the page for each detail. Check these against the original.")
    if _needs_documents():
        return
    documents = st.session_state.documents
    tabs = st.tabs([d.name[:30] for d in documents])
    for tab, doc in zip(tabs, documents):
        with tab:
            left, right = st.columns([3, 1])
            with right:
                _preview(doc)
            with left:
                confidence = doc.classification.get("confidence")
                evidence = ", ".join(doc.classification.get("evidence", [])[:4])
                st.markdown(f"{theme.pill(doc.doc_type_label, 'teal')} " + (f"<span style='font-size:.82rem;color:var(--muted)'>Matched words: {theme.e(evidence)}. Rule score {confidence}.</span>" if evidence else ""), unsafe_allow_html=True)
                for warning in doc.warnings:
                    st.warning(warning)
                rows = document_facts(doc)
                if rows:
                    st.markdown(theme.facts(rows), unsafe_allow_html=True)
                else:
                    theme.empty("No details could be extracted from this document.")
            with st.expander("Mortgage, possession and other mentions"):
                f = doc.fields
                any_mention = False
                for key, label in (("mortgage_refs", "Mortgage or loan"), ("release_refs", "Release"), ("litigation_refs", "Court or dispute"), ("inheritance_refs", "Inheritance"), ("possession_details", "Possession"), ("ownership_shares", "Shares"), ("land_use_refs", "Land use"), ("permission_refs", "Permissions")):
                    for item in f.get(key) or []:
                        any_mention = True
                        st.markdown(f"**{label}** (p.{item['page']}): {item['value']}")
                if not any_mention:
                    st.caption("None found.")
            with st.expander("Text read from each page"):
                for page in doc.pages:
                    how = "PDF text" if page.method == "text-layer" else f"OCR ({page.method}), confidence {page.ocr_confidence}%"
                    st.markdown(f"**Page {page.number}**, {how}")
                    st.text(page.text[:4000])
            st.download_button("Download details as JSON", json.dumps(doc.to_dict(), ensure_ascii=False, indent=2, default=str), f"{doc.name}.json", "application/json", key=f"json-{doc.name}")


def ownership() -> None:
    theme.intro("Ownership Details", "Names as the documents state them, oldest first. This is not verified ownership, as only a proper title search can establish that.")
    if _needs_documents():
        return
    documents = [d for d in st.session_state.documents if d.status in ("ok", "partial")]
    rows = []
    from core.document_comparator import _doc_date  # local import keeps this page's dependency obvious

    for doc in sorted(documents, key=lambda d: _doc_date(d) or datetime.date.max):
        date = _doc_date(doc)
        f = doc.fields
        entries = []
        for key, label in (("sellers", "From"), ("buyers", "To"), ("owners", "Owner named"), ("landlord", "Landlord"), ("tenant", "Tenant"), ("poa_principal", "Principal"), ("poa_attorney", "Attorney")):
            names = f.get(key) or []
            if names:
                entries.append((label, ", ".join(f"{n['value']} (p.{n['page']})" for n in names)))
        rows.append((date, doc, entries))
    for date, doc, entries in rows:
        st.markdown(f'<div class="card"><h4>{theme.e(date or "Date not found")} · {theme.e(doc.doc_type_label)}</h4><p style="font-size:.8rem">{theme.e(doc.name)}</p>{theme.facts(entries) if entries else "<p>No names found.</p>"}</div>', unsafe_allow_html=True)
    chain = [c for c in st.session_state.result["comparisons"] if c.check == "ownership_chain"]
    if chain:
        st.markdown("### Chain of ownership")
        for c in chain:
            label, cls = STATUS_PILL[c.status]
            st.markdown(f'<div class="card"><p>{theme.pill(label, cls)} {theme.e(c.summary)}</p></div>', unsafe_allow_html=True)
    st.markdown('<div class="notice">Mutation is not conclusive proof of title. Property tax receipts do not conclusively establish title. A registered document does not automatically establish a perfect title.</div>', unsafe_allow_html=True)
    previous = [(d, p) for d in documents for p in d.fields.get("previous_owners") or []]
    if previous:
        st.markdown("### Earlier owners mentioned")
        for doc, person in previous:
            st.markdown(f"- {person['value']} ({doc.name}, p.{person['page']})")


def compare() -> None:
    theme.intro("Compare Documents", "Python rules compare each detail across your documents. Nothing here is guessed by an AI model.")
    if _needs_documents():
        return
    comparisons = st.session_state.result["comparisons"]
    grouped: dict[str, list] = {}
    for c in comparisons:
        grouped.setdefault(c.check, []).append(c)
    for check, items in grouped.items():
        worst = next((s for s in ("mismatch", "variation", "missing", "not_comparable", "match") if any(i.status == s for i in items)), "match")
        label, cls = STATUS_PILL[worst]
        st.markdown(f"### {CHECK_LABELS.get(check, check)} &nbsp; {theme.pill(label, cls)}", unsafe_allow_html=True)
        for item in items:
            label, cls = STATUS_PILL[item.status]
            sources = " · ".join(f"{d['document']}" + (f", p.{d['page']}" if d.get("page") else "") for d in item.documents[:3])
            st.markdown(f'<div class="card"><p>{theme.e(item.summary)}</p>' + (f'<p style="font-size:.78rem;color:var(--muted);margin-top:4px">{theme.e(sources)}</p>' if sources else "") + "</div>", unsafe_allow_html=True)


def risks() -> None:
    theme.intro("Risk Analysis", "Each item says why it was raised, where it was seen, and how to verify it. A missing document here only means it was not uploaded.")
    if _needs_documents():
        return
    findings = st.session_state.result["findings"]
    counts = {s: sum(f.severity == s for f in findings) for s in (HIGH, WARNING, INFO)}
    cols = st.columns(3)
    cols[0].markdown(theme.metric(counts[HIGH], "High Priority: resolve before paying", "var(--high)"), unsafe_allow_html=True)
    cols[1].markdown(theme.metric(counts[WARNING], "Warnings: check these", "var(--warn)"), unsafe_allow_html=True)
    cols[2].markdown(theme.metric(counts[INFO], "Information: good to know", "var(--info)"), unsafe_allow_html=True)
    st.write("")
    selected = st.multiselect("Show", [HIGH, WARNING, INFO], default=[HIGH, WARNING, INFO])
    shown = [f for f in findings if f.severity in selected]
    if not findings:
        theme.empty("No rule-based findings in what could be read. This does not mean the property is free of problems.")
    for finding in shown:
        st.markdown(theme.finding_card(finding), unsafe_allow_html=True)
    if findings:
        st.markdown('<div class="notice">No findings in a category does not prove there is no problem. BhoomiCheck does not see court, bank or government records.</div>', unsafe_allow_html=True)


def checklist() -> None:
    theme.intro("Due-Diligence Checklist", "Tick items as you complete them. 'Seen in uploads' means a matching document was uploaded, not that its contents are verified.")
    documents = st.session_state.documents
    suggested = st.session_state.result["checklist_contexts"] if st.session_state.result else []
    all_contexts = list(CHECKLISTS)
    default = suggested[0] if suggested else "Property purchase"
    context = st.selectbox("Checklist for", all_contexts, index=all_contexts.index(default))
    if suggested:
        st.caption("Suggested from your documents: " + ", ".join(suggested))
    cls_for = {"Document seen in uploads": "ok", "Not seen in uploads": "warning", "Check in person or with an office": "neutral"}
    for index, item in enumerate(generate_checklist(context, documents)):
        col1, col2 = st.columns([0.05, 0.95])
        col1.checkbox("Done", key=f"check-{context}-{index}", label_visibility="collapsed")
        col2.markdown(f'<div class="card"><h4>{theme.e(item["task"])}</h4><p>{theme.e(item["why"])}</p><p style="margin-top:5px;font-size:.8rem">{theme.pill(item["status"], cls_for[item["status"]])} <b>Where:</b> {theme.e(item["where"])}</p></div>', unsafe_allow_html=True)


def assistant() -> None:
    theme.intro("Legal Assistant", "Ask in English, Hindi or Hinglish about your documents or Indian property law. Answers cite the document page or legal source.")
    model = llm_status()
    if model["llm_available"]:
        st.caption(f"Language model: {model['model']}. Replies must pass citation checks, or quoted sources are shown instead.")
    else:
        st.markdown('<div class="notice"><b>No language model is connected.</b> Answers come from extracted facts, fixed explanations and direct quotes from legal sources. To get written explanations, connect a model as described in the README.</div>', unsafe_allow_html=True)
    language = st.radio("Reply in", ["Same as my question", "English", "हिंदी", "Hinglish"], horizontal=True)
    forced = {"English": "en", "हिंदी": "hi", "Hinglish": "hinglish"}.get(language)
    st.caption("Try: " + " · ".join(EXAMPLES))
    for message in st.session_state.chat:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])
            if message.get("citations"):
                _sources_expander(message["citations"])
    question = st.chat_input("Ask a question")
    if question:
        st.session_state.chat.append({"role": "user", "content": question})
        result = st.session_state.result
        with st.spinner("Checking your documents and legal sources"):
            response = answer(question, st.session_state.documents, result["findings"] if result else [], forced)
        st.session_state.chat.append({"role": "assistant", "content": response["answer"], "citations": response["citations"]})
        st.rerun()


def _sources_expander(citations: list[dict]) -> None:
    with st.expander("Sources"):
        for c in citations:
            where = f", p.{c['page']}" if c["page"] else ""
            link = f"[{c['title']}, {c['provision']}{where}]({c['url']})" if c["url"] else f"{c['title']}, {c['provision']}{where}"
            st.markdown(f"**{c['tag']}** {link}  \n{c['heading']}  \nStatus: {c['legal_status']}")


def report() -> None:
    theme.intro("Property Report", "Download everything in one report to share with your lawyer or family.")
    if _needs_documents():
        return
    result = st.session_state.result
    pdf = build_pdf(result)
    docx = build_docx(result)
    col1, col2, col3 = st.columns(3)
    col1.download_button("Download PDF report", pdf, "BhoomiCheck_Report.pdf", "application/pdf", width="stretch")
    col2.download_button("Download Word report", docx, "BhoomiCheck_Report.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", width="stretch")
    col3.download_button("Download data (JSON)", json.dumps(serialisable(result), ensure_ascii=False, indent=2, default=str), "BhoomiCheck_Data.json", "application/json", width="stretch")
    st.markdown("### Report preview")
    preview = pymupdf.open(stream=pdf, filetype="pdf")
    st.caption(f"{len(preview)} page(s)")
    st.image(preview[0].get_pixmap(dpi=90).tobytes("png"), width="stretch")


def about() -> None:
    theme.intro("About and Disclaimer", "What BhoomiCheck does, how it works, and its limits.")
    st.markdown("### What it cannot tell you")
    for note in SAFETY_NOTES:
        st.markdown(f"- {note}")
    st.markdown("- BhoomiCheck never says a property is 100% safe, has guaranteed clear title, has certified ownership, or has no litigation.")
    st.markdown("- For inheritance, ownership conflicts, litigation, suspected forgery and serious title questions, please go to a qualified lawyer.")
    st.markdown("### How it works")
    model = llm_status()
    retriever = get_retriever()
    sources = json.loads(config.SOURCES_JSON.read_text())["sources"] if config.SOURCES_JSON.exists() else []
    available = [s for s in sources if s["availability"] == "available"]
    st.markdown(theme.facts([
        ("Language model", model["model"]), ("Legal search", retriever.mode), ("Legal sources indexed", f"{len(available)} of {len(sources)} attempted"), ("Searchable passages", f"{len(retriever.chunks):,}"),
        ("Comparison and risk rules", "Python rules, not AI"),
        ("Legal knowledge", "Retrieved from the indexed documents. No model was trained on this legal material."),
    ]), unsafe_allow_html=True)
    st.markdown("### Legal sources")
    for s in sources:
        if s["availability"] == "available":
            st.markdown(f"- [{s['title']}]({s['url']}) · {s['jurisdiction']} · {s['status']}")
    missing = [s for s in sources if s["availability"] != "available"]
    if missing:
        with st.expander(f"{len(missing)} source(s) could not be collected"):
            for s in missing:
                st.markdown(f"- {s['title']}")
    st.markdown("### Privacy")
    st.markdown("Uploads are held in memory for your browser session only. If a cloud language model is connected, your question and extracted facts are sent to that provider.")
