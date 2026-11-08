"""Collect official Indian property-law sources into knowledge_base/documents.

Tries each target's known official URLs, then India Code's public repository API.
Any source that cannot be fetched is recorded as unavailable with the reason; its
contents are never invented. Existing files are kept unless --refresh is passed, so
re-running only fetches what is missing.

Usage: python scripts/collect_sources.py [--refresh] [--only id1,id2]
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import pymupdf
import requests
from bs4 import BeautifulSoup

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import config  # noqa: E402

NIC = "https://www.indiacode.nic.in/bitstream/123456789"
NIC2 = "https://www.indiacode.nic.in/indiacode/bitstream/123456789"
THC = "https://www.thc.nic.in/Central%20Governmental%20Acts"  # central Acts on a High Court website
API = "https://indiacode.gov.in/server/api"

# role: why it is in the corpus. status: legal status as far as the source shows.
TARGETS = [
    {"id": "tpa_1882", "title": "Transfer of Property Act, 1882", "jurisdiction": "India (central)", "status": "in force",
     "urls": [f"{NIC}/2338/1/A1882-04.pdf"], "api_query": "Transfer of Property Act 1882", "api_year": "1882"},
    {"id": "registration_1908", "title": "Registration Act, 1908", "jurisdiction": "India (central)", "status": "in force (draft replacement Bill published 2025)",
     "urls": [f"{NIC}/15937/1/the_registration_act%2C1908.pdf"], "api_query": "Registration Act 1908", "api_year": "1908"},
    {"id": "stamp_1899", "title": "Indian Stamp Act, 1899", "jurisdiction": "India (central); states amend duty rates", "status": "in force",
     "urls": [f"{NIC}/14645/1/a1899-2.pdf", "https://revenue.py.gov.in/downloads/actsandrules/Indian%20StampAct1899.pdf"], "api_query": "Indian Stamp Act 1899", "api_year": "1899"},
    {"id": "rera_2016", "title": "Real Estate (Regulation and Development) Act, 2016", "jurisdiction": "India (central)", "status": "in force",
     "urls": ["https://www.up-rera.in/pdf/reraact.pdf", "https://reraonline.kerala.gov.in/PDF/RERA%20Act,%202016.pdf", f"{NIC}/2158/3/A2016-16.pdf", f"{NIC2}/2158/1/A201616.pdf"], "api_query": "Real Estate (Regulation and Development) Act 2016", "api_year": "2016"},
    {"id": "contract_1872", "title": "Indian Contract Act, 1872", "jurisdiction": "India (central)", "status": "in force",
     "urls": [f"{THC}/Indian%20Contract%20Act,%201872.pdf", "https://aphc.gov.in/docs/6_20241130050320.pdf", f"{NIC2}/2187/2/A187209.pdf"], "api_query": "Indian Contract Act 1872", "api_year": "1872"},
    {"id": "specific_relief_1963", "title": "Specific Relief Act, 1963", "jurisdiction": "India (central)", "status": "in force",
     "urls": [f"{NIC}/1583/7/A1963-47.pdf", "https://cdnbbsr.s3waas.gov.in/s3ec037a4bf9ba2bd774068ad50351fb89/uploads/2023/06/2023060229-1.pdf"], "api_query": "Specific Relief Act 1963", "api_year": "1963"},
    {"id": "limitation_1963", "title": "Limitation Act, 1963", "jurisdiction": "India (central)", "status": "in force",
     "urls": [f"{THC}/Limitation%20Act,%202019.pdf", f"{NIC2}/1565/1/A196336.pdf"], "api_query": "Limitation Act 1963", "api_year": "1963"},
    {"id": "hindu_succession_1956", "title": "Hindu Succession Act, 1956", "jurisdiction": "India (central)", "status": "in force",
     "urls": [f"{NIC}/1713/1/AAA1956suc___30.pdf"], "api_query": "Hindu Succession Act 1956", "api_year": "1956"},
    {"id": "indian_succession_1925", "title": "Indian Succession Act, 1925", "jurisdiction": "India (central)", "status": "in force",
     "urls": [f"{THC}/Indian%20Succession%20Act,%201925.pdf", f"{NIC2}/2385/1/A192539.pdf"], "api_query": "Indian Succession Act 1925", "api_year": "1925"},
    {"id": "poa_1882", "title": "Powers of Attorney Act, 1882", "jurisdiction": "India (central)", "status": "in force",
     "urls": [], "api_query": "Powers of Attorney Act 1882", "api_year": "1882"},
    {"id": "benami_1988", "title": "Prohibition of Benami Property Transactions Act, 1988", "jurisdiction": "India (central)", "status": "in force",
     "urls": [f"{NIC2}/1921/1/198845.pdf", f"{NIC2}/1921/1/A198845.pdf"], "api_query": "Prohibition of Benami Property Transactions Act 1988", "api_year": "1988"},
    {"id": "easements_1882", "title": "Indian Easements Act, 1882", "jurisdiction": "India (central)", "status": "in force",
     "urls": [f"{THC}/Indian%20Easements%20Act,%201882.pdf"], "api_query": "Indian Easements Act 1882", "api_year": "1882"},
    {"id": "partition_1893", "title": "Partition Act, 1893", "jurisdiction": "India (central)", "status": "in force",
     "urls": [], "api_query": "Partition Act 1893", "api_year": "1893"},
    {"id": "up_revenue_code_2006", "title": "Uttar Pradesh Revenue Code, 2006", "jurisdiction": "Uttar Pradesh", "status": "in force",
     "urls": ["https://www.indiacode.nic.in/bitstream/123456789/17001/1/revcodeeng_excld2026.pdf",
              "https://www.indiacode.nic.in/bitstream/123456789/17001/1/revcodeenglish.pdf",
              "https://www.lbsnaa.gov.in/storage/uploads/pdf_data/1742473203_Uttar%20Pradesh%20Revenue%20Code%202006%20updated%20till%2005.03.2021.pdf",
              "https://vaad.up.nic.in/pdf/Revenue_code_2006_englist_hindi_updated.pdf"],
     "api_query": "Uttar Pradesh Revenue Code 2006", "api_year": "2006"},
    {"id": "mh_land_revenue_1966", "title": "Maharashtra Land Revenue Code, 1966", "jurisdiction": "Maharashtra", "status": "in force",
     "urls": [], "api_query": "Maharashtra Land Revenue Code 1966", "api_year": "1966"},
    {"id": "ka_land_revenue_1964", "title": "Karnataka Land Revenue Act, 1964", "jurisdiction": "Karnataka", "status": "in force",
     "urls": ["https://upload.indiacode.nic.in/showfile?actid=AC_KA_71_596_00007_12_1551859218716&filename=%2812_of_1964%29_03_of_2022_%28e%29.pdf&type=actfile", "https://upload.indiacode.nic.in/showfile?actid=AC_KA_71_596_00007_12_1551859218716&filename=12_of_1964_%28e%29.pdf&type=actfile"], "api_query": "Karnataka Land Revenue Act 1964", "api_year": "1964"},
    {"id": "draft_registration_bill_2025", "title": "Draft Registration Bill, 2025 (Department of Land Resources)", "jurisdiction": "India (central)",
     "status": "DRAFT for consultation, not law. Enactment status not confirmed from an official source",
     "urls": ["https://cdnbbsr.s3waas.gov.in/s3d69116f8b0140cdeb1f99a4d5096ffe4/uploads/2025/05/20250526906486876.pdf"]},
    {"id": "model_tenancy_2021", "title": "Model Tenancy Act, 2021 (MoHUA)", "jurisdiction": "Model law, applies only where a state adopts it",
     "status": "model law, not binding by itself",
     "urls": ["https://www.mohua.gov.in/upload/uploadfiles/files/Model-Tenancy-Act-English-02_06_2021.pdf",
              "https://mohua.gov.in/upload/uploadfiles/files/Model-Tenancy-Act-English-02_06_2021.pdf"],
     "api_query": "Model Tenancy Act 2021"},
    {"id": "dilrmp_guidelines", "title": "DILRMP Guidelines (Department of Land Resources, MoRD)", "jurisdiction": "India (central)", "status": "government programme guidelines, not a statute", "kind": "guidelines",
     "urls": ["https://cdnbbsr.s3waas.gov.in/s3d69116f8b0140cdeb1f99a4d5096ffe4/uploads/2024/04/20240425160100930.pdf",
              "https://landrevenue.rajasthan.gov.in/content/dam/landrevenue/settlementdepartment/pdffolder/Scheme%20and%20Section/DILRMP/Final%20Guidelines%20of%20DILRMP%202021-26.pdf"]},
    {"id": "uttarakhand_tenancy_2021", "title": "Uttarakhand Tenancy Act, 2021 (state enactment based on the Model Tenancy Act)", "jurisdiction": "Uttarakhand", "status": "in force in Uttarakhand",
     "urls": ["https://www.indiacode.nic.in/bitstream/123456789/20015/1/uk_tenancy_act,_2021_eng.pdf"]},
    {"id": "sc_2025_insc_1238", "title": "Karam Singh v. Amarjit Singh, 2025 INSC 1238 (Supreme Court of India)", "jurisdiction": "India (central)", "status": "Supreme Court judgment", "kind": "judgment",
     "urls": ["https://api.sci.gov.in/supremecourt/2022/32133/32133_2022_14_1502_65047_Judgement_15-Oct-2025.pdf"]},
    {"id": "sc_2024_insc_1006", "title": "Mansoor Saheb v. Salima, 2024 INSC 1006 (Supreme Court of India)", "jurisdiction": "India (central)", "status": "Supreme Court judgment", "kind": "judgment",
     "urls": ["https://api.sci.gov.in/supremecourt/2006/12193/12193_2006_9_1506_58088_Judgement_19-Dec-2024.pdf"]},
    {"id": "sc_2023_insc_1009", "title": "P. Kishore Kumar v. Vittal K. Patkar, 2023 INSC 1009 (Supreme Court of India)", "jurisdiction": "India (central)", "status": "Supreme Court judgment", "kind": "judgment",
     "urls": ["https://api.sci.gov.in/supremecourt/2011/10304/10304_2011_5_1501_48291_Judgement_20-Nov-2023.pdf"]},
    {"id": "dolr_home", "title": "Department of Land Resources: website", "jurisdiction": "India (central)", "status": "government web page",
     "urls": ["https://www.dolr.gov.in/"], "html": True},
    {"id": "dolr_dilrmp", "title": "Department of Land Resources: Digital India Land Records Modernization Programme", "jurisdiction": "India (central)", "status": "government web page",
     "urls": ["https://www.dolr.gov.in/programmes-schemes/digital-india-land-records-modernization-programme/",
              "https://dolr.gov.in/en/programme-schemes/dilrmp/digital-india-land-records-modernization-programme"], "html": True},
    {"id": "rera_portal", "title": "MoHUA RERA portal", "jurisdiction": "India (central)", "status": "government web page",
     "urls": ["https://rera.mohua.gov.in/"], "html": True},
    {"id": "up_igrs", "title": "IGRS Uttar Pradesh (registration department portal)", "jurisdiction": "Uttar Pradesh", "status": "government web page",
     "urls": ["https://igrsup.gov.in/"], "html": True},
    {"id": "up_bhulekh", "title": "UP Bhulekh (land records portal)", "jurisdiction": "Uttar Pradesh", "status": "government web page",
     "urls": ["https://upbhulekh.gov.in/"], "html": True},
]

session = requests.Session()
session.headers["User-Agent"] = config.USER_AGENT


# A download only counts if it really is this document: (text expected early on, minimum pages).
VALIDATION = {
    "tpa_1882": ("transfer of property act", 30), "registration_1908": ("registration act", 15),
    "stamp_1899": ("stamp act", 30), "rera_2016": ("real estate (regulation and development) act", 30),
    "contract_1872": ("indian contract act", 30), "specific_relief_1963": ("specific relief act", 10),
    "limitation_1963": ("limitation act", 15), "hindu_succession_1956": ("hindu succession act", 10),
    "indian_succession_1925": ("indian succession act", 60), "poa_1882": ("powers-of-attorney act", 2),
    "benami_1988": ("benami", 15), "easements_1882": ("easements act", 15), "partition_1893": ("partition act", 2),
    "up_revenue_code_2006": ("revenue code", 40), "mh_land_revenue_1966": ("maharashtra land revenue code", 60),
    "ka_land_revenue_1964": ("karnataka land revenue act", 40), "draft_registration_bill_2025": ("registration bill", 20),
    "model_tenancy_2021": ("model tenancy act", 15), "dilrmp_guidelines": ("land resources", 20), "sc_2025_insc_1238": ("supreme court", 3), "sc_2024_insc_1006": ("supreme court", 3), "sc_2023_insc_1009": ("supreme court", 3), "uttarakhand_tenancy_2021": ("tenancy act", 15),
}


def validate_pdf(target_id: str, blob: bytes) -> str:
    """Return an empty string if the PDF is what we think it is, else the reason it is not."""
    rule = VALIDATION.get(target_id)
    if not rule:
        return ""
    phrase, min_pages = rule
    try:
        pdf = pymupdf.open(stream=blob, filetype="pdf")
    except Exception as exc:
        return f"unreadable PDF ({type(exc).__name__})"
    if len(pdf) < min_pages:
        return f"only {len(pdf)} pages, expected at least {min_pages}: probably a notification, not the Act"
    opening = re.sub(r"\s+", " ", " ".join(pdf[i].get_text() for i in range(min(4, len(pdf))))).lower()
    if phrase not in opening:
        return f"expected text '{phrase}' not found in the opening pages"
    return ""


def _title_tokens(query: str) -> set[str]:
    stop = {"the", "of", "and", "act", "code", "indian"}
    return {t for t in re.findall(r"[a-z]+", query.lower()) if t not in stop}


def api_candidates(target: dict) -> tuple[list[str], list[str]]:
    """Find PDF bitstreams for a target through India Code's public API."""
    notes: list[str] = []
    urls: list[str] = []
    query = target.get("api_query")
    if not query:
        return urls, notes
    try:
        data = session.get(f"{API}/discover/search/objects",
                           params={"query": query, "size": 8, "dsoType": "ITEM"}, timeout=90).json()
    except Exception as exc:  # network or JSON failure: report and move on
        return urls, [f"India Code API search failed: {type(exc).__name__}"]
    want = _title_tokens(query)
    objects = data.get("_embedded", {}).get("searchResult", {}).get("_embedded", {}).get("objects", [])
    for obj in objects:
        item = obj["_embedded"]["indexableObject"]
        title_tokens = _title_tokens(item.get("name", ""))
        year = target.get("api_year")
        if not want <= title_tokens | {year or ""} and not want - {year} <= title_tokens:
            continue
        if year and year not in item.get("name", "") and year not in json.dumps(item.get("metadata", {}).get("dc.date.act_year", [])):
            continue
        try:
            bundles = session.get(f"{API}/core/items/{item['uuid']}/bundles", params={"embed": "bitstreams"}, timeout=90).json()
        except Exception as exc:
            notes.append(f"India Code bundles failed: {type(exc).__name__}")
            continue
        for bundle in bundles.get("_embedded", {}).get("bundles", []):
            if bundle.get("name") != "ORIGINAL":
                continue
            streams = bundle.get("_embedded", {}).get("bitstreams", {}).get("_embedded", {}).get("bitstreams", [])
            pdfs = [x for x in streams if x.get("name", "").lower().endswith(".pdf")]
            # The Act is usually the largest file; rules and notifications are small.
            for stream in sorted(pdfs, key=lambda x: x.get("sizeBytes") or 0, reverse=True)[:4]:
                urls.append(stream["_links"]["content"]["href"])
    return urls, notes


