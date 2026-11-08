"""Legal assistant for English, Hindi and Hinglish.

Without a language model it answers from extracted facts and quotes retrieved passages,
and it says so. With a model, the reply must pass citation checks or the quoted answer is used.
"""
from __future__ import annotations

import re

from core.ai_engine import NO_MODEL, get_provider
from core.citation_validator import validate_answer
from core.document_comparator import compare_all
from core.legal_retrieval import get_retriever
from core.models import ProcessedDocument
from core.prompts import ASSISTANT_TEMPLATE, SYSTEM_ASSISTANT

HINGLISH_WORDS = set("kya hai hain kaun kitna kitni kaise kab kyu kyun mein mera meri mere ka ki ke ko se par aur ya nahi nahin koi hota hoti karna karein batao bataiye chahiye zaroori ye yeh iska uska zameen ghar makan".split())


def detect_language(text: str) -> str:
    if re.search(r"[ऀ-ॿ]", text):
        return "hi"
    words = re.findall(r"[a-z]+", text.lower())
    if sum(w in HINGLISH_WORDS for w in words) >= 2 or (words and sum(w in HINGLISH_WORDS for w in words) / len(words) >= 0.25):
        return "hinglish"
    return "en"


T = {
    "en": {
        "not_verified": "This is what the document states. It is not independently verified ownership.",
        "not_found": "I could not find that in the uploaded documents. That does not mean it does not exist, so please check the original papers.",
        "no_docs": "No documents are uploaded yet, so I cannot tell you that. Upload your documents on the Upload page, and I will answer from them.",
        "law_not_found": "I could not find that in the legal sources BhoomiCheck has collected, so I will not guess. Please check with a lawyer or on India Code.",
        "refuse": "I cannot certify or guarantee this. No one can confirm clear title, safety or the absence of litigation from these papers alone. BhoomiCheck only flags what the documents show.",
        "lawyer": "Please have a qualified property lawyer verify this before you pay or sign.",
        "law_intro": "Here is what the collected legal sources say. These are direct extracts, not legal advice:",
        "no_llm": "No language model is connected, so this answer uses extracted facts and direct quotes only.",
        "findings_intro": "BhoomiCheck's checks found the following:",
        "no_findings": "The checks found no such issue in what could be read. That does not prove there is none.",
        "out_of_scope": "I can only help with Indian property documents and related law. Please ask about your property papers.",
        "seller": "The seller named in {doc} is {value}", "buyer": "The buyer named in {doc} is {value}", "owner": "The owner named in {doc} is {value}",
        "area": "The area stated in {doc} is {value}", "survey": "The survey or Khasra number in {doc} is {value}", "khata": "The Khata number in {doc} is {value}",
        "amount": "The transaction amount in {doc} is {value}", "execution_date": "The execution date in {doc} is {value}", "registration_date": "The registration date in {doc} is {value}",
        "document_no": "The registration document number in {doc} is {value}", "address": "The property address in {doc} is {value}", "sub_registrar": "The Sub-Registrar office in {doc} is {value}",
        "landlord": "The landlord named in {doc} is {value}", "tenant": "The tenant named in {doc} is {value}", "rent": "The monthly rent in {doc} is {value}", "deposit": "The security deposit in {doc} is {value}", "term": "The period in {doc} is {value} months",
        "boundary": "The {direction} boundary in {doc} is {value}", "doc_type": "{doc} looks like a {value}",
    },
    "hi": {
        "not_verified": "यह वही है जो दस्तावेज़ में लिखा है। इससे स्वामित्व की स्वतंत्र पुष्टि नहीं होती।",
        "not_found": "अपलोड किए गए दस्तावेज़ों में यह जानकारी नहीं मिली। इसका मतलब यह नहीं कि वह मौजूद नहीं है, कृपया मूल कागज़ देखें।",
        "no_docs": "अभी कोई दस्तावेज़ अपलोड नहीं है, इसलिए मैं यह नहीं बता सकता। अपलोड पेज पर दस्तावेज़ डालें।",
        "law_not_found": "BhoomiCheck के कानूनी स्रोतों में यह नहीं मिला, इसलिए मैं अनुमान नहीं लगाऊँगा। कृपया वकील से या India Code पर जाँचें।",
        "refuse": "मैं इसकी पुष्टि या गारंटी नहीं दे सकता। केवल इन कागज़ों से कोई भी साफ़ स्वामित्व, सुरक्षा या मुकदमा न होने की पुष्टि नहीं कर सकता। BhoomiCheck केवल वही बताता है जो दस्तावेज़ों में दिखता है।",
        "lawyer": "पैसे देने या हस्ताक्षर करने से पहले किसी योग्य संपत्ति वकील से जाँच करवाएँ।",
        "law_intro": "संग्रहित कानूनी स्रोतों में यह लिखा है। ये सीधे उद्धरण (अंग्रेज़ी में) हैं, कानूनी सलाह नहीं:",
        "no_llm": "कोई भाषा मॉडल जुड़ा नहीं है, इसलिए यह उत्तर केवल निकाले गए तथ्यों और सीधे उद्धरणों पर आधारित है।",
        "findings_intro": "BhoomiCheck की जाँच में यह मिला:",
        "no_findings": "जो पढ़ा जा सका उसमें ऐसी कोई बात नहीं मिली। इससे यह सिद्ध नहीं होता कि ऐसा कुछ नहीं है।",
        "out_of_scope": "मैं केवल भारतीय संपत्ति दस्तावेज़ों और उनसे जुड़े कानून में मदद कर सकता हूँ।",
        "seller": "{doc} में विक्रेता का नाम {value} है", "buyer": "{doc} में क्रेता का नाम {value} है", "owner": "{doc} में मालिक का नाम {value} है",
        "area": "{doc} में क्षेत्रफल {value} लिखा है", "survey": "{doc} में खसरा/सर्वे संख्या {value} है", "khata": "{doc} में खाता संख्या {value} है",
        "amount": "{doc} में सौदे की राशि {value} है", "execution_date": "{doc} में निष्पादन की तिथि {value} है", "registration_date": "{doc} में रजिस्ट्री की तिथि {value} है",
        "document_no": "{doc} में रजिस्ट्री दस्तावेज़ संख्या {value} है", "address": "{doc} में संपत्ति का पता {value} है", "sub_registrar": "{doc} में उप-पंजीयक कार्यालय {value} है",
        "landlord": "{doc} में मकान मालिक {value} है", "tenant": "{doc} में किरायेदार {value} है", "rent": "{doc} में मासिक किराया {value} है", "deposit": "{doc} में सिक्योरिटी डिपॉज़िट {value} है", "term": "{doc} में अवधि {value} महीने है",
        "boundary": "{doc} में {direction} सीमा {value} है", "doc_type": "{doc} संभवतः {value} है",
    },
    "hinglish": {
        "not_verified": "Yeh wahi hai jo document mein likha hai. Isse ownership ki independent verification nahi hoti.",
        "not_found": "Uploaded documents mein yeh nahi mila. Iska matlab yeh nahi ki woh exist nahi karta, please original papers check karein.",
        "no_docs": "Abhi koi document upload nahi hai, isliye main yeh nahi bata sakta. Upload page par documents daalein.",
        "law_not_found": "BhoomiCheck ke legal sources mein yeh nahi mila, isliye main guess nahi karunga. Please lawyer se ya India Code par check karein.",
        "refuse": "Main iski guarantee ya certification nahi de sakta. Sirf in papers se koi bhi clear title, safety ya litigation na hone ki confirmation nahi de sakta. BhoomiCheck sirf wahi batata hai jo documents mein dikhta hai.",
        "lawyer": "Payment ya sign karne se pehle kisi qualified property lawyer se verify zaroor karwayein.",
        "law_intro": "Collected legal sources mein yeh likha hai. Yeh direct extracts hain (English mein), legal advice nahi:",
        "no_llm": "Koi language model connected nahi hai, isliye yeh answer sirf extracted facts aur direct quotes par based hai.",
        "findings_intro": "BhoomiCheck ke checks mein yeh mila:",
        "no_findings": "Jo padha ja saka usme aisa kuch nahi mila. Isse yeh prove nahi hota ki aisa kuch nahi hai.",
        "out_of_scope": "Main sirf Indian property documents aur related law mein help kar sakta hoon.",
        "seller": "{doc} mein seller ka naam {value} hai", "buyer": "{doc} mein buyer ka naam {value} hai", "owner": "{doc} mein owner ka naam {value} hai",
        "area": "{doc} mein area {value} likha hai", "survey": "{doc} mein Khasra/Survey number {value} hai", "khata": "{doc} mein Khata number {value} hai",
        "amount": "{doc} mein transaction amount {value} hai", "execution_date": "{doc} mein execution date {value} hai", "registration_date": "{doc} mein registration date {value} hai",
        "document_no": "{doc} mein registration document number {value} hai", "address": "{doc} mein property address {value} hai", "sub_registrar": "{doc} mein Sub-Registrar office {value} hai",
        "landlord": "{doc} mein landlord {value} hai", "tenant": "{doc} mein tenant {value} hai", "rent": "{doc} mein monthly rent {value} hai", "deposit": "{doc} mein security deposit {value} hai", "term": "{doc} mein period {value} months hai",
        "boundary": "{doc} mein {direction} boundary {value} hai", "doc_type": "{doc} shayad {value} hai",
    },
}

