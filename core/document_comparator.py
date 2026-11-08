"""Cross-document comparison. Only deterministic Python rules decide what conflicts.

Each comparison returns a plain record; risk_detector turns records into user-facing findings.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from itertools import combinations

from rapidfuzz import fuzz

from core.information_extractor import as_date, value_of
from core.models import ProcessedDocument

TRANSFER_TYPES = {"sale_deed", "gift_deed", "partition_deed"}
TITLES = r"\b(?:shri|sri|smt|mr|mrs|ms|miss|dr|sh|late|kumari|kum|m/s|mohd|md)\b\.?"
TITLES_HI = r"(?:^|\s)(?:श्रीमती|श्री|सुश्री|कुमारी|स्व\.?)(?=\s)"

_VOWELS = {"अ": "a", "आ": "a", "इ": "i", "ई": "i", "उ": "u", "ऊ": "u", "ए": "e", "ऐ": "ai", "ओ": "o", "औ": "au", "ऋ": "ri"}
_MATRAS = {"ा": "a", "ि": "i", "ी": "i", "ु": "u", "ू": "u", "े": "e", "ै": "ai", "ो": "o", "ौ": "au", "ृ": "ri"}
_CONS = {"क": "k", "ख": "kh", "ग": "g", "घ": "gh", "ङ": "n", "च": "ch", "छ": "chh", "ज": "j", "झ": "jh", "ञ": "n",
         "ट": "t", "ठ": "th", "ड": "d", "ढ": "dh", "ण": "n", "त": "t", "थ": "th", "द": "d", "ध": "dh", "न": "n",
         "प": "p", "फ": "ph", "ब": "b", "भ": "bh", "म": "m", "य": "y", "र": "r", "ल": "l", "व": "v", "श": "sh",
         "ष": "sh", "स": "s", "ह": "h", "ड़": "r", "ढ़": "rh", "ज़": "z", "फ़": "f", "क़": "k", "ग़": "g", "ख़": "kh"}


def romanise(text: str) -> str:
    """Rough Devanagari to Latin, only so Hindi and English spellings of a name can be compared."""
    out: list[str] = []
    for word in text.split():
        chars: list[str] = []
        i = 0
        while i < len(word):
            ch = word[i]
            nxt = word[i + 1] if i + 1 < len(word) else ""
            if ch + nxt in _CONS:  # nukta consonants
                ch = ch + nxt
                i += 1
                nxt = word[i + 1] if i + 1 < len(word) else ""
            if ch in _CONS:
                chars.append(_CONS[ch])
                if nxt == "्":
                    i += 1
                elif nxt in _MATRAS:
                    chars.append(_MATRAS[nxt])
                    i += 1
                else:
                    chars.append("a")
            elif ch in _VOWELS:
                chars.append(_VOWELS[ch])
            elif ch in "ंँ":
                chars.append("n")
            elif ch.isascii():
                chars.append(ch)
            i += 1
        roman = "".join(chars)
        if len(roman) > 3 and roman.endswith("a") and word[-1] in _CONS:  # Hindi drops the final vowel sound
            roman = roman[:-1]
        out.append(roman)
    return " ".join(out)


def normalise_name(name: str) -> str:
    name = re.sub(TITLES, " ", name, flags=re.I)
    name = re.sub(TITLES_HI, " ", name)
    if re.search(r"[ऀ-ॿ]", name):
        name = romanise(name)
    name = name.lower().replace(".", " ")
    name = re.sub(r"[^a-z ]", " ", name)
    name = name.replace("sh", "s").replace("aa", "a").replace("ee", "i").replace("oo", "u").replace("v", "w")
    return re.sub(r"\s+", " ", name).strip()


def initials_match(a: str, b: str) -> bool:
    """'R C Verma' and 'Ramesh Chandra Verma' could be one person."""
    ta, tb = a.split(), b.split()
    if len(ta) != len(tb) or ta[-1] != tb[-1]:
        return False
    return all(x[0] == y[0] and (len(x) == 1 or len(y) == 1 or x == y) for x, y in zip(ta[:-1], tb[:-1]))


def compare_names(a: str, b: str) -> dict:
    """Return same, variation or different. 'Variation' means a person must check it."""
    na, nb = normalise_name(a), normalise_name(b)
    if not na or not nb:
        return {"result": "different", "score": 0}
    if na == nb:
        return {"result": "same", "score": 100}
    if initials_match(na, nb):
        return {"result": "variation", "score": 85, "note": "one spelling uses initials"}
    score = fuzz.token_sort_ratio(na, nb)
    # Romanising Hindi is approximate, so small spelling gaps there are not evidence of anything.
    if score >= 85 and bool(re.search(r"[\u0900-\u097F]", a)) != bool(re.search(r"[\u0900-\u097F]", b)):
        return {"result": "same", "score": score, "note": "compared across Hindi and English spelling"}
    subset = fuzz.token_set_ratio(na, nb)
    if score >= 90:
        return {"result": "same" if score >= 96 else "variation", "score": score}
    # a shared core with a missing word: 'Anita Sharma' and 'Anita Devi Sharma'
    ta, tb = set(na.split()), set(nb.split())
    if subset >= 95 and min(len(ta), len(tb)) >= 2:
        return {"result": "variation", "score": subset, "note": "one spelling has extra words"}
    if score >= 80 and na.split()[-1] == nb.split()[-1] and fuzz.ratio(na.split()[0], nb.split()[0]) >= 80:
        return {"result": "variation", "score": score}
    return {"result": "different", "score": score}


@dataclass
class Comparison:
    check: str
    status: str  # match | mismatch | variation | not_comparable | missing
    summary: str
    documents: list[dict] = field(default_factory=list)  # [{document, page, value, evidence}]
    detail: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


def _ref(doc: ProcessedDocument, item: dict | None, value=None) -> dict:
    item = item or {}
    return {"document": doc.name, "doc_type": doc.doc_type_label, "page": item.get("page"),
            "value": value if value is not None else item.get("value"), "evidence": item.get("evidence", "")}


def _readable(docs: list[ProcessedDocument]) -> list[ProcessedDocument]:
    return [d for d in docs if d.status in ("ok", "partial")]


def _doc_date(doc: ProcessedDocument):
    f = doc.fields
    for key in ("registration_date", "execution_date", "mutation_order_date", "ec_date", "receipt_date"):
        parsed = as_date(f.get(key))
        if parsed:
            return parsed
    return None


def transfer_deeds(docs: list[ProcessedDocument]) -> list[ProcessedDocument]:
    """Title transfer deeds in date order. Undated deeds sort last and are flagged elsewhere."""
    deeds = [d for d in _readable(docs) if d.doc_type in TRANSFER_TYPES and d.fields.get("buyers")]
    import datetime as _dt
    return sorted(deeds, key=lambda d: _doc_date(d) or _dt.date.max)


def compare_survey(docs: list[ProcessedDocument]) -> list[Comparison]:
    return _compare_identifier(docs, "survey_numbers", "Survey / Khasra number")


def compare_khata(docs: list[ProcessedDocument]) -> list[Comparison]:
    return _compare_identifier(docs, "khata_numbers", "Khata number")


def _compare_identifier(docs, key: str, label: str) -> list[Comparison]:
    holders = [(d, d.fields.get(key) or []) for d in _readable(docs)]
    holders = [(d, items) for d, items in holders if items]
    if len(holders) < 2:
        return [Comparison(f"{key}", "not_comparable",
                           f"{label}: fewer than two uploaded documents state one, so it could not be compared.")]
    out = []
    conflict = False
    for (d1, items1), (d2, items2) in combinations(holders, 2):
        s1, s2 = {i["value"] for i in items1}, {i["value"] for i in items2}
        if s1 & s2:
            continue
        conflict = True
        out.append(Comparison(key, "mismatch",
                              f"{label} differs: {', '.join(sorted(s1))} in {d1.name}, but {', '.join(sorted(s2))} in {d2.name}.",
                              [_ref(d1, items1[0], sorted(s1)), _ref(d2, items2[0], sorted(s2))]))
    if not conflict:
        common = set.intersection(*[{i["value"] for i in items} for _, items in holders])
        text = ", ".join(sorted(common)) if common else "overlapping values"
        out.append(Comparison(key, "match", f"{label} is consistent across {len(holders)} documents ({text}).",
                              [_ref(d, items[0], [i["value"] for i in items]) for d, items in holders]))
    return out


def compare_area(docs: list[ProcessedDocument], tolerance: float = 0.01) -> list[Comparison]:
    holders = [(d, d.fields["area"]) for d in _readable(docs) if d.fields.get("area")]
    if len(holders) < 2:
        return [Comparison("area", "not_comparable", "Area: fewer than two uploaded documents state one, so it could not be compared.")]
    out = []
    conflict = False
    for (d1, a1), (d2, a2) in combinations(holders, 2):
        v1, v2 = a1["value"], a2["value"]
        if v1["sq_m"] is None or v2["sq_m"] is None:
            if v1["amount"] != v2["amount"] or v1["unit"] != v2["unit"]:
                conflict = True
                out.append(Comparison("area", "not_comparable",
                                      f"Area in {d1.name} ({v1['text']}) and {d2.name} ({v2['text']}) use a local unit whose size differs by state, so it was not converted. Compare them manually.",
                                      [_ref(d1, a1, v1["text"]), _ref(d2, a2, v2["text"])]))
            continue
        bigger = max(v1["sq_m"], v2["sq_m"])
        diff = abs(v1["sq_m"] - v2["sq_m"]) / bigger if bigger else 0
        if diff > tolerance:
            conflict = True
            out.append(Comparison("area", "mismatch",
                                  f"Area differs by about {diff * 100:.1f}%: {v1['text']} ({v1['sq_m']} sq. m) in {d1.name}, but {v2['text']} ({v2['sq_m']} sq. m) in {d2.name}.",
                                  [_ref(d1, a1, v1["text"]), _ref(d2, a2, v2["text"])], {"difference_pct": round(diff * 100, 2)}))
    if not conflict:
        out.append(Comparison("area", "match", f"Area is consistent across {len(holders)} documents, within {tolerance:.0%}.",
                              [_ref(d, a, a["value"]["text"]) for d, a in holders]))
    return out


_BOUNDARY_FILLER = set("the of a an wide feet foot ft meter metre mtr road lane street by side no number property plot land house site".split())


def _same_boundary(a: str, b: str) -> bool:
    """Two descriptions of one boundary. Numbers must agree, and so must what remains after filler."""
    if set(re.findall(r"\d+", a)) != set(re.findall(r"\d+", b)):
        return False
    road = re.compile(r"\b(road|lane|street|path|gali|marg)\b", re.I)
    if bool(road.search(a)) and bool(road.search(b)) and road.search(a).group(1).lower() != road.search(b).group(1).lower():
        return False
    core_a = " ".join(w for w in re.findall(r"\w+", a.lower()) if w not in _BOUNDARY_FILLER)
    core_b = " ".join(w for w in re.findall(r"\w+", b.lower()) if w not in _BOUNDARY_FILLER)
    if not core_a or not core_b:
        return True
    return fuzz.token_sort_ratio(core_a, core_b) >= 70


def compare_boundaries(docs: list[ProcessedDocument]) -> list[Comparison]:
    holders = [(d, d.fields["boundaries"]) for d in _readable(docs) if d.fields.get("boundaries")]
    if len(holders) < 2:
        return [Comparison("boundaries", "not_comparable", "Boundaries: fewer than two uploaded documents state them, so they could not be compared.")]
    out = []
    for (d1, b1), (d2, b2) in combinations(holders, 2):
        for direction in sorted(set(b1) & set(b2)):
            v1, v2 = b1[direction]["value"], b2[direction]["value"]
            if not _same_boundary(v1, v2):
                out.append(Comparison("boundaries", "mismatch",
                                      f"{direction.title()} boundary differs: '{v1}' in {d1.name}, but '{v2}' in {d2.name}.",
                                      [_ref(d1, b1[direction]), _ref(d2, b2[direction])], {"direction": direction}))
    if not out:
        out.append(Comparison("boundaries", "match", f"Boundaries that could be compared agree across {len(holders)} documents."))
    return out


def _names(doc, key) -> list[dict]:
    return doc.fields.get(key) or []


def compare_owner_names(docs: list[ProcessedDocument]) -> list[Comparison]:
    """Compare later records and agreements against the person the latest deed transferred to."""
    usable = _readable(docs)
    deeds = transfer_deeds(usable)
    out: list[Comparison] = []
    if not deeds:
        holders = [(d, n) for d in usable for n in _names(d, "owners")]
        for (d1, n1), (d2, n2) in combinations(holders, 2):
            if d1 is d2:
                continue
            res = compare_names(n1["value"], n2["value"])
            if res["result"] != "same":
                out.append(Comparison("owner_name", "mismatch" if res["result"] == "different" else "variation",
                                      f"Owner name differs: '{n1['value']}' in {d1.name}, but '{n2['value']}' in {d2.name}.",
                                      [_ref(d1, n1), _ref(d2, n2)], res))
        return out or [Comparison("owner_name", "not_comparable", "No transfer deed was uploaded, so owner names were only compared between other records.")]

    latest = deeds[-1]
    latest_date = _doc_date(latest)
    buyers = _names(latest, "buyers")
    sellers = _names(latest, "sellers")
    for doc in usable:
        if doc in deeds:
            continue
        roles = {"owners": "owner", "landlord": "landlord", "poa_principal": "principal"}
        if doc.doc_type == "mutation_record":
            roles = {"buyers": "new owner in mutation"}
        for key, role in roles.items():
            for person in _names(doc, key):
                doc_date = _doc_date(doc)
                expected = list(buyers)
                # A record older than the deed should name the seller, not the buyer.
                if doc_date and latest_date and doc_date < latest_date:
                    expected = list(sellers) or expected
                results = [compare_names(person["value"], e["value"]) for e in expected]
                best = max(results, key=lambda r: {"same": 2, "variation": 1, "different": 0}[r["result"]] * 1000 + r["score"], default=None)
                if best is None:
                    continue
                refs = [_ref(latest, expected[0]), _ref(doc, person)]
                names = " / ".join(e["value"] for e in expected)
                if best["result"] == "different":
                    out.append(Comparison("owner_name", "mismatch",
                                          f"{doc.name} names '{person['value']}' as {role}, but {latest.name} points to '{names}'.",
                                          refs, {"role": role, **best}))
                elif best["result"] == "variation":
                    out.append(Comparison("owner_name", "variation",
                                          f"Name spelling differs: '{person['value']}' ({role}) in {doc.name} and '{names}' in {latest.name}. They may or may not be the same person.",
                                          refs, {"role": role, **best}))
    if not out:
        out.append(Comparison("owner_name", "match", f"Owner names in other records agree with {latest.name}."))
    return out


def _same_parties(a: ProcessedDocument, b: ProcessedDocument) -> bool:
    def overlap(key: str) -> bool:
        return any(compare_names(x["value"], y["value"])["result"] == "same" for x in _names(a, key) for y in _names(b, key))
    return overlap("sellers") and overlap("buyers")


def check_chain(docs: list[ProcessedDocument]) -> list[Comparison]:
    """Each deed's seller should be the buyer in the deed before it."""
    deeds = transfer_deeds(docs)
    out: list[Comparison] = []
    if not deeds:
        return [Comparison("ownership_chain", "missing", "No registered transfer deed (sale, gift or partition) was found in the uploaded documents.")]
    for earlier, later in zip(deeds, deeds[1:]):
        if _same_parties(earlier, later):  # two copies or versions of one transaction are not a chain
            continue
        for seller in _names(later, "sellers"):
            results = [compare_names(seller["value"], b["value"]) for b in _names(earlier, "buyers")]
            if not results:
                continue
            verdicts = {r["result"] for r in results}
            if "same" in verdicts:
                out.append(Comparison("ownership_chain", "match",
                                      f"Chain link holds: {later.name} seller '{seller['value']}' is a buyer in {earlier.name}.",
                                      [_ref(earlier, _names(earlier, 'buyers')[0]), _ref(later, seller)]))
            elif "variation" in verdicts:
                out.append(Comparison("ownership_chain", "variation",
                                      f"Chain link needs checking: {later.name} seller '{seller['value']}' is spelled differently from the buyer in {earlier.name}.",
                                      [_ref(earlier, _names(earlier, 'buyers')[0]), _ref(later, seller)]))
            else:
                buyers = ", ".join(b["value"] for b in _names(earlier, "buyers"))
                out.append(Comparison("ownership_chain", "mismatch",
                                      f"Chain break: {later.name} seller is '{seller['value']}', but {earlier.name} transferred to '{buyers}'. An uploaded document does not show how the seller acquired the property.",
                                      [_ref(earlier, _names(earlier, 'buyers')[0]), _ref(later, seller)]))
    # Earlier deeds that the oldest uploaded deed refers to but which were not uploaded.
    first = deeds[0]
    refs = first.fields.get("prior_deed_refs") or []
    uploaded_dates = {_doc_date(d).isoformat() for d in deeds if _doc_date(d)} | {
        as_date(d.fields.get("execution_date")).isoformat() for d in deeds if as_date(d.fields.get("execution_date"))}
    missing_refs = [r for r in refs if r.get("date") not in uploaded_dates]
    for ref in missing_refs:
        out.append(Comparison("ownership_chain", "missing",
                              f"{first.name} refers to an earlier {ref['deed_type']} dated {ref['date'] or 'not stated'} that is not among the uploaded documents.",
                              [{"document": first.name, "doc_type": first.doc_type_label, "page": ref["page"], "value": ref.get("from"), "evidence": ref["evidence"]}], {"reference": ref}))
    if not refs and len(deeds) == 1:
        seller_name = ", ".join(s["value"] for s in _names(first, "sellers")) or "the seller"
        out.append(Comparison("ownership_chain", "missing",
                              f"Only one transfer deed was uploaded and it does not clearly say how {seller_name} acquired the property.",
                              [_ref(first, (_names(first, 'sellers') or [{}])[0])]))
    return out


