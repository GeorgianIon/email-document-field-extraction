# Email Analysis Demo

Demo aplicație pentru disertație - integrează cele 3 paradigme (P1/P2/P3) într-un sistem unitar cu UI Streamlit.

## Structura

```
demo_app/
├── app.py                    # Streamlit application (entry point)
├── config.py                 # Configuration (paths, URLs, timeouts)
├── requirements.txt          # Python dependencies
├── README.md                 # This file
│
├── backend/
│   └── colab_backend.ipynb   # FastAPI server for VLM + Donut (rulează pe Colab)
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

1. Deschide `backend/colab_backend.ipynb` pe Google Colab Pro
2. Runtime → Change runtime type → **T4 GPU**
3. Asigură-te că ai uploadat `donut_models.zip` în `/content/drive/My Drive/disertatie/`
4. Pune token-ul ngrok în celula 6:
   - Cont gratuit: https://dashboard.ngrok.com/get-started/your-authtoken
5. Rulează toate celulele
6. Copiază URL-ul ngrok afișat (ex: `https://abc123.ngrok-free.app`)

### 2. Frontend (Local)

```bash
cd demo_app
pip install -r requirements.txt
```

Configurare (variabile de mediu, cu fallback-uri sensibile în `config.py`):
- `DISSERTATION_PATH` — calea către scripturile P1. **Implicit**: folderul `../src` din repo, deci merge fără nicio setare după clonare.
- `TESSERACT_PATH` — calea către executabilul Tesseract. **Implicit**: caută `tesseract` în PATH.
- `COLAB_BACKEND_URL` — URL-ul ngrok din Colab (necesar doar pentru P2/P3). Se poate seta și din UI, la pasul Setup.

Exemplu (Windows PowerShell):
```powershell
$env:TESSERACT_PATH = "C:\Program Files\Tesseract-OCR\tesseract.exe"
$env:COLAB_BACKEND_URL = "https://abc123.ngrok-free.app"
```

Pornește aplicația:

```bash
streamlit run app.py
```

Browser-ul se deschide automat la http://localhost:8501

### 3. Pentru modul Live (Outlook)

Necesită:
- Windows
- Outlook desktop instalat și configurat
- Cont de email funcțional în Outlook

`pywin32` se instalează automat din requirements.txt (doar pe Windows).

## Utilizare

### Flow standard

1. **Setup** — verifică conexiunea la backend Colab
2. **Mode Selection** — alegi Live (Outlook) sau Upload (.msg files)
3. **Paradigm** — alegi P1, P2, sau P3 Hybrid
4. **Procesare** — automată (Live) sau manuală (Upload)
5. **Report** — vezi statistici și exportă rezultate

### Paradigme

| Paradigm | Locație | Componente |
|---|---|---|
| **P1: Pipeline Clasic** | Local | TF-IDF + Regex + OCR + Reconciliation |
| **P2: VLM Zero-Shot** | Colab | Qwen2.5-VL face totul într-un prompt |
| **P3: Hybrid** | Local + Colab | Donut pentru documente (Colab) + restul local |

## Troubleshooting

**Backend Offline:**
- Verifică că notebook-ul Colab încă rulează (sesiunea Colab Pro durează 12h)
- ngrok-ul gratuit expiră periodic — restartează celula 6 din notebook
- Copiază noul URL în `config.py` sau în UI Setup

**Outlook nu se conectează:**
- Asigură-te că Outlook desktop e deschis
- Pe Windows, rulează Streamlit dintr-un terminal cu același user ca Outlook
- Dacă apare prompt de securitate Outlook, dă „Allow"

**P1 nu găsește modulele:**
- Verifică variabila `DISSERTATION_PATH` (implicit `../src`)
- Asigură-te că în acel folder există: `email_field_extractor.py`, `document_field_extractor.py`, `reconciliation.py`

**Tesseract not found (P1 OCR):**
- Instalează: https://github.com/UB-Mannheim/tesseract/wiki
- Adaugă în PATH: `C:\Program Files\Tesseract-OCR`

## Notă pentru susținere

Recomandare: testează tot flow-ul cu 1-2 zile înainte de susținere. ngrok-ul poate avea pică, Colab Pro poate avea sesiune expirată, Outlook poate avea probleme de sincronizare.

**Plan B la susținere:** dacă backend-ul Colab nu răspunde, demo-ul rulează în continuare cu P1 (totul local). Tu menționezi în UI: „Backend Colab momentan indisponibil — folosesc P1 ca fallback".
