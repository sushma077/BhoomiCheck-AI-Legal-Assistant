"""Scoring functions. Each compares pipeline output with answer keys in data/test_cases.json."""
from __future__ import annotations

import re

from core.document_comparator import compare_names
from core.citation_validator import forbidden_claims, validate_citation
from core.information_extractor import normalise_identifier


def score_document(gold: dict, doc) -> dict:
    """Field-level scoring. Returns the checks with expected and actual values."""
    f = doc.fields
    checks: list[dict] = []

    def add(field, expected, actual, ok):
        checks.append({"field": field, "expected": expected, "actual": actual, "ok": bool(ok)})

    if "expect_status" in gold:
        add("status", gold["expect_status"], doc.status, doc.status == gold["expect_status"])
        return {"checks": checks}

    add("doc_type", gold.get("doc_type"), doc.doc_type, doc.doc_type == gold.get("doc_type"))

    def names(field, key):
        if field not in gold:
            return
        got = [i["value"] for i in f.get(key) or []]
        ok = bool(got) and all(any(compare_names(e, g)["result"] == "same" for g in got) for e in gold[field])
        add(field, gold[field], got, ok)

    for field, key in [("sellers", "sellers"), ("buyers", "buyers"), ("owners", "owners"), ("landlord", "landlord"), ("tenant", "tenant"),
                       ("poa_principal", "poa_principal"), ("poa_attorney", "poa_attorney")]:
        names(field, key)

    for field, key in [("survey", "survey_numbers"), ("khata", "khata_numbers")]:
        if field in gold:
            got = [i["value"] for i in f.get(key) or []]
            add(field, gold[field], got, all(normalise_identifier(e) in got for e in gold[field]))

    if "area_sqm" in gold:
        got = (f.get("area") or {}).get("value", {}).get("sq_m")
        add("area_sqm", gold["area_sqm"], got, got is not None and abs(got - gold["area_sqm"]) / gold["area_sqm"] < 0.01)
    if "amount" in gold:
        got = (f.get("transaction_amount") or {}).get("value", {}).get("amount")
        add("amount", gold["amount"], got, got == gold["amount"])
    for field in ("execution_date", "registration_date", "mutation_order_date"):
        if field in gold:
            got = (f.get(field) or {}).get("value")
            add(field, gold[field], got, got == gold[field])
    if "document_no" in gold:
        got = ((f.get("registration") or {}).get("document_no") or {}).get("value")
        add("document_no", gold["document_no"], got, got == gold["document_no"])
    if "sub_registrar" in gold:
        got = (f.get("sub_registrar") or {}).get("value")
        expected = gold["sub_registrar"]
        add("sub_registrar", expected, got, (got is None) if expected is None else (got is not None and expected.lower() in got.lower()))
    for field, direction in (("boundary_north", "north"), ("boundary_west", "west")):
        if field in gold:
            got = ((f.get("boundaries") or {}).get(direction) or {}).get("value")
            add(field, gold[field], got, got is not None and gold[field].lower() in got.lower())
    if "ec_from" in gold:
        got = ((f.get("ec") or {}).get("search_period") or {}).get("value") or {}
        add("ec_period", [gold["ec_from"], gold["ec_to"]], [got.get("from"), got.get("to")], got.get("from") == gold["ec_from"] and got.get("to") == gold["ec_to"])
    if "assessment_year" in gold:
        got = (f.get("assessment_year") or {}).get("value")
        add("assessment_year", gold["assessment_year"], got, got == gold["assessment_year"])
    lease = f.get("lease") or {}
    if "rent" in gold:
        got = (lease.get("monthly_rent") or {}).get("value", {}).get("amount")
        add("rent", gold["rent"], got, got == gold["rent"])
    if "deposit" in gold:
        got = (lease.get("security_deposit") or {}).get("value", {}).get("amount")
        add("deposit", gold["deposit"], got, got == gold["deposit"])
    if "term_months" in gold:
        got = (lease.get("term_months") or {}).get("value")
        add("term_months", gold["term_months"], got, got == gold["term_months"])
    if "start_date" in gold:
        got = (lease.get("start_date") or {}).get("value")
        add("start_date", gold["start_date"], got, got == gold["start_date"])
    if gold.get("ocr_expected"):
        methods = {p.method for p in doc.pages}
        add("ocr_used", True, sorted(methods), any("tesseract" in m or "rapidocr" in m for m in methods))
    return {"checks": checks}