# Plain definitions written for this app. Each points to where the reader can check it.
TERMS = {
    "mutation": {"keys": ["mutation", "dakhil kharij", "दाखिल खारिज", "दाखिल-खारिज", "namantaran", "नामांतरण", "ferfar", "फेरफार"],
                 "en": "Mutation updates the name in revenue or municipal records after a transfer. It is mainly for revenue purposes, and it does not by itself create or prove ownership.",
                 "hi": "दाखिल खारिज (नामांतरण) का अर्थ है हस्तांतरण के बाद राजस्व या नगर निकाय के रिकॉर्ड में नाम बदलना। यह मुख्यतः राजस्व के लिए होता है, और इससे अपने आप स्वामित्व न तो बनता है और न ही सिद्ध होता है।",
                 "hinglish": "Dakhil kharij (mutation) ka matlab hai transfer ke baad revenue ya municipal record mein naam update karna. Yeh mainly revenue ke liye hota hai, aur isse apne aap ownership na banti hai na prove hoti hai.",
                 "query": "Does a mutation entry confer title to land?"},
    "encumbrance": {"keys": ["encumbrance", "ऋणभार", "bhar mukt", "भार मुक्त"],
                    "en": "An Encumbrance Certificate lists registered transactions on a property for the period searched. It may not reveal every claim, such as unregistered ones.",
                    "hi": "ऋणभार प्रमाणपत्र (EC) खोजी गई अवधि में संपत्ति पर पंजीकृत लेन-देन दिखाता है। यह हर दावा नहीं दिखाता, जैसे अपंजीकृत दावे।",
                    "hinglish": "Encumbrance Certificate search period ke registered transactions dikhata hai. Yeh har claim nahi dikhata, jaise unregistered claims.",
                    "query": "registered documents index search of registers certified copies"},
    "khatauni": {"keys": ["khatauni", "खतौनी", "jamabandi", "जमाबंदी", "khasra", "खसरा"],
                 "en": "Khasra, Khatauni and Jamabandi are revenue records. They show plot numbers and recorded holders, and they are not conclusive proof of title.",
                 "hi": "खसरा, खतौनी और जमाबंदी राजस्व रिकॉर्ड हैं। इनसे प्लॉट नंबर और दर्ज व्यक्ति का पता चलता है, पर ये स्वामित्व का अंतिम प्रमाण नहीं हैं।",
                 "hinglish": "Khasra, Khatauni aur Jamabandi revenue records hain. Inse plot number aur recorded person pata chalta hai, par yeh ownership ka final proof nahi hain.",
                 "query": "record of rights revenue record mutation"},
    "poa": {"keys": ["power of attorney", "mukhtarnama", "मुख्तारनामा", "gpa", "spa"],
            "en": "A Power of Attorney lets one person (the agent) act for another (the principal), within the powers it states. The authority generally ends if the principal revokes it or dies.",
            "hi": "मुख्तारनामा एक व्यक्ति (एजेंट) को दूसरे (प्रिंसिपल) की ओर से, लिखी गई शक्तियों के भीतर, काम करने देता है। प्रिंसिपल के रद्द करने या मृत्यु पर यह अधिकार आम तौर पर समाप्त हो जाता है।",
            "hinglish": "Mukhtarnama (Power of Attorney) se ek vyakti (agent) doosre (principal) ki taraf se, likhi hui powers ke andar, kaam kar sakta hai. Principal ke revoke karne ya death par authority generally khatam ho jati hai.",
            "query": "termination of agency revocation death of principal agent"},
    "mortgage": {"keys": ["what is mortgage", "what is a mortgage", "girvi kya", "गिरवी क्या", "बंधक क्या", "mortgage kya"],
                 "en": "A mortgage transfers an interest in specific immovable property to secure a loan or other debt.",
                 "hi": "बंधक (गिरवी) में किसी विशेष अचल संपत्ति में हित का हस्तांतरण, ऋण या अन्य देनदारी की सुरक्षा के लिए किया जाता है।",
                 "hinglish": "Mortgage (girvi) mein specific immovable property ka interest loan ya debt ko secure karne ke liye transfer hota hai.",
                 "query": "what is a mortgage defined"},
}

