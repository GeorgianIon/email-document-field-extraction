"""

Extracts key fields from email text using regex patterns:
  - amount (monetary value)
  - currency (USD, EUR, GBP, RON, CHF or symbols / words)
  - doc_number (invoice/quotation reference number)
  - date (various formats)

Also evaluates extraction accuracy against ground truth.

Usage:
    python email_field_extractor.py [--split test] [--data_dir .]
"""

import argparse
import csv
import json
import os
import re
from collections import defaultdict
from typing import Optional, Dict, Tuple


# Currency mapping

CURRENCY_MAP = {
    "$": "USD", "€": "EUR", "£": "GBP",
    "usd": "USD", "eur": "EUR", "gbp": "GBP",
    "ron": "RON", "chf": "CHF",
    "dollar": "USD", "euro": "EUR", "pound": "GBP",
    "dollars": "USD", "euros": "EUR", "pounds": "GBP",
}

CURRENCY_CODES = {"USD", "EUR", "GBP", "RON", "CHF"}


# Regex patterns

# Amount patterns — match numbers with various formatting.
# IMPORTANT: order matters — more specific / safer patterns first; the first
# pattern (in this list order) that matches anywhere in the text wins.
AMOUNT_PATTERNS = [
    # === SYMBOL AFTER NUMBER (European style) ===
    # Space-separated thousands + symbol after: 144 167.95 £ or 71 745.50 €
    r'(?<!\d)(?P<num>\d{1,3}(?:\s\d{3})+[.,]\d{2})\s*(?P<sym>[$€£])',
    # Comma-separated thousands + symbol after: 5,368.00 $
    r'(?<!\d)(?P<num>\d{1,3}(?:,\d{3})+\.\d{2})\s*(?P<sym>[$€£])',
    # Dot-separated thousands + symbol after (EU): 5.368,00 €
    r'(?<!\d)(?P<num>\d{1,3}(?:\.\d{3})+,\d{2})\s*(?P<sym>[$€£])',

    # === NUMBER + CURRENCY CODE ===
    # Generic: optional thousands, 1-2 decimals + code: 12,345.67 USD / 833.5 GBP / 144 167.95 RON
    r'(?<!\d)(?P<num>\d{1,3}(?:[,.\s]\d{3})*[.,]\d{1,2})(?![.,\d])\s*(?P<cur>USD|EUR|GBP|RON|CHF)',
    # Plain large number (no thousands sep), 1-2 decimals + code: 155838.14 GBP
    r'(?<!\d)(?P<num>\d{4,}[.,]\d{1,2})(?!\d)\s*(?P<cur>USD|EUR|GBP|RON|CHF)',
    # Whole number with thousands + code: 12,345 RON
    r'(?<!\d)(?P<num>\d{1,3}(?:[,.\s]\d{3})+)(?![.,]\d)\s*(?P<cur>USD|EUR|GBP|RON|CHF)',
    # Plain whole number (no separators / decimals) + code: 833 USD, 132663 GBP
    r'(?<!\d)(?P<num>\d+)(?!\d)(?!\s*[.,]\d)\s*(?P<cur>USD|EUR|GBP|RON|CHF)',

    # === CURRENCY CODE BEFORE NUMBER ===
    # USD 144 167.95 / EUR 12,345.67 / GBP 5.368,00 / CHF 833.5
    r'\b(?P<cur>USD|EUR|GBP|RON|CHF)\s*(?P<num>\d{1,3}(?:[,.\s]\d{3})*[.,]\d{1,2})(?![.,\d])',
    # GBP 155838.14
    r'\b(?P<cur>USD|EUR|GBP|RON|CHF)\s*(?P<num>\d{4,}[.,]\d{1,2})(?!\d)',
    # RON 12,345
    r'\b(?P<cur>USD|EUR|GBP|RON|CHF)\s*(?P<num>\d{1,3}(?:[,.\s]\d{3})+)(?![.,]\d)',
    # USD 833
    r'\b(?P<cur>USD|EUR|GBP|RON|CHF)\s*(?P<num>\d+)(?!\d)(?!\s*[.,]\d)',

    # === SYMBOL BEFORE NUMBER ===
    # Symbol + space-separated: £144 167.95
    r'(?P<sym>[$€£])\s*(?P<num>\d{1,3}(?:\s\d{3})+[.,]\d{2})',
    # Symbol + comma/dot separated: $12,345.67 or €12.345,67
    r'(?P<sym>[$€£])\s*(?P<num>\d{1,3}(?:[,.]\d{3})+[.,]\d{2})',
    # Symbol + plain large number, 1-2 decimals: $155838.14
    r'(?P<sym>[$€£])\s*(?P<num>\d{4,}[.,]\d{1,2})(?!\d)',
    # Symbol + whole with thousands: $12,345
    r'(?P<sym>[$€£])\s*(?P<num>\d{1,3}(?:[,.\s]\d{3})+)(?![.,]\d)',
    # Symbol + small number, 1-2 decimals: $55.4 or $55.40
    r'(?P<sym>[$€£])\s*(?P<num>\d{1,3}[.,]\d{1,2})(?![.,\d])',
    # Symbol + plain whole number: $833
    r'(?P<sym>[$€£])\s*(?P<num>\d+)(?!\d)(?!\s*[.,]\d)',
    # Plain whole number + symbol: 833 $
    r'(?<!\d)(?P<num>\d+)(?!\d)(?!\s*[.,]\d)\s*(?P<sym>[$€£])',

    # === NUMBER + CURRENCY WORD  /  WORD + NUMBER ===
    # 1,234.56 dollars / 833.5 euros
    r'(?<!\d)(?P<num>\d{1,3}(?:[,.\s]\d{3})*[.,]\d{1,2})(?![.,\d])\s*(?P<cur>dollars?|euros?|pounds?)\b',
    # 12,345 dollars
    r'(?<!\d)(?P<num>\d{1,3}(?:[,.\s]\d{3})+)(?![.,]\d)\s*(?P<cur>dollars?|euros?|pounds?)\b',
    # 833 dollars
    r'(?<!\d)(?P<num>\d+)(?!\d)(?!\s*[.,]\d)\s*(?P<cur>dollars?|euros?|pounds?)\b',
    # dollars 1,234.56
    r'\b(?P<cur>dollars?|euros?|pounds?)\s+(?P<num>\d{1,3}(?:[,.\s]\d{3})*[.,]\d{1,2})(?![.,\d])',
    # dollars 833
    r'\b(?P<cur>dollars?|euros?|pounds?)\s+(?P<num>\d+)(?!\d)(?!\s*[.,]\d)',

    # === FALLBACK ===
    # Small number (exactly 2 decimals) + currency code: 55.40 RON
    r'(?<!\d)(?P<num>\d{1,3}[.,]\d{2})\s*(?P<cur>USD|EUR|GBP|RON|CHF)',
    # Small number + symbol: 55.40 £ or 923,91 €
    r'(?<!\d)(?P<num>\d{1,3}[.,]\d{2})\s*(?P<sym>[$€£])',
    # Symbol + small number: $55.40 or €923,91
    r'(?P<sym>[$€£])\s*(?P<num>\d{1,3}[.,]\d{2})(?!\d)',
    # Standalone plain decimal (no currency nearby): 12345.67
    r'(?<![.\d])(?P<num>\d{3,}[.]\d{2})(?!\d)',
]

