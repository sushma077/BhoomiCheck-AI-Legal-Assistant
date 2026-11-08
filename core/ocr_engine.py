"""OCR with Tesseract (English and Hindi), falling back to RapidOCR (no system install)."""
from __future__ import annotations

import io
import shutil
from dataclasses import dataclass

from PIL import Image, ImageOps

import config


@dataclass
class OcrResult:
    text: str
    confidence: float  # 0-100 mean word confidence
    engine: str


def tesseract_available() -> bool:
    return shutil.which("tesseract") is not None


def _prepare(image: Image.Image) -> Image.Image:
    image = ImageOps.exif_transpose(image).convert("L")
    if max(image.size) < 1600:  # small phone photos read better when enlarged
        scale = 1600 / max(image.size)
        image = image.resize((int(image.width * scale), int(image.height * scale)), Image.LANCZOS)
    return ImageOps.autocontrast(image)


def _tesseract(image: Image.Image) -> OcrResult:
    import pytesseract

    available = set(pytesseract.get_languages(config=""))
    langs = "+".join(l for l in config.OCR_LANGS.split("+") if l in available) or "eng"
    data = pytesseract.image_to_data(image, lang=langs, output_type=pytesseract.Output.DICT,
                                     config="--psm 4")
    lines: dict[tuple, list[str]] = {}
    confidences: list[float] = []
    for i, word in enumerate(data["text"]):
        if not word.strip():
            continue
        key = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
        lines.setdefault(key, []).append(word)
        conf = float(data["conf"][i])
        if conf >= 0:
            confidences.append(conf)
    text = "\n".join(" ".join(words) for words in lines.values())
    mean = sum(confidences) / len(confidences) if confidences else 0.0
    return OcrResult(text=text, confidence=round(mean, 1), engine=f"tesseract:{langs}")


def _rapidocr(image: Image.Image) -> OcrResult:
    import numpy as np
    from rapidocr_onnxruntime import RapidOCR

    result, _ = RapidOCR()(np.array(image.convert("RGB")))
    if not result:
        return OcrResult("", 0.0, "rapidocr")
    text = "\n".join(line[1] for line in result)
    conf = 100 * sum(float(line[2]) for line in result) / len(result)
    return OcrResult(text=text, confidence=round(conf, 1), engine="rapidocr")


def ocr_image(image: Image.Image) -> OcrResult:
    prepared = _prepare(image)
    if tesseract_available():
        return _tesseract(prepared)
    return _rapidocr(prepared)


def ocr_bytes(blob: bytes) -> OcrResult:
    return ocr_image(Image.open(io.BytesIO(blob)))