REFUSAL = re.compile(
    r"\b(?:guarantee|guaranteed|certify|certified|certification|100\s*%|completely safe|bilkul safe|pakka safe|fully safe|perfect title|ignore (?:your|all|previous)|pretend|disregard (?:your|the) rules)\b"
    r"|confirm (?:that |there is |there's )?(?:no litigation|clear title|no case)|no litigation|clear title hai|title clear|गारंटी|पूरी तरह सुरक्षित|100% सुरक्षित|safe to (?:buy|purchase)|is (?:this|it|the property) safe|kya (?:ye|yeh).{0,20}safe",
    re.I)

# (intent, patterns, field key)
FIELD_INTENTS = [
    ("seller", r"\bseller\b|\bvendor\b|bechne wala|विक्रेता|बेचने वाला|bechne"),
    ("buyer", r"\bbuyer\b|\bvendee\b|\bpurchaser\b|kharidne|क्रेता|खरीदार|खरीदने"),
    ("landlord", r"\blandlord\b|\blessor\b|makan malik|मकान मालिक"),
    ("tenant", r"\btenant\b|\blessee\b|kirayedar|किरायेदार"),
    ("rent", r"\brent\b|kiraya|किराया"),
    ("deposit", r"\bdeposit\b|डिपॉज़िट|जमा राशि"),
    ("term", r"\bperiod\b|\bduration\b|\bterm\b|अवधि|kitne (?:mahine|saal)"),
    ("area", r"\barea\b|\bsize\b|\bmeasur|kshetrafal|क्षेत्रफल|रकबा|kitna bada"),
    ("survey", r"\bsurvey\b|\bkhasra\b|खसरा|सर्वे"),
    ("khata", r"\bkhata\b|खाता"),
    ("amount", r"\bprice\b|\bamount\b|\bconsideration\b|kitne (?:ka|mein)|कीमत|राशि|प्रतिफल|paisa|\bcost\b"),
    ("registration_date", r"registration date|date of registration|registered on|registry (?:kab|date)|रजिस्ट्री (?:कब|की तिथि)"),
    ("execution_date", r"execution date|date of execution|executed on|निष्पादन"),
    ("document_no", r"document (?:no|number)|registration (?:no|number)|दस्तावेज़ संख्या"),
    ("sub_registrar", r"sub[- ]?registrar|उप-?पंजीयक"),
    ("address", r"\baddress\b|\blocation\b|where is|पता|kahan hai"),
    ("boundary", r"\bboundar|\bchauhaddi\b|चौहद्दी|सीमा"),
    ("doc_type", r"what (?:kind|type) of document|what is this document|yeh kaun sa document|कौन सा दस्तावेज़"),
    ("owner", r"\bowner\b|\bmalik\b|मालिक|स्वामी|khatedar|खातेदार"),
]
RISK_INTENT = re.compile(r"\brisk|\bproblem|\bissue|\bmismatch|\bmatch\b|\bcompare|\bconflict|\bdiffer|dikkat|samasya|समस्या|जोखिम|मेल|\bgirvi\b|गिरवी|बंधक|\bmortgage|\bloan\b|कर्ज|\bkarz\b|\bencumbr|litigation|\bcase\b|mukadma|मुकदमा|\bmissing\b|\bpoa\b|attorney", re.I)
TOPIC_FILTERS = [
    (re.compile(r"mortgage|\bloan\b|girvi|गिरवी|बंधक|कर्ज|karz|encumbr", re.I), {"encumbrance"}),
    (re.compile(r"litigation|\bcase\b|mukadma|मुकदमा|\bsuit\b", re.I), {"litigation"}),
    (re.compile(r"owner|malik|मालिक|\bname\b|\bnaam\b", re.I), {"ownership", "ownership_chain"}),
    (re.compile(r"survey|khasra|खसरा|\barea\b", re.I), {"property_identity"}),
    (re.compile(r"\bpoa\b|attorney|mukhtar|मुख्तार", re.I), {"poa"}),
    (re.compile(r"missing|nahi hai|upload", re.I), {"missing_documents", "ownership_chain"}),
]
UNSUPPORTED_FACTS = re.compile(r"\bpan\b|aadhaar|aadhar|आधार|\bphone\b|\bmobile\b|\bemail\b|bank account|\bage of\b|पैन", re.I)
DOMAIN = re.compile(
    r"propert|land|deed|sale|sell|buy|purchase|mortgage|lease|rent|tenant|landlord|title|owner|register|registration|stamp|mutation|khasra|khata|encumbr|attorney|agent|will\b|inherit|succession|heir|gift|partition|possession|suit|limitation|rera|builder|flat|promoter|apartment|contract|section|act\b|registry|girvi|zameen|makan|bainama|kiraya|virasat|mukhtar|"
    r"[ऀ-ॿ]*(?:संपत्ति|जमीन|ज़मीन|बैनामा|रजिस्ट्री|बंधक|गिरवी|किराय|वारिस|विरासत|वसीयत|दान|मुख्तार|खसरा|खतौनी|खाता|दाखिल|कब्ज|मालिक|धारा|कानून|स्टाम्प|बंटवारा|बिल्डर|फ्लैट)", re.I)