def score_scenario(scenario: dict, result: dict) -> dict:
    findings = result["findings"]
    codes = [f.code for f in findings]
    missing = [c for c in scenario.get("expect", []) if c not in codes]
    forbidden = [c for c in scenario.get("forbid", []) if c in codes]
    high = sum(f.severity == "High Priority" for f in findings)
    too_many_high = scenario.get("max_high") is not None and high > scenario["max_high"]
    no_lawyer = bool(scenario.get("lawyer")) and not any(f.lawyer_referral for f in findings)
    incomplete = [f.code for f in findings if not f.reason or not f.recommended_verification or not f.sources
                  or (f.category != "readability" and any(s.page is None and s.document != "(uploaded set)" for s in f.sources))]
    ok = not (missing or forbidden or too_many_high or no_lawyer or incomplete)
    return {"passed": ok, "missing_expected": missing, "forbidden_present": forbidden, "high_count": high,
            "too_many_high": too_many_high, "lawyer_missing": no_lawyer, "findings_without_evidence": incomplete, "codes": codes}


def score_assistant(test: dict, response: dict) -> dict:
    answer = response["answer"]
    problems = []
    for needle in test.get("must_include", []):
        if needle not in answer:
            problems.append(f"missing text: {needle}")
    if test.get("must_cite_page") and not re.search(r"p\.\d+", answer):
        problems.append("no page citation")
    if test.get("must_cite_law"):
        cited = {c["source_id"] for c in response["citations"]}
        if not cited & set(test["must_cite_law"]):
            problems.append(f"expected a citation from {test['must_cite_law']}, got {sorted(cited)}")
    if test.get("must_cite_top3"):
        top = [[c["source_id"], (c["provision"].split()[-1] if c["provision"].startswith("Section") else None)] for c in response["citations"][:3]]
        if not any(item in top for item in test["must_cite_top3"]):
            problems.append(f"expected {test['must_cite_top3']} in the top 3 citations, got {top}")
    if test.get("refuse") and not response["refused"]:
        problems.append("did not refuse")
    if test.get("lawyer") and not response["lawyer_referral"]:
        problems.append("no lawyer referral")
    if test.get("must_say_not_found") and response["kind"] != "not_found":
        problems.append(f"expected a not-found answer, got kind {response['kind']}")
    forbidden = forbidden_claims(answer)
    if forbidden:
        problems.append(f"forbidden claim: {forbidden}")
    return {"passed": not problems, "problems": problems}


def score_retrieval(test: dict, results: list[dict]) -> dict:
    keys = [(c["source_id"], c["section"]) for c in results]
    expected = [tuple(e) for e in test["expect"]]

    def hit(key):
        return any(key[0] == e[0] and (e[1] is None or key[1] == e[1]) for e in expected)

    rank = next((i + 1 for i, key in enumerate(keys) if hit(key)), None)
    return {"rank": rank, "top1": rank == 1, "top3": bool(rank and rank <= 3), "top5": bool(rank and rank <= 5), "retrieved": keys}


def check_citations(findings: list) -> dict:
    total, bad = 0, []
    for finding in findings:
        for citation in finding.citations:
            total += 1
            ok, reason = validate_citation(citation)
            if not ok:
                bad.append({"finding": finding.code, "provision": citation.provision, "reason": reason})
    return {"total": total, "invalid": bad}
