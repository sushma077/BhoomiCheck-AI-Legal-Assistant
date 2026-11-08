"""Rule-based extraction of property facts. Every value keeps its page and evidence text.

Nothing here decides whether a fact is true. It only records what a document says.
"""
from __future__ import annotations

import re
from datetime import date, datetime

from core.models import ProcessedDocument

TITLE = r"(?:Shri|Sri|Smt|Mr|Mrs|Ms|Miss|Dr|Sh|Late|Kumari|Kum|M/s|Mohd|Md)\.?"
NAME_WORD = r"[A-Z][A-Za-z'.\-]*"
# A person's name: optional titles, then 1-6 capitalised words.
NAME = rf"(?:{TITLE}\s+)*{NAME_WORD}(?:\s+{NAME_WORD}){{0,5}}"
NAME_HI = r"[ऀ-ॿ]+(?:\s+[ऀ-ॿ]+){0,4}"
NAME_STOP = re.compile(
    r"\s*(?:,|\(|\bS/o\b|\bD/o\b|\bW/o\b|\bR/o\b|\bson of\b|\bdaughter of\b|\bwife of\b|\bresident\b|\baged?\b"
    r"|\bhereinafter\b|\bthrough\b|\bvide\b|\bdated\b|\bfor\b|\bof\b|\bat\b|\bin\b|\bwho\b|\bhas\b|\bhad\b|\bis\b|\bto\b|\bfrom\b"
    r"|पत्नी|पुत्र|पुत्री|निवासी).*$", re.I | re.S)
NOT_NAMES = {"the", "this", "that", "said", "name", "address", "details", "property", "nil", "none", "not", "and",
             "first", "second", "party", "vendor", "vendee", "seller", "buyer", "purchaser", "owner", "witness",
             "sale", "deed", "date", "document", "page", "registered", "as", "government", "synthetic"}

MONTHS = {m: i + 1 for i, m in enumerate(
    "january february march april may june july august september october november december".split())}
MONTHS.update({m[:3]: i for m, i in list(MONTHS.items())})
MONTHS["sept"] = 9

DATE_RE = (r"(?:\d{1,2}(?:st|nd|rd|th)?(?:\s+day\s+of)?[\s\-]+(?:[A-Za-z]{3,9})[,\s\-]+\d{4}"
           r"|[A-Za-z]{3,9}\s+\d{1,2},\s*\d{4}"
           r"|\d{1,2}[/\-.]\d{1,2}[/\-.]\d{4})")


def parse_date(text: str) -> date | None:
    """Parse Indian-style dates. Numeric dates are read as day/month/year."""
    text = text.strip()
    m = re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{4})", text)
    try:
        if m:
            return date(int(m[3]), int(m[2]), int(m[1]))
        m = re.fullmatch(r"(\d{1,2})(?:st|nd|rd|th)?(?:\s+day\s+of)?[\s\-]+([A-Za-z]{3,9})[,\s\-]+(\d{4})", text)
        if m and m[2].lower() in MONTHS:
            return date(int(m[3]), MONTHS[m[2].lower()], int(m[1]))
        m = re.fullmatch(r"([A-Za-z]{3,9})\s+(\d{1,2}),\s*(\d{4})", text)
        if m and m[1].lower() in MONTHS:
            return date(int(m[3]), MONTHS[m[1].lower()], int(m[2]))
    except ValueError:
        return None
    return None


def parse_amount(text: str) -> int | None:
    digits = re.sub(r"[^\d.]", "", text).rstrip(".")
    if not digits:
        return None
    try:
        return int(float(digits))
    except ValueError:
        return None


def format_inr(value: int) -> str:
    s = str(value)
    if len(s) <= 3:
        return f"Rs. {s}"
    head, tail = s[:-3], s[-3:]
    groups = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return f"Rs. {','.join(groups)},{tail}"


def clean_name(raw: str) -> str | None:
    name = NAME_STOP.sub("", raw.strip(" :-–—\t\n'\"“”.,"))
    name = re.sub(r"\s+", " ", name).strip(" :-–—'\"“”,")
    kept = []
    for token in name.split():  # 'Farida Khan. Assessment No.' ends at the full stop after a word
        kept.append(token)
        if token.endswith(".") and len(token) > 3 and not re.fullmatch(TITLE, token, re.I):
            kept[-1] = token.rstrip(".")
            break
    name = " ".join(kept)
    if not name or len(name) < 3:
        return None
    if name.lower().split()[0] in NOT_NAMES or name.lower() in NOT_NAMES:
        return None
    return name


