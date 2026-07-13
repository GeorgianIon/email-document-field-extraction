# Document & Email Field Extraction — Three Paradigms Compared

A reproducible benchmark that pits three fundamentally different approaches to the
same real-world procurement problem against each other: **extract key fields from
supplier emails and their document attachments (invoices, quotations, price lists),
then reconcile the two and flag discrepancies.**

The study compares:

- **P1 — Classical Pipeline:** DistilBERT intent classification + Tesseract OCR + regex field extraction + rule-based reconciliation.
- **P2 — Zero-Shot VLM:** `Qwen2.5-VL-3B-Instruct` prompted directly on the document images, no training.
- **P3 — Fine-Tuned Document Model:** `naver-clova-ix/donut-base` fine-tuned end-to-end (OCR-free) for structured extraction.

> This repository is the codebase behind my MSc dissertation in *Advanced Digital
> Imaging Techniques* (Politehnica București, ETTI). It contains the full data
> generation pipeline, all three paradigms, a robustness/augmentation study, and a
> Streamlit demo app that unifies the three approaches behind one interface.

---

## Why this problem

In procurement, the same figures arrive twice: once as free text in an email
("the quote is valid until…", "please find invoice 12345 attached") and once inside
an attached document. A useful automation has to (1) understand *what the email is
about*, (2) pull the same fields from **both** modalities, and (3) notice when they
**disagree** — a wrong amount or currency on an invoice is exactly the kind of error
worth catching automatically.

That makes it a clean testbed for a bigger question: for structured extraction from
business documents, **when is a hand-built classical pipeline enough, when does a
zero-shot VLM justify its cost, and when is fine-tuning a document model worth it?**

---

## Results

