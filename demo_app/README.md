# Email Analysis Demo

Demo application for the dissertation — unifies the three paradigms (P1/P2/P3) into a
single system behind a Streamlit UI.

## Structure

```
demo_app/
├── app.py                    # Streamlit application (entry point)
├── config.py                 # Configuration (paths, URLs, timeouts)
├── requirements.txt          # Python dependencies
├── README.md                 # This file
│
├── backend/
│   └── colab_backend.ipynb   # FastAPI server for VLM + Donut (runs on Colab)
│
├── utils/
│   ├── outlook_monitor.py    # Outlook COM integration (live mode)
│   ├── inference_router.py   # Routes requests: P1 local, P2/P3 to Colab
│   ├── database.py           # SQLite for storing analyses
│   └── report_generator.py   # HTML/PDF/CSV report generation
│
├── demo_data/                # Local SQLite database
└── reports/                  # Generated reports
```

## Setup

### 1. Backend (Colab)

1. Open `backend/colab_backend.ipynb` in Google Colab Pro
2. Runtime → Change runtime type → **T4 GPU**
3. Make sure `donut_models.zip` is uploaded to `/content/drive/My Drive/disertatie/`
4. Put your ngrok token in cell 6:
   - Free account: https://dashboard.ngrok.com/get-started/your-authtoken
5. Run all cells
6. Copy the ngrok URL shown (e.g. `https://abc123.ngrok-free.app`)

### 2. Frontend (local)

```bash
cd demo_app
pip install -r requirements.txt
```

Configuration (via environment variables, with sensible fallbacks in `config.py`):
- `DISSERTATION_PATH` — path to the P1 scripts. **Default**: the repo's `../src`
  folder, so it works with no setup after cloning.
- `TESSERACT_PATH` — path to the Tesseract executable. **Default**: looks up
  `tesseract` on your PATH.
- `COLAB_BACKEND_URL` — the ngrok URL from Colab (only needed for P2/P3). Can also be
  set from the UI, at the Setup step.

Example (Windows PowerShell):
```powershell
$env:TESSERACT_PATH = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:COLAB_BACKEND_URL = "https://abc123.ngrok-free.app"
```

Start the app:

```bash
streamlit run app.py
```

The browser opens automatically at http://localhost:8501

### 3. For Live mode (Outlook)

Requires:
- Windows
- Outlook desktop installed and configured
- A working email account in Outlook

`pywin32` is installed automatically from requirements.txt (Windows only).

## Usage

### Standard flow

1. **Setup** — check the connection to the Colab backend
2. **Mode Selection** — choose Live (Outlook) or Upload (.msg files)
3. **Paradigm** — choose P1, P2, or P3 Hybrid
4. **Processing** — automatic (Live) or manual (Upload)
5. **Report** — view statistics and export results

### Paradigms

| Paradigm | Location | Components |
|---|---|---|
| **P1: Classical Pipeline** | Local | TF-IDF + Regex + OCR + Reconciliation |
| **P2: VLM Zero-Shot** | Colab | Qwen2.5-VL does everything in one prompt |
| **P3: Hybrid** | Local + Colab | Donut for documents (Colab) + the rest local |

> Note: the demo uses the lightweight **TF-IDF baseline** for local intent
> classification (fast, no transformer to load). The benchmark in the main README
> reports the fine-tuned **DistilBERT** classifier; both reach ~100% on clean data.

## Troubleshooting

**Backend Offline:**
- Check that the Colab notebook is still running (a Colab Pro session lasts ~12h)
- Free ngrok tunnels expire periodically — restart cell 6 in the notebook
- Copy the new URL into the `COLAB_BACKEND_URL` variable (or into the UI Setup)

**Outlook won't connect:**
- Make sure Outlook desktop is open
- On Windows, run Streamlit from a terminal under the same user as Outlook
- If an Outlook security prompt appears, click "Allow"

**P1 can't find the modules:**
- Check the `DISSERTATION_PATH` variable (default `../src`)
- Make sure that folder contains: `email_field_extractor.py`,
  `document_field_extractor.py`, `reconciliation.py`

**Tesseract not found (P1 OCR):**
- Install: https://github.com/UB-Mannheim/tesseract/wiki
- Add to PATH: `C:\Program Files\Tesseract-OCR`

## Notes for a live demo

Recommendation: test the whole flow 1–2 days before presenting. ngrok can be flaky,
a Colab Pro session may have expired, and Outlook can have sync issues.

**Plan B:** if the Colab backend doesn't respond, the demo still runs with P1
(fully local). Just mention in the UI: "Colab backend temporarily unavailable —
using P1 as fallback."
