"""Shared data structures. Everything is plain data so it serialises to JSON."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

HIGH, WARNING, INFO = "High Priority", "Warning", "Information"
SEVERITY_ORDER = {HIGH: 0, WARNING: 1, INFO: 2}


@dataclass
class Page:
    number: int  # 1-based, as a person would count pages
    text: str
    method: str  # "text-layer", "tesseract" or "rapidocr"
    ocr_confidence: float | None = None


@dataclass
class ProcessedDocument:
    name: str
    pages: list[Page] = field(default_factory=list)
    status: str = "ok"  # ok | partial | unreadable | error
    warnings: list[str] = field(default_factory=list)
    doc_type: str = "other"
    doc_type_label: str = "Other property document"
    classification: dict[str, Any] = field(default_factory=dict)
    fields: dict[str, Any] = field(default_factory=dict)

    @property
    def full_text(self) -> str:
        return "\n".join(p.text for p in self.pages)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class SourceRef:
    """Where a finding comes from in an uploaded document."""
    document: str
    page: int | None = None
    evidence: str = ""


@dataclass
class Citation:
    """A pointer into the indexed legal corpus, checked by citation_validator."""
    source_id: str
    title: str
    provision: str
    url: str | None
    page: int | None
    chunk_id: str
    quote: str = ""
    verified: bool = False


@dataclass
class Finding:
    code: str
    severity: str
    title: str
    reason: str
    recommended_verification: str
    sources: list[SourceRef] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    lawyer_referral: bool = False
    category: str = "general"

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
