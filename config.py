"""Central configuration for BhoomiCheck. Paths and tunables live here."""
from __future__ import annotations

import os
from pathlib import Path

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is a convenience, not a requirement
    pass

ROOT = Path(__file__).resolve().parent

APP_NAME = "BhoomiCheck"
TAGLINE = "Understand Documents. Identify Risks. Verify Before You Invest."

# Knowledge base
KB_DIR = ROOT / "knowledge_base"
KB_DOCS_DIR = KB_DIR / "documents"
KB_INDEX_DIR = KB_DIR / "index"
SOURCES_JSON = KB_DIR / "sources.json"
CHUNKS_JSON = KB_INDEX_DIR / "chunks.json"
EMBEDDINGS_NPY = KB_INDEX_DIR / "embeddings.npy"
INDEX_MANIFEST = KB_INDEX_DIR / "manifest.json"

# Data and outputs
DATA_DIR = ROOT / "data"
SYNTHETIC_DIR = DATA_DIR / "synthetic_documents"
TEST_CASES_JSON = DATA_DIR / "test_cases.json"
RAW_OUTPUTS_DIR = ROOT / "raw_outputs"
EVAL_DIR = ROOT / "evaluation"
DELIVERABLES_DIR = ROOT / "deliverables"
FONT_DIR = ROOT / "assets" / "fonts"

# Embeddings: multilingual so Hindi and Hinglish questions can find English statutes.
EMBEDDING_MODEL = os.getenv(
    "BHOOMI_EMBEDDING_MODEL",
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
)

# LLM providers. Keys are read from the environment and never logged.
ANTHROPIC_MODEL = os.getenv("BHOOMI_ANTHROPIC_MODEL", "claude-sonnet-5-5")
OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
OLLAMA_MODEL = os.getenv("BHOOMI_OLLAMA_MODEL", "")  # empty: first model Ollama lists
MLX_MODEL = os.getenv("BHOOMI_MLX_MODEL", "")  # empty: MLX provider stays off
LLM_PROVIDER = os.getenv("BHOOMI_LLM_PROVIDER", "auto")  # auto|anthropic|ollama|mlx|none

# OCR
OCR_LANGS = os.getenv("BHOOMI_OCR_LANGS", "eng+hin")
OCR_DPI = 300
MIN_PAGE_TEXT_CHARS = 40  # below this a PDF page is treated as scanned
MIN_OCR_CONFIDENCE = 45.0  # mean Tesseract word confidence below this is "unreadable"

# Retrieval
RETRIEVAL_TOP_K = 5
CHUNK_TARGET_CHARS = 1400
CHUNK_MAX_CHARS = 2200

USER_AGENT = "BhoomiCheck/1.0 (legal research; student project)"

LEGAL_NOTICE = (
    "BhoomiCheck gives preliminary document assistance. It is not legal advice and "
    "does not certify title or ownership. Have a qualified property lawyer verify "
    "the documents, and check the original records, before you pay or sign."
)
