"""Chunk the collected sources by legal provision and build the retrieval index.

Incremental: chunks of unchanged files are reused, and only new chunk text is embedded.
Usage: python scripts/build_index.py [--no-embeddings]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pymupdf

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

FOOTNOTE = re.compile(r"^\s*\d+\s*\.?\s*(?:Subs\.|Ins\.|Omitted|Rep\.|The words|Added|Sub-section|Clause|Section \d|Now see|Cl\.|S\. ?\d|For the|Certain words|Extended|This Act has|The Act|Vide|Inserted|Substituted|Amended)")
# "54. Heading", "1[53A. Heading", "[3. (1) No promoter"
SECTION = re.compile(r"^\s*(?:\d{0,2}\s*\[)*\s*(\d{1,3}[A-Z]{0,2})\s*\.\s*(?:\d{0,2}\s*\[)*\s*([A-Z\(\"“‘'\[].*)$")
SCHEDULE = re.compile(r"^\s*(?:THE\s+)?(?:(?:FIRST|SECOND|THIRD|FOURTH)\s+)?SCHEDULE(?:\s+[IVX]+)?\s*$")
HEADING_SPLIT = re.compile(r"\.\s*[\[]?\d*[—–―-]+\s*|\s*[—–―]\s*")


def section_key(value: str) -> tuple[int, str]:
    m = re.match(r"(\d+)([A-Z]*)", value)
    return int(m.group(1)), m.group(2)


def is_contents_page(lines: list[str]) -> bool:
    """Arrangement-of-sections pages would otherwise pollute every search."""
    if any("ARRANGEMENT OF" in l.upper() for l in lines[:12]):
        return True
    body = [l for l in lines if l.strip()]
    if len(body) < 12:
        return False
    numbered = sum(bool(re.match(r"^\s*\d{1,3}[A-Z]{0,2}\s*\.", l)) for l in body)
    short = sum(len(l.strip()) < 75 for l in body)
    return numbered / len(body) > 0.4 and short / len(body) > 0.8


def best_heading_sequence(candidates: list[dict]) -> set[int]:
    """Pick the heaviest strictly increasing run of section numbers (weighted LIS).

    A stray numbered line or a contents entry cannot derail parsing, because it has to
    fit an increasing sequence through the whole Act to survive. Real headings carry a
    dash after the title, and so weigh more than contents entries.
    """
    if not candidates:
        return set()
    best = [c["weight"] for c in candidates]
    prev = [-1] * len(candidates)
    for i, cand in enumerate(candidates):
        for j in range(max(0, i - 400), i):
            if section_key(candidates[j]["section"]) < section_key(cand["section"]) and best[j] + cand["weight"] > best[i]:
                best[i], prev[i] = best[j] + cand["weight"], j
    i = max(range(len(candidates)), key=best.__getitem__)
    chosen = set()
    while i != -1:
        chosen.add(candidates[i]["line_id"])
        i = prev[i]
    return chosen


def split_long(text: str) -> list[str]:
    if len(text) <= config.CHUNK_MAX_CHARS:
        return [text]
    parts, current = [], ""
    for sentence in re.split(r"(?<=[.;:])\s+", text):
        if current and len(current) + len(sentence) > config.CHUNK_TARGET_CHARS:
            parts.append(current.strip())
            current = current[-150:]  # small overlap so a clause is not cut off from its context
        current += " " + sentence
    if current.strip():
        parts.append(current.strip())
    return parts


def chunk_pages(source: dict, path: Path) -> list[dict]:
    """Judgments and guidelines have no section numbers, so they are chunked by page."""
    pdf = pymupdf.open(path)
    label = "Judgment" if source.get("kind") == "judgment" else "Guidelines"
    blocks = [{"provision": f"{label}, page {i}", "section": None, "heading": "", "page": i, "text": page.get_text("text")}
              for i, page in enumerate(pdf, start=1)]
    return _to_chunks(source, blocks)


def chunk_pdf(source: dict, path: Path) -> list[dict]:
    pdf = pymupdf.open(path)
    lines: list[dict] = []
    candidates: list[dict] = []
    for page_index, page in enumerate(pdf, start=1):
        raw = page.get_text("text").splitlines()
        if is_contents_page(raw):
            continue
        for text in raw:
            if FOOTNOTE.match(text) or re.fullmatch(r"\s*\d{1,3}\s*", text) or not text.strip():
                continue
            line_id = len(lines)
            lines.append({"page": page_index, "text": text.strip()})
            match = SECTION.match(text)
            if match:
                rest = match.group(2)
                weight = 3 if re.search(r"[—–―]|\.-|^\(1\)", rest) else 1
                candidates.append({"line_id": line_id, "section": match.group(1), "weight": weight})
    chosen = best_heading_sequence(candidates)
    section_of = {c["line_id"]: c["section"] for c in candidates if c["line_id"] in chosen}

    blocks: list[dict] = []
    current: dict | None = None
    in_schedule = False
    for line_id, line in enumerate(lines):
        if SCHEDULE.match(line["text"]) and section_of and line_id > min(section_of):
            in_schedule = True
            current = {"provision": re.sub(r"\s+", " ", line["text"]).title(), "section": None, "heading": "", "page": line["page"], "text": line["text"]}
            blocks.append(current)
            continue
        if line_id in section_of and not in_schedule:
            rest = SECTION.match(line["text"]).group(2)
            heading = HEADING_SPLIT.split(rest, maxsplit=1)[0][:110].strip(" .\"“”")
            current = {"provision": f"Section {section_of[line_id]}", "section": section_of[line_id], "heading": heading, "page": line["page"], "text": line["text"]}
            blocks.append(current)
            continue
        if current is None:
            current = {"provision": "Preamble", "section": None, "heading": "", "page": line["page"], "text": ""}
            blocks.append(current)
        current["text"] += " " + line["text"]
    return _to_chunks(source, blocks)


def _to_chunks(source: dict, blocks: list[dict]) -> list[dict]:
    chunks = []
    counts: dict[str, int] = {}
    for block in blocks:
        text = re.sub(r"\s+", " ", block["text"]).strip()
        if len(text) < 40:
            continue
        for part in split_long(text):
            key = block["provision"].replace(" ", "_").lower()
            counts[key] = counts.get(key, 0) + 1
            chunks.append({
                "chunk_id": f"{source['id']}::{key}::{counts[key]}",
                "source_id": source["id"], "title": source["title"], "url": source.get("url"),
                "jurisdiction": source["jurisdiction"], "legal_status": source["status"],
                "page": block["page"], "provision": block["provision"], "section": block["section"],
                "heading": block["heading"], "text": part,
            })
    return chunks


def chunk_text_file(source: dict, path: Path) -> list[dict]:
    text = path.read_text(encoding="utf-8")
    blocks = [{"provision": "Web page", "section": None, "heading": "", "page": None, "text": p}
              for p in re.split(r"\n\s*\n", text) if len(p) > 60]
    return _to_chunks(source, blocks)


def embed(texts: list[str]) -> np.ndarray:
    from fastembed import TextEmbedding

    model = TextEmbedding(config.EMBEDDING_MODEL)
    return np.array(list(model.embed(texts, batch_size=16)), dtype=np.float32)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--no-embeddings", action="store_true", help="build the BM25-only index")
    args = parser.parse_args()
    config.KB_INDEX_DIR.mkdir(parents=True, exist_ok=True)

    sources = json.loads(config.SOURCES_JSON.read_text())["sources"]
    manifest = json.loads(config.INDEX_MANIFEST.read_text()) if config.INDEX_MANIFEST.exists() else {"files": {}}
    old_chunks = json.loads(config.CHUNKS_JSON.read_text()) if config.CHUNKS_JSON.exists() else []
    by_source: dict[str, list[dict]] = {}
    for chunk in old_chunks:
        by_source.setdefault(chunk["source_id"], []).append(chunk)

    all_chunks: list[dict] = []
    files = {}
    for source in sources:
        if source["availability"] != "available":
            continue
        path = config.KB_DOCS_DIR / source["local_file"]
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        files[source["id"]] = digest
        if manifest["files"].get(source["id"]) == digest and source["id"] in by_source:
            chunks = by_source[source["id"]]
            state = "reused"
        else:
            if source["format"] != "pdf":
                chunks = chunk_text_file(source, path)
            elif source.get("kind") in ("judgment", "guidelines"):
                chunks = chunk_pages(source, path)
            else:
                chunks = chunk_pdf(source, path)
            state = "rebuilt"
        all_chunks.extend(chunks)
        sections = sum(1 for c in chunks if c["section"])
        print(f"{state:8}{source['id']:32}{len(chunks):5} chunks {sections:5} in sections")

    config.CHUNKS_JSON.write_text(json.dumps(all_chunks, ensure_ascii=False, indent=0))

    embedded = False
    if not args.no_embeddings:
        cache: dict[str, np.ndarray] = {}
        if config.EMBEDDINGS_NPY.exists() and len(old_chunks) == len(np.load(config.EMBEDDINGS_NPY)):
            vectors = np.load(config.EMBEDDINGS_NPY)
            cache = {hashlib.md5(c["text"].encode()).hexdigest(): vectors[i] for i, c in enumerate(old_chunks)}
        keys = [hashlib.md5(c["text"].encode()).hexdigest() for c in all_chunks]
        todo = [i for i, k in enumerate(keys) if k not in cache]
        print(f"embedding {len(todo)} new chunks, reusing {len(keys) - len(todo)}")
        if todo:
            inputs = [f"{all_chunks[i]['title']} {all_chunks[i]['provision']} {all_chunks[i]['heading']}. {all_chunks[i]['text']}" for i in todo]
            for key, vector in zip([keys[i] for i in todo], embed(inputs)):
                cache[key] = vector
        matrix = np.vstack([cache[k] for k in keys]).astype(np.float32)
        matrix /= np.maximum(np.linalg.norm(matrix, axis=1, keepdims=True), 1e-9)
        np.save(config.EMBEDDINGS_NPY, matrix)
        embedded = True

    config.INDEX_MANIFEST.write_text(json.dumps({
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "chunk_count": len(all_chunks),
        "embedding_model": config.EMBEDDING_MODEL if embedded else None,
        "files": files,
    }, indent=2))
    print(f"indexed {len(all_chunks)} chunks from {len(files)} sources; embeddings={embedded}")


if __name__ == "__main__":
    main()
