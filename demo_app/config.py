"""
config.py
─────────
Configuration for the demo application.
Edit this file to point to your project paths and Colab backend URL.
"""

import os

# ═══════════════════════════════════════════════════════════
# Paths
# ═══════════════════════════════════════════════════════════

# Path to the dissertation project (where P1 modules from src/ are located).
# Override with the DISSERTATION_PATH environment variable; defaults to the
# repository's src/ folder so the app works out-of-the-box after cloning.
DISSERTATION_PATH = os.environ.get(
    'DISSERTATION_PATH',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'src'))
)

# Storage for app data
APP_DIR = os.path.dirname(os.path.abspath(__file__))
DEMO_DATA_DIR = os.path.join(APP_DIR, 'demo_data')
REPORTS_DIR = os.path.join(APP_DIR, 'reports')

# Make sure directories exist
os.makedirs(DEMO_DATA_DIR, exist_ok=True)
os.makedirs(REPORTS_DIR, exist_ok=True)

# ═══════════════════════════════════════════════════════════
# Colab Backend
# ═══════════════════════════════════════════════════════════

# URL from ngrok (paste here after starting Colab notebook)
# Example: 'https://abc123.ngrok-free.app'
COLAB_BACKEND_URL = ''  # FILL THIS IN

# Timeouts (seconds)
VLM_TIMEOUT = 120  # VLM is slow on inference
DONUT_TIMEOUT = 60

# ═══════════════════════════════════════════════════════════
# Outlook Settings
# ═══════════════════════════════════════════════════════════

# Polling interval for Outlook live monitoring (seconds)
OUTLOOK_POLL_INTERVAL = 5

# Maximum emails to fetch per poll
OUTLOOK_MAX_PER_POLL = 5

# ═══════════════════════════════════════════════════════════
# UI Settings
# ═══════════════════════════════════════════════════════════

PARADIGMS = {
    'P1': {
        'name': 'P1: Pipeline Clasic',
        'description': 'TF-IDF + Regex + OCR (totul local, rapid)',
        'requires_backend': False,
    },
    'P2': {
        'name': 'P2: VLM Zero-Shot',
        'description': 'Qwen2.5-VL pe Colab (ruleaza prin backend)',
        'requires_backend': True,
    },
    'P3': {
        'name': 'P3: Hybrid (Donut + Pipeline)',
        'description': 'Donut pentru documente (Colab) + restul local',
        'requires_backend': True,
    },
}

# Set environment variable so inference_router can find P1 modules
os.environ['DISSERTATION_PATH'] = DISSERTATION_PATH
