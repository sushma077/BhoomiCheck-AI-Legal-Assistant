"""Turn an uploaded PDF or image into page-wise text, using OCR only where needed."""
from __future__ import annotations

import io
import re
import unicodedata
from pathlib import Path

import pymupdf as fitz
from PIL import Image, UnidentifiedImageError

import config
from core.models import Page, ProcessedDocument
from core.ocr_engine import ocr_image

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png"}
SUPPORTED_SUFFIXES = IMAGE_SUFFIXES | {".pdf"}


def _meaningful_chars(text: str) -> int:
    return len(re.findall(r"[A-Za-z0-9ऀ-ॿ]", text))


def _text_layer_garbled(text: str) -> bool:
    """PDF fonts often map Hindi glyphs badly, so the page looks right but extracts as junk."""
    devanagari = len(re.findall(r"[\u0900-\u097F]", text))
    if devanagari < 5:
        return False
    stray = len(re.findall(r"[\u00C0-\u024F\u02B0-\u02FF]", text))
    return stray >= max(2, 0.01 * devanagari)


def _page_readable(text: str, confidence: float | None) -> bool:
    if _meaningful_chars(text) < config.MIN_PAGE_TEXT_CHARS:
        return False
    return confidence is None or confidence >= config.MIN_OCR_CONFIDENCE


def _clean(text: str) -> str:
    """Undo PDF ligatures such as 'ﬁ' and 'ﬃ', which break word matching."""
    for ligature, plain in (("ﬁ", "fi"), ("ﬂ", "fl"), ("ﬀ", "ff"), ("ﬃ", "ffi"), ("ﬄ", "ffl")):
        text = text.replace(ligature, plain)
    return unicodedata.normalize("NFC", text)


def _process_pdf(blob: bytes, doc: ProcessedDocument) -> None:
    pdf = fitz.open(stream=blob, filetype="pdf")
    if pdf.needs_pass:
        doc.status = "error"
        doc.warnings.append("This PDF is password protected. Remove the password and upload it again.")
        return
    for index, page in enumerate(pdf, start=1):
        text = _clean(page.get_text("text")).strip()
        if _meaningful_chars(text) >= config.MIN_PAGE_TEXT_CHARS and not _text_layer_garbled(text):
            doc.pages.append(Page(index, text, "text-layer"))
            continue
        pixmap = page.get_pixmap(dpi=config.OCR_DPI, colorspace=fitz.csGRAY)
        image = Image.open(io.BytesIO(pixmap.tobytes("png")))
        result = ocr_image(image)
        doc.pages.append(Page(index, _clean(result.text), result.engine, result.confidence))


def _finalise(doc: ProcessedDocument) -> None:
    if doc.status == "error":
        return
    if not doc.pages:
        doc.status = "unreadable"
        doc.warnings.append("No pages could be read from this file.")
        return
    readable = [p for p in doc.pages if _page_readable(p.text, p.ocr_confidence)]
    bad = [p.number for p in doc.pages if p not in readable]
    if not readable:
        doc.status = "unreadable"
        doc.warnings.append(
            "The text in this file could not be read reliably. Upload a clearer scan. Nothing "
            "should be concluded about this document from BhoomiCheck's output."
        )
    elif bad:
        doc.status = "partial"
        doc.warnings.append(f"Page(s) {', '.join(map(str, bad))} could not be read reliably and were not relied on.")


def process_bytes(blob: bytes, name: str) -> ProcessedDocument:
    doc = ProcessedDocument(name=name)
    suffix = Path(name).suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        doc.status = "error"
        doc.warnings.append(f"Unsupported file type '{suffix}'. Upload a PDF, JPG, JPEG or PNG.")
        return doc
    try:
        if suffix == ".pdf":
            _process_pdf(blob, doc)
        else:
            result = ocr_image(Image.open(io.BytesIO(blob)))
            doc.pages.append(Page(1, _clean(result.text), result.engine, result.confidence))
    except (fitz.FileDataError, UnidentifiedImageError, RuntimeError, ValueError) as exc:
        doc.status = "error"
        doc.warnings.append(f"This file could not be opened ({type(exc).__name__}). It may be damaged.")
        return doc
    _finalise(doc)
    return doc


def process_path(path: str | Path) -> ProcessedDocument:
    path = Path(path)
    return process_bytes(path.read_bytes(), path.name)