def _cite(document: str, page) -> str:
    return f"[{document}, p.{page}]" if page else f"[{document}]"


def _field_values(doc: ProcessedDocument, intent: str) -> list[tuple[str, int | None, dict]]:
    """Return (display value, page, extras) tuples for one kind of fact in one document."""
    f = doc.fields
    def items(key):
        return [(i["value"], i.get("page"), {}) for i in f.get(key) or []]
    if intent == "seller":
        return items("sellers")
    if intent == "buyer":
        return items("buyers")
    if intent == "owner":
        return items("owners") or items("buyers")
    if intent == "landlord":
        return items("landlord")
    if intent == "tenant":
        return items("tenant")
    if intent == "survey":
        return items("survey_numbers")
    if intent == "khata":
        return items("khata_numbers")
    if intent == "area" and f.get("area"):
        return [(f["area"]["value"]["text"].rstrip(". "), f["area"]["page"], {})]
    if intent == "amount" and f.get("transaction_amount"):
        return [(f["transaction_amount"]["value"]["display"], f["transaction_amount"]["page"], {})]
    if intent in ("execution_date", "registration_date") and f.get(intent):
        return [(f[intent]["value"], f[intent]["page"], {})]
    if intent == "document_no" and (f.get("registration") or {}).get("document_no"):
        item = f["registration"]["document_no"]
        return [(item["value"], item["page"], {})]
    if intent == "sub_registrar" and f.get("sub_registrar"):
        return [(f["sub_registrar"]["value"], f["sub_registrar"]["page"], {})]
    if intent == "address" and f.get("property_address"):
        return [(f["property_address"]["value"], f["property_address"]["page"], {})]
    if intent == "boundary":
        return [(v["value"], v["page"], {"direction": k}) for k, v in (f.get("boundaries") or {}).items()]
    lease = f.get("lease") or {}
    if intent == "rent" and lease.get("monthly_rent"):
        return [(lease["monthly_rent"]["value"]["display"], lease["monthly_rent"]["page"], {})]
    if intent == "deposit" and lease.get("security_deposit"):
        return [(lease["security_deposit"]["value"]["display"], lease["security_deposit"]["page"], {})]
    if intent == "term" and lease.get("term_months"):
        return [(str(lease["term_months"]["value"]), lease["term_months"]["page"], {})]
    if intent == "doc_type":
        return [(doc.doc_type_label, 1, {})]
    return []