def check_dates(docs: list[ProcessedDocument]) -> list[Comparison]:
    out: list[Comparison] = []
    usable = _readable(docs)
    for doc in usable:
        f = doc.fields
        ex, reg = as_date(f.get("execution_date")), as_date(f.get("registration_date"))
        if ex and reg:
            days = (reg - ex).days
            if days < 0:
                out.append(Comparison("dates", "mismatch", f"{doc.name} shows registration ({reg}) before execution ({ex}), which is not possible for one document.",
                                      [_ref(doc, f["execution_date"]), _ref(doc, f["registration_date"])], {"days": days}))
            elif days > 122:
                out.append(Comparison("dates", "mismatch", f"{doc.name} was registered {days} days after execution. The Registration Act normally allows four months for presentation, so check how this was accepted.",
                                      [_ref(doc, f["execution_date"]), _ref(doc, f["registration_date"])], {"days": days, "kind": "late_registration"}))
    deeds = transfer_deeds(usable)
    if deeds:
        latest = deeds[-1]
        deed_date = _doc_date(latest)
        for doc in usable:
            f = doc.fields
            if doc.doc_type == "mutation_record" and deed_date:
                mut = as_date(f.get("mutation_order_date"))
                if mut and mut < deed_date:
                    new_owner = {value_of(b) for b in _names(doc, "buyers")}
                    same_buyer = any(compare_names(n, value_of(b))["result"] != "different" for n in new_owner for b in _names(latest, "buyers"))
                    if same_buyer:
                        out.append(Comparison("dates", "mismatch", f"{doc.name} is dated {mut}, before the deed it records ({latest.name}, {deed_date}).",
                                              [_ref(doc, f.get("mutation_order_date")), _ref(latest, latest.fields.get("registration_date") or latest.fields.get("execution_date"))], {"kind": "mutation_before_deed"}))
            if doc.doc_type == "encumbrance_certificate" and deed_date:
                period = (f.get("ec") or {}).get("search_period")
                if period:
                    v = period["value"]
                    if v["to"] < deed_date.isoformat():
                        out.append(Comparison("dates", "mismatch", f"{doc.name} only searches up to {v['to']}, which ends before the latest deed ({deed_date}). Anything recorded after that date is not covered.",
                                              [_ref(doc, period), _ref(latest, latest.fields.get("registration_date") or latest.fields.get("execution_date"))], {"kind": "ec_period_short"}))
    if not out:
        out.append(Comparison("dates", "match", "No date inconsistency was detected in the dates BhoomiCheck could read."))
    return out


