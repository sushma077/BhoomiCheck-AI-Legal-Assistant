"""Turn extracted facts and comparison results into findings with evidence and legal references.

Rules decide. AI, when available, may only explain findings in simpler words.
"""
from __future__ import annotations

import re

from core.document_comparator import Comparison, transfer_deeds
from core.information_extractor import as_date
from core.legal_retrieval import get_retriever
from core.models import HIGH, INFO, SEVERITY_ORDER, WARNING, Citation, Finding, ProcessedDocument, SourceRef

# Provisions attached to each kind of finding. Looked up exactly in the index, so a provision
# that is not present in the collected text is simply not cited.
LEGAL_BASIS: dict[str, list[tuple[str, str]]] = {
    "owner": [("tpa_1882", "41"), ("tpa_1882", "55")],
    "chain": [("tpa_1882", "54"), ("tpa_1882", "55")],
    "identity": [("registration_1908", "21"), ("tpa_1882", "55")],
    "mortgage": [("tpa_1882", "58"), ("tpa_1882", "59"), ("tpa_1882", "56")],
    "poa": [("registration_1908", "33"), ("contract_1872", "182"), ("contract_1872", "201"), ("poa_1882", "2")],
    "inheritance": [("hindu_succession_1956", "8"), ("indian_succession_1925", "63")],
    "litigation": [("tpa_1882", "52")],
    "registration": [("registration_1908", "17"), ("registration_1908", "49"), ("tpa_1882", "54")],
    "reg_time": [("registration_1908", "23"), ("registration_1908", "25")],
    "stamp": [("stamp_1899", "35")],
    "lease": [("tpa_1882", "105"), ("tpa_1882", "107"), ("registration_1908", "17")],
    "gift": [("tpa_1882", "122"), ("tpa_1882", "123")],
    "rera": [("rera_2016", "3"), ("rera_2016", "13")],
    "agreement": [("tpa_1882", "53A"), ("specific_relief_1963", "10")],
}


def citations_for(key: str) -> list[Citation]:
    retriever = get_retriever()
    out = []
    for source_id, section in LEGAL_BASIS.get(key, []):
        chunk = retriever.get_provision(source_id, section)
        if chunk:
            quote = chunk["text"][:220]
            out.append(Citation(source_id=source_id, title=chunk["title"], provision=chunk["provision"], url=chunk["url"],
                                page=chunk["page"], chunk_id=chunk["chunk_id"], quote=quote, verified=True))
    return out


def _sources(comparison: Comparison) -> list[SourceRef]:
    return [SourceRef(d["document"], d.get("page"), (d.get("evidence") or "")[:220]) for d in comparison.documents]


def _item_source(doc: ProcessedDocument, item: dict | None) -> SourceRef:
    item = item or {}
    return SourceRef(doc.name, item.get("page"), (item.get("evidence") or "")[:220])


def _usable(docs: list[ProcessedDocument]) -> list[ProcessedDocument]:
    return [d for d in docs if d.status in ("ok", "partial")]


