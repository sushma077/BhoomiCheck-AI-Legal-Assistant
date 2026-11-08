"""Hybrid legal search: BM25 and multilingual embeddings, merged by reciprocal rank fusion.

RAG here means looking up passages. No model has been trained on this legal material.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache

import numpy as np
from rank_bm25 import BM25Okapi

import config

# Hindi and Hinglish terms that citizens use, mapped to the statute's vocabulary.
GLOSSARY = {
    "bainama": "sale deed conveyance", "बैनामा": "sale deed conveyance", "registry": "registration sale deed registered document",
    "रजिस्ट्री": "registration sale deed registered document", "rajistri": "registration sale deed", "dakhil kharij": "mutation record of rights",
    "दाखिल खारिज": "mutation record of rights", "namantaran": "mutation", "नामांतरण": "mutation", "ferfar": "mutation", "फेरफार": "mutation",
    "khatauni": "record of rights", "खतौनी": "record of rights", "khasra": "survey number record of rights", "खसरा": "survey number",
    "jamabandi": "record of rights", "जमाबंदी": "record of rights", "girvi": "mortgage", "गिरवी": "mortgage", "rehan": "mortgage", "रेहन": "mortgage",
    "बंधक": "mortgage", "bandhak": "mortgage", "karz": "loan mortgage", "कर्ज": "loan mortgage", "loan": "mortgage charge",
    "mukhtarnama": "power of attorney", "मुख्तारनामा": "power of attorney", "mukhtar": "power of attorney agent", "मुख्तार": "power of attorney agent",
    "virasat": "succession heirs inheritance", "विरासत": "succession heirs inheritance", "varasat": "succession heirs inheritance", "वरासत": "succession heirs",
    "uttaradhikar": "succession", "उत्तराधिकार": "succession", "waris": "heirs succession", "वारिस": "heirs succession", "वसीयत": "will testament", "wasiyat": "will testament",
    "batwara": "partition", "बंटवारा": "partition", "बँटवारा": "partition", "daan": "gift", "दान": "gift", "dan patra": "gift deed", "दान पत्र": "gift deed",
    "किराये": "rent lease", "किराए": "rent lease", "रजिस्ट्रेशन": "registration", "registration": "registered", "kiraya": "rent lease", "किराया": "rent lease", "kirayanama": "lease rent agreement", "किरायेदार": "tenant lessee", "kirayedar": "tenant lessee", "makan malik": "landlord lessor", "मकान मालिक": "landlord lessor",
    "bayana": "earnest money advance agreement for sale", "बयाना": "earnest money advance", "kabza": "possession", "कब्जा": "possession", "कब्ज़ा": "possession",
    "zameen": "land immovable property", "ज़मीन": "land immovable property", "जमीन": "land immovable property", "jameen": "land immovable property",
    "makan": "house immovable property", "मकान": "house immovable property", "ghar": "house immovable property", "plot": "immovable property",
    "स्टाम्प": "stamp duty", "stamp": "stamp duty instrument", "मुकदमा": "suit litigation pending", "mukadma": "suit litigation pending", "मालिक": "owner title",
    "bechna": "sale transfer", "बेचना": "sale transfer", "kharidna": "purchase sale", "खरीदना": "purchase sale", "kharid": "purchase sale", "खरीद": "purchase sale",
    "panjikaran": "registration", "पंजीकरण": "registration", "पंजीकृत": "registered registration", "samay seema": "limitation period", "समय सीमा": "limitation period",
    "builder": "promoter real estate project", "बिल्डर": "promoter real estate project", "flat": "apartment promoter allottee", "फ्लैट": "apartment promoter allottee",
}

ACT_HINTS = {
    r"transfer of property|\btpa\b": "tpa_1882", r"registration act|\bregistration\b.*\b1908\b": "registration_1908",
    r"stamp act": "stamp_1899", r"\brera\b|real estate \(?regulation": "rera_2016", r"contract act": "contract_1872",
    r"specific relief": "specific_relief_1963", r"limitation act": "limitation_1963", r"hindu succession": "hindu_succession_1956",
    r"indian succession": "indian_succession_1925", r"power[s-]* ?of[- ]attorney act": "poa_1882", r"benami": "benami_1988",
    r"partition act": "partition_1893", r"up revenue|uttar pradesh revenue": "up_revenue_code_2006", r"maharashtra land": "mh_land_revenue_1966",
    r"karnataka land": "ka_land_revenue_1964", r"registration bill": "draft_registration_bill_2025", r"model tenancy": "model_tenancy_2021",
}
# Core provisions for common citizen questions. These lift the provision a lawyer would open
# first, ahead of passages that merely share words. They never add text to an answer.
TOPICS = [
    (r"(?=.*\bsale|.*\bsell|.*\bpurchase)(?=.*regist)", [("tpa_1882", "54"), ("registration_1908", "17")]),
    (r"\bwhat is (?:a )?sale\b|sale .*defined|how is (?:a )?sale made", [("tpa_1882", "54")]),
    (r"(?=.*\b(?:must|compulsor|mandatory|required|need|necessary|zaroori))(?=.*regist)", [("registration_1908", "17")]),
    (r"(?=.*\bnot registered|.*\bunregistered|.*\bwithout regist|.*\bnever (?:took|registered))", [("registration_1908", "49")]),
    (r"(?=.*\b(?:lease|rent|tenan))(?=.*regist)", [("tpa_1882", "107"), ("registration_1908", "17")]),
    (r"(?=.*\b(?:time|months?|deadline|limit))(?=.*regist)", [("registration_1908", "23")]),
    (r"(?=.*(?:mutation|revenue record|record of rights|khatauni|dakhil|दाखिल))(?=.*(?:\bown|title|malik|मालिक|proof|prove))", [("sc_2025_insc_1238", None)]),
    (r"\bwhat is (?:a )?mortgage|mortgage .*defined|types? of mortgage", [("tpa_1882", "58")]),
    (r"(?:girvi|गिरवी|बंधक|mortgage).*(?:kya|क्या)", [("tpa_1882", "58")]),
    (r"\bgift\b", [("tpa_1882", "122"), ("tpa_1882", "123")]),
    (r"(?=.*(?:\bcase\b|\bsuit\b|litigation|court))(?=.*(?:transfer|bought|buyer|sale|sold|purchase))", [("tpa_1882", "52")]),
    (r"(?=.*(?:possession|moved in))(?=.*(?:contract|agreement|advance))", [("tpa_1882", "53A")]),
    (r"(?=.*(?:\bagent|\battorney|\bagency))(?=.*(?:death|dead|died|passed away|end|revoke|terminat|khatam))", [("contract_1872", "201")]),
    (r"(?=.*(?:\bstamp))(?=.*(?:evidence|court|underpaid|not duly|admissib))", [("stamp_1899", "35")]),
    (r"(?=.*(?:promoter|builder|developer))(?=.*(?:regist))", [("rera_2016", "3")]),
    (r"(?=.*(?:promoter|builder|developer))(?=.*(?:advance|booking|ten per|10\s*%|percent))", [("rera_2016", "13")]),
    (r"(?=.*(?:promoter|builder|developer|\bflat\b))(?=.*(?:refund|compensation|possession|paisa wapas))", [("rera_2016", "18")]),
    (r"(?=.*(?:coparcen|joint family|daughter))", [("hindu_succession_1956", "6")]),
    (r"(?=.*(?:intestate|without (?:a )?will|bina will|dying|succession|virasat))(?=.*(?:hindu|male|bina|virasat|property))", [("hindu_succession_1956", "8")]),
    (r"(?=.*\bwill\b)(?=.*(?:execut|attest|made|valid))", [("indian_succession_1925", "63")]),
]
STATE_WORDS = {"uttar pradesh": "Uttar Pradesh", " up ": "Uttar Pradesh", "maharashtra": "Maharashtra", "mumbai": "Maharashtra", "pune": "Maharashtra",
               "karnataka": "Karnataka", "bengaluru": "Karnataka", "bangalore": "Karnataka", "lucknow": "Uttar Pradesh", "noida": "Uttar Pradesh", "ghaziabad": "Uttar Pradesh",
               "उत्तर प्रदेश": "Uttar Pradesh", "महाराष्ट्र": "Maharashtra", "कर्नाटक": "Karnataka"}
STOP = set("a an the of to in on for and or is are was were be by with as at it this that from which shall may any such not no if".split())


def tokenize(text: str) -> list[str]:
    tokens = re.findall(r"[a-z0-9]+|[ऀ-ॿ]+", text.lower())
    return [t for t in tokens if t not in STOP]


def expand_query(query: str) -> str:
    lowered = query.lower()
    extra = [meaning for term, meaning in GLOSSARY.items() if term in lowered]
    return f"{query} {' '.join(extra)}" if extra else query


class LegalRetriever:
    def __init__(self) -> None:
        self.chunks: list[dict] = json.loads(config.CHUNKS_JSON.read_text()) if config.CHUNKS_JSON.exists() else []
        docs = [tokenize(f"{c['title']} {c['provision']} {c['heading']} {c['heading']} {c['text']}") for c in self.chunks]
        self.bm25 = BM25Okapi(docs) if docs else None
        self.vectors = np.load(config.EMBEDDINGS_NPY) if config.EMBEDDINGS_NPY.exists() else None
        if self.vectors is not None and len(self.vectors) != len(self.chunks):
            self.vectors = None  # never mix an index with vectors from another build
        self._embedder = None
        self.embedding_error: str | None = None
        self._position = {c["chunk_id"]: i for i, c in enumerate(self.chunks)}
        self._by_section: dict[tuple[str, str], list[dict]] = {}
        for chunk in self.chunks:
            if chunk["section"]:
                self._by_section.setdefault((chunk["source_id"], chunk["section"]), []).append(chunk)

    @property
    def mode(self) -> str:
        return "hybrid (BM25 + embeddings)" if self.vectors is not None and self.embedding_error is None else "BM25 keyword search"

    def _embed_query(self, query: str) -> np.ndarray | None:
        if self.vectors is None or self.embedding_error:
            return None
        try:
            if self._embedder is None:
                from fastembed import TextEmbedding

                self._embedder = TextEmbedding(config.EMBEDDING_MODEL)
            vector = np.array(list(self._embedder.embed([query]))[0], dtype=np.float32)
            return vector / max(np.linalg.norm(vector), 1e-9)
        except Exception as exc:  # e.g. model not downloadable on this host: fall back to BM25
            self.embedding_error = type(exc).__name__
            return None

    def get_provision(self, source_id: str, section: str) -> dict | None:
        """Exact lookup, used for rule findings so their citations are never guessed."""
        chunks = self._by_section.get((source_id, section))
        return chunks[0] if chunks else None

    def _first_mentioning(self, source_id: str, lowered: str) -> dict | None:
        """For judgments, which have no sections: the page that talks about mutation and title."""
        pages = [c for c in self.chunks if c["source_id"] == source_id]
        return next((c for c in pages if re.search(r"mutation[^.]{0,120}(?:title|ownership)", c["text"], re.I)), pages[0] if pages else None)

    def _direct_hits(self, query: str) -> list[int]:
        """'section 54 of the Transfer of Property Act' should return exactly that."""
        lowered = query.lower()
        m = re.search(r"(?:section|sec\.?|s\.|धारा)\s*(\d{1,3}[a-z]{0,2})\b", lowered)
        if not m:
            return []
        section = m.group(1).upper()
        hits = []
        for pattern, source_id in ACT_HINTS.items():
            if re.search(pattern, lowered):
                for i, chunk in enumerate(self.chunks):
                    if chunk["source_id"] == source_id and chunk["section"] == section:
                        hits.append(i)
        return hits

    def search(self, query: str, top_k: int = config.RETRIEVAL_TOP_K, include_draft: bool | None = None) -> list[dict]:
        if not self.chunks:
            return []
        expanded = expand_query(query)
        lowered = f" {expanded.lower()} "
        if include_draft is None:
            include_draft = bool(re.search(r"\bdraft\b|\bbill\b|new registration|proposed", lowered))

        bm25_scores = self.bm25.get_scores(tokenize(expanded))
        rankings = [np.argsort(bm25_scores)[::-1][:60]]
        query_vector = self._embed_query(expanded)
        if query_vector is not None:
            rankings.append(np.argsort(self.vectors @ query_vector)[::-1][:60])

        fused: dict[int, float] = {}
        for ranking in rankings:
            for rank, index in enumerate(ranking):
                fused[int(index)] = fused.get(int(index), 0.0) + 1.0 / (60 + rank)

        states = {state for word, state in STATE_WORDS.items() if word in lowered}
        hinted = {source_id for pattern, source_id in ACT_HINTS.items() if re.search(pattern, lowered)}
        for index in list(fused):
            chunk = self.chunks[index]
            if chunk["source_id"] == "draft_registration_bill_2025" and not include_draft:
                del fused[index]
                continue
            jurisdiction = chunk["jurisdiction"]
            if chunk["source_id"] in hinted:
                fused[index] *= 1.6
            is_central = jurisdiction.startswith("India")
            if not is_central and not any(s in jurisdiction for s in states):
                fused[index] *= 0.55  # state law should not outrank central law unless a state is named
            elif states and any(s in jurisdiction for s in states):
                fused[index] *= 1.5
            if not chunk["section"]:
                fused[index] *= 0.85

        topic_hits: list[int] = []
        for pattern, provisions in TOPICS:
            if re.search(pattern, lowered, re.S):
                for source_id, section in provisions:
                    chunk = self.get_provision(source_id, section) if section else self._first_mentioning(source_id, lowered)
                    if chunk:
                        topic_hits.append(self._position[chunk["chunk_id"]])
        for index in topic_hits:
            fused[index] = fused.get(index, 0.0) + 0.05  # well above any fused rank score

        direct = self._direct_hits(expanded)
        ordered = direct + [i for i in sorted(fused, key=fused.get, reverse=True) if i not in direct]
        results = []
        for index in ordered[:top_k]:
            result = dict(self.chunks[index])
            result["score"] = round(fused.get(index, 1.0), 5)
            results.append(result)
        return results


@lru_cache(maxsize=1)
def get_retriever() -> LegalRetriever:
    return LegalRetriever()