def _document_facts(docs: list[ProcessedDocument]) -> str:
    lines = []
    for doc in docs:
        lines.append(f"Document {doc.name} ({doc.doc_type_label}, status {doc.status}):")
        for intent, _ in FIELD_INTENTS:
            for value, page, extras in _field_values(doc, intent):
                extra = f" {extras['direction']}" if extras else ""
                lines.append(f"  {intent}{extra}: {value} [D: {doc.name}, p.{page}]")
    return "\n".join(lines) or "(no documents uploaded)"


def _passages(chunks: list[dict]) -> str:
    return "\n\n".join(f"[L{i}] {c['title']}, {c['provision']} ({c['heading']}): {c['text'][:900]}" for i, c in enumerate(chunks, start=1)) or "(none)"


def _citations(chunks: list[dict]) -> list[dict]:
    return [{"tag": f"L{i}", "source_id": c["source_id"], "title": c["title"], "provision": c["provision"], "heading": c["heading"],
             "page": c["page"], "url": c["url"], "chunk_id": c["chunk_id"], "legal_status": c["legal_status"]} for i, c in enumerate(chunks, start=1)]


def _quote(text: str, limit: int = 340) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    if len(text) <= limit:
        return text
    cut = text[:limit].rsplit(" ", 1)[0]
    return cut + " ..."