# Document number patterns
DOC_NUMBER_PATTERNS = [
    # PROFORMA-2025-001, INV-2025-12345, PO-2025-0042, CN-2024-998, etc.
    # (longer prefixes listed first so they win over their own substrings)
    r'\b(?P<docnum>(?:PROFORMA|PROF|PRO|INVOICE|INV|BILL|DOC|QUO|QUOTE|OFFER|OFF|ORDER|ORD|REV|REF|CRN|CRED|FV|QT|PL|PR|PO|SO|CN|F|Q)[-/]?\d{4}[-/]\d{3,6})\b',
    # "invoice no. 12345", "PO number 12345", "purchase order #99812", "ref: ABC-12"
    r'\b(?:invoice|quotation|quote|offer|proforma|bill|order|purchase\s+order|p\.?o\.?|s\.?o\.?|credit\s+note|ref(?:erence)?|doc(?:ument)?)\s*(?:no\.?|number|num\.?|#|nr\.?)\s*[:.]?\s*(?P<docnum>[A-Za-z0-9][\w\-/]{3,19})',
]

# Date patterns (ordered by specificity)
DATE_PATTERNS = [
    # ISO dash: 2025-06-15
    r'(?P<date>\d{4}-\d{2}-\d{2})',
    # ISO slash: 2025/06/15
    r'(?P<date>\d{4}/\d{2}/\d{2})',
    # Dash European: 23-05-2026 (DD-MM-YYYY)
    r'(?P<date>\d{1,2}-\d{1,2}-\d{4})',
    # Long, month first (optional ordinal): June 15, 2025 / June 15th 2025
    r'(?P<date>(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
    # Long, day first (optional ordinal / "of"): 15 June 2025 / 15th of June, 2025
    r'(?P<date>\d{1,2}(?:st|nd|rd|th)?\s+(?:of\s+)?(?:January|February|March|April|May|June|July|August|September|October|November|December),?\s+\d{4})',
    # Abbreviated, month first (optional dot): Jun 15, 2025 / Jun. 15 2025
    r'(?P<date>(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{1,2}(?:st|nd|rd|th)?,?\s+\d{4})',
    # Abbreviated, day first (optional dot): 15 Jun 2025 / 15 Jun. 2025
    r'(?P<date>\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+\d{4})',
    # Slash, 4-digit year: 06/15/2025 or 15/06/2025
    r'(?P<date>\d{1,2}/\d{1,2}/\d{4})',
    # European dot, 4-digit year: 31.12.2026
    r'(?P<date>\d{1,2}\.\d{1,2}\.\d{4})',
    # 2-digit year with -, / or . : 23-05-26, 15/06/25, 31.12.26
    r'(?P<date>\d{1,2}[-/.]\d{1,2}[-/.]\d{2})(?!\d)',
]

