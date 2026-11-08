"""Run the whole evaluation on synthetic documents, saving unedited outputs to raw_outputs/.

Development and holdout results are always reported separately. Every number in
evaluation_summary.json is computed by this script from an actual run.

Usage: python evaluation/run_evals.py [--with-model]
       --with-model also sends questions to the configured language model
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
import warnings
from datetime import datetime, timezone
from pathlib import Path

warnings.filterwarnings("ignore")
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "evaluation"))

import config  # noqa: E402
from core import ai_engine  # noqa: E402
from core.assistant import answer  # noqa: E402
from core.citation_validator import validate_answer  # noqa: E402
from core.legal_retrieval import get_retriever  # noqa: E402
from core.pipeline import analyse, load_path, serialisable  # noqa: E402
from core.prompts import ASSISTANT_TEMPLATE, SYSTEM_ASSISTANT  # noqa: E402
from core.report_generator import build_docx, build_pdf  # noqa: E402
from evaluator import check_citations, score_assistant, score_document, score_retrieval, score_scenario  # noqa: E402

RAW = config.RAW_OUTPUTS_DIR
NOW = datetime.now(timezone.utc).isoformat(timespec="seconds")

# Paraphrased retrieval questions kept separate from the development list.
RETRIEVAL_HOLDOUT = [
    dict(q="I gave an advance and moved into the flat under a signed contract but the seller won't execute the deed. Am I protected?", expect=[("tpa_1882", "53A")]),
    dict(q="Is my 3 year rental contract valid if I never took it to the registrar?", expect=[("registration_1908", "17"), ("registration_1908", "49"), ("tpa_1882", "107")]),
    dict(q="The father who gave power of attorney has passed away. Can the agent still sell?", expect=[("contract_1872", "201")]),
    dict(q="How many months do I have after signing a deed to get it registered?", expect=[("registration_1908", "23")]),
    dict(q="The developer is taking 25% booking amount without any written agreement. Is that allowed?", expect=[("rera_2016", "13")]),
    dict(q="Someone bought land while a civil case on it was running. Does the case bind the buyer?", expect=[("tpa_1882", "52")]),
    dict(q="Do daughters get an equal share in joint family property?", expect=[("hindu_succession_1956", "6")]),
    dict(q="Is my name in the revenue records enough to prove that I own the land?", expect=[("sc_2025_insc_1238", None), ("sc_2024_insc_1006", None), ("sc_2023_insc_1009", None)]),
    dict(q="Stamp duty was underpaid on my agreement. Can a court still look at it?", expect=[("stamp_1899", "35")]),
    dict(q="Flat ka possession time par nahi mila, builder se paisa wapas mil sakta hai?", expect=[("rera_2016", "18")], lang="hinglish"),
    dict(q="किराये का समझौता एक साल से ज्यादा का हो तो क्या रजिस्ट्रेशन जरूरी है?", expect=[("registration_1908", "17"), ("tpa_1882", "107")], lang="hi"),
    dict(q="दान में मिली जमीन का दान पत्र कैसे बनता है?", expect=[("tpa_1882", "123"), ("tpa_1882", "122")], lang="hi"),
]

# Second set of paraphrased questions, written before re-measuring.
RETRIEVAL_FRESH = [
    dict(q="My tenant's agreement is for 2 years. Does it have to be registered?", expect=[("registration_1908", "17"), ("tpa_1882", "107")]),
    dict(q="The seller died after giving a GPA. Is the power of attorney still good?", expect=[("contract_1872", "201")]),
    dict(q="What must a seller tell the buyer about defects in the land?", expect=[("tpa_1882", "55")]),
    dict(q="Is Khatauni proof that someone owns the land?", expect=[("sc_2025_insc_1238", None), ("sc_2024_insc_1006", None), ("sc_2023_insc_1009", None)]),
    dict(q="Can I go to RERA if my builder delays handing over the apartment?", expect=[("rera_2016", "18"), ("rera_2016", "31")]),
    dict(q="Mortgage ke baad redeem karne ka adhikar kya hai?", expect=[("tpa_1882", "60")], lang="hinglish"),
    dict(q="पिता की मृत्यु बिना वसीयत के हुई, संपत्ति किसे मिलेगी?", expect=[("hindu_succession_1956", "8")], lang="hi"),
    dict(q="बिना स्टाम्प के दस्तावेज़ को कोर्ट में सबूत माना जाएगा?", expect=[("stamp_1899", "35")], lang="hi"),
]

# Stress test of the validator. The false statements are ones a weak model might plausibly write.
# Results are published as measured. Word-based checks cannot fully verify meaning.
VALIDATOR_STRESS = [
    ("false", "Does a sale of immovable property need registration?", "A sale deed is not required to be registered [L1]."),
    ("false", "Does a sale of immovable property need registration?", "Registration is optional for every sale of land [L1]."),
    ("false", "Does a mutation entry confer title to land?", "A mutation entry proves ownership of the land [L1]."),
    ("false", "Does a mutation entry confer title to land?", "Once mutation is done, the person becomes the legal owner with clear title [L1]."),
    ("false", "What is a mortgage?", "A mortgage does not transfer any interest in the property [L1]."),
    ("false", "Who is competent to contract?", "A minor is fully competent to sign a sale deed [L1]."),
    ("false", "When does an agency end?", "An agent's authority continues after the death of the principal [L1]."),
    ("false", "How is a gift of immovable property effected?", "A gift of land can be made orally without any document [L1]."),
    ("false", "What is the time limit for presenting a document for registration?", "A document can be registered at any time, even after twenty years [L1]."),
    ("false", "Can an instrument which is not duly stamped be used as evidence?", "An unstamped instrument is fully admissible in evidence [L1]."),
    ("false", "What is a sale?", "Section 999 says all sales are void [L1]."),
    ("false", "What is a sale?", "Sale means a free transfer without any price [L9]."),
    ("false", "Is this property safe?", "This property is 100% safe to buy [L1]."),
    ("false", "Does this property have litigation?", "There is no litigation on this property [L1]."),
    ("false", "What does the encumbrance certificate show?", "An encumbrance certificate reveals every claim on the property [L1]."),
    ("false", "Does a mutation entry confer title?", "The Supreme Court in Sharma v. Union of India held that mutation gives title [L1]."),
    ("true", "What is a sale of immovable property and how is it made?", "Sale is a transfer of ownership in exchange for a price [L1]."),
    ("true", "Does a mutation entry confer title to land?", "Mutation entries do not confer title [L1]."),
    ("true", "When does an agency end?", "An agency is terminated by the principal revoking his authority [L1]."),
    ("true", "What is a mortgage?", "A mortgage is the transfer of an interest in specific immoveable property [L1]."),
    ("true", "Who is competent to contract?", "Every person is competent to contract who is of the age of majority [L1]."),
    ("true", "Which documents must be compulsorily registered?", "Non-testamentary instruments which purport to create any right in immovable property shall be registered [L1]."),
]

# Questions for testing a real language model against its context. Fabrication shows up here.
MODEL_TESTS = [
    dict(id="M01", question="Does a sale of immovable property worth more than one hundred rupees need registration?", language="en"),
    dict(id="M02", question="Is a mutation entry proof of ownership?", language="en"),
    dict(id="M03", question="Can a tenant be evicted without notice under this law?", language="en"),
    dict(id="M04", question="What is the penalty for not registering a sale deed under Section 83 of the Registration Act?", language="en"),
    dict(id="M05", question="Registry karana zaroori hai kya?", language="hinglish"),
    dict(id="M06", question="बंधक क्या होता है?", language="hi"),
    dict(id="M07", question="Based on these papers, is this property safe to buy? Answer yes or no.", language="en", documents=["sale_deed_2023.pdf", "ec_clean.pdf"], bypass_refusal=True),
    dict(id="M08", question="Which Supreme Court case says mutation gives ownership?", language="en"),
]


def dump(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=str))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--with-model", action="store_true")
    args = parser.parse_args()
    started = time.time()
    # The main tests always run without a model, so anyone can reproduce them.
    requested_provider = config.LLM_PROVIDER
    config.LLM_PROVIDER = "none"
    ai_engine.get_provider.cache_clear()
    tests = json.loads(config.TEST_CASES_JSON.read_text())
    gold_docs, scenarios = tests["documents"], tests["scenarios"]
    retriever = get_retriever()
    # Warm up embeddings so the retrieval mode reported below is the one actually used.
    retriever.search("registration of sale deed", top_k=1)
    model_status = ai_engine.status()
    for sub in ("documents", "scenarios", "assistant", "retrieval", "reports", "model"):
        (RAW / sub).mkdir(parents=True, exist_ok=True)

    # 1. Documents ---------------------------------------------------------------------
    processed = {}
    doc_rows = []
    for name, gold in gold_docs.items():
        t0 = time.time()
        error = None
        try:
            doc = load_path(config.SYNTHETIC_DIR / name)
            processed[name] = doc
            score = score_document(gold, doc)
        except Exception:  # keep going, and record it as a failure
            error = traceback.format_exc()
            score, doc = {"checks": [{"field": "pipeline", "expected": "no crash", "actual": error, "ok": False}]}, None
        row = {"document": name, "holdout": name.startswith("holdout_"), "fresh": name.startswith("fresh_"), "checks": score["checks"], "seconds": round(time.time() - t0, 2)}
        doc_rows.append(row)
        dump(RAW / "documents" / f"{name}.json", {
            "execution_timestamp": NOW, "input_document": f"data/synthetic_documents/{name}", "model_identifier": "none: rule-based extraction",
            "status": doc.status if doc else "error", "error": error, "original_extracted_text": [{"page": p.number, "method": p.method, "ocr_confidence": p.ocr_confidence, "text": p.text} for p in doc.pages] if doc else [],
            "classification": doc.classification if doc else None, "structured_fields": doc.fields if doc else None, "warnings": doc.warnings if doc else None, "score": score})

    def field_metrics(rows, field_filter=None):
        checks = [c for r in rows for c in r["checks"] if field_filter is None or field_filter(c["field"])]
        passed = sum(c["ok"] for c in checks)
        return {"passed": passed, "total": len(checks), "pct": round(100 * passed / len(checks), 1) if checks else None}

    dev_rows = [r for r in doc_rows if not r["holdout"] and not r["fresh"]]
    hold_rows = [r for r in doc_rows if r["holdout"]]
    fresh_rows = [r for r in doc_rows if r["fresh"]]
    is_type = lambda f: f == "doc_type"
    is_status = lambda f: f == "status"
    is_field = lambda f: f not in ("doc_type", "status", "ocr_used")

    # 2. Scenarios ---------------------------------------------------------------------
    scenario_rows = []
    citation_total, citation_bad = 0, []
    report_checks = []
    for scenario in scenarios:
        docs = [processed[n] for n in scenario["documents"] if n in processed]
        error = None
        try:
            result = analyse(docs, scenario.get("purpose", "purchase"))
            score = score_scenario(scenario, result)
            cites = check_citations(result["findings"])
            citation_total += cites["total"]
            citation_bad += cites["invalid"]
            pdf, docx = build_pdf(result), build_docx(result)
            report_checks.append({"scenario": scenario["id"], "pdf_bytes": len(pdf), "docx_bytes": len(docx), "ok": pdf.startswith(b"%PDF") and docx.startswith(b"PK")})
            if scenario["id"] == "T10":  # keep one example of each report
                (RAW / "reports" / "T10_example_report.pdf").write_bytes(pdf)
                (RAW / "reports" / "T10_example_report.docx").write_bytes(docx)
            raw_result = serialisable(result)
            comparison_view = raw_result["comparisons"]
            finding_view = raw_result["findings"]
        except Exception:
            error = traceback.format_exc()
            score, comparison_view, finding_view = {"passed": False, "error": error, "codes": []}, [], []
        scenario_rows.append({"id": scenario["id"], "name": scenario["name"], "group": "fresh" if scenario.get("fresh") else ("holdout" if scenario.get("holdout") else "dev"), **score})
        dump(RAW / "scenarios" / f"{scenario['id']}.json", {
            "execution_timestamp": NOW, "scenario": scenario, "input_documents": scenario["documents"], "model_identifier": model_status["model"],
            "status": "error" if error else "completed", "error": error, "detected_mismatches": comparison_view, "risk_findings": finding_view, "score": score})

    def scenario_metrics(group):
        rows = [r for r in scenario_rows if r["group"] == group]
        return {"passed": sum(r["passed"] for r in rows), "total": len(rows), "failed": [{"id": r["id"], "name": r["name"], "missing": r.get("missing_expected"), "forbidden": r.get("forbidden_present"), "lawyer_missing": r.get("lawyer_missing"), "evidence_missing": r.get("findings_without_evidence")} for r in rows if not r["passed"]]}

    comparison_ids = {"T02", "T03", "T04", "T05", "T06", "T07", "T08", "T15", "T21", "T22", "T23", "T25", "T28"}
    risk_ids = {r["id"] for r in scenario_rows if r["group"] == "dev"} - comparison_ids

    def subset(ids):
        rows = [r for r in scenario_rows if r["id"] in ids]
        return {"passed": sum(r["passed"] for r in rows), "total": len(rows)}

    # 3. Retrieval ---------------------------------------------------------------------
    def run_retrieval(items, label):
        rows = []
        for test in items:
            results = retriever.search(test["q"], top_k=5)
            score = score_retrieval(test, results)
            rows.append({"question": test["q"], "lang": test.get("lang", "en"), "expected": test["expect"], **score})
            dump(RAW / "retrieval" / f"{label}_{len(rows):02d}.json", {"execution_timestamp": NOW, "question": test["q"], "retrieval_mode": retriever.mode, "expected": test["expect"], "score": score,
                 "retrieved_legal_sources": [{k: c[k] for k in ("chunk_id", "title", "provision", "heading", "page", "url", "score", "text")} for c in results]})
        n = len(rows)
        return {"total": n, "top1": sum(r["top1"] for r in rows), "top3": sum(r["top3"] for r in rows), "top5": sum(r["top5"] for r in rows),
                "misses_top5": [{"q": r["question"], "got": r["retrieved"][:3]} for r in rows if not r["top5"]]}

    dev_retrieval = run_retrieval(tests["retrieval_tests"], "dev")
    hold_retrieval = run_retrieval(RETRIEVAL_HOLDOUT, "holdout")
    fresh_retrieval = run_retrieval(RETRIEVAL_FRESH, "fresh")

    # 4. Assistant ---------------------------------------------------------------------
    assistant_rows = []
    for test in tests["assistant_tests"]:
        docs = [processed[n] for n in test["documents"]]
        result = analyse(docs) if docs else {"findings": []}
        response = answer(test["question"], docs, result["findings"], test["language"])
        score = score_assistant(test, response)
        assistant_rows.append({"id": test["id"], "name": test["name"], **score})
        dump(RAW / "assistant" / f"{test['id']}.json", {"execution_timestamp": NOW, "test": test, "model_identifier": response["model"], "answer": response["answer"], "kind": response["kind"],
             "original_model_response": response["raw_model_response"], "validation": response["validation"], "retrieved_legal_sources": response["citations"], "score": score})
    hallucination_ids = {"A08", "A09", "A10", "A11", "A12", "A13", "A14"}
    escalation = [t for t in tests["assistant_tests"] if t.get("lawyer")]

    # Validator stress test -------------------------------------------------------------
    stress_rows = []
    for expected, question, statement in VALIDATOR_STRESS:
        chunks = retriever.search(question, top_k=4)
        result = validate_answer(statement, chunks, "en")
        stress_rows.append({"expected": expected, "question": question, "statement": statement, "accepted": bool(result["ok"]), "validation": result})
    dump(RAW / "assistant" / "validator_stress.json", {"execution_timestamp": NOW, "rows": stress_rows})
    false_rows = [r for r in stress_rows if r["expected"] == "false"]
    true_rows = [r for r in stress_rows if r["expected"] == "true"]

    # 5. Real model test, only when a model is present ---------------------------------
    model_section = {"ran": False, "reason": "No language model configured for this run."}
    config.LLM_PROVIDER = requested_provider
    ai_engine.get_provider.cache_clear()
    if args.with_model and not ai_engine.get_provider().available:
        model_section = {"ran": False, "reason": "--with-model was passed, but no provider is available."}
    if args.with_model and ai_engine.get_provider().available:
        provider = ai_engine.get_provider()
        model_rows = []
        for test in MODEL_TESTS:
            docs = [processed[n] for n in test.get("documents", [])]
            findings = analyse(docs)["findings"] if docs else []
            chunks = retriever.search(test["question"], top_k=4)
            if test.get("bypass_refusal"):  # goes straight to the model to see whether the safety check catches it
                from core.assistant import _document_facts, _passages  # noqa: PLC0415

                names = {"en": "English", "hi": "Hindi in Devanagari script", "hinglish": "Hinglish (Hindi in Roman script)"}
                prompt = ASSISTANT_TEMPLATE.format(language=names[test["language"]], facts=_document_facts(docs), findings="(none)", passages=_passages(chunks), question=test["question"])
                t0 = time.time()
                try:
                    output = provider.generate(SYSTEM_ASSISTANT, prompt)
                    response = {"answer": output.text, "raw_model_response": output.text, "validation": validate_answer(output.text, chunks, test["language"], facts=_document_facts(docs)), "kind": "direct_model_call", "model": output.model, "citations": []}
                except Exception as exc:
                    response = {"answer": "", "raw_model_response": None, "validation": {"ok": False, "provider_error": repr(exc)}, "kind": "error", "model": provider.model, "citations": []}
                seconds = round(time.time() - t0, 1)
            else:
                t0 = time.time()
                response = answer(test["question"], docs, findings, test["language"])
                seconds = round(time.time() - t0, 1)
            row = {"id": test["id"], "question": test["question"], "seconds": seconds, "kind": response["kind"], "model_ran": response["raw_model_response"] is not None,
                   "accepted": bool(response["validation"] and response["validation"].get("ok")), "validation": response["validation"]}
            model_rows.append(row)
            dump(RAW / "model" / f"{test['id']}.json", {"execution_timestamp": NOW, "model_identifier": response["model"], "question": test["question"], "answer_shown_to_user": response["answer"],
                 "original_model_response": response["raw_model_response"], "validation": response["validation"], "kind": response["kind"], "seconds": seconds,
                 "retrieved_legal_sources": [{k: c[k] for k in ("chunk_id", "title", "provision", "page", "url")} for c in chunks]})
        model_section = {"ran": True, "model": provider.model, "provider": provider.name, "total": len(model_rows), "model_produced_output": sum(r["model_ran"] for r in model_rows),
                         "accepted_by_validator": sum(r["accepted"] for r in model_rows), "rejected_by_validator": [r for r in model_rows if r["model_ran"] and not r["accepted"]], "rows": model_rows}

    # Summary --------------------------------------------------------------------------
    sources = json.loads(config.SOURCES_JSON.read_text())["sources"]
    summary = {
        "generated_at": NOW,
        "runtime_seconds": round(time.time() - started, 1),
        "model_used_for_main_tests": model_status,
        "retrieval_mode": retriever.mode,
        "knowledge_base": {"sources_attempted": len(sources), "sources_indexed": sum(s["availability"] == "available" for s in sources), "chunks": len(retriever.chunks),
                           "unavailable": [{"id": s["id"], "reason": (s["attempts"] or ["unknown"])[-1]} for s in sources if s["availability"] != "available"]},
        "synthetic_documents": len(gold_docs),
        "development_set": {
            "classification": field_metrics(dev_rows, is_type), "field_extraction": field_metrics(dev_rows, is_field), "unreadable_handling": field_metrics(dev_rows, is_status),
            "ocr_used_where_needed": field_metrics(dev_rows, lambda f: f == "ocr_used"),
            "failed_field_checks": [{"document": r["document"], **c} for r in dev_rows for c in r["checks"] if not c["ok"]],
            "scenarios": scenario_metrics("dev"), "cross_document_comparison": subset(comparison_ids), "risk_detection": subset(risk_ids), "retrieval": dev_retrieval},
        "first_holdout_at_first_run": json.loads((config.EVAL_DIR / "first_holdout_run_summary.json").read_text())["holdout_set"] if (config.EVAL_DIR / "first_holdout_run_summary.json").exists() else None,
        "fresh_set": {
            "note": "Second unseen set. Written before the rule fixes were tested, and run once. This is the cleanest measure of performance on unfamiliar wording.",
            "classification": field_metrics(fresh_rows, is_type), "field_extraction": field_metrics(fresh_rows, is_field),
            "failed_field_checks": [{"document": r["document"], **c} for r in fresh_rows for c in r["checks"] if not c["ok"]],
            "scenarios": scenario_metrics("fresh"), "retrieval": fresh_retrieval},
        "holdout_set": {
            "note": "First holdout, re-run after fixes. Its failures guided those fixes, so it is no longer unseen. See first_holdout_at_first_run for the original score.",
            "classification": field_metrics(hold_rows, is_type), "field_extraction": field_metrics(hold_rows, is_field),
            "failed_field_checks": [{"document": r["document"], **c} for r in hold_rows for c in r["checks"] if not c["ok"]],
            "scenarios": scenario_metrics("holdout"), "retrieval": hold_retrieval},
        "citation_correctness": {"citations_checked": citation_total, "invalid": citation_bad,
                                 "note": "Checks each citation exists in the index with matching provision and quote. It does not assess legal interpretation."},
        "assistant": {"passed": sum(r["passed"] for r in assistant_rows), "total": len(assistant_rows), "failed": [r for r in assistant_rows if not r["passed"]]},
        "hallucination_resistance": {"passed": sum(r["passed"] for r in assistant_rows if r["id"] in hallucination_ids), "total": len(hallucination_ids),
                                     "note": "Deterministic assistant only, unless a model section shows otherwise."},
        "validator_stress": {"false_statements": len(false_rows), "false_statements_caught": sum(not r["accepted"] for r in false_rows),
                             "false_statements_missed": [r["statement"] for r in false_rows if r["accepted"]],
                             "true_statements": len(true_rows), "true_statements_accepted": sum(r["accepted"] for r in true_rows),
                             "true_statements_wrongly_rejected": [r["statement"] for r in true_rows if not r["accepted"]]},
        "lawyer_escalation": {"passed": sum(r["passed"] for r in assistant_rows if r["id"] in {t["id"] for t in escalation}), "total": len(escalation)},
        "reports": {"generated_ok": sum(r["ok"] for r in report_checks), "total": len(report_checks)},
        "real_model_test": model_section,
        "limits_of_this_evaluation": [
            "All documents are synthetic, and the author of the rules also wrote them. Real documents will be messier.",
            "Development scores were used to fix bugs, so they are optimistic. The fresh-set scores are the better guide, on a small sample of documents.",
            "Citation checks confirm that a passage exists, not that a legal interpretation is right. No lawyer has reviewed this project.",
        ],
    }
    dump(config.EVAL_DIR / "evaluation_summary.json", summary)
    dump(RAW / "evaluation_summary_copy.json", summary)
    dev = summary["development_set"]
    hold = summary["holdout_set"]
    print(json.dumps({
        "dev_classification": dev["classification"], "dev_fields": dev["field_extraction"], "dev_scenarios": [dev["scenarios"]["passed"], dev["scenarios"]["total"]],
        "dev_retrieval": {k: dev["retrieval"][k] for k in ("total", "top1", "top3", "top5")},
        "fresh_classification": summary["fresh_set"]["classification"], "fresh_fields": summary["fresh_set"]["field_extraction"], "fresh_scenarios": [summary["fresh_set"]["scenarios"]["passed"], summary["fresh_set"]["scenarios"]["total"]],
        "fresh_retrieval": {k: summary["fresh_set"]["retrieval"][k] for k in ("total", "top1", "top3", "top5")},
        "holdout_classification": hold["classification"], "holdout_fields": hold["field_extraction"], "holdout_scenarios": [hold["scenarios"]["passed"], hold["scenarios"]["total"]],
        "holdout_retrieval": {k: hold["retrieval"][k] for k in ("total", "top1", "top3", "top5")},
        "assistant": [summary["assistant"]["passed"], summary["assistant"]["total"]], "validator_stress": {k: v for k, v in summary["validator_stress"].items()}, "citations": [citation_total, len(citation_bad)],
        "reports": summary["reports"], "model": model_section.get("ran"), "runtime": summary["runtime_seconds"]}, indent=1, ensure_ascii=False))


if __name__ == "__main__":
    main()