def from_comparisons(comparisons: list[Comparison]) -> list[Finding]:
    out: list[Finding] = []
    for c in comparisons:
        src = _sources(c) or [SourceRef("(uploaded set)", None, "This comes from looking across all uploaded documents.")]
        if c.status == "match":
            continue
        if c.check == "owner_name" and c.status == "mismatch":
            out.append(Finding("OWNER_NAME_MISMATCH", HIGH, "Owner names do not match across documents", c.summary,
                               "Compare the original documents and ask the seller to explain the difference. Check the current Record of Rights at the Tehsil or land records office.",
                               src, citations_for("owner"), True, "ownership"))
        elif c.check == "owner_name" and c.status == "variation":
            out.append(Finding("OWNER_NAME_VARIATION", WARNING, "Same person? Name is written differently", c.summary,
                               "Check ID proof, and ask for an affidavit or name-correction record if it is the same person.",
                               src, citations_for("identity"), False, "ownership"))
        elif c.check == "survey_numbers" and c.status == "mismatch":
            out.append(Finding("SURVEY_MISMATCH", HIGH, "Survey or Khasra numbers do not match", c.summary,
                               "Confirm the correct number against the land record, the registered deed and a site map. The documents may describe different land.",
                               src, citations_for("identity"), True, "property_identity"))
        elif c.check == "khata_numbers" and c.status == "mismatch":
            out.append(Finding("KHATA_MISMATCH", WARNING, "Khata numbers differ", c.summary,
                               "Khata numbers can legitimately change after mutation. Check the current Khatauni or Khata extract to confirm the history.",
                               src, [], False, "property_identity"))
        elif c.check == "area" and c.status == "mismatch":
            pct = c.detail.get("difference_pct", 0)
            out.append(Finding("AREA_MISMATCH", HIGH if pct >= 5 else WARNING, "Property area differs between documents", c.summary,
                               "Get the land measured by a licensed surveyor and compare with the deed and the revenue map.",
                               src, citations_for("identity"), pct >= 5, "property_identity"))
        elif c.check == "area" and c.status == "not_comparable" and c.documents:
            out.append(Finding("AREA_LOCAL_UNIT", INFO, "Area uses a local land unit", c.summary,
                               "Bigha and similar units vary by state or district. Confirm the local conversion with the revenue office.",
                               src, [], False, "property_identity"))
        elif c.check == "boundaries" and c.status == "mismatch":
            out.append(Finding("BOUNDARY_MISMATCH", WARNING, "Boundaries differ between documents", c.summary,
                               "Inspect the site with a surveyor and check what actually adjoins the property on that side.",
                               src, citations_for("identity"), False, "property_identity"))
        elif c.check == "ownership_chain" and c.status == "mismatch":
            out.append(Finding("CHAIN_BREAK", HIGH, "Ownership chain has a gap", c.summary,
                               "Ask for the document showing how this seller acquired the property, then have a lawyer trace the title.",
                               src, citations_for("chain"), True, "ownership_chain"))
        elif c.check == "ownership_chain" and c.status == "variation":
            out.append(Finding("CHAIN_NAME_VARIATION", WARNING, "Ownership chain link needs a name check", c.summary,
                               "Confirm with ID proof or the registered records that both spellings refer to one person.",
                               src, citations_for("identity"), False, "ownership_chain"))
        elif c.check == "ownership_chain" and c.status == "missing":
            out.append(Finding("CHAIN_INCOMPLETE", WARNING, "Earlier ownership documents were not uploaded", c.summary + " This does not mean they do not exist.",
                               "Ask the seller for earlier title deeds and get certified copies from the Sub-Registrar. A title search commonly goes back 30 years, and your lawyer can advise on the right period.",
                               src, citations_for("chain"), False, "ownership_chain"))
        elif c.check == "dates" and c.status == "mismatch":
            kind = c.detail.get("kind")
            if kind == "late_registration":
                out.append(Finding("LATE_REGISTRATION", WARNING, "Long gap between signing and registration", c.summary,
                                   "Check the endorsement on the deed, and with the Sub-Registrar, to see how delay was dealt with.",
                                   src, citations_for("reg_time"), False, "registration"))
            elif kind == "ec_period_short":
                out.append(Finding("EC_PERIOD_SHORT", WARNING, "Encumbrance Certificate does not cover the latest period", c.summary,
                                   "Apply for a fresh Encumbrance Certificate that runs up to the present date.",
                                   src, [], False, "encumbrance"))
            elif kind == "mutation_before_deed":
                out.append(Finding("DATE_INCONSISTENT", HIGH, "Dates are inconsistent between documents", c.summary,
                                   "Check the certified copy of each record, as a transfer cannot normally be recorded before it happens.",
                                   src, citations_for("registration"), True, "dates"))
            else:
                out.append(Finding("DATE_INCONSISTENT", HIGH, "Dates in a document are not possible", c.summary,
                                   "Get a certified copy from the Sub-Registrar and compare it with this copy. A qualified lawyer should review any unexplained alteration.",
                                   src, citations_for("registration"), True, "dates"))
        elif c.check == "amounts" and c.status == "mismatch":
            out.append(Finding("AMOUNT_MISMATCH", WARNING, "Transaction amount differs between documents", c.summary,
                               "Ask why the amounts differ and confirm against payment records. Understated values can raise stamp duty questions.",
                               src, citations_for("stamp"), False, "transaction"))
        elif c.check == "registration_refs" and c.status == "mismatch":
            out.append(Finding("REGISTRATION_REF_MISMATCH", WARNING, "Registration number is quoted differently", c.summary,
                               "Check the number against the Sub-Registrar's index or a certified copy.",
                               src, citations_for("registration"), False, "registration"))
    return out