def compare_amounts(docs: list[ProcessedDocument]) -> list[Comparison]:
    usable = _readable(docs)
    holders = [(d, d.fields["transaction_amount"]) for d in usable
               if d.fields.get("transaction_amount") and d.doc_type in ("sale_deed", "agreement_to_sell", "encumbrance_certificate", "mutation_record")]
    deeds = transfer_deeds(usable)
    latest = deeds[-1] if deeds else None
    # Only documents about the same transaction can be compared: the latest deed, its
    # agreement to sell, and records whose buyer matches it. An older deed in the chain
    # was a different sale, so a different price there is expected.
    related = []
    for doc, item in holders:
        if latest is None or doc is latest:
            related.append((doc, item))
            continue
        if doc.doc_type in TRANSFER_TYPES:
            continue
        doc_date, latest_date = _doc_date(doc), _doc_date(latest)
        buyer_match = any(compare_names(value_of(a), value_of(b))["result"] != "different"
                          for a in _names(doc, "buyers") for b in _names(latest, "buyers"))
        if buyer_match or (doc.doc_type == "agreement_to_sell" and doc_date and latest_date and doc_date <= latest_date):
            related.append((doc, item))
    if len(related) < 2:
        return [Comparison("amounts", "not_comparable", "Transaction amount: fewer than two documents about the same transaction state one.")]
    out = []
    for (d1, a1), (d2, a2) in combinations(related, 2):
        if a1["value"]["amount"] != a2["value"]["amount"]:
            out.append(Comparison("amounts", "mismatch", f"Transaction amount differs: {a1['value']['display']} in {d1.name}, but {a2['value']['display']} in {d2.name}.",
                                  [_ref(d1, a1, a1["value"]["display"]), _ref(d2, a2, a2["value"]["display"])]))
    return out or [Comparison("amounts", "match", f"Transaction amount is consistent across {len(related)} related documents.")]


