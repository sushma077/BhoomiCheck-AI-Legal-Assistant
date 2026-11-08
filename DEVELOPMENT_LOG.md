# BhoomiCheck development log

A running record of real decisions, mistakes and corrections made while building
this project. Entries are written when they happen. The solution PDF takes its
"AI error" example from this file.

Author of the code: Claude (Claude Code, model `claude-opus-5-5`), working from the
project brief. "AI error" below means an error made by that assistant, or by the
small local model where stated.

## Environment found on 2026-11-07

- macOS 26.6.2, Apple M1, 8 GB RAM, Python 3.13 system / 3.12 project venv.
- No Anthropic or other LLM key in the environment. No Ollama. No Tesseract at the start.
- Installed `tesseract` and `tesseract-lang` through Homebrew (ARM prefix).

## Errors and corrections

### E1. Wrong diagnosis of India Code as "blocked"

- **What the AI concluded:** `www.indiacode.nic.in` returned HTTP 403 to the first
  probe, so the AI told the user several government sites were blocking scripts and
  planned to record India Code as unavailable.
- **How it was caught:** reading the body of the response instead of only the status
  code. The page was a "Site Migration" notice pointing to `indiacode.gov.in`.
- **Correction:** the collector now uses the new host's public repository API. The
  same probe also showed the 403s on `mohua.gov.in` and `legislative.gov.in` went away
  once the client identified itself plainly, without a browser-style `Mozilla/5.0`
  string. No protection was bypassed.
- **Lesson:** a status code is not a diagnosis. Read the response.

### E2. Trusting a PDF's text layer for Hindi

- **What the AI assumed:** the first version of `document_processor.py` used a PDF's text
  layer whenever it had enough characters, and only ran OCR on empty pages.
- **How it was caught:** a rendering test printed the text layer of a correctly displayed
  Hindi page as `खाता संéया 214 ... Zेİफल`. The picture was correct and the text was garbage.
  OCR of the same page returned `खाता संख्या 214 ... क्षेत्रफल` at 92% confidence.
- **Correction:** the processor now detects stray Latin-extended characters mixed with
  Devanagari and sends those pages to OCR.

### E3. Collector saved the wrong legal documents and reported success

- **What the AI wrote:** the India Code API fallback in `collect_sources.py` took the first
  PDF attached to a record and marked the source "available". The run printed `14/23 sources
  available`.
- **How it was caught:** checking page counts and first lines before indexing. The "RERA
  Act" file was a 2-page Rajasthan notification, the "Contract Act" file had no extractable
  text, the "Specific Relief Act" file was one garbled page, and the "Karnataka Land Revenue
  Act" and "Benami Act" files were short notifications. India Code attaches rules and
  notifications to the same record as the Act.
- **Correction:** every download must now pass a content check: expected title text in the
  opening pages, plus a minimum page count. Attachments are tried largest first. Wrong files
  were deleted before any index was built.
- **Why it matters:** a RAG index built on these files would have answered RERA questions from
  an unrelated notification while the source list still said "RERA Act".

### E4. Registration number taken from the wrong deed

- **What the AI wrote:** `_registration()` returned the first "Document No." on the page.
- **How it was caught:** printing extracted fields for the base sale deed. It reported
  `3341/2009`, the earlier deed quoted in the recitals, instead of `2217/2023`, the deed's own number.
- **Correction:** numbers in sentences about an earlier purchase are skipped, and the last
  remaining number wins, as registration endorsements come at the end of a deed.

### E5. Fuzzy match treated different boundaries as equal

- **What the AI wrote:** boundaries were compared with `token_set_ratio`, which scores shared words highly.
- **How it was caught:** test T07. "30 feet wide road" and "12 feet wide lane" passed as the same boundary.
- **Correction:** differing numbers now count as a mismatch, and common words are removed before comparing.

### E6. Sale deed classified as a Power of Attorney

- **What the AI wrote:** the classifier gave triple weight to anything in the first 500 characters.
  A sale deed signed "through his General Power of Attorney holder" scored as a POA.