def mortgage_findings(docs: list[ProcessedDocument]) -> list[Finding]:
    usable = _usable(docs)
    mortgages = [(d, m) for d in usable for m in d.fields.get("mortgage_refs") or []]
    releases = [(d, r) for d in usable for r in d.fields.get("release_refs") or []]
    if not mortgages:
        return []
    src = [_item_source(d, m) for d, m in mortgages[:5]]
    if releases:
        src += [_item_source(d, r) for d, r in releases[:3]]
        return [Finding("MORTGAGE_WITH_RELEASE", INFO, "A mortgage is mentioned, along with a possible release",
                        "The documents mention a mortgage or loan, and also words that suggest it was released. BhoomiCheck cannot confirm the loan was fully closed.",
                        "Get the bank's no-dues letter and the registered release or reconveyance, and take a fresh Encumbrance Certificate.",
                        src, citations_for("mortgage"), False, "encumbrance")]
    return [Finding("MORTGAGE_NO_RELEASE", HIGH, "Possible mortgage with no release document uploaded",
                    "The documents mention a mortgage, loan or charge, but no release or no-dues reference was found in the uploads. It may exist elsewhere, but it was not seen.",
                    "Ask for the bank's no-dues letter and the registered release deed. Confirm with the bank in writing and check a fresh Encumbrance Certificate before paying.",
                    src, citations_for("mortgage"), True, "encumbrance")]


def poa_findings(docs: list[ProcessedDocument]) -> list[Finding]:
    usable = _usable(docs)
    out: list[Finding] = []
    poa_docs = [d for d in usable if d.doc_type == "power_of_attorney"]
    for doc in poa_docs:
        text = re.sub(r"\s+", " ", doc.full_text)
        page = doc.pages[0].number if doc.pages else None
        has_sale_power = re.search(r"(?:to|power to|authority to|authori[sz]ed to|empower\w* to)[^.;]{0,60}\b(?:sell|convey|transfer|execute (?:a |the )?sale)", text, re.I)
        if not has_sale_power:
            out.append(Finding("POA_AUTHORITY_UNCLEAR", HIGH, "Power of Attorney does not clearly allow a sale",
                               f"{doc.name} was read for words giving power to sell or transfer the property, and none were found. An agent's authority depends on what the document says.",
                               "Have a lawyer read the full Power of Attorney and confirm it covers this exact property and transaction.",
                               [SourceRef(doc.name, page, text[:200])], citations_for("poa"), True, "poa"))
        registered = doc.fields.get("registration") or {}
        if not registered.get("document_no") and not doc.fields.get("registration_date") and not re.search(r"\bregistered (?:at|with|before|as|on)\b|\bauthenticated\b", text, re.I):
            out.append(Finding("POA_NOT_REGISTERED", WARNING, "No registration details on the Power of Attorney",
                               f"BhoomiCheck did not find registration or authentication details in {doc.name}. It may be notarised only, or the details may be missing from this copy.",
                               "Check whether the document was registered or authenticated, and whether state rules require that for this kind of transaction.",
                               [SourceRef(doc.name, page, text[:200])], citations_for("poa"), False, "poa"))
        out.append(Finding("POA_CONFIRM_ALIVE", WARNING, "Confirm the Power of Attorney is still valid",
                           "An agent's authority generally ends if the principal revokes it, dies or becomes of unsound mind. A document cannot show this by itself.",
                           "Ask for a recent confirmation from the principal in person, or a life certificate, and check for any revocation.",
                           [SourceRef(doc.name, page, "")], citations_for("poa"), False, "poa"))
    for deed in transfer_deeds(usable):
        text = re.sub(r"\s+", " ", deed.full_text)
        m = re.search(r"[^.;]{0,100}(?:through (?:his|her|their|the)?\s*(?:duly\s+)?(?:constituted\s+)?(?:general |special )?(?:power of )?attorney|power of attorney holder|\bGPA holder\b|\bSPA holder\b|by virtue of (?:a |the )?(?:general |special )?power of attorney)[^.;]{0,100}", text, re.I)
        if m and not poa_docs:
            page = next((p.number for p in deed.pages if re.search(r"attorney", p.text, re.I)), None)
            out.append(Finding("POA_DOC_NOT_UPLOADED", HIGH, "Deed was signed through an agent, and the Power of Attorney was not uploaded",
                               f"{deed.name} appears to be executed through a Power of Attorney holder, but no Power of Attorney is among the uploads.",
                               "Get the Power of Attorney, check its scope, and confirm the principal was alive and had not revoked it on the signing date.",
                               [SourceRef(deed.name, page, m.group(0).strip()[:220])], citations_for("poa"), True, "poa"))
    return out


