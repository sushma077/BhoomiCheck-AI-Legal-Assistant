"""Rule-based document classification: weighted phrases, with extra weight for the title area."""
from __future__ import annotations

import re

from core.models import ProcessedDocument

LABELS = {
    "sale_deed": "Sale Deed",
    "agreement_to_sell": "Agreement to Sell",
    "rent_agreement": "Rent Agreement",
    "lease_deed": "Lease Deed",
    "gift_deed": "Gift Deed",
    "partition_deed": "Partition Deed",
    "mutation_record": "Mutation Record",
    "land_record": "Khasra / Khatauni / Jamabandi",
    "encumbrance_certificate": "Encumbrance Certificate",
    "property_tax_receipt": "Property Tax Receipt",
    "power_of_attorney": "Power of Attorney",
    "noc": "No Objection Certificate",
    "rera_document": "RERA Document",
    "will": "Will",
    "other": "Other property document",
}

# (pattern, weight). Long, specific phrases carry the most weight.
SIGNALS: dict[str, list[tuple[str, int]]] = {
    "sale_deed": [(r"\b(sale|conveyance) deed\b", 6), (r"\bdeed of (sale|conveyance|absolute sale)\b", 6),
                  (r"\b(vendor|vendee)\b", 2), (r"sale consideration", 2), (r"बैनामा|विक्रय (पत्र|विलेख)", 6),
                  (r"\bbainama\b", 6), (r"hereby (sell|sells|convey|conveys|transfer|transfers)", 3)],
    "agreement_to_sell": [(r"agreement (to|for) sell", 8), (r"agreement for sale", 8), (r"\bbayana\b|बयाना", 4),
                          (r"earnest money", 3), (r"balance (sale )?consideration", 2), (r"विक्रय (का )?अनुबंध", 6)],
    "rent_agreement": [(r"\brent(al)? agreement\b", 8), (r"leave and licen[cs]e", 8), (r"\blandlord\b", 3), (r"\btenant\b", 3),
                       (r"monthly rent", 3), (r"किराया(नामा)?", 5), (r"security deposit", 1)],
    "lease_deed": [(r"\blease deed\b", 8), (r"deed of lease", 8), (r"\blessor\b", 3), (r"\blessee\b", 3), (r"lease rent", 2)],
    "gift_deed": [(r"\bgift deed\b", 8), (r"deed of gift", 8), (r"\bdonor\b", 3), (r"\bdonee\b", 3), (r"दान ?(पत्र|विलेख)", 6), (r"\bhiba\b", 4)],
    "partition_deed": [(r"\bpartition deed\b", 8), (r"deed of partition", 8), (r"\bbatwara\b|बंटवारा|बँटवारा", 6), (r"family settlement", 4)],
    "mutation_record": [(r"\bmutation\b", 5), (r"dakhil[- ]?kharij|दाखिल[- ]?खारिज", 8), (r"namantaran|नामांतरण", 8),
                        (r"\bferfar\b|फेरफार", 8), (r"mutation (order|record|certificate|entry)", 6), (r"transferor", 1), (r"transferee", 1)],
    "land_record": [(r"\bkhatauni\b|खतौनी", 8), (r"\bjamabandi\b|जमाबंदी", 8), (r"\bkhasra\b|खसरा", 2), (r"record of rights", 5),
                    (r"7/12|satbara|सातबारा", 8), (r"\brtc\b|\bpahani\b", 6), (r"\bkhewat\b", 3), (r"खातेदार", 3)],
    "encumbrance_certificate": [(r"encumbrance certificate", 10), (r"certificate of encumbrance", 10), (r"\bnil encumbrance\b", 4),
                                (r"ऋणभार|भार ?मुक्त", 8), (r"\bform\s*(no\.?\s*)?(15|16)\b", 3), (r"search (period|conducted)", 2)],
    "property_tax_receipt": [(r"property tax", 7), (r"house tax", 7), (r"\breceipt\b", 2), (r"assessment (year|no)", 3),
                             (r"(municipal|nagar) (corporation|nigam|palika)", 2), (r"संपत्ति कर|गृह कर", 7)],
    "power_of_attorney": [(r"power of attorney", 8), (r"\bgpa\b|\bspa\b", 3), (r"attorney holder", 4), (r"मुख्तारनामा|मुख्तार", 8), (r"\bmukhtarnama\b", 8),
                          (r"\bprincipal\b", 1)],
    "noc": [(r"no[- ]objection certificate", 10), (r"\bn\.?o\.?c\.?\b", 5), (r"अनापत्ति", 8), (r"no objection", 4)],
    "rera_document": [(r"\brera\b", 7), (r"real estate regulatory authority", 8), (r"real estate \(regulation", 4), (r"registration certificate of project", 8), (r"form[- ]?['\"]?c['\"]?\b", 1)],
    "will": [(r"\blast will\b", 10), (r"\btestament\b", 6), (r"\btestator\b", 4), (r"वसीयत", 8), (r"\bwasiyat\b", 8)],
}


def classify_text(text: str) -> dict:
    """Return the best type, a 0-1 share of signal weight, and the phrases that matched."""
    lowered = text.lower()
    # The first few real lines usually carry the title. A party clause further down does not count.
    lines = [l for l in lowered.splitlines() if l.strip() and "synthetic test document" not in l]
    title_zone = " ".join(lines[:3])[:220]
    scores: dict[str, float] = {}
    matched: dict[str, list[str]] = {}
    for doc_type, signals in SIGNALS.items():
        score = 0.0
        for pattern, weight in signals:
            hits = re.findall(pattern, lowered)
            if not hits:
                continue
            found = re.search(pattern, lowered).group(0)
            matched.setdefault(doc_type, []).append(found)
            score += weight * min(len(hits), 3) ** 0.5  # repetition helps, with diminishing returns
            if re.search(pattern, title_zone):
                score += weight * 3  # the title says what the document is
        if score:
            scores[doc_type] = round(score, 2)
    if not scores:
        return {"type": "other", "label": LABELS["other"], "confidence": 0.0, "evidence": [], "scores": {}}
    best = max(scores, key=scores.get)
    if scores[best] < 6:  # a weak single keyword is not enough to name the document
        return {"type": "other", "label": LABELS["other"], "confidence": round(scores[best] / 20, 2),
                "evidence": matched[best], "scores": scores}
    confidence = round(scores[best] / sum(scores.values()), 2)
    return {"type": best, "label": LABELS[best], "confidence": confidence, "evidence": matched[best][:5], "scores": scores}


def classify(doc: ProcessedDocument) -> ProcessedDocument:
    result = classify_text(doc.full_text)
    doc.classification = result
    doc.doc_type = result["type"]
    doc.doc_type_label = result["label"]
    return doc
