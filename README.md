# BhoomiCheck

**Understand Documents. Identify Risks. Verify Before You Invest.**

> BhoomiCheck gives preliminary help with documents. It is not legal advice and does not certify title or ownership. Before you pay or sign, have a qualified property lawyer check the documents.

## 1. Project description

For most Indian families, a house or a plot of land is the biggest purchase they will ever make. The papers involved include sale deeds, mutation records, Khatauni and 7/12 extracts, encumbrance certificates and powers of attorney. They are long, often in Hindi or legal English, and they can contradict one another. Many buyers sign without fully understanding them.

BhoomiCheck is a web app that helps a citizen read these documents before relying on them. You upload your property papers, and BhoomiCheck:

- reads the documents
- pulls out the key details, with the page each one came from
- compares the documents with each other
- flags anything that needs checking
- answers your questions in English, Hindi or Hinglish

Answers about the law quote official sources: Acts from India Code, Supreme Court judgments and government guidelines.

BhoomiCheck was built for the Kuku placement assignment, Problem 2: Build an AI Lawyer. It is designed not to behave like a confident chatbot. Python rules make every decision, legal answers quote real sources, and the app refuses to promise "clear title" or "100% safe", because nobody can promise that from documents alone.

## 2. Features

| Page | What it does |
|---|---|
| **Home** | Overview of the app and where to start |
| **Upload Documents** | Upload PDF, JPG, JPEG or PNG files, several at a time. Scanned pages are read with OCR in English and Hindi |
| **Document Analysis** | Identifies each document's type (sale deed, mutation, Khatauni, encumbrance certificate, power of attorney, lease and others) and lists its key details: names, Khasra and Khata numbers, area, boundaries, dates, amounts and registration number. Each detail shows the page it came from |
| **Ownership Details** | Lists the owners in date order and shows the chain of ownership |
| **Compare Documents** | Checks names, Khasra and Khata numbers, area, boundaries, dates and amounts across documents, and matches names written in Hindi against the same names in English |
| **Risk Analysis** | Findings rated *High Priority*, *Warning* or *Information*. Each one gives the reason, the document and page, what to verify and the relevant law |
| **Due-Diligence Checklist** | Checklists for buying, selling, renting, agricultural, residential, commercial and inherited property |
| **Legal Assistant** | Answers questions about your documents and about Indian property law, in English, Hindi or Hinglish. It quotes sources and refuses requests to certify title |
| **Property Report** | Downloads the analysis as a PDF, Word or JSON report you can take to a lawyer |
| **About and Disclaimer** | Shows the sources used, the app's limits and the current settings |

Other features:

- **No API key needed.** The app works fully offline, without any AI model. A language model can be connected for more natural answers if you want one (see below).
- **Official legal sources.** 20 sources, split into 2,833 searchable passages. These include the Transfer of Property Act, Registration Act, Indian Stamp Act, RERA, Hindu Succession Act, Uttar Pradesh and Maharashtra revenue law, and Supreme Court judgments.
- **Sample documents.** The app comes with 51 synthetic documents about fictional people, for trying it out and testing.
- **Honest testing.** Pytest tests and a full evaluation are included. Their raw outputs are kept in `raw_outputs/`.

## 3. How it works

```
Upload -> Read text (PDF text layer, or Tesseract OCR for scans) -> Identify document type
       -> Extract details, with page and evidence -> Compare documents with Python rules
       -> Risk findings -> Checklists and reports

Question -> Refuse if it asks for certification -> Answer from document facts, findings or definitions
         -> Search legal sources (keyword + meaning search) -> Answer with quoted passages
         -> Optional language model, whose reply must pass a citation check
```

**Step by step:**

1. **Reading.** The app first uses the text built into the PDF. Some Hindi PDFs give garbled text this way, so BhoomiCheck detects that and reads those pages with Tesseract OCR instead. Scanned images also go to OCR. If Tesseract isn't installed, RapidOCR is used.
2. **Identifying the document.** Each document's type is worked out from its title and the keywords it contains.
3. **Extracting details.** Python rules pull out names, property numbers, area, boundaries, dates, amounts and registration details. Each value keeps its page number and the line of text it came from.
4. **Comparing.** Rules compare those details across documents. One example is a sale deed that names a different buyer from the mutation record. Names in Hindi are converted to English letters so they can be matched.
5. **Risk findings.** Each mismatch or warning sign becomes a finding with a severity, the reason, where it was seen and what to verify. Findings link to the exact section of the law.
6. **Legal search.** The legal sources are split by section, for Acts, or by page, for judgments and guidelines. A question is answered by searching two ways at once, by keywords (BM25) and by meaning (multilingual embeddings), and combining the results.
7. **Answering.** Without a model, the assistant answers using the facts from your documents, fixed explanations and direct quotes from the law, and it says so. With a model, the model may only explain the passages that were found. A citation validator then checks the reply and rejects it if it contains forbidden promises, section numbers not found in the sources, or statements the sources don't support. Source quotes are always shown alongside a model's answer.

**AI and rules.** Python rules make every extraction, comparison and risk decision. Embeddings help find relevant passages. A language model, if connected, can only explain law that has already been found. It cannot create a finding.

**Retrieval, not training.** Legal passages are looked up when a question is asked. No model was trained on this material.

**Project layout:**

