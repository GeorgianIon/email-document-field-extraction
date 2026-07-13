# Dataset

This folder holds the **synthetic** supplier-email dataset used across all three
paradigms. Everything here is generated from templates and fictional company
names in [`../src/config.py`](../src/config.py) — there is no real correspondence
or personal data.

## Files

| File | Description |
|------|-------------|
| `emails.csv` | 500 email records with an intent label and ground-truth fields (amount, currency, doc_number, date), including whether each field is explicitly mentioned in the body. |
| `pairs.csv` | Email-to-attachment mapping. Records the document type, format (PDF/PNG) and any deliberate email↔document mismatch used to test reconciliation. |
| `train.csv` / `val.csv` / `test.csv` | 70 / 15 / 15 stratified split (by intent **and** mismatch presence), no leakage. |
| `splits.json` | The `email_id → split` assignment used to produce the CSVs above. |

## What is *not* committed

The rendered attachment files (`attachments/`) are **not** in the repo — they are
large and fully reproducible. Regenerate the whole dataset from scratch:

```bash
cd ../src
python generate_dataset.py   --data_dir ../data     # emails.csv + pairs.csv
python generate_documents.py --data_dir ../data     # renders attachments/ (PDF + PNG)
python split_dataset.py      --data_dir ../data      # train/val/test + splits.json
```

The pipeline is seeded (`SEED = 42` in `config.py`), so regeneration is
deterministic.