# Currency standalone patterns (when amount is already found)
CURRENCY_PATTERNS = [
    r'\b(?P<cur>USD|EUR|GBP|RON|CHF)\b',
    r'\b(?P<cur>dollars?|euros?|pounds?)\b',
    r'(?P<sym>[$€£])',
]



# Normalization functions


def normalize_amount(raw: str) -> Optional[float]:
    """Convert a raw amount string to float."""
    if not raw:
        return None
    s = raw.strip()

    # Remove spaces used as thousands separator
    s = s.replace(" ", "")

    # Detect European format: 12.345,67 (dots for thousands, comma for decimal)
    if re.match(r'^\d{1,3}(\.\d{3})+,\d{1,2}$', s):
        s = s.replace(".", "").replace(",", ".")
    # Detect standard format: 12,345.67 (commas for thousands, dot for decimal)
    elif re.match(r'^\d{1,3}(,\d{3})+\.\d{1,2}$', s):
        s = s.replace(",", "")
    # Detect comma as decimal: 12345,67
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    # Standard: just remove commas
    else:
        s = s.replace(",", "")

    try:
        return round(float(s), 2)
    except ValueError:
        return None


def normalize_currency(raw: str) -> Optional[str]:
    """Convert currency symbol/name to standard code."""
    if not raw:
        return None
    raw = raw.strip().lower()
    if raw.upper() in CURRENCY_CODES:
        return raw.upper()
    return CURRENCY_MAP.get(raw)