def _quoted_answer(chunks: list[dict], lang: str, top: int = 3) -> str:
    parts = [T[lang]["law_intro"]]
    for i, chunk in enumerate(chunks[:top], start=1):
        where = f"{chunk['title']}, {chunk['provision']}" + (f", p.{chunk['page']}" if chunk["page"] else "")
        parts.append(f"[L{i}] {where}: \"{_quote(chunk['text'])}\"")
    return "\n\n".join(parts)


def _result(answer, lang, kind, chunks=None, model=NO_MODEL, raw=None, validation=None, refused=False, lawyer=False, doc_refs=None) -> dict:
    return {"answer": answer, "language": lang, "kind": kind, "refused": refused, "lawyer_referral": lawyer, "model": model,
            "raw_model_response": raw, "validation": validation, "citations": _citations(chunks or []), "retrieved": chunks or [], "doc_refs": doc_refs or []}


def _term_match(question: str) -> dict | None:
    lowered = question.lower()
    asks_meaning = re.search(r"what (?:is|does|are)|meaning|explain|kya (?:hota|hoti|hai)|matlab|क्या (?:होता|होती|है)|मतलब|अर्थ|समझा", lowered)
    if not asks_meaning:
        return None
    for term in TERMS.values():
        if any(k in lowered for k in term["keys"]):
            return term
    return None


