# Raw outputs

Unedited JSON written by `evaluation/run_evals.py` during real runs. Nothing in here is written by hand, except `first_run/E7_original_model_output.txt`, which was copied from terminal output and says so.

| Folder | Contents |
|---|---|
| `documents/` | One file per input document: extracted page text, OCR method and confidence, classification, structured fields, score |
| `scenarios/` | One file per test scenario: input documents, detected mismatches, risk findings, score, status and errors |
| `assistant/` | Assistant answers, retrieved sources and scores, plus `validator_stress.json` |
| `retrieval/` | Each search question with its retrieved passages, URLs and rank |
| `model/` | The real local language model: original response, what the user would see, validation result |
| `reports/` | An example PDF and Word report from a real scenario |
| `first_run/` | Frozen first runs of the two unseen test sets, and the bad model answer described in `DEVELOPMENT_LOG.md` E7 |

Every file records its execution timestamp and model identifier. Files generated without a language model show `none (deterministic rules and retrieval)` or `none: rule-based extraction`. They are not model output.

All input documents are synthetic, with fictional people and places.

To regenerate: `.venv/bin/python evaluation/run_evals.py`, or add `--with-model` if a language model is configured.

Re-running overwrites everything except `first_run/`. Local model answers vary between runs, so `model/` will differ.