def normalize_date(raw: str) -> Optional[str]:
    """Convert various date formats to YYYY-MM-DD."""
    if not raw:
        return None

    from datetime import datetime

    raw = raw.strip().replace(",", "")
    # Remove ordinal suffixes: 15th -> 15, 1st -> 1
    raw = re.sub(r'(\d{1,2})(st|nd|rd|th)\b', r'\1', raw, flags=re.IGNORECASE)
    # Remove the word "of": "15 of June" -> "15 June"
    raw = re.sub(r'\bof\b', ' ', raw, flags=re.IGNORECASE)
    # Remove a dot right after letters (month abbreviation): "Jun." -> "Jun"
    raw = re.sub(r'(?<=[A-Za-z])\.', '', raw)
    # Collapse whitespace
    raw = re.sub(r'\s+', ' ', raw).strip()

    formats = [
        "%Y-%m-%d",          # 2025-06-15
        "%Y/%m/%d",          # 2025/06/15
        "%B %d %Y",          # June 15 2025
        "%b %d %Y",          # Jun 15 2025
        "%d %B %Y",          # 15 June 2025
        "%d %b %Y",          # 15 Jun 2025
        "%m/%d/%Y",          # 06/15/2025
        "%d/%m/%Y",          # 15/06/2025
        "%d-%m-%Y",          # 23-05-2026
        "%d.%m.%Y",          # 31.12.2026
        "%d-%m-%y",          # 23-05-26
        "%d/%m/%y",          # 15/06/25
        "%d.%m.%y",          # 31.12.26
        "%m/%d/%y",          # 06/15/25
    ]

    for fmt in formats:
        try:
            dt = datetime.strptime(raw, fmt)
            return dt.strftime("%Y-%m-%d")
        except ValueError:
            continue

    return None



# Main extraction function


def extract_fields(text: str) -> Dict[str, Optional[str]]:
    """
    Extract amount, currency, doc_number, and date from email text.
    Returns a dict with normalized values (or None if not found).
    """
    result = {
        "pred_amount": None,
        "pred_currency": None,
        "pred_doc_number": None,
        "pred_date": None,
    }

    # ── Extract document number ──
    for pattern in DOC_NUMBER_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            doc_num = match.group("docnum").strip()
            result["pred_doc_number"] = doc_num.upper()
            break

    # ── Extract amount and possibly currency ──
    for pattern in AMOUNT_PATTERNS:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            groups = match.groupdict()

            # Amount
            raw_num = groups.get("num", "")
            amount = normalize_amount(raw_num)
            if amount and amount > 0:
                result["pred_amount"] = amount

            # Currency from same match
            if "sym" in groups and groups["sym"]:
                result["pred_currency"] = normalize_currency(groups["sym"])
            elif "cur" in groups and groups["cur"]:
                result["pred_currency"] = normalize_currency(groups["cur"])
            break

    # ── Extract currency (standalone, if not found with amount) ──
    if result["pred_currency"] is None:
        for pattern in CURRENCY_PATTERNS:
            match = re.search(pattern, text, re.IGNORECASE)
            if match:
                groups = match.groupdict()
                raw = groups.get("cur") or groups.get("sym") or ""
                cur = normalize_currency(raw)
                if cur:
                    result["pred_currency"] = cur
                    break

    # ── Extract date ──
    dates_found = []
    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw_date = match.group("date")
            normalized = normalize_date(raw_date)
            if normalized:
                dates_found.append((normalized, match.start()))

    if dates_found:
        # Heuristic: prefer a date near a relevant keyword; else take the last one.
        keywords = ["valid", "due", "effective", "until", "expires", "deadline", "by"]
        best_date = None

        for date, pos in dates_found:
            context = text[max(0, pos - 100):pos].lower()
            if any(kw in context for kw in keywords):
                best_date = date
                break

        if best_date is None:
            best_date = dates_found[-1][0]

        result["pred_date"] = best_date

    return result


# Evaluation