- **How it was caught:** test T18 was missing the POA finding, and the deed had been given POA checks.
- **Correction:** the title zone is now the first few lines of the document, skipping the synthetic-document marking.

### E7. A local model gave dangerous advice and the validator approved it (main example)

- **What the AI wrote:** the assistant's validator in `citation_validator.py` only rejected forbidden
  phrases and section numbers missing from the context. This assistant designed it and treated
  it as sufficient hallucination protection.
- **What happened:** the first real run of the local model (`mlx-community/Qwen2.5-3B-Instruct-4bit`)
  on "Registry karana zaroori hai kya?" returned garbled Hindi saying registration is *not* required
  (`Registry करना जरूरी नहीं ...`). The retrieved passages say the opposite: a sale of tangible immovable
  property of Rs. 100 or more can be made only by a registered instrument (Transfer of Property
  Act s.54). The validator returned `ok: true`, so a user would have seen it.
- **How it was caught:** a person-style read of raw model output, rather than trusting the green result.
  No automated test had flagged it. The answer carried no citation at all, and nothing required one.
- **Correction:** legal answers must now carry a passage tag. Sentences need word overlap with the passages.
  A negative claim needs a matching negative in the sources. Garbled or wrong-script text is rejected.
  Small local models may only answer in English. Hindi and Hinglish replies use fixed text and quotes.
  Rejected output stays in `raw_outputs/` for audit, and the user sees the quoted answer instead.
- **Lesson:** a validator that passes is not evidence of safety until it has been tested against real
  bad output. Model answers now run in the evaluation as a separate section.

### E8. Extraction rules overfitted to the AI's own documents

- **What the AI wrote:** extraction rules that scored 236 of 237 field checks on the development documents, which
  the same AI also wrote. (An earlier draft of this entry said "279 of 280", from a partial script run. The frozen
  evaluation file shows 236 of 237, and this entry was corrected.)
- **How it was caught:** the first run of the holdout set, written in other wording, scored **18 of 28 (64.3%)**
  on fields and 3 of 4 on scenarios. Narrative party clauses, inline "(Licensor)" roles, number words ("twenty-four
  months") and "I, X ... appoint Y" were all missed. Result frozen in `evaluation/first_holdout_run_summary.json`.
- **Correction:** general fixes for those patterns. That holdout is no longer unseen, so a second new set
  (`fresh_*`) was written before the fixes were tested and run once to get a clean measure.

### E9. Legal questions routed to document lookups

- **What the AI wrote:** any question containing "tenant" went to the document-fact lookup.
- **How it was caught:** model test M03. "Can a tenant be evicted without notice under this law?" returned
  "no documents uploaded" instead of searching the law.
- **Correction:** document-fact routing now needs a question form asking for a fact.

### E10. Sub-Registrar value swallowed the next line

- **What the AI wrote:** the Sub-Registrar pattern ran on flattened text, so line breaks were lost.
- **How it was caught:** reading the rendered report: `Sub-Registrar: Harinagar-II Certificate Date`.
- **First fix failed, twice:** the replacement pattern was accidentally case-sensitive and missed every `Sub-Registrar`.
  Regression tests failed on 11 documents (dev fields fell to 225 of 237). The AI first blamed line wrapping, rewrote the
  code on that theory, and the tests failed the same way. Reading the pattern showed the real cause.
- **Correction:** a case-insensitive pattern on flattened text that stops at words beginning the next item. This came
  after the fresh-set measurement, so that score is preserved separately in `evaluation/fresh_set_first_run_summary.json`.

## Known behaviour worth stating

- The strict validator rejects most local-model answers, including at least one correct one (M02). Across the full evaluation
  runs it accepted at most 1 answer per run, and none in some runs. It fails closed, and the user sees quoted law.
- Local model answers vary between runs, so the same question (M01) was accepted in one run and rejected in another.
- The validator caught 11 of 16 plausible false statements. The five it missed are listed in `evaluation_summary.json`.
  Word-based checks cannot verify meaning, which is why source quotes always appear with any model reply.
