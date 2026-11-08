"""The complete analysis: read, classify, extract, compare, assess, build checklists."""
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from core.ai_engine import status as llm_status
from core.checklist_generator import generate as generate_checklist, suggest_contexts
from core.document_classifier import classify
from core.document_comparator import compare_all
from core.document_processor import process_bytes, process_path
from core.information_extractor import extract
from core.models import ProcessedDocument
from core.risk_detector import detect_risks

SAFETY_NOTES = [
    "Extracted ownership information is what the documents state. It has not been independently verified.",
    "Mutation is not conclusive proof of title.",
    "Property tax receipts do not conclusively establish title.",
    "An Encumbrance Certificate may not reveal every possible claim.",
    "A registered document does not automatically establish a perfect title.",
    "A document that was not uploaded may still exist. Its absence here proves nothing.",
]


def prepare(doc: ProcessedDocument) -> ProcessedDocument:
    if doc.status in ("ok", "partial"):
        classify(doc)
    return extract(doc)


def load_bytes(blob: bytes, name: str) -> ProcessedDocument:
    return prepare(process_bytes(blob, name))


def load_path(path: str | Path) -> ProcessedDocument:
    return prepare(process_path(path))


def analyse(docs: list[ProcessedDocument], purpose: str = "purchase") -> dict:
    comparisons = compare_all(docs)
    findings = detect_risks(docs, comparisons, purpose)
    contexts = suggest_contexts(docs)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "model": llm_status(),
        "documents": docs,
        "comparisons": comparisons,
        "findings": findings,
        "checklist_contexts": contexts,
        "checklists": {context: generate_checklist(context, docs) for context in contexts},
        "safety_notes": SAFETY_NOTES,
    }


def serialisable(result: dict) -> dict:
    """A JSON-ready copy of analyse()'s result."""
    out = dict(result)
    out["documents"] = [d.to_dict() for d in result["documents"]]
    out["comparisons"] = [c.to_dict() for c in result["comparisons"]]
    out["findings"] = [f.to_dict() for f in result["findings"]]
    return out
