"""Checks that legal citations exist in the index and that answers do not overclaim."""
from __future__ import annotations

import re

from core.legal_retrieval import get_retriever
from core.models import Citation

# Claims BhoomiCheck must never make, in English, Hinglish and Hindi.
FORBIDDEN = [
    r"100\s*%\s*(?:safe|clear|secure|guarantee)", r"guarantee[ds]?\b.{0,30}\b(?:title|ownership|safe)", r"(?:title|property|ownership)\b.{0,30}\bguaranteed\b",
    r"\bclear title\b.{0,20}\b(?:confirmed|certified|verified|assured)\b", r"\b(?:is|has|have) (?:a )?(?:clear|perfect|marketable) title\b", r"\bcertified owner(?:ship)?\b", r"\bcertif(?:y|ied|ies)\b.{0,30}\b(?:title|owner)",
    r"\bno litigation\b", r"\bno (?:pending )?(?:court )?cases?\b", r"\bcompletely safe\b", r"\bsafe to (?:buy|purchase|invest)\b", r"\bdefinitely (?:safe|the owner)\b",
    r"पूरी तरह सुरक्षित", r"100\s*%\s*सुरक्षित", r"गारंटी(?:शुदा)? (?:है|देता|देते)", r"bilkul safe", r"pakka safe", r"koi (?:dikkat|problem|case) nahi",
]
# Statements contradicting the project's safety rules. A negation here is part of the claim.
FORBIDDEN_ALWAYS = [
    r"(?:sale|deed|registry|registration)\b.{0,50}\b(?:is |are )?(?:not|never) (?:required|needed|necessary|mandatory|compulsory)",
    r"(?:no|without) (?:need|requirement)\b.{0,25}\bregist", r"need(?:s)? not be registered", r"(?:does|do)(?: not|n't) need (?:to be )?regist",
    r"\bmutation\b.{0,60}\b(?:proves?|establish(?:es)?|confers?|creates?|gives?|grants?|conclusive)\b.{0,30}\b(?:title|ownership|owner)\b",
    r"\b(?:tax receipts?|property tax)\b.{0,60}\b(?:proves?|establish(?:es)?|conclusive)\b.{0,30}\b(?:title|ownership|owner)\b",
    r"\b(?:encumbrance certificate|\bec\b)\b.{0,60}\b(?:shows?|reveals?|lists?|covers?) (?:all|every|each)\b",
    r"\bregist(?:ered|ration)\b.{0,50}\b(?:guarantees?|proves?|ensures?)\b.{0,30}\b(?:title|ownership)\b",
    r"\bmissing\b.{0,40}\b(?:does not exist|doesn't exist|never existed)\b",
]
NEGATION = r"(?:not|cannot|can't|never|does not|do not|doesn't|don't|unable|won't|no one can|नहीं|nahi|nahin)"


def validate_citation(citation: Citation | dict) -> tuple[bool, str]:
    data = citation if isinstance(citation, dict) else citation.__dict__
    retriever = get_retriever()
    chunk = next((c for c in retriever.chunks if c["chunk_id"] == data.get("chunk_id")), None)
    if chunk is None:
        return False, "chunk not found in index"
    if chunk["source_id"] != data.get("source_id"):
        return False, "chunk belongs to a different source"
    if chunk["provision"] != data.get("provision"):
        return False, "provision label does not match the chunk"
    quote = _norm(data.get("quote") or "")
    if quote and quote not in _norm(chunk["text"]):
        return False, "quoted text does not appear in the chunk"
    return True, "ok"


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def forbidden_claims(answer: str) -> list[str]:
    """Absolute assurances that are not negated in the same sentence."""
    problems = []
    for sentence in re.split(r"(?<=[.!?।])\s+|\n", answer):
        for pattern in FORBIDDEN:
            match = re.search(pattern, sentence, re.I)
            if match and not re.search(NEGATION, sentence, re.I):
                problems.append(match.group(0))
        for pattern in FORBIDDEN_ALWAYS:
            match = re.search(pattern, sentence, re.I)
            if match and not re.search(r"\b(?:does not|do not|doesn't|don't|cannot|can't|is not|isn't|neither|nor|no) (?:\w+ ){0,3}(?:prove|establish|confer|create|give|grant|conclusive|guarantee|ensure|show|reveal|list|cover)", sentence, re.I):
                problems.append(match.group(0))
    return problems