All numbers are on the held-out **test** split. The dataset is synthetic and
template-based, so absolute scores are optimistic by design — the interesting signal
is in the *relative* behaviour and in how each paradigm degrades under corruption
(see [Robustness](#robustness)).

### Clean data

| Task | P1 — Pipeline | P2 — VLM (zero-shot) | P3 — Donut (fine-tuned) |
|------|:-------------:|:--------------------:|:-----------------------:|
| Intent classification (F1 macro) | **100.0%** (DistilBERT) | 81.4% | — |
| Email field extraction | 100.0% | 89.2% | — |
| Document field extraction | 97.7% | 72.3% | **98.6%** |
| Mismatch detection (F1) | **95.7%** | 57.9% | — |

*"—" = the paradigm does not cover that task by design. Donut is a document-only
extractor; reconciliation and intent for P3 reuse the pipeline components.*

Pipeline reconciliation in detail (test split): **precision 100%, recall 91.7%,
F1 95.7%**, overall accuracy 98.2% — it never raised a false mismatch, and missed
only one true discrepancy.

Document field extraction, per field:

| Field | P1 (OCR + regex) | P3 (Donut, clean) |
|-------|:----------------:|:-----------------:|
| amount     | 55/55 | 55/55 |
| currency   | 55/55 | 55/55 |
| doc_number | 50/55 | 53/55 |
| date       | 55/55 | 54/55 |

The pipeline's document errors are almost entirely `doc_number` OCR confusions
(`Q-2024-19714` → `Q-2004-19714`, `AV0` vs `QUO`, dropped digits) — the classic
failure mode of OCR + regex on look-alike glyphs.

### Robustness

To show that near-perfect clean-data scores are an artefact of controlled templates,
every input is corrupted at three severities across three scenarios (noisy **text**,
degraded **image**, and **mixed**). Highlights on medium severity:

- **P3 (Donut)** degrades most gracefully on document fields: **98.6% → 96.4%**.
- **Intent classification** is the most robust task overall: DistilBERT holds **100% F1 even under text augmentation**, while the TF-IDF + LogReg baseline slips to 98.8% — the transformer earns its keep exactly where noise is introduced.
- **P2 (VLM)** is remarkably stable on intent/email fields but its mismatch F1 is
  brittle, sliding from 57.9% toward ~48% under text noise.
- **P1 (Pipeline)** is the most exposed: OCR-dependent steps drop noticeably once
  images are degraded, which is exactly the weakness a fine-tuned OCR-free model
  like Donut is meant to address.

The takeaway: **the classical pipeline wins on clean, templated inputs and on
reconciliation logic; the fine-tuned document model wins on robustness; the
zero-shot VLM buys you generality with no training but pays for it in precision.**

---

## Repository structure

```
email-document-field-extraction/
├── src/                         # Paradigm 1 + data generation (pure-Python, CLI scripts)
│   ├── config.py                #   dataset schema, distributions, supplier data (SEED=42)
│   ├── templates.py             #   email templates per intent class
│   ├── generate_dataset.py      #   -> emails.csv, pairs.csv
│   ├── generate_documents.py    #   -> rendered PDF/PNG attachments
│   ├── split_dataset.py         #   -> stratified train/val/test + splits.json
│   ├── intent_classifier.py     #   TF-IDF baseline + DistilBERT fine-tuning
│   ├── email_field_extractor.py #   regex extraction from email text
│   ├── document_field_extractor.py  # Tesseract OCR + regex from attachments
│   ├── reconciliation.py        #   text vs document field comparison / mismatch detection
│   ├── augmentation.py          #   text/image/mixed corruption at 3 severities
│   ├── evaluate_augmented.py    #   re-train + evaluate P1 under augmentation
│   ├── final_comparison.py      #   aggregates P1/P2/P3 into the comparison tables
│   └── demo_pipeline.py         #   run the full pipeline on a real .msg / email
│
├── notebooks/                   # GPU paradigms (run on Colab)
│   ├── colab_intent_classifier.ipynb   # baseline + DistilBERT
│   ├── colab_vlm_evaluation.ipynb      # P2: Qwen2.5-VL zero-shot
│   └── colab_donut_finetuning.ipynb    # P3: Donut fine-tuning
│
├── data/                        # generated synthetic dataset (CSVs) + how to regenerate
├── results/                     # pre-computed evaluation JSONs for all paradigms
├── demo_app/                    # Streamlit app unifying P1/P2/P3 (+ Outlook live mode)
├── requirements.txt             # deps for P1, data generation, augmentation
└── LICENSE
```

---

## Quickstart

### 1. Install

```bash
git clone https://github.com/<your-username>/email-document-field-extraction.git
cd email-document-field-extraction
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Paradigm 1 needs the **Tesseract** OCR engine installed on the system (the Python
`pytesseract` package is only a wrapper). On Ubuntu: `sudo apt install tesseract-ocr`.

### 2. (Optional) Regenerate the dataset

The CSVs are already in `data/`. To rebuild everything deterministically:

```bash
cd src
python generate_dataset.py   --data_dir ../data
python generate_documents.py --data_dir ../data     # renders attachments -> data/attachments/
python split_dataset.py      --data_dir ../data
```

### 3. Run Paradigm 1

> **Attachments:** document extraction needs the rendered files in
> `data/attachments/`. They are not committed (large, reproducible) — run
> `generate_documents.py` from step 2, or drop your own PDFs/PNGs there matching the
> `attachment_path` column in `data/pairs.csv`. See
> [`data/attachments/README.md`](data/attachments/README.md).

```bash
cd src
python email_field_extractor.py    --split test --data_dir ../data
python document_field_extractor.py --split test --data_dir ../data
python reconciliation.py           --split test --data_dir ../data
```

### 4. Paradigms 2 & 3

Open the notebooks in `notebooks/` on Google Colab (T4/A100), upload the CSVs +
attachments when prompted, and run all cells. They export their metrics as the JSON
files already checked into `results/`.

### 5. Full comparison table

```bash
cd src
python final_comparison.py --data_dir ../results   # reads results/*.json, prints all tables
```

The pre-computed P2 (VLM) and P3 (Donut) metrics live in `results/`. The P1-augmented
column populates only after you run the robustness pipeline (`augmentation.py` +
`evaluate_augmented.py`), which writes `augmented_results/` — until then that column
shows as pending, by design.

### 6. Try it on a real email

```bash
cd src
python demo_pipeline.py --msg path/to/email.msg          # from an Outlook .msg
python demo_pipeline.py --file email.txt --attachment invoice.pdf
```

---

## The demo app

`demo_app/` is a Streamlit application that puts the three paradigms behind a single
UI. It can ingest emails from an uploaded `.msg` file or, on Windows, monitor an
Outlook inbox live; it routes P1 locally and P2/P3 to a Colab-hosted FastAPI backend
(exposed via ngrok), stores analyses in SQLite, and exports HTML/CSV reports. See
[`demo_app/README.md`](demo_app/README.md) for setup.

Paths are configured via environment variables (`DISSERTATION_PATH`, `TESSERACT_PATH`,
`COLAB_BACKEND_URL`) with sensible defaults — nothing machine-specific is hardcoded.

---

## Dataset

500 synthetic supplier emails across five intents (`quote_offer`,
`invoice_submission`, `price_validity_confirmation`, `price_increase`, `other`),
each optionally paired with a rendered PDF/PNG attachment. Around 35% of paired
records contain a deliberate email↔document discrepancy (amount, currency or date)
so reconciliation has something real to catch. Everything is fictional and generated
from `src/config.py`. Details in [`data/README.md`](data/README.md).

---

## Tech stack

**Python** · scikit-learn · Hugging Face `transformers` / `datasets` · PyTorch ·
DistilBERT · Qwen2.5-VL · Donut · Tesseract OCR · ReportLab / Pillow / pypdfium2 ·
nlpaug / OpenCV / Albumentations · Streamlit · FastAPI · SQLite

---

## Author

**Ion Florentin-Georgian** — MSc, Advanced Digital Imaging Techniques (Politehnica
București, ETTI). Dissertation defended 2026.

Licensed under the [MIT License](LICENSE).
