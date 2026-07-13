"""
inference_router.py
───────────────────
Routes inference to the right place:
- P1 (Pipeline): always local
- P2 (VLM): always Colab backend
- P3 (Donut Hybrid): Donut on Colab, rest local

Each paradigm produces the same standardized output structure for fair comparison.
"""

import os
import sys
import requests
import json
from typing import Dict, Optional, List

# Set Tesseract path. Override with TESSERACT_PATH env var, else fall back to PATH.
import shutil
import pytesseract
TESSERACT_PATH = os.environ.get('TESSERACT_PATH') or shutil.which('tesseract')
if TESSERACT_PATH and os.path.exists(TESSERACT_PATH):
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_PATH
# Add parent directory to path to import sibling modules
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import P1 components from the dissertation project
# (User must place these scripts in the project folder)
DISSERTATION_PATH = os.environ.get(
    'DISSERTATION_PATH',
    os.path.abspath(os.path.join(os.path.dirname(__file__), '..', '..', 'src'))
)
if os.path.exists(DISSERTATION_PATH):
    sys.path.insert(0, DISSERTATION_PATH)


def safe_import_p1():
    """Try to import P1 components."""
    try:
        from email_field_extractor import extract_fields as extract_email_fields
        from document_field_extractor import extract_fields_from_document
        from reconciliation import reconcile_pair, fields_match
        return extract_email_fields, extract_fields_from_document, reconcile_pair
    except ImportError as e:
        print(f'WARNING: Cannot import P1 modules: {e}')
        return None, None, None


def classify_intent_keywords(text: str) -> str:
    """Keyword-based intent classification (fallback)."""
    text_lower = text.lower()
    scores = {
        'invoice_submission': 0, 'quote_offer': 0,
        'price_validity_confirmation': 0, 'price_increase': 0, 'other': 0,
    }
    for kw in ['invoice', 'billing', 'payment due', 'amount due', 'payable']:
        if kw in text_lower: scores['invoice_submission'] += 3
    for kw in ['quotation', 'quote', 'commercial offer', 'our offer']:
        if kw in text_lower: scores['quote_offer'] += 3
    for kw in ['still valid', 'remain valid', 'prices remain', 'confirm that']:
        if kw in text_lower: scores['price_validity_confirmation'] += 3
    for kw in ['price increase', 'price adjustment', 'new pricing',
                'new prices', 'revised pricing', '% increase']:
        if kw in text_lower: scores['price_increase'] += 4

    import re
    if re.search(r'price.{0,50}increase|increase.{0,50}price', text_lower):
        scores['price_increase'] += 3
    if 'valid until' in text_lower and scores['price_increase'] == 0:
        scores['quote_offer'] += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else 'other'


def classify_intent_baseline(text: str, model_path: str = 'baseline_model.pkl') -> str:
    """Use keyword classifier first (robust for real emails), TF-IDF as fallback."""
    # Try keywords first - they generalize better to real-world vocabulary
    keyword_result = classify_intent_keywords(text)
    if keyword_result != 'other':
        return keyword_result
    
    # Fall back to TF-IDF if keywords don't match
    try:
        import pickle
        full_path = os.path.join(DISSERTATION_PATH, model_path) if not os.path.isabs(model_path) else model_path
        if os.path.exists(full_path):
            with open(full_path, 'rb') as f:
                pipeline = pickle.load(f)
            pred = pipeline.predict([text])[0]
            labels = ['invoice_submission', 'other', 'price_increase',
                      'price_validity_confirmation', 'quote_offer']
            return labels[pred]
    except Exception:
        pass
    return keyword_result


# ═══════════════════════════════════════════════════════════
# Output structure
# ═══════════════════════════════════════════════════════════

def empty_result() -> Dict:
    """Standard empty result structure."""
    return {
        'intent': None,
        'email_fields': {'amount': None, 'currency': None, 'doc_number': None, 'date': None},
        'document_fields': {'amount': None, 'currency': None, 'doc_number': None, 'date': None},
        'is_consistent': None,
        'mismatched_fields': [],
        'paradigm': None,
        'errors': [],
    }