def inheritance_findings(docs: list[ProcessedDocument]) -> list[Finding]:
    hits = [(d, i) for d in _usable(docs) for i in d.fields.get("inheritance_refs") or []]
    if not hits:
        return []
    return [Finding("INHERITANCE_CONCERN", WARNING, "Inheritance appears in the ownership history",
                    "The documents refer to inheritance, legal heirs, a will or a deceased owner. Other heirs may have rights that these papers do not show.",
                    "Ask for the death certificate, will or legal heir papers, and consent or relinquishment from all heirs. A lawyer should check this, as personal law may apply.",
                    [_item_source(d, i) for d, i in hits[:5]], citations_for("inheritance"), True, "inheritance")]


def litigation_findings(docs: list[ProcessedDocument]) -> list[Finding]:
    hits = [(d, i) for d in _usable(docs) for i in d.fields.get("litigation_refs") or []]
    if not hits:
        return []
    return [Finding("LITIGATION_REFERENCE", HIGH, "Possible court case or dispute is mentioned",
                    "The documents use words that may refer to a court case, stay, attachment or dispute. BhoomiCheck does not check court records, so it cannot tell the current status.",
                    "Have a lawyer search the relevant court records and read the order before you proceed. A transfer during a pending case may be bound by its outcome.",
                    [_item_source(d, i) for d, i in hits[:5]], citations_for("litigation"), True, "litigation")]


def registration_findings(docs: list[ProcessedDocument]) -> list[Finding]:
    out: list[Finding] = []
    for doc in _usable(docs):
        f = doc.fields
        page = doc.pages[0].number if doc.pages else None
        if doc.doc_type in ("sale_deed", "gift_deed", "partition_deed"):
            reg = f.get("registration") or {}
            missing = [label for key, label in (("document_no", "document number"),) if key not in reg]
            if not f.get("registration_date"):
                missing.append("registration date")
            if not f.get("sub_registrar"):
                missing.append("Sub-Registrar office")
            if missing:
                severe = "document number" in missing and "registration date" in missing
                key = "gift" if doc.doc_type == "gift_deed" else "registration"
                out.append(Finding("REGISTRATION_DETAILS_MISSING", HIGH if severe else WARNING,
                                   f"Registration details not found in {doc.doc_type_label}",
                                   f"BhoomiCheck did not find: {', '.join(missing)} in {doc.name}. If this copy is unregistered, the transfer may not be effective. If the details are simply unreadable or not on this copy, a certified copy will show them.",
                                   "Get a certified copy from the Sub-Registrar's office, and confirm the document number, book, volume and date.",
                                   [SourceRef(doc.name, page, "No registration details matched on any page.")], citations_for(key), severe, "registration"))
            if not f.get("stamp_duty"):
                out.append(Finding("STAMP_NOT_FOUND", INFO, "Stamp duty details not found",
                                   f"BhoomiCheck did not find a stamp duty amount in {doc.name}. It may be on a stamp paper or e-stamp page not uploaded.",
                                   "Check the stamp paper or e-stamp certificate, and whether the duty paid is correct for your state.",
                                   [SourceRef(doc.name, page, "")], citations_for("stamp"), False, "registration"))
        if doc.doc_type == "agreement_to_sell":
            out.append(Finding("AGREEMENT_NOT_TITLE", INFO, "An agreement to sell is not a transfer of ownership",
                               f"{doc.name} is an agreement to sell. Ownership normally passes only through a registered sale deed.",
                               "Make sure a registered sale deed follows, and take legal advice on part-payment and possession.",
                               [_item_source(doc, f.get("transaction_amount"))], citations_for("agreement"), False, "registration"))
    return out