def _nonexistent_section(question: str) -> bool:
    """A question that names a specific section the index does not have."""
    retriever = get_retriever()
    m = re.search(r"(?:section|sec\.?|धारा)\s*(\d{1,3}[a-z]{0,2})\b", question.lower())
    if not m:
        return False
    return not retriever._direct_hits(question) and any(re.search(p, question.lower()) for p in _act_patterns())


def _act_patterns():
    from core.legal_retrieval import ACT_HINTS

    return list(ACT_HINTS)


def _try_model(question: str, lang: str, docs, findings, chunks: list[dict], fallback: str, kind: str, doc_refs=None, lawyer=False) -> dict:
    """Ask the model if there is one. An answer that fails the checks is replaced, and logged."""
    provider = get_provider()
    if not provider.available:
        note = T[lang]["no_llm"]
        return _result(f"{fallback}\n\n{note}", lang, kind, chunks, lawyer=lawyer, doc_refs=doc_refs)
    if lang != "en" and not provider.reliable_in_indian_languages:
        # Small local models produced wrong, garbled Hindi in testing, and overlap checks
        # cannot verify Hindi against English statutes. Fixed text and quotes are used instead.
        return _result(fallback, lang, kind, chunks, model=NO_MODEL, validation={"ok": None, "skipped": f"{provider.name} is limited to English"}, lawyer=lawyer, doc_refs=doc_refs)
    language_name = {"en": "English", "hi": "Hindi in Devanagari script", "hinglish": "Hinglish (Hindi in Roman script)"}[lang]
    finding_lines = "\n".join(f"- {f.severity}: {f.title}. {f.reason}" for f in (findings or [])[:8]) or "(none)"
    prompt = ASSISTANT_TEMPLATE.format(language=language_name, facts=_document_facts(docs), findings=finding_lines, passages=_passages(chunks), question=question)
    try:
        response = provider.generate(SYSTEM_ASSISTANT, prompt)
    except Exception as exc:  # any provider failure falls back to the deterministic answer
        return _result(f"{fallback}\n\n{T[lang]['no_llm']}", lang, kind, chunks, validation={"ok": False, "provider_error": type(exc).__name__}, lawyer=lawyer, doc_refs=doc_refs)
    facts = _document_facts(docs)
    validation = validate_answer(response.text, chunks, lang, facts=facts)
    if not validation["ok"]:
        # Show the safe answer. The rejected text stays in raw_model_response for audit.
        return _result(fallback, lang, kind, chunks, model=response.model, raw=response.text, validation=validation, lawyer=lawyer, doc_refs=doc_refs)
    # The checks cannot fully verify meaning, so the source wording always appears with the reply.
    shown = f"{response.text}\n\n{fallback}"
    return _result(shown, lang, kind + "+model", chunks, model=response.model, raw=response.text, validation=validation, lawyer=lawyer, doc_refs=doc_refs)