def _flat(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _snippet(text: str, start: int, end: int, pad: int = 60) -> str:
    """Text around a match, cut at word boundaries so evidence reads properly."""
    left = max(0, start - pad)
    right = min(len(text), end + pad)
    while left > 0 and not text[left - 1].isspace():
        left -= 1
    while right < len(text) and not text[right].isspace():
        right += 1
    return _flat(text[left:right]).strip()


def _field(value, page, text, start, end) -> dict:
    return {"value": value, "page": page, "evidence": _snippet(text, start, end), "method": "rule"}


def _first(doc: ProcessedDocument, patterns: list[str], group: int = 1, flags: int = re.I, flat: bool = True):
    """Earliest page wins; within a page, the first pattern in the list wins."""
    for page in doc.pages:
        text = _flat(page.text) if flat else page.text
        for pattern in patterns:
            m = re.search(pattern, text, flags)
            if m:
                yield_value = m.group(group).strip()
                return yield_value, page.number, text, m.start(), m.end()
    return None


def _labelled_names(doc: ProcessedDocument, labels: str) -> list[dict]:
    """Names introduced by a label, e.g. 'Name of Seller: X' or 'Vendor (First Party) - X'."""
    out: dict[str, dict] = {}
    pattern = rf"(?im)^[ \t]*(?:\d+[.)]\s*)?(?:name of (?:the )?)?(?:{labels})(?:\s+name)?(?:\s*\([^)\n]*\))?(?:\s+name)?\s*[:\-–—|]\s*(.+)$"
    for page in doc.pages:
        for m in re.finditer(pattern, page.text):
            for part in re.split(r"\s+(?:and|&)\s+|;", m.group(1)):
                match = re.match(NAME, part.strip()) or re.match(NAME_HI, part.strip())
                name = clean_name(match.group(0)) if match else None
                if name and name not in out:
                    out[name] = _field(name, page.number, page.text, m.start(), m.end())
    return list(out.values())


_RELATION_BEFORE = re.compile(r"(?:son|daughter|wife|husband|widow) of\s*$|[SDW]/o\.?\s*$", re.I)


def _name_in_segment(segment: str) -> str | None:
    """The party in a description. Titled names win, and a parent's name is never the party."""
    titled = [m for m in re.finditer(rf"{TITLE}\s+{NAME_WORD}(?:\s+{NAME_WORD}){{0,4}}", segment)
              if not _RELATION_BEFORE.search(segment[:m.start()])]
    if titled:
        return clean_name(titled[-1].group(0))
    found = re.search(NAME, segment)
    return clean_name(found.group(0)) if found else None


def _narrative_names(doc: ProcessedDocument, role_words: str) -> list[dict]:
    """Names introduced by role wording: '(hereinafter called the VENDOR)' or 'Mrs. X (Licensor)'."""
    out: dict[str, dict] = {}
    clause = rf"\(?\s*(?:hereinafter|herein after|hereafter)[^)]{{0,90}}?[\"'“‘]?\s*(?:{role_words})\b"
    inline = rf"((?:{TITLE}\s+)?{NAME_WORD}(?:\s+{NAME_WORD}){{0,4}})\s*\((?:the\s+)?(?:{role_words})\)"
    for page in doc.pages:
        text = _flat(page.text)
        for m in re.finditer(clause, text, re.I):
            window = text[max(0, m.start() - 320):m.start()]
            # the party description starts after the last BETWEEN / BY / AND separator
            parts = re.split(r"\b(?:BETWEEN|AND|BY|WITH)\b\s*:?", window)
            segment = parts[-1] if parts else window
            name = _name_in_segment(segment) or _name_in_segment(window)
            if name and name not in out:
                out[name] = _field(name, page.number, text, m.start() - len(segment), m.end())
        for m in re.finditer(inline, text, re.I):
            name = _name_in_segment(m.group(1))
            if name and name not in out:
                out[name] = _field(name, page.number, text, m.start(), m.end())
    return list(out.values())


def _names(doc: ProcessedDocument, labels: str, role_words: str | None = None) -> list[dict]:
    found = _labelled_names(doc, labels)
    if not found and role_words:
        found = _narrative_names(doc, role_words)
    return found


def _hindi_names(doc: ProcessedDocument, labels: str) -> list[dict]:
    out: dict[str, dict] = {}
    for page in doc.pages:
        for m in re.finditer(rf"(?:{labels})\s*[:\-–—]?\s*(?:श्रीमती|श्री|सुश्री|कुमारी)?\s*({NAME_HI})", page.text):
            name = clean_name(m.group(1))
            if name and name not in out:
                out[name] = _field(name, page.number, page.text, m.start(), m.end())
    return list(out.values())


# Numbers ------------------------------------------------------------------------------

_NUM = r"([0-9][0-9A-Za-z]*(?:\s?[/\-]\s?[0-9A-Za-z]+)*)"


def normalise_identifier(value: str) -> str:
    return re.sub(r"[\s\-]+", "/", value.strip()).upper().strip("/")


_BOUNDARY_BEFORE = re.compile(r"(?:north|south|east|west|adjoining|उत्तर|दक्षिण|पूर्व|पश्चिम)\W{0,12}$", re.I)


def _numbers(doc: ProcessedDocument, labels: str) -> list[dict]:
    out: dict[str, dict] = {}
    pattern = rf"(?:{labels})\s*(?:\(?\s*(?:no|nos|number|numbers|संख्या|सं)\s*\)?\.?)\s*[:.\-–]?\s*{_NUM}"
    for page in doc.pages:
        text = _flat(page.text)
        for m in re.finditer(pattern, text, re.I):
            value = normalise_identifier(m.group(1))
            if _BOUNDARY_BEFORE.search(text[max(0, m.start() - 20):m.start()]):
                continue  # a neighbouring plot named as a boundary is not this property
            if value not in out:
                out[value] = _field(value, page.number, text, m.start(), m.end())
    return list(out.values())


UNIT_TO_SQM = [
    (r"sq(?:uare)?\.?\s*(?:ft|feet|foot)\.?|sft|वर्ग\s*फ(?:ु|ी)ट", "sq. ft", 0.09290304),
    (r"sq(?:uare)?\.?\s*(?:yd|yds|yards?|yard)\.?|gaj|गज|वर्ग\s*गज", "sq. yd", 0.83612736),
    (r"sq(?:uare)?\.?\s*(?:m|mt|mtr|mtrs|metres?|meters?)\.?|वर्ग\s*मीटर", "sq. m", 1.0),
    (r"hectares?|hect?\.?|हेक्टेयर|हे\.", "hectare", 10000.0),
    (r"acres?|एकड़", "acre", 4046.8564224),
    (r"bighas?|बीघा", "bigha", None),  # bigha size differs by state, so it is never converted
    (r"biswas?|बिस्वा", "biswa", None),
    (r"marlas?|kanals?|guntha?s?|cents?", "local unit", None),
]
_AREA_UNITS = "|".join(p for p, _, _ in UNIT_TO_SQM)
_AREA_RE = re.compile(rf"([0-9][0-9,]*(?:\.[0-9]+)?)\s*(?:\()?\s*({_AREA_UNITS})", re.I)


def _unit_info(unit_text: str) -> tuple[str, float | None]:
    for pattern, name, factor in UNIT_TO_SQM:
        if re.fullmatch(pattern, unit_text.strip(), re.I):
            return name, factor
    return unit_text, None


def _area(doc: ProcessedDocument) -> dict | None:
    fallback = None
    for page in doc.pages:
        text = _flat(page.text)
        for m in _AREA_RE.finditer(text):
            number = float(m.group(1).replace(",", ""))
            if number <= 0:
                continue
            unit, factor = _unit_info(m.group(2))
            fld = _field({"amount": number, "unit": unit,
                          "sq_m": round(number * factor, 2) if factor else None,
                          "text": _flat(m.group(0)).rstrip(". ")}, page.number, text, m.start(), m.end())
            context = text[max(0, m.start() - 70):m.start()].lower()
            if re.search(r"area|measur|admeasur|क्षेत्रफल|रकबा|plot|size|total", context):
                return fld
            fallback = fallback or fld
    return fallback


DIRECTIONS = {"north": ("north", "उत्तर"), "south": ("south", "दक्षिण"), "east": ("east", "पूर्व"), "west": ("west", "पश्चिम")}


def _boundaries(doc: ProcessedDocument) -> dict:
    out: dict[str, dict] = {}
    all_words = "|".join(w for words in DIRECTIONS.values() for w in words)
    for page in doc.pages:
        # A boundary on its own line ends at the line end, whatever follows it.
        for key, words in DIRECTIONS.items():
            m = re.search(rf"(?im)^[ \t]*(?:on the\s+)?(?:{'|'.join(words)})(?:\s+side)?(?:\s+by)?\s*[:\-–—]\s*(.{{3,90}})$", page.text)
            if m and key not in out:
                out[key] = _field(m.group(1).strip(" ,;.|"), page.number, page.text, m.start(), m.end())
        text = _flat(page.text)
        for key, words in DIRECTIONS.items():
            if key in out:
                continue
            word = "|".join(words)
            m = re.search(
                rf"(?:\bon the\s+|\bon\s+|towards?\s+(?:the\s+)?)?(?<![A-Za-z\-])(?:{word})(?:\s+side)?(?:\s+by)?\s*[:\-–—]\s*"
                rf"(.{{3,70}}?)(?=\s*(?:;|(?<!No)\.(?:\s|$)|,?\s*(?:on the\s+)?(?:{all_words})(?:\s+side)?(?:\s+by)?\s*[:\-–—]|$))",
                text, re.I)
            if not m:
                m = re.search(rf"\bon the\s+(?:{word})\s+by\s+(.{{3,70}}?)(?=\s*(?:;|(?<!No)\.(?:\s|$)|,?\s*(?:and\s+)?on the\s+(?:{all_words})|$))", text, re.I)
            if m:
                out[key] = _field(m.group(1).strip(" ,"), page.number, text, m.start(), m.end())
    return out


# OCR often turns "Rs." into "Rs," or "Rs:" and a 1 into an l.
AMOUNT = r"(?:Rs[\W_]{0,3}|INR|₹|रु\.?|रुपये)\s*([0-9][0-9,]*(?:\.\d+)?)"


def _amount(doc: ProcessedDocument, contexts: list[str]) -> dict | None:
    for context in contexts:
        for page in doc.pages:
            text = _flat(page.text)
            m = re.search(rf"(?:{context})[^.;]{{0,80}}?{AMOUNT}", text, re.I)
            if m:
                value = parse_amount(m.group(1))
                if value:
                    return _field({"amount": value, "display": format_inr(value)}, page.number, text, m.start(), m.end())
    return None


def _date_near(doc: ProcessedDocument, patterns: list[str]) -> dict | None:
    for pattern in patterns:
        for page in doc.pages:
            text = _flat(page.text)
            m = re.search(rf"(?:{pattern})[^.;\n]{{0,40}}?({DATE_RE})", text, re.I)
            if m:
                parsed = parse_date(m.group(1))
                if parsed:
                    return _field(parsed.isoformat(), page.number, text, m.start(), m.end())
    return None


def _mentions(doc: ProcessedDocument, pattern: str, limit: int = 6) -> list[dict]:
    """Sentences that contain a pattern, with their page."""
    out: list[dict] = []
    seen: set[str] = set()
    for page in doc.pages:
        for sentence in re.split(r"(?<=[.;।])\s+|\n", page.text):
            if re.search(pattern, sentence, re.I):
                clean = _flat(sentence).strip()
                if len(clean) > 8 and clean.lower() not in seen:
                    seen.add(clean.lower())
                    out.append({"value": clean[:280], "page": page.number, "evidence": clean[:280], "method": "rule"})
                    if len(out) >= limit:
                        return out
    return out


MORTGAGE = r"mortgag|hypothecat|equitable charge|\bcharge (?:created|in favou?r)|\blien\b|home loan|housing loan|loan account|बंधक|रेहन|\bgirvi\b|गिरवी"
RELEASE = r"\brelease(?:d)? (?:deed|of (?:mortgage|charge))|reconvey|no[- ]dues|mortgage (?:has been )?(?:redeemed|discharged|released|satisfied)|satisfaction of charge|loan (?:has been )?(?:closed|repaid)|बंधक मुक्त"
NEGATED = r"\b(?:no|not|nil|without|free from|free of|neither|nor)\b[^.;]{0,50}"
LITIGATION = r"\b(?:civil|original|title|partition)? ?suit\b|\bo\.?s\.? no|writ petition|\blitigation\b|\bstay order\b|\bstatus quo\b|\binjunction\b|\blis pendens\b|\battachment\b|court case|pending before|\bdispute[ds]?\b|वाद संख्या|न्यायालय|मुकदमा"
INHERIT = r"\binherit|legal heirs?|\bheirship\b|\bsuccession\b|\bdeceased\b|\bwill dated\b|\bexpired\b|\bvarasat\b|\bvirasat\b|वरासत|विरासत|उत्तराधिकार|\bcoparcen|\bancestral\b|\bintestate\b"
LAND_USE = r"\bagricultural (?:land|use)\b|\bnon[- ]agricultural\b|\bn\.?a\.? (?:order|permission|conversion)\b|\bland[- ]use\b|\bconversion\b|\bgreen belt\b|\bforest land\b|\bmaster plan\b|\bzoning\b|कृषि भूमि|भूमि उपयोग"
PERMISSIONS = r"\boccupancy certificate\b|\bcompletion certificate\b|\bsanction(?:ed)? (?:building )?plan\b|\bbuilding plan\b|\brera (?:registration|no)\b|\bn\.?o\.?c\.?\b|\bno objection\b|\bfire (?:noc|clearance)\b"
POSSESSION = r"\bpossession\b|कब्जा|कब्ज़ा"
SHARES = r"(?:\b\d+/\d+(?:th|rd|nd)?\s*(?:undivided\s+)?share\b|\b\d+(?:\.\d+)?\s*%\s*(?:undivided\s+)?share\b|\bundivided share\b|\bjoint owners?\b|\bco-owners?\b|\bहिस्सा\b)"


def _not_negated(items: list[dict], word_pattern: str) -> list[dict]:
    """Drop mentions such as 'free from all mortgages', keeping real references."""
    kept = []
    for item in items:
        if re.search(NEGATED + rf"(?:{word_pattern})", item["value"], re.I):
            continue
        kept.append(item)
    return kept


_PRIOR_CONTEXT = re.compile(r"purchased|acquired|inherited|earlier|previous|by (?:a |an )?registered|vide (?:a |an )?(?:registered )?(?:sale|gift)|from [A-Z]", re.I)


def _registration(doc: ProcessedDocument) -> dict:
    """This document's own registration. Numbers quoted about an earlier deed are skipped."""
    reg: dict[str, dict] = {}
    pattern = r"(?:registration|registered|regn\.?|reg\.?|document|doc\.?|deed|serial|instrument)\s*(?:as\s+)?(?:document\s+)?(?:no|number|sr\.? no)\.?\s*[:.\-]?\s*([A-Z0-9][A-Z0-9/\-]*\d[A-Z0-9/\-]*(?:\s+of\s+\d{4})?)"
    last = None
    for page in doc.pages:
        text = _flat(page.text)
        for m in re.finditer(pattern, text, re.I):
            sentence_start = max(text.rfind(". ", 0, m.start()), text.rfind("; ", 0, m.start())) + 1
            if _PRIOR_CONTEXT.search(text[sentence_start:m.start()]):
                continue
            last = _field(re.sub(r"\s+of\s+", "/", m.group(1)), page.number, text, m.start(), m.end())
    if last:
        reg["document_no"] = last
    patterns = {
        "book_no": [r"book\s*(?:no\.?|number)?\s*[:.\-]?\s*([0-9IVX]+)\b"],
        "volume_no": [r"(?:volume|vol\.?|jild|जिल्द)\s*(?:no\.?|number)?\s*[:.\-]?\s*([0-9A-Z]+)\b"],
        "pages": [r"pages?\s*(?:no\.?|nos\.?)?\s*[:.\-]?\s*(\d+\s*(?:to|-|–)\s*\d+)"],
    }
    for key, pats in patterns.items():
        hit = _first(doc, pats)
        if hit:
            value, page, text, start, end = hit
            reg[key] = _field(value, page, text, start, end)
    return reg


def _prior_deeds(doc: ProcessedDocument) -> list[dict]:
    """References to an earlier deed, which tell us what the ownership chain should contain."""
    out = []
    pattern = (rf"(?:by|vide|through|under|means of)\s+(?:a\s+|an\s+|the\s+)?(?:registered\s+)?(sale deed|gift deed|conveyance deed|partition deed|will|relinquishment deed|deed)\b"
               rf"[^.;]{{0,120}}?(?:dated|executed on|registered on)\s*({DATE_RE})[^.;]{{0,120}}")
    for page in doc.pages:
        text = _flat(page.text)
        for m in re.finditer(pattern, text, re.I):
            parsed = parse_date(m.group(2))
            sentence = m.group(0)
            frm = re.search(rf"\bfrom\s+({NAME})", sentence)
            no = re.search(r"(?:document|doc\.?|registration|deed)\s*no\.?\s*[:.\-]?\s*([A-Z0-9/\-]*\d[A-Z0-9/\-]*)", sentence, re.I)
            out.append({"deed_type": m.group(1).lower(), "date": parsed.isoformat() if parsed else None,
                        "from": clean_name(frm.group(1)) if frm else None,
                        "document_no": no.group(1) if no else None,
                        "page": page.number, "evidence": _snippet(text, m.start(), m.end(), 20), "method": "rule"})
    return out


def _previous_owners(doc: ProcessedDocument, prior: list[dict]) -> list[dict]:
    out: dict[str, dict] = {}
    for ref in prior:
        if ref.get("from"):
            out[ref["from"]] = {"value": ref["from"], "page": ref["page"], "evidence": ref["evidence"], "method": "rule"}
    for page in doc.pages:
        text = _flat(page.text)
        for m in re.finditer(rf"(?:purchased from|acquired from|earlier owned by|previously owned by|previous owner\s*[:\-]|erstwhile owner\s*[:\-]|inherited from|gifted by)\s+({NAME})", text, re.I):
            name = clean_name(m.group(1))
            if name and name not in out:
                out[name] = _field(name, page.number, text, m.start(), m.end())
    return list(out.values())


def _address(doc: ProcessedDocument) -> dict | None:
    hit = _first(doc, [
        r"(?:property address|address of (?:the )?property|location of (?:the )?property|property (?:details|situated)|premises)\s*[:\-]\s*(.{10,160}?)(?=\s*(?:\.\s|;|Khasra|Survey|Area|Total|Boundar|North|$))",
        r"(?:situated|situate|located|lying)\s+(?:at|in)\s+(.{10,160}?)(?=\s*(?:\.\s|;|,?\s*(?:hereinafter|measuring|admeasuring|having|bounded|Khasra|Survey)|$))",
    ])
    if not hit:
        return None
    value, page, text, start, end = hit
    return _field(value.strip(" ,"), page, text, start, end)


def _lease(doc: ProcessedDocument) -> dict:
    lease: dict = {}
    rent = _amount(doc, [r"monthly rent", r"rent of", r"lease rent", r"licen[cs]e fee", r"rent\b"])
    if rent:
        lease["monthly_rent"] = rent
    deposit = _amount(doc, [r"security deposit", r"refundable deposit", r"\bdeposit\b"])
    if deposit:
        lease["security_deposit"] = deposit
    words = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10, "eleven": 11, "twelve": 12,
             "eighteen": 18, "twenty": 20, "twenty-one": 21, "twenty-two": 22, "twenty-three": 23, "twenty-four": 24, "thirty": 30, "thirty-six": 36, "forty-eight": 48, "sixty": 60}
    number = r"\d{1,3}|" + "|".join(sorted(words, key=len, reverse=True))
    for page in doc.pages:
        text = _flat(page.text)
        m = (re.search(rf"(?:period|term|duration|tenure)\s+(?:of\s+)?(?:this\s+\w+\s+)?(?:is\s+|shall be\s+|:\s*|-\s*)?(?:for\s+|of\s+)?(?:a\s+period\s+of\s+)?({number})\s*(?:\(\w+\)\s*)?(months?|years?)", text, re.I)
             or re.search(rf"\bfor\s+(?:a\s+(?:period|term)\s+of\s+)?({number})\s*(?:\(\w+\)\s*)?(months?|years?)\b", text, re.I)
             or re.search(rf"\b({number})\s*(?:\(\w+\)\s*)?(months?|years?)\s+(?:from|commencing|starting|beginning)\b", text, re.I))
        if m:
            value = m.group(1).lower()
            n = int(value) if value.isdigit() else words[value]
            months = n * 12 if m.group(2).lower().startswith("year") else n
            lease["term_months"] = _field(months, page.number, text, m.start(), m.end())
            break
    start = _date_near(doc, [r"commenc\w+", r"starting from", r"with effect from", r"effective from", r"(?:months?|years?) from", r"beginning"])
    if start:
        lease["start_date"] = start
    return lease