def fetch_pdf(url: str) -> tuple[bytes | None, str]:
    resp = None
    for attempt in range(3):
        try:
            resp = session.get(url, timeout=60, allow_redirects=True)
        except Exception as exc:
            if attempt == 2:
                return None, f"{url}: {type(exc).__name__}"
            continue
        if resp.status_code not in (502, 503, 504):
            break
        time.sleep(5 * (attempt + 1))
    if resp.status_code != 200:
        return None, f"{url}: HTTP {resp.status_code}"
    if not resp.content.startswith(b"%PDF"):
        return None, f"{url}: response is not a PDF ({resp.headers.get('content-type')})"
    return resp.content, ""


def fetch_html(url: str) -> tuple[str | None, str]:
    try:
        resp = session.get(url, timeout=90, allow_redirects=True)
    except Exception as exc:
        return None, f"{url}: {type(exc).__name__}"
    if resp.status_code != 200:
        return None, f"{url}: HTTP {resp.status_code}"
    soup = BeautifulSoup(resp.content[:6_000_000], "html.parser")
    for tag in soup(["script", "style", "noscript", "svg", "nav", "footer"]):
        tag.decompose()
    text = re.sub(r"\n\s*\n+", "\n\n", soup.get_text("\n"))
    text = re.sub(r"[ \t]+", " ", text).strip()
    if len(text) < 200:
        return None, f"{url}: page has too little server-rendered text ({len(text)} chars)"
    return text, ""