def answer(question: str, docs: list[ProcessedDocument] | None = None, findings: list | None = None, language: str | None = None) -> dict:
    docs = docs or []
    findings = findings or []
    lang = language or detect_language(question)
    t = T[lang]
    usable = [d for d in docs if d.status in ("ok", "partial")]
    retriever = get_retriever()

    # 1. Requests for certification or to break the rules never reach a model.
    if REFUSAL.search(question):
        high = [f for f in findings if f.severity == "High Priority"]
        extra = ""
        if high:
            titles = list(dict.fromkeys(f.title for f in high))
            extra = "\n\n" + t["findings_intro"] + "\n" + "\n".join(f"- {title}" for title in titles[:4])
        return _result(f"{t['refuse']}{extra}\n\n{t['lawyer']}", lang, "refusal", refused=True, lawyer=True)

    # 2. Facts BhoomiCheck never extracts.
    if UNSUPPORTED_FACTS.search(question):
        return _result(t["not_found"] if docs else t["no_docs"], lang, "not_found")

    # 3. A named section that is not in the index.
    if _nonexistent_section(question):
        return _result(t["law_not_found"], lang, "not_found")

    # 4. What does this term mean?
    term = _term_match(question)
    if term:
        chunks = retriever.search(term["query"], top_k=3)
        sources = "\n".join(f"[L{i}] {c['title']}, {c['provision']}" + (f", p.{c['page']}" if c["page"] else "") for i, c in enumerate(chunks, 1))
        return _result(f"{term[lang]}\n\n{sources}", lang, "definition", chunks)

    # 5. Facts from uploaded documents. A question about what the law allows is not one of these.
    for intent, pattern in FIELD_INTENTS:
        if re.search(pattern, question, re.I) and not RISK_INTENT.search(question) and _asks_for_a_fact(question):
            if not docs:
                return _result(t["no_docs"], lang, "not_found")
            lines, refs = [], []
            for doc in usable:
                for value, page, extras in _field_values(doc, intent):
                    direction = extras.get("direction", "")
                    lines.append(t[intent].format(doc=doc.name, value=value, direction=direction) + f" {_cite(doc.name, page)}.")
                    refs.append({"document": doc.name, "page": page, "value": value})
            if not lines:
                return _result(t["not_found"], lang, "not_found")
            suffix = t["not_verified"] if intent in ("seller", "buyer", "owner", "landlord") else ""
            return _result("\n".join(lines) + (f"\n\n{suffix}" if suffix else ""), lang, "document_fact", doc_refs=refs)

    # 6. Risks and comparisons from the rule checks.
    if RISK_INTENT.search(question) and docs:
        categories: set[str] = set()
        for pattern, cats in TOPIC_FILTERS:
            if pattern.search(question):
                categories |= cats
        relevant = [f for f in findings if not categories or f.category in categories]
        if not findings and usable:
            from core.risk_detector import detect_risks

            findings = detect_risks(docs, compare_all(docs))
            relevant = [f for f in findings if not categories or f.category in categories]
        if not relevant:
            return _result(t["no_findings"] + "\n\n" + t["lawyer"], lang, "findings", lawyer=True)
        lines = [t["findings_intro"]]
        refs = []
        for f in relevant[:5]:
            where = "; ".join(_cite(s.document, s.page) for s in f.sources[:2])
            lines.append(f"- {f.severity}: {f.reason} {where}")
            refs += [{"document": s.document, "page": s.page} for s in f.sources[:2]]
        return _result("\n".join(lines) + "\n\n" + t["lawyer"], lang, "findings", lawyer=True, doc_refs=refs)

    # 7. Legal questions.
    chunks = retriever.search(question, top_k=4) if DOMAIN.search(question) or re.search(r"[a-z]", question.lower()) and _has_glossary_term(question) else []
    if not chunks:
        if not DOMAIN.search(question):
            return _result(t["out_of_scope"], lang, "out_of_scope")
        return _result(t["law_not_found"], lang, "not_found")
    return _try_model(question, lang, docs, findings, chunks, _quoted_answer(chunks, lang), "legal")


def _asks_for_a_fact(question: str) -> bool:
    if len(question.split()) <= 3:
        return True
    return bool(re.search(r"\bwho\b|\bwhat(?:'s| is| are)?\s+(?:the|my|this)\b|\bwhich\b|\bwhere\b|how much|how big|\bwhen (?:was|is)\b|\bmy\b|in this (?:deed|document)|"
                          r"\bkaun\b|\bkitn[aie]\b|\bkya hai\b|\bkab\b|\bkahan\b|\bmein\b|कौन|कितन|कब|कहाँ|क्या है", question, re.I))


def _has_glossary_term(question: str) -> bool:
    from core.legal_retrieval import GLOSSARY

    lowered = question.lower()
    return any(term in lowered for term in GLOSSARY)
