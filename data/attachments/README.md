# Attachments

The rendered document attachments (invoices, quotations, price lists as **PDF and
PNG**) referenced by `../pairs.csv` go **here**, in this folder.

The `attachment_path` column in `pairs.csv` looks like `attachments/invoice_0186.pdf`,
and the extraction scripts resolve it as `<data_dir>/<attachment_path>` — so with the
recommended `--data_dir ../data`, every file must live at
`data/attachments/<filename>`.

The files themselves are **not committed** to the repository (310 files, large, and
fully reproducible) — with the exception of a **small set of example documents** kept
here so the synthetic invoices, quotations and price lists can be viewed directly on
GitHub without regenerating anything:

- `invoice_0123.pdf` / `invoice_0121.png`
- `quotation_0001.pdf` / `quotation_0004.png`
- `price_list_0325.pdf` / `price_list_0334.png`
- `generic_0402.pdf`

To generate the full set (all 310 attachments referenced by `pairs.csv`):

```bash
cd ../../src
python generate_documents.py --data_dir ../data
```

This reads `data/pairs.csv` and writes all 310 attachments into this folder
(208 PDF + 102 PNG), deterministically (`SEED = 42`).