def lease_findings(docs: list[ProcessedDocument]) -> list[Finding]:
    out: list[Finding] = []
    for doc in _usable(docs):
        if doc.doc_type not in ("rent_agreement", "lease_deed"):
            continue
        lease = doc.fields.get("lease") or {}
        term = lease.get("term_months")
        reg = doc.fields.get("registration") or {}
        is_registered = bool(reg.get("document_no") or doc.fields.get("registration_date"))
        if term and term["value"] > 12 and not is_registered:
            out.append(Finding("LEASE_NEEDS_REGISTRATION", WARNING, "Long lease without registration details",
                               f"{doc.name} states a term of {term['value']} months, and no registration details were found. Leases of more than one year, or year-to-year leases, generally must be registered.",
                               "Register the agreement at the Sub-Registrar's office, and check local rent law. An unregistered lease may be of limited use as evidence.",
                               [_item_source(doc, term)], citations_for("lease"), False, "lease"))
        elif term and term["value"] <= 12:
            out.append(Finding("LEASE_SHORT_TERM", INFO, "Short-term rent agreement",
                               f"{doc.name} states a term of {term['value']} months. Registration may be optional at this length under central law, but state rules vary, such as Maharashtra's rule for leave and licence.",
                               "Check your state's requirement, and whether police verification of tenants is required locally.",
                               [_item_source(doc, term)], citations_for("lease"), False, "lease"))
        if not term:
            out.append(Finding("LEASE_TERM_MISSING", WARNING, "Lease period not found",
                               f"BhoomiCheck did not find a clear lease period in {doc.name}.",
                               "Make sure the period, rent, deposit and notice terms are written clearly.",
                               [SourceRef(doc.name, 1, "")], citations_for("lease"), False, "lease"))
        if not lease.get("monthly_rent"):
            out.append(Finding("LEASE_RENT_MISSING", WARNING, "Rent amount not found",
                               f"BhoomiCheck did not find a monthly rent in {doc.name}.",
                               "Make sure the rent is written in the agreement.",
                               [SourceRef(doc.name, 1, "")], [], False, "lease"))
    return out


def land_use_findings(docs: list[ProcessedDocument]) -> list[Finding]:
    out = []
    hits = [(d, i) for d in _usable(docs) for i in d.fields.get("land_use_refs") or []]
    agricultural = [(d, i) for d, i in hits if re.search(r"agricultural|कृषि", i["value"], re.I) and not re.search(r"non[- ]agricultural", i["value"], re.I)]
    if agricultural:
        out.append(Finding("LAND_USE_AGRICULTURAL", WARNING, "Land appears to be agricultural",
                           "The documents describe the land as agricultural. Many states restrict who can buy agricultural land, and how it can be used or built on.",
                           "Check state restrictions on buyers and on conversion, the land-use classification, and any conversion order at the revenue or planning office.",
                           [_item_source(d, i) for d, i in agricultural[:4]], [], False, "land_use"))
    elif hits:
        out.append(Finding("LAND_USE_MENTIONED", INFO, "Land-use terms are mentioned",
                           "The documents mention land-use, conversion or zoning. These can limit how the property can be used.",
                           "Verify the classification at the development authority or revenue office.",
                           [_item_source(d, i) for d, i in hits[:3]], [], False, "land_use"))
    return out


EXPECTED_DOCS = {
    "purchase": [("sale_deed", "Registered sale deed or earlier title deed"), ("encumbrance_certificate", "Encumbrance Certificate"),
                 ("mutation_record", "Mutation record"), ("property_tax_receipt", "Latest property tax receipt")],
    "rental": [("rent_agreement", "Rent agreement")],
    "agricultural": [("sale_deed", "Registered sale deed or earlier title deed"), ("land_record", "Khasra / Khatauni / Jamabandi"),
                     ("encumbrance_certificate", "Encumbrance Certificate"), ("mutation_record", "Mutation record")],
}


