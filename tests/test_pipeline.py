"""Pytest suite. Development scenarios run here. The holdout set runs only in evaluation/run_evals.py."""
import json
import unicodedata

import pytest

import config
from core.assistant import answer, detect_language
from core.checklist_generator import CHECKLISTS, generate
from core.citation_validator import forbidden_claims, validate_answer, validate_citation
from core.document_comparator import compare_names, romanise
from core.document_processor import process_bytes
from core.information_extractor import format_inr, parse_date
from core.legal_retrieval import get_retriever
from core.pipeline import SAFETY_NOTES, analyse, load_path
from core.report_generator import build_docx, build_pdf
from core.risk_detector import citations_for
from evaluator import score_assistant, score_document, score_scenario

TESTS = json.loads(config.TEST_CASES_JSON.read_text())
_cache = {}


def doc(name):
    if name not in _cache:
        _cache[name] = load_path(config.SYNTHETIC_DIR / name)
    return _cache[name]


DEV_SCENARIOS = [s for s in TESTS["scenarios"] if not s.get("holdout") and not s.get("fresh")]


@pytest.mark.parametrize("scenario", DEV_SCENARIOS, ids=[s["id"] for s in DEV_SCENARIOS])
def test_scenario(scenario):
    result = analyse([doc(n) for n in scenario["documents"]], scenario.get("purpose", "purchase"))
    score = score_scenario(scenario, result)
    assert score["passed"], score


DEV_DOCS = {k: v for k, v in TESTS["documents"].items() if not k.startswith(("holdout_", "fresh_"))}


@pytest.mark.parametrize("name", list(DEV_DOCS))
def test_document_classification_and_status(name):
    gold, d = DEV_DOCS[name], doc(name)
    if "expect_status" in gold:
        assert d.status == gold["expect_status"]
    else:
        assert d.doc_type == gold["doc_type"]


def test_field_extraction_on_the_base_deed():
    checks = score_document(DEV_DOCS["sale_deed_2023.pdf"], doc("sale_deed_2023.pdf"))["checks"]
    assert [c for c in checks if not c["ok"]] == []


def test_recited_earlier_deed_is_not_this_deeds_number():
    assert doc("sale_deed_2023.pdf").fields["registration"]["document_no"]["value"] == "2217/2023"


def test_every_finding_has_reason_source_and_verification():
    result = analyse([doc("sale_deed_2023.pdf"), doc("ec_mortgage.pdf"), doc("mutation_owner_mismatch.pdf")])
    assert result["findings"]
    for f in result["findings"]:
        assert f.reason and f.recommended_verification and f.sources


def test_pages_are_referenced():
    result = analyse([doc("sale_deed_2023.pdf"), doc("ec_mortgage.pdf")])
    mortgage = next(f for f in result["findings"] if f.code == "MORTGAGE_NO_RELEASE")
    assert any(s.page == 1 and s.document == "ec_mortgage.pdf" for s in mortgage.sources)


def test_missing_document_wording_does_not_claim_absence():
    result = analyse([doc("sale_deed_2023.pdf")])
    missing = [f for f in result["findings"] if f.code == "MISSING_DOCUMENT"]
    assert missing and all("does not mean it does not exist" in f.reason for f in missing)


def test_unreadable_document_produces_no_facts():
    d = doc("unreadable_noise.png")
    assert d.status == "unreadable" and "sellers" not in d.fields


def test_unsupported_file_type_is_refused():
    assert process_bytes(b"x", "notes.docx").status == "error"


def test_duplicates_of_one_transaction_are_not_a_chain_break():
    result = analyse([doc("sale_deed_2023.pdf"), doc("sale_deed_boundary_mismatch.pdf")])
    assert "CHAIN_BREAK" not in [f.code for f in result["findings"]]


@pytest.mark.parametrize("a,b,expected", [
    ("Ramesh Chandra Verma", "RAMESH CHANDRA VERMA", "same"), ("Smt. Anita Sharma", "Anita Sharma", "same"),
    ("श्रीमती अनीता शर्मा", "Anita Sharma", "same"), ("R. C. Verma", "Ramesh Chandra Verma", "variation"),
    ("Anita Sharma", "Anita Devi Sharma", "variation"), ("Rakesh Verma", "Ramesh Chandra Verma", "different"),
    ("Anita Sharma", "Anita Verma", "different"), ("Suresh Prasad", "Mahesh Prasad", "different"),
])
def test_name_comparison(a, b, expected):
    assert compare_names(a, b)["result"] == expected


def test_romanise():
    assert romanise("अनीता शर्मा").startswith("anita")


@pytest.mark.parametrize("raw,iso", [("12/03/2023", "2023-03-12"), ("12-03-2023", "2023-03-12"), ("12th day of March, 2023", "2023-03-12"), ("March 12, 2023", "2023-03-12"), ("7 Jun 2022", "2022-06-07")])
def test_date_parsing(raw, iso):
    assert parse_date(raw).isoformat() == iso


def test_impossible_date_is_rejected():
    assert parse_date("31/02/2023") is None


def test_indian_number_format():
    assert format_inr(4500000) == "Rs. 45,00,000"


@pytest.mark.parametrize("text,lang", [("Who is the seller?", "en"), ("Is deed mein seller kaun hai?", "hinglish"), ("विक्रेता कौन है?", "hi")])
def test_language_detection(text, lang):
    assert detect_language(text) == lang


ASSISTANT = TESTS["assistant_tests"]