def collect(target: dict, refresh: bool) -> dict:
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    ext = "txt" if target.get("html") else "pdf"
    path = config.KB_DOCS_DIR / f"{target['id']}.{ext}"
    record = {k: target[k] for k in ("id", "title", "jurisdiction", "status")}
    record["kind"] = target.get("kind", "web page" if target.get("html") else "statute")
    record.update(format=ext, attempts=[], retrieved_at=None, url=None, local_file=None, availability="unavailable")

    if path.exists() and not refresh:
        record.update(availability="available", local_file=path.name, kept_existing=True)
        return record

    candidates = list(target["urls"])
    tried_api = False
    index = 0
    while True:
        if index >= len(candidates):
            if tried_api or target.get("html"):
                break
            tried_api = True
            extra, notes = api_candidates(target)
            record["attempts"].extend(notes)
            candidates.extend(extra)
            if index >= len(candidates):
                break
        url = candidates[index]
        index += 1
        if target.get("html"):
            text, err = fetch_html(url)
            if text:
                path.write_text(text, encoding="utf-8")
                record.update(availability="available", url=url, local_file=path.name, retrieved_at=now,
                              sha256=hashlib.sha256(text.encode()).hexdigest())
                return record
        else:
            blob, err = fetch_pdf(url)
            if blob:
                problem = validate_pdf(target["id"], blob)
                if problem:
                    record["attempts"].append(f"{url}: rejected, {problem}")
                    continue
                path.write_bytes(blob)
                record.update(availability="available", url=url, local_file=path.name, retrieved_at=now,
                              size_bytes=len(blob), sha256=hashlib.sha256(blob).hexdigest())
                return record
        record["attempts"].append(err)
    return record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--refresh", action="store_true", help="download again even if a file exists")
    parser.add_argument("--only", default="", help="comma separated target ids")
    args = parser.parse_args()

    config.KB_DOCS_DIR.mkdir(parents=True, exist_ok=True)
    only = {x for x in args.only.split(",") if x}
    targets = [t for t in TARGETS if not only or t["id"] in only]

    previous = {}
    if config.SOURCES_JSON.exists():
        previous = {r["id"]: r for r in json.loads(config.SOURCES_JSON.read_text())["sources"]}

    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda t: collect(t, args.refresh), targets))

    for rec in results:
        old = previous.get(rec["id"], {})
        if rec.get("kept_existing"):  # keep provenance from the original download
            rec.update({k: old[k] for k in ("url", "retrieved_at", "sha256", "size_bytes") if k in old})
            rec.pop("kept_existing")
        previous[rec["id"]] = rec
        print(f"{rec['availability']:12} {rec['id']:32} {rec.get('url') or rec['attempts'][-1:]}", flush=True)

    ordered = [previous[t["id"]] for t in TARGETS if t["id"] in previous]
    config.SOURCES_JSON.write_text(json.dumps({
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "sources": ordered,
    }, indent=2, ensure_ascii=False))
    ok = sum(r["availability"] == "available" for r in ordered)
    print(f"{ok}/{len(ordered)} sources available")


if __name__ == "__main__":
    main()