def compare_registration_refs(docs: list[ProcessedDocument]) -> list[Comparison]:
    """Does the EC or mutation record quote the same document number as the deed?"""
    usable = _readable(docs)
    deeds = transfer_deeds(usable)
    if not deeds:
        return []
    latest = deeds[-1]
    deed_no = (latest.fields.get("registration") or {}).get("document_no")
    if not deed_no:
        return []
    out = []
    for doc in usable:
        if doc.doc_type not in ("mutation_record", "encumbrance_certificate"):
            continue
        no = (doc.fields.get("registration") or {}).get("document_no")
        if no and no["value"].upper() != deed_no["value"].upper():
            buyer_match = any(compare_names(value_of(a), value_of(b))["result"] != "different"
                              for a in _names(doc, "buyers") for b in _names(latest, "buyers"))
            if buyer_match:
                out.append(Comparison("registration_refs", "mismatch", f"Document number differs: {deed_no['value']} in {latest.name}, but {no['value']} in {doc.name}.",
                                      [_ref(latest, deed_no), _ref(doc, no)]))
    return out


def compare_all(docs: list[ProcessedDocument]) -> list[Comparison]:
    results: list[Comparison] = []
    for check in (compare_owner_names, compare_survey, compare_khata, compare_area, compare_boundaries,
                  check_chain, check_dates, compare_amounts, compare_registration_refs):
        results.extend(check(docs))
    return results