def unsupported_sections(answer: str, context_chunks: list[dict]) -> list[str]:
    """Section numbers in an answer that are not in the passages given to the model."""
    allowed = {str(c.get("section")).upper() for c in context_chunks if c.get("section")}
    context_text = " ".join(c.get("text", "") for c in context_chunks).lower()
    unsupported = []
    for m in re.finditer(r"(?:section|sec\.|s\.|धारा)\s*(\d{1,3}[A-Za-z]{0,2})\b", answer, re.I):
        number = m.group(1).upper()
        if number not in allowed and f"section {number.lower()}" not in context_text:
            unsupported.append(m.group(0))
    return unsupported


def unknown_tags(answer: str, context_count: int) -> list[str]:
    """[L3] style tags that point past the passages supplied."""
    return [m.group(0) for m in re.finditer(r"\[L(\d+)\]", answer) if not 1 <= int(m.group(1)) <= context_count]


STOP = set("""a an the of to in on for and or is are was were be been being by with as at it its this that these those from which shall may any such not no if
can could should would will must do does did has have had you your i we they he she his her their there here what when how why who whom so but than then also only
into about under over more most other some each every all both yes need needs needed required require requires please note says say said per up out""".split())
NEGATIVE = re.compile(r"\b(?:not|no|never|cannot|can't|don't|doesn't|isn't|aren't|without|neither|nor|unnecessary|optional)\b", re.I)


def _content_words(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z]{3,}", text.lower()) if w not in STOP}


def _stem(word: str) -> str:
    for suffix in ("ation", "ered", "ing", "ies", "ed", "es", "s"):
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def ungrounded_sentences(answer: str, context: str, threshold: float = 0.4) -> list[str]:
    """English sentences whose content words mostly do not appear in the supplied material."""
    known = {_stem(w) for w in _content_words(context)}
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", re.sub(r"\[[^\]]*\]", " ", answer)):
        words = {_stem(w) for w in _content_words(sentence)}
        if len(words) >= 4 and len(words & known) / len(words) < threshold:
            out.append(sentence.strip())
    return out


def unsupported_negatives(answer: str, context: str) -> list[str]:
    """A negative claim ('not required') needs a matching negative sentence in the sources.

    Word overlap alone cannot catch this: 'registration is not required' shares its words
    with a passage saying registration is required.
    """
    context_sentences = [s for s in re.split(r"(?<=[.;:])\s+", context) if NEGATIVE.search(s)]
    context_words = [{_stem(w) for w in _content_words(s)} for s in context_sentences]
    out = []
    for sentence in re.split(r"(?<=[.!?])\s+|\n", re.sub(r"\[[^\]]*\]", " ", answer)):
        if not NEGATIVE.search(sentence):
            continue
        words = {_stem(w) for w in _content_words(sentence)}
        if len(words) < 2:
            continue
        if not any(len(words & cw) / len(words) >= 0.75 for cw in context_words):
            out.append(sentence.strip())
    return out


def script_problems(answer: str, language: str) -> list[str]:
    """Replacement characters, or a script that does not fit the requested language."""
    problems = []
    if "�" in answer:
        problems.append("contains corrupted characters")
    devanagari = len(re.findall(r"[ऀ-ॿ]", answer))
    latin = len(re.findall(r"[A-Za-z]", re.sub(r"\[[^\]]*\]", " ", answer)))
    if language == "hinglish" and devanagari > 5:
        problems.append("Hinglish was requested, but the reply is in Devanagari")
    if language == "hi" and latin > devanagari:
        problems.append("Hindi was requested, but the reply is mostly Latin script")
    if language == "en" and devanagari > 5:
        problems.append("English was requested, but the reply is in Devanagari")
    return problems


def validate_answer(answer: str, context_chunks: list[dict], language: str = "en", facts: str = "", require_tag: bool = True) -> dict:
    forbidden = forbidden_claims(answer)
    unsupported = unsupported_sections(answer, context_chunks)
    tags = unknown_tags(answer, len(context_chunks))
    context = " ".join(f"{c.get('title', '')} {c.get('heading', '')} {c.get('text', '')}" for c in context_chunks) + " " + facts
    has_valid_tag = bool(re.search(r"\[L\d+\]", answer)) and not tags
    missing_tag = require_tag and bool(context_chunks) and not has_valid_tag
    scripts = script_problems(answer, language)
    # Overlap checks need the answer and the sources to share a language.
    ungrounded = ungrounded_sentences(answer, context) if language == "en" else []
    negatives = unsupported_negatives(answer, context) if language == "en" else []
    ok = not (forbidden or unsupported or tags or missing_tag or scripts or ungrounded or negatives or not answer.strip())
    return {"ok": ok, "forbidden_claims": forbidden, "unsupported_sections": unsupported, "unknown_tags": tags, "missing_citation_tag": missing_tag,
            "script_problems": scripts, "ungrounded_sentences": ungrounded, "unsupported_negatives": negatives, "empty": not answer.strip()}