# ═══════════════════════════════════════════════════════════
# P1: Pipeline (fully local)
# ═══════════════════════════════════════════════════════════

def run_p1(subject: str, body: str, attachment_path: Optional[str] = None) -> Dict:
    """Run Pipeline P1 entirely locally."""
    extract_email_fields, extract_doc_fields, reconcile = safe_import_p1()

    result = empty_result()
    result['paradigm'] = 'P1'

    full_text = f'Subject: {subject}\n\n{body}'

    # Intent
    result['intent'] = classify_intent_baseline(full_text)

    # Email fields
    if extract_email_fields:
        try:
            ef = extract_email_fields(full_text)
            for f in ['amount', 'currency', 'doc_number', 'date']:
                result['email_fields'][f] = ef.get(f'pred_{f}')
        except Exception as e:
            result['errors'].append(f'Email extraction: {e}')

    # Document fields
    if attachment_path and os.path.exists(attachment_path) and extract_doc_fields:
        try:
            doc_type = 'invoice' if result['intent'] == 'invoice_submission' else 'quotation'
            df = extract_doc_fields(attachment_path, doc_type)
            if df.get('ocr_success'):
                for f in ['amount', 'currency', 'doc_number', 'date']:
                    result['document_fields'][f] = df.get(f'pred_{f}')

                # Reconciliation
                if reconcile:
                    ef_for_recon = {f'pred_{f}': result['email_fields'][f]
                                    for f in ['amount', 'currency', 'doc_number', 'date']}
                    recon = reconcile(ef_for_recon, df)
                    result['is_consistent'] = recon['verdict'] == 'consistent'
                    result['mismatched_fields'] = recon.get('mismatched_fields', [])
            else:
                result['errors'].append('OCR failed')
        except Exception as e:
            result['errors'].append(f'Document extraction: {e}')

    return result


# ═══════════════════════════════════════════════════════════
# P2: VLM (entirely on Colab)
# ═══════════════════════════════════════════════════════════

def run_p2(subject: str, body: str, attachment_path: Optional[str] = None,
           backend_url: str = '', timeout: int = 120) -> Dict:
    """Run VLM on Colab backend."""
    result = empty_result()
    result['paradigm'] = 'P2'

    if not backend_url:
        result['errors'].append('No backend URL configured')
        return result

    try:
        files = {}
        data = {'subject': subject, 'body': body}

        if attachment_path and os.path.exists(attachment_path):
            with open(attachment_path, 'rb') as f:
                files['image'] = (os.path.basename(attachment_path), f.read())

        url = f'{backend_url.rstrip("/")}/vlm'
        if files:
            response = requests.post(url, data=data, files=files, timeout=timeout)
        else:
            response = requests.post(url, data=data, timeout=timeout)

        if response.status_code == 200:
            vlm_out = response.json()
            result['intent'] = vlm_out.get('intent')
            result['email_fields'] = vlm_out.get('email_fields', result['email_fields'])
            result['document_fields'] = vlm_out.get('document_fields', result['document_fields'])
            result['is_consistent'] = vlm_out.get('is_consistent')
            result['mismatched_fields'] = vlm_out.get('mismatched_fields', [])
        else:
            result['errors'].append(f'VLM API error {response.status_code}: {response.text[:100]}')

    except requests.exceptions.Timeout:
        result['errors'].append(f'VLM timeout after {timeout}s')
    except requests.exceptions.ConnectionError:
        result['errors'].append('Cannot connect to backend (Colab offline?)')
    except Exception as e:
        result['errors'].append(f'VLM error: {e}')

    return result


# ═══════════════════════════════════════════════════════════
# P3 Hybrid: Donut for documents + P1 for everything else
# ═══════════════════════════════════════════════════════════