@pytest.mark.parametrize("test", ASSISTANT, ids=[t["id"] for t in ASSISTANT])
def test_assistant(test):
    docs = [doc(n) for n in test["documents"]]
    findings = analyse(docs)["findings"] if docs else []
    response = answer(test["question"], docs, findings, test["language"])
    score = score_assistant(test, response)
    assert score["passed"], (score, response["answer"])


def test_index_is_populated_and_records_failures_honestly():
    sources = json.loads(config.SOURCES_JSON.read_text())["sources"]
    available = [s for s in sources if s["availability"] == "available"]
    assert len(available) >= 15
    assert get_retriever().chunks
    for s in available:
        assert (config.KB_DOCS_DIR / s["local_file"]).exists() and s["url"]
    for s in sources:
        if s["availability"] != "available":
            assert not (config.KB_DOCS_DIR / f"{s['id']}.pdf").exists()


def test_every_chunk_keeps_its_source_metadata():
    for c in get_retriever().chunks:
        assert c["title"] and c["url"] and c["jurisdiction"] and c["provision"]


@pytest.mark.parametrize("key", ["owner", "chain", "mortgage", "poa", "litigation", "registration", "reg_time", "lease", "gift", "rera", "stamp", "agreement", "inheritance"])
def test_rule_citations_exist_in_the_index(key):
    citations = citations_for(key)
    assert citations
    for citation in citations:
        assert validate_citation(citation)[0]


@pytest.mark.parametrize("source,section,phrase", [
    ("tpa_1882", "54", "transfer of ownership in exchange for a price"), ("tpa_1882", "58", "transfer of an interest in specific immoveable property"),
    ("tpa_1882", "107", "registered instrument"), ("tpa_1882", "52", "pendency"), ("registration_1908", "23", "four months"),
    ("contract_1872", "201", "dying"), ("rera_2016", "13", "ten per cent"),
])
def test_cited_provisions_say_what_the_rules_rely_on(source, section, phrase):
    text = " ".join(c["text"] for c in get_retriever().chunks if c["source_id"] == source and c["section"] == section).lower()
    assert phrase in " ".join(text.split())


def test_draft_bill_is_excluded_unless_asked_for():
    retriever = get_retriever()
    assert all(c["source_id"] != "draft_registration_bill_2025" for c in retriever.search("registration of documents", top_k=10))
    assert any(c["source_id"] == "draft_registration_bill_2025" for c in retriever.search("draft Registration Bill 2025 digital registration", top_k=10))


def test_mutation_judgment_quote_is_in_the_index():
    text = " ".join(c["text"] for c in get_retriever().chunks if c["source_id"] == "sc_2025_insc_1238")
    assert "mutation entries do not confer title" in " ".join(text.split())


@pytest.mark.parametrize("claim", ["This property is 100% safe.", "This has a clear title certified by us.", "There is no litigation on this property.", "Yeh property bilkul safe hai.", "A mutation entry proves ownership."])
def test_forbidden_claims_are_detected(claim):
    assert forbidden_claims(claim)


@pytest.mark.parametrize("claim", ["I cannot say this property is 100% safe.", "Mutation does not prove ownership.", "No one can confirm there is no litigation."])
def test_negated_cautions_are_allowed(claim):
    assert not forbidden_claims(claim)


def test_the_real_bad_model_answer_is_now_rejected():
    """Regression for DEVELOPMENT_LOG.md E7: the actual reply from the local model."""
    bad = "Registry करना जरूरी नहीं, का� urgently registration करना नहीं है।"
    assert not validate_answer(bad, get_retriever().search("Registry karana zaroori hai kya?", top_k=4), "hinglish")["ok"]


def test_answer_without_a_citation_is_rejected():
    assert validate_answer("Yes, a sale needs registration.", get_retriever().search("sale registration", top_k=3), "en")["missing_citation_tag"]


def test_invented_section_is_rejected():
    assert validate_answer("Section 999 says so [L1].", get_retriever().search("sale registration", top_k=3), "en")["unsupported_sections"]


def test_invented_tag_is_rejected():
    assert validate_answer("A sale needs registration [L9].", get_retriever().search("sale registration", top_k=3), "en")["unknown_tags"]


@pytest.mark.parametrize("context", list(CHECKLISTS))
def test_each_checklist_generates(context):
    items = generate(context, [])
    assert items and all(i["task"] and i["why"] and i["where"] for i in items)


def test_checklist_marks_uploaded_documents_as_seen_not_verified():
    items = generate("Property purchase", [doc("ec_clean.pdf")])
    ec = next(i for i in items if "Encumbrance" in i["task"])
    assert ec["status"] == "Document seen in uploads" and "verified" not in ec["status"].lower()


def test_reports_contain_required_sections_and_safety_notes():
    import io

    import pymupdf
    from docx import Document

    result = analyse([doc("sale_deed_2023.pdf"), doc("ec_mortgage.pdf"), doc("hindi_khatauni_scan.pdf")])
    text = " ".join(p.get_text() for p in pymupdf.open(stream=build_pdf(result), filetype="pdf"))
    text = unicodedata.normalize("NFKC", " ".join(text.split()))  # PDF extraction returns ligatures
    docx_text = " ".join(p.text for p in Document(io.BytesIO(build_docx(result))).paragraphs)
    for heading in ("Property overview", "Extracted details", "Comparison findings", "Missing information", "Potential risks", "Due-diligence checklist", "Recommended next steps", "Official source references", "Matters requiring lawyer verification"):
        assert heading in text and heading in docx_text
    assert SAFETY_NOTES[1] in text and SAFETY_NOTES[1] in docx_text