| Path | Contents |
|---|---|
| `app.py`, `ui/` | The Streamlit interface |
| `core/` | Reading, OCR, classification, extraction, comparison, risk rules, legal search, validation, assistant and reports |
| `knowledge_base/` | Legal sources, the search index and `sources.json`. See [its README](knowledge_base/README.md) |
| `data/synthetic_documents/` | Sample documents with fictional people |
| `scripts/` | Download sources, build the index, create sample documents, build the PDF documents |
| `evaluation/`, `tests/` | The evaluation and the Pytest suite |
| `raw_outputs/` | Unedited outputs from real runs. See [its README](raw_outputs/README.md) |
| `deliverables/` | Solution document, project summary and walkthrough script |
| `DEVELOPMENT_LOG.md` | Real errors made during the build, and how each was found and fixed |

## 4. Install and run on your own computer

### What you need

- **Python 3.12**
- **Tesseract OCR**, with the Hindi language pack. This is optional, because the app uses RapidOCR if Tesseract is missing, but Tesseract is recommended.
- About **2 GB of free disk space**. The first legal search downloads a free embedding model of a few hundred MB. If the download fails, search uses keywords only.

### macOS (tested)

```bash
# 1. Install Tesseract with its language packs
brew install tesseract tesseract-lang

# 2. Go to the project folder
cd BhoomiCheck

# 3. Create a virtual environment and install the packages
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt

# 4. Start the app
.venv/bin/streamlit run app.py
```

### Linux: Debian or Ubuntu (not tested)

```bash
sudo apt install tesseract-ocr tesseract-ocr-hin python3.12 python3.12-venv
cd BhoomiCheck
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/streamlit run app.py
```

### Windows (not tested)

1. Install Python 3.12 from [python.org](https://www.python.org/downloads/). Tick "Add Python to PATH".
2. Optional: install Tesseract using the UB Mannheim installer, include Hindi, and add its folder to PATH.
3. In Command Prompt:

```bat
cd BhoomiCheck
py -3.12 -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\streamlit run app.py
```

### Use the app

Open **http://localhost:8501** in your browser. To stop the app, press `Ctrl + C` in the terminal.

To try it, upload these sample files from `data/synthetic_documents/`:

- `sale_deed_2023.pdf`
- `mutation_owner_mismatch.pdf`
- `ec_mortgage.pdf`
- `hindi_khatauni_scan.pdf`

Then open Compare Documents and Risk Analysis.

### Optional: connect a language model

You don't need one. The app picks the first option it finds, in this order. To set the values, copy `.env.example` to `.env`. Keys are read from the environment and never logged.

| Option | How to turn it on | Tested? |
|---|---|---|
| Anthropic API | Set `ANTHROPIC_API_KEY` in `.env` | Code written, **not run** (no key was available) |
| Local Ollama | Install and run Ollama | Code written, **not run** (Ollama was not installed) |
| Local MLX (Apple Silicon Macs) | `.venv/bin/pip install -r requirements-local-model.txt`, then set `BHOOMI_MLX_MODEL=mlx-community/Qwen2.5-3B-Instruct-4bit` | **Tested** |
| None (default) | Nothing | **Tested.** Used for all main test results |

If you connect a cloud provider, your questions and the extracted document details are sent to that provider.

### Run the tests

```bash
.venv/bin/python -m pytest tests -q        # 157 tests, all passing at the last run
.venv/bin/python evaluation/run_evals.py   # full evaluation, writes evaluation/evaluation_summary.json
```

### Rebuild everything from scratch (optional)

```bash
.venv/bin/python scripts/collect_sources.py        # add --refresh to download again
.venv/bin/python scripts/build_index.py
.venv/bin/python scripts/generate_synthetic_docs.py
.venv/bin/python evaluation/run_evals.py
.venv/bin/python scripts/build_docs.py
```

## 5. Known limitations

- **It has never been tested on real documents.** Every test document is synthetic, and the same AI wrote both the rules and the test documents. The results on wording the rules had not seen are the fairer guide:

  | Measure | Development set | Unseen set 1, first run | Unseen set 2, first run |
  |---|---|---|---|
  | Field extraction | 236/237 (99.6%) | 18/28 (64.3%) | 22/27 (81.5%) |
  | Scenarios | 32/32 | 3/4 | 4/4 |
  | Classification | 35/35 | 6/6 | 6/6 |
  | Legal search, correct in top 3 | 31/32 | 10/12 | 6/8 |

  Set 1 showed that the rules were overfitted to the development set, and general fixes were made before set 2 was run. Expect real documents to score lower.
- **Extraction uses rules.** Unfamiliar wording or layouts can be missed. Some failures are listed in `evaluation/evaluation_summary.json`.
- **The citation validator can't fully check meaning.** In a stress test it caught 11 of 16 plausible false statements, so it missed 5, and it accepted all 6 true ones. It also rejects some correct answers. In the final run, the local model produced 6 answers and 1 passed. This is why source quotes always appear alongside a model's answer.
- **Citation checks confirm the source, not the reading.** All 184 citations checked point to passages that really exist. That does not prove the legal interpretation is correct.
- **Hindi and Hinglish support is limited without a capable model.** Replies use fixed text plus English quotes, and finding text stays in English. Search in Hindi is weaker than in English.
- **Legal coverage is partial.** Only Uttar Pradesh and Maharashtra revenue law is included. The Benami Act, Karnataka law, the Model Tenancy Act and some portal sources could not be collected. 8 of 28 planned sources were unavailable, and `knowledge_base/sources.json` records them as unavailable.
- **Some law may be out of date.** Some Act copies carry older amendment dates, and it was not confirmed whether the draft Registration Bill, 2025 has become law.
- **It only sees what you upload.** It does not check court, bank, registry or land-record systems, and it cannot detect forgery or a missing document that was never uploaded.
- **Only some setups have been tested.** The app was tested on an Apple Silicon Mac only. Linux, Windows, the Anthropic and Ollama connectors, and Streamlit Cloud deployment have not been tried.
- **No lawyer has reviewed this project.**