def missing_doc_findings(docs: list[ProcessedDocument], purpose: str) -> list[Finding]:
    usable = _usable(docs)
    present = {d.doc_type for d in usable}
    is_rental_only = bool(present) and present <= {"rent_agreement", "lease_deed", "property_tax_receipt", "other"}
    key = "rental" if purpose == "rental" or is_rental_only else ("agricultural" if purpose == "agricultural" else "purchase")
    out = []
    for doc_type, label in EXPECTED_DOCS[key]:
        if doc_type not in present and not (doc_type == "rent_agreement" and "lease_deed" in present) and not (doc_type == "sale_deed" and present & {"gift_deed", "partition_deed"}):
            out.append(Finding("MISSING_DOCUMENT", INFO, f"Not uploaded: {label}",
                               f"{label} was not among the uploaded documents. This does not mean it does not exist.",
                               f"Ask for the {label} and review it before relying on the other papers.",
                               [SourceRef("(uploaded set)", None, f"Uploaded types: {', '.join(sorted(present)) or 'none readable'}")], [], False, "missing_documents"))
    return out


def permissions_findings(docs: list[ProcessedDocument]) -> list[Finding]:
    usable = _usable(docs)
    apartment = [(d, p.number) for d in usable for p in d.pages if re.search(r"\b(?:flat|apartment|tower|builder|promoter)\b", p.text, re.I)]
    present = {d.doc_type for d in usable}
    if not apartment or "rera_document" in present or present <= {"rent_agreement", "lease_deed"}:
        return []
    seen = " ".join(i["value"].lower() for d in usable for i in d.fields.get("permission_refs") or [])
    missing = [label for pattern, label in ((r"occupancy", "Occupancy Certificate"), (r"completion", "Completion Certificate"), (r"sanction|building plan", "sanctioned building plan"), (r"rera", "RERA registration")) if not re.search(pattern, seen)]
    if not missing:
        return []
    doc, page = apartment[0]
    return [Finding("PERMISSIONS_NOT_SEEN", INFO, "Building permissions were not seen in the uploads",
                    f"This looks like a flat or building project. These were not seen: {', '.join(missing)}. This does not mean they do not exist, and some may not apply.",
                    "Ask the seller or builder for these, and search the state RERA website if the project is covered.",
                    [SourceRef(doc.name, page, "Flat, apartment or builder wording appears on this page.")], citations_for("rera"), False, "permissions")]


def readability_findings(docs: list[ProcessedDocument]) -> list[Finding]:
    out = []
    for doc in docs:
        if doc.status in ("unreadable", "error"):
            out.append(Finding("DOCUMENT_UNREADABLE", WARNING, "A document could not be read",
                               f"{doc.name}: {' '.join(doc.warnings)} BhoomiCheck has drawn no conclusion from this file.",
                               "Upload a clear scan of at least 300 DPI, or ask for a certified copy.",
                               [SourceRef(doc.name, None, "")], [], False, "readability"))
        elif doc.status == "partial":
            out.append(Finding("DOCUMENT_PARTLY_UNREADABLE", WARNING, "Some pages could not be read",
                               f"{doc.name}: {' '.join(doc.warnings)}",
                               "Upload clearer copies of those pages, and read them yourself.",
                               [SourceRef(doc.name, None, "")], [], False, "readability"))
    return out


def _merge_repeats(findings: list[Finding]) -> list[Finding]:
    """Three documents can produce several pairwise conflicts about one fact. Show them as one finding."""
    merged: dict[str, Finding] = {}
    for finding in findings:
        existing = merged.get(finding.code)
        if existing is None:
            merged[finding.code] = finding
            continue
        existing.reason = f"{existing.reason} {finding.reason}"
        seen = {(s.document, s.page) for s in existing.sources}
        existing.sources += [s for s in finding.sources if (s.document, s.page) not in seen]
        existing.lawyer_referral = existing.lawyer_referral or finding.lawyer_referral
        if SEVERITY_ORDER[finding.severity] < SEVERITY_ORDER[existing.severity]:
            existing.severity = finding.severity
    return list(merged.values())


def detect_risks(docs: list[ProcessedDocument], comparisons: list[Comparison], purpose: str = "purchase") -> list[Finding]:
    findings = (readability_findings(docs) + _merge_repeats(from_comparisons(comparisons)) + mortgage_findings(docs) + poa_findings(docs)
                + inheritance_findings(docs) + litigation_findings(docs) + registration_findings(docs) + lease_findings(docs)
                + land_use_findings(docs) + permissions_findings(docs) + missing_doc_findings(docs, purpose))
    return sorted(findings, key=lambda f: SEVERITY_ORDER[f.severity])


__all__ = ["detect_risks", "citations_for", "as_date"]