def evaluate_extraction(data_path: str):
    """Evaluate field extraction on a split CSV."""
    records = []
    with open(data_path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            records.append(row)

    print(f"\nEvaluating on {len(records)} records from {os.path.basename(data_path)}")
    print("=" * 60)

    field_results = {
        "amount":     {"correct": 0, "incorrect": 0, "missing": 0, "not_applicable": 0},
        "currency":   {"correct": 0, "incorrect": 0, "missing": 0, "not_applicable": 0},
        "doc_number": {"correct": 0, "incorrect": 0, "missing": 0, "not_applicable": 0},
        "date":       {"correct": 0, "incorrect": 0, "missing": 0, "not_applicable": 0},
    }

    errors = []

    for rec in records:
        text = f"Subject: {rec['subject']}\n\n{rec['body']}"
        extracted = extract_fields(text)

        for field in ["amount", "currency", "doc_number", "date"]:
            mentions_field = rec.get(f"mentions_{field}", "False") == "True"
            gt_value = rec.get(f"gt_{field}", "")

            if not mentions_field or not gt_value:
                field_results[field]["not_applicable"] += 1
                continue

            pred_value = extracted.get(f"pred_{field}")

            if pred_value is None:
                field_results[field]["missing"] += 1
                errors.append({
                    "email_id": rec["email_id"],
                    "field": field,
                    "error": "not_extracted",
                    "gt": gt_value,
                    "pred": None,
                    "text_snippet": text[:200],
                })
                continue

            is_correct = False

            if field == "amount":
                try:
                    gt_float = float(gt_value)
                    is_correct = abs(pred_value - gt_float) < 0.1
                except (ValueError, TypeError):
                    pass

            elif field == "currency":
                is_correct = (str(pred_value).upper() == str(gt_value).upper())

            elif field == "doc_number":
                is_correct = (str(pred_value).upper().strip() ==
                              str(gt_value).upper().strip())

            elif field == "date":
                is_correct = (str(pred_value) == str(gt_value))

            if is_correct:
                field_results[field]["correct"] += 1
            else:
                field_results[field]["incorrect"] += 1
                errors.append({
                    "email_id": rec["email_id"],
                    "field": field,
                    "error": "wrong_value",
                    "gt": gt_value,
                    "pred": pred_value,
                })

    print(f"\n{'Field':<15s} {'Correct':>8s} {'Wrong':>8s} {'Missing':>8s} {'N/A':>8s} {'Accuracy':>10s}")
    print("-" * 60)

    overall_correct = 0
    overall_total = 0

    for field in ["amount", "currency", "doc_number", "date"]:
        r = field_results[field]
        total = r["correct"] + r["incorrect"] + r["missing"]
        acc = r["correct"] / total if total > 0 else 0.0
        print(f"{field:<15s} {r['correct']:>8d} {r['incorrect']:>8d} "
              f"{r['missing']:>8d} {r['not_applicable']:>8d} {acc:>10.2%}")
        overall_correct += r["correct"]
        overall_total += total

    overall_acc = overall_correct / overall_total if overall_total > 0 else 0
    print("-" * 60)
    print(f"{'OVERALL':<15s} {overall_correct:>8d} "
          f"{overall_total - overall_correct:>8d} "
          f"{'':>8s} {'':>8s} {overall_acc:>10.2%}")

    if errors:
        print(f"\nSample errors (first 10):")
        for err in errors[:10]:
            print(f"  [{err['email_id']}] {err['field']}: "
                  f"gt={err['gt']} → pred={err['pred']} ({err['error']})")

    return field_results, errors



# Main


def main():
    parser = argparse.ArgumentParser(description="Email field extraction")
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--data_dir", default=".")
    args = parser.parse_args()

    data_path = os.path.join(args.data_dir, f"{args.split}.csv")

    if not os.path.exists(data_path):
        print(f"Error: {data_path} not found. Run split_dataset.py first.")
        return

    results, errors = evaluate_extraction(data_path)

    output_path = os.path.join(args.data_dir, f"extraction_results_{args.split}.json")
    with open(output_path, "w") as f:
        json.dump({
            "field_results": results,
            "num_errors": len(errors),
            "errors": errors[:50],
        }, f, indent=2)
    print(f"\n✓ Results saved to {output_path}")


if __name__ == "__main__":
    main()