def _ec(doc: ProcessedDocument) -> dict:
    out: dict = {}
    for page in doc.pages:
        text = _flat(page.text)
        m = re.search(rf"(?:period|from)\D{{0,30}}?({DATE_RE})\s*(?:to|till|until|-|–)\s*({DATE_RE})", text, re.I)
        if m:
            a, b = parse_date(m.group(1)), parse_date(m.group(2))
            if a and b:
                out["search_period"] = _field({"from": a.isoformat(), "to": b.isoformat()}, page.number, text, m.start(), m.end())
                break
    nil = _first(doc, [r"(nil encumbrance|no encumbrance|no entries (?:found|were found)|nil entries|no acts? or charges?)"])
    if nil:
        value, page, text, start, end = nil
        out["nil_statement"] = _field(value, page, text, start, end)
    return out


def extract(doc: ProcessedDocument) -> ProcessedDocument:
    """Fill doc.fields. Roles depend on the document type, so a landlord is never called a seller."""
    t = doc.doc_type
    f: dict = {}

    if doc.status in ("unreadable", "error"):
        doc.fields = {"extraction_skipped": "Document could not be read."}
        return doc

    if t in ("sale_deed", "agreement_to_sell", "mutation_record", "encumbrance_certificate", "other"):
        f["sellers"] = _names(doc, r"seller|sellers|vendor|vendors|transferor|transferors|executant|first party|previous owner|old owner|पूर्व स्वामी", r"vendors?|sellers?|first party|transferors?")
        f["buyers"] = _names(doc, r"buyer|buyers|vendee|vendees|purchaser|purchasers|transferee|transferees|claimant|second party|new owner|नया स्वामी", r"vendees?|buyers?|purchasers?|second party|transferees?")
    if t == "gift_deed":
        f["sellers"] = _names(doc, r"donor|donors", r"donors?")
        f["buyers"] = _names(doc, r"donee|donees", r"donees?")
    if t == "partition_deed":
        f["owners"] = _names(doc, r"(?:first|second|third|fourth)? ?party|allottee|sharer", r"parties|party")
    if t in ("rent_agreement", "lease_deed"):
        f["landlord"] = _names(doc, r"landlord|lessor|licensor|owner", r"landlord|lessor|licensor|first party")
        f["tenant"] = _names(doc, r"tenant|lessee|licensee", r"tenant|lessee|licensee|second party")
        f["lease"] = _lease(doc)
    if t == "power_of_attorney":
        f["poa_principal"] = _names(doc, r"principal|executant|donor|grantor", r"principal|executant|donor")
        f["poa_attorney"] = _names(doc, r"attorney|attorney holder|agent|power of attorney holder|grantee", r"attorney|agent|attorney holder")
        for page in doc.pages:
            text = _flat(page.text)
            if not f["poa_principal"]:
                m = re.search(rf"\bI,?\s+((?:{TITLE}\s+)?{NAME_WORD}(?:\s+{NAME_WORD}){{0,4}})", text)
                name = clean_name(m.group(1)) if m else None
                if name:
                    f["poa_principal"] = [_field(name, page.number, text, m.start(), m.end())]
            if not f["poa_attorney"]:
                m = re.search(rf"\b(?:appoint|nominate|constitute|authori[sz]e)s?\s+(?:and \w+\s+)?(?:my \w+\s+|his \w+\s+|her \w+\s+)?((?:{TITLE}\s+)?{NAME_WORD}(?:\s+{NAME_WORD}){{0,4}})", text)
                name = clean_name(m.group(1)) if m else None
                if name:
                    f["poa_attorney"] = [_field(name, page.number, text, m.start(), m.end())]
        f["poa_kind"] = "general" if re.search(r"general power of attorney|\bgpa\b", doc.full_text, re.I) else (
            "special" if re.search(r"special power of attorney|\bspa\b", doc.full_text, re.I) else "not stated")
    if t in ("land_record", "property_tax_receipt", "mutation_record", "noc", "rera_document", "encumbrance_certificate", "other"):
        owners = _names(doc, r"owner|owners|name of owner|assessee|taxpayer|tax payer|khatedar|khatadar|tenure holder|recorded owner|account holder|occupier|in favou?r of|applicant|promoter")
        owners += _hindi_names(doc, r"खातेदार(?:\s*का\s*नाम)?|भूमिधर|स्वामी(?:\s*का\s*नाम)?")
        f["owners"] = owners
    if t == "mutation_record":
        f["buyers"] = f.get("buyers") or _hindi_names(doc, r"नया स्वामी|अंतरिती|क्रेता")
        f["sellers"] = f.get("sellers") or _hindi_names(doc, r"पूर्व स्वामी|अंतरक|विक्रेता")
    if t == "will":
        f["owners"] = _names(doc, r"testator", r"testator")

    prior = _prior_deeds(doc)
    f["prior_deed_refs"] = prior
    f["previous_owners"] = _previous_owners(doc, prior)
    f["property_address"] = _address(doc)
    f["survey_numbers"] = _numbers(doc, r"khasra|खसरा|survey|सर्वे|gata|गाटा|gat|r\.?s\.?|dag")
    f["plot_numbers"] = _numbers(doc, r"plot|प्लॉट|भूखंड|house|flat|unit|property id|property")
    f["khata_numbers"] = _numbers(doc, r"khata|खाता|khatauni|खतौनी|khewat|ledger")
    f["area"] = _area(doc)
    f["boundaries"] = _boundaries(doc)

    contexts = [r"(?:total |sale |agreed |full )?consideration", r"sale price", r"price of", r"sum of", r"amount of", r"बैनामा (?:राशि|मूल्य)", r"प्रतिफल"]
    if t in ("sale_deed", "agreement_to_sell", "mutation_record", "encumbrance_certificate", "gift_deed", "other"):
        f["transaction_amount"] = _amount(doc, contexts)
    if t == "agreement_to_sell":
        f["earnest_money"] = _amount(doc, [r"earnest money", r"advance", r"bayana", r"token"])
    if t == "property_tax_receipt":
        f["tax_paid"] = _amount(doc, [r"(?:amount|tax) (?:paid|received)", r"total (?:amount|tax)", r"amount"])
        f["assessment_year"] = None
        hit = _first(doc, [r"(?:assessment|financial|tax)\s+year\s*[:\-]?\s*(\d{4}\s*[-–/]\s*\d{2,4})"])
        if hit:
            value, page, text, start, end = hit
            f["assessment_year"] = _field(value, page, text, start, end)
        f["receipt_date"] = _date_near(doc, [r"(?:receipt|payment)\s+date", r"date of (?:receipt|payment)", r"dated"])
    f["stamp_duty"] = _amount(doc, [r"stamp duty", r"stamp paper", r"e-?stamp", r"स्टाम्प"])

    # An EC lists many deeds, so none of those numbers is the certificate's own registration.
    f["registration"] = _registration(doc) if t != "encumbrance_certificate" else {}
    f["execution_date"] = _date_near(doc, [r"date of execution", r"execution date", r"executed (?:at [A-Za-z ]+ )?on", r"(?:made|entered into)[^.;]{0,30}?on", r"this deed[^.;]{0,30}?on", r"दिनांक"])
    f["registration_date"] = _date_near(doc, [r"date of registration", r"registration date", r"registered on", r"presented[^.;]{0,30}?on"])
    if t == "mutation_record":
        f["mutation_order_date"] = _date_near(doc, [r"(?:date of )?(?:mutation )?order(?: date)?", r"order dated", r"mutation dated", r"आदेश दिनांक", r"दिनांक"])
        hit = _first(doc, [r"mutation\s*(?:case|order|entry)?\s*no\.?\s*[:.\-]?\s*([A-Z0-9/\-]*\d[A-Z0-9/\-]*)", r"(?:case|entry)\s*no\.?\s*[:.\-]?\s*([A-Z0-9/\-]*\d[A-Z0-9/\-]*)"])
        if hit:
            value, page, text, start, end = hit
            f["mutation_no"] = _field(value, page, text, start, end)
    if t == "encumbrance_certificate":
        f["ec"] = _ec(doc)
        f["ec_date"] = _date_near(doc, [r"date of issue", r"issued on", r"certificate date", r"dated"])

    # Flattened text, cut at words that begin the next item, so a following heading is not swallowed.
    hit = None
    for page in doc.pages:
        text = _flat(page.text)
        m = re.search(r"(?i:sub[- ]?registrar\s*(?:office)?)\s*[,:\-–]?\s*(?:of\s+|at\s+)?([A-Z][A-Za-z\-]*(?:\s+[A-Z][A-Za-z\-]*){0,3})", text)
        if m:
            value = re.split(r"\s+(?:on|dated|as|in|vide|Book|Date|Document|Registration|Certificate|Search|Stamp|Signed|Serial)\b", m.group(1))[0]
            hit = (value, page.number, text, m.start(), m.end())
            break
    if hit:
        value, page, text, start, end = hit
        f["sub_registrar"] = _field(value.strip(), page, text, start, end)

    f["ownership_shares"] = _mentions(doc, SHARES, 4)
    f["possession_details"] = _mentions(doc, POSSESSION, 3)
    f["mortgage_refs"] = _not_negated(_mentions(doc, MORTGAGE), MORTGAGE)
    f["release_refs"] = _mentions(doc, RELEASE)
    f["litigation_refs"] = _not_negated(_mentions(doc, LITIGATION), LITIGATION)
    f["inheritance_refs"] = _mentions(doc, INHERIT, 4)
    f["land_use_refs"] = _mentions(doc, LAND_USE, 4)
    f["permission_refs"] = _mentions(doc, PERMISSIONS, 4)
    doc.fields = f
    return doc


def value_of(item):
    """Convenience: the value of a field dict, or None."""
    return item.get("value") if isinstance(item, dict) else None


def as_date(item) -> date | None:
    value = value_of(item)
    try:
        return datetime.strptime(value, "%Y-%m-%d").date() if value else None
    except (TypeError, ValueError):
        return None