def run_p3_hybrid(subject: str, body: str, attachment_path: Optional[str] = None,
                  backend_url: str = '', timeout: int = 60) -> Dict:
    """
    Hybrid pipeline:
    - Intent classification: TF-IDF baseline (local)
    - Email field extraction: regex (local)
    - Document field extraction: Donut (Colab)
    - Reconciliation: local
    """
    extract_email_fields, _, reconcile = safe_import_p1()

    result = empty_result()
    result['paradigm'] = 'P3 Hybrid'

    full_text = f'Subject: {subject}\n\n{body}'

    # Intent (local)
    result['intent'] = classify_intent_baseline(full_text)

    # Email fields (local regex)
    if extract_email_fields:
        try:
            ef = extract_email_fields(full_text)
            for f in ['amount', 'currency', 'doc_number', 'date']:
                result['email_fields'][f] = ef.get(f'pred_{f}')
        except Exception as e:
            result['errors'].append(f'Email extraction: {e}')

    # Document fields (Donut on Colab)
    if attachment_path and os.path.exists(attachment_path):
        if not backend_url:
            result['errors'].append('No backend URL for Donut')
        else:
            try:
                with open(attachment_path, 'rb') as f:
                    files = {'image': (os.path.basename(attachment_path), f.read())}
                url = f'{backend_url.rstrip("/")}/donut'
                response = requests.post(url, files=files, timeout=timeout)

                if response.status_code == 200:
                    donut_out = response.json()
                    for f in ['amount', 'currency', 'doc_number', 'date']:
                        result['document_fields'][f] = donut_out.get(f)
                else:
                    result['errors'].append(f'Donut API error {response.status_code}')
            except requests.exceptions.Timeout:
                result['errors'].append(f'Donut timeout after {timeout}s')
            except requests.exceptions.ConnectionError:
                result['errors'].append('Cannot connect to backend')
            except Exception as e:
                result['errors'].append(f'Donut error: {e}')

    # Reconciliation (local)
    if reconcile and any(result['email_fields'].values()) and any(result['document_fields'].values()):
        try:
            ef_for_recon = {f'pred_{f}': result['email_fields'][f]
                            for f in ['amount', 'currency', 'doc_number', 'date']}
            df_for_recon = {f'pred_{f}': result['document_fields'][f]
                            for f in ['amount', 'currency', 'doc_number', 'date']}
            df_for_recon['ocr_success'] = True
            recon = reconcile(ef_for_recon, df_for_recon)
            result['is_consistent'] = recon['verdict'] == 'consistent'
            result['mismatched_fields'] = recon.get('mismatched_fields', [])
        except Exception as e:
            result['errors'].append(f'Reconciliation: {e}')

    return result


# ═══════════════════════════════════════════════════════════
# Main routing
# ═══════════════════════════════════════════════════════════

def run_inference(paradigm: str, subject: str, body: str,
                  attachment_path: Optional[str] = None,
                  backend_url: str = '') -> Dict:
    """Route to the right paradigm."""
    if paradigm == 'P1':
        return run_p1(subject, body, attachment_path)
    elif paradigm == 'P2':
        return run_p2(subject, body, attachment_path, backend_url)
    elif paradigm == 'P3':
        return run_p3_hybrid(subject, body, attachment_path, backend_url)
    else:
        result = empty_result()
        result['errors'].append(f'Unknown paradigm: {paradigm}')
        return result


def check_backend(backend_url: str) -> Dict:
    """Check if Colab backend is reachable."""
    if not backend_url:
        return {'available': False, 'reason': 'No URL configured'}
    try:
        r = requests.get(f'{backend_url.rstrip("/")}/health', timeout=10)
        if r.status_code == 200:
            return {'available': True, **r.json()}
        return {'available': False, 'reason': f'Status {r.status_code}'}
    except requests.exceptions.Timeout:
        return {'available': False, 'reason': 'Timeout'}
    except requests.exceptions.ConnectionError:
        return {'available': False, 'reason': 'Connection error'}
    except Exception as e:
        return {'available': False, 'reason': str(e)}
