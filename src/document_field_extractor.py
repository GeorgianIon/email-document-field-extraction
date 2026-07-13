"""

Extracts key fields from document attachments (invoices, quotations, price lists).

Pipeline (Classical approach):
  1. Load document (PDF → rasterize to image, or PNG directly)
  2. Run Tesseract OCR to get text
  3. Apply regex patterns to extract: amount, currency, doc_number, date
  4. Evaluate against ground truth from pairs.csv

This represents the "document-only" scenario in the dissertation.

Usage:
    python document_field_extractor.py [--split test] [--data_dir .]
"""

import argparse
import csv
import json
import os
import re
from collections import defaultdict
from typing import Optional, Dict, List, Tuple

import pytesseract
from PIL import Image


# PDF to Image conversion


def pdf_to_image(pdf_path: str, dpi: int = 200) -> Image.Image:
    """Convert first page of PDF to PIL Image."""
    import pypdfium2 as pdfium
    pdf = pdfium.PdfDocument(pdf_path)
    page = pdf[0]
    scale = dpi / 72
    bitmap = page.render(scale=scale)
    img = bitmap.to_pil()
    pdf.close()
    return img


def load_document_image(doc_path: str) -> Image.Image:
    """Load a document as PIL Image regardless of format."""
    if doc_path.lower().endswith(".pdf"):
        return pdf_to_image(doc_path)
    else:
        return Image.open(doc_path)



# OCR


def ocr_document(img: Image.Image, lang: str = "eng") -> str:
    """Run Tesseract OCR on a document image."""
    # Use --psm 6 (assume uniform block of text) for better results on documents
    custom_config = r'--oem 3 --psm 6'
    text = pytesseract.image_to_string(img, lang=lang, config=custom_config)
    return text


# Currency mapping


CURRENCY_CODES = {"USD", "EUR", "GBP", "RON", "CHF"}
CURRENCY_MAP = {
    "$": "USD", "€": "EUR", "£": "GBP",
    "usd": "USD", "eur": "EUR", "gbp": "GBP",
    "ron": "RON", "chf": "CHF",
}


def normalize_currency(raw: str) -> Optional[str]:
    if not raw:
        return None
    raw = raw.strip().lower()
    if raw.upper() in CURRENCY_CODES:
        return raw.upper()
    return CURRENCY_MAP.get(raw)



# Amount extraction from OCR text


# Patterns specifically tuned for document OCR output
# Documents typically have "TOTAL:" or "TOTAL QUOTE:" followed by an amount

TOTAL_KEYWORDS = [
    r"TOTAL\s*QUOTE",
    r"TOTAL\s*:",
    r"TOTAL\b",
    r"GRAND\s*TOTAL",
    r"AMOUNT\s*DUE",
    r"NET\s*AMOUNT",
    r"BALANCE\s*DUE",
    r"Representative\s*total",
]

DOC_AMOUNT_PATTERNS = [
    # Symbol + number: $12,345.67 or €12.345,67 or £492.12
    r'(?P<sym>[$€£¢])\s*(?P<num>\d[\d,.\s]*\d)',
    # Number + symbol: 12,345.67$ or 492.12£
    r'(?P<num>\d[\d,.\s]*\d)\s*(?P<sym>[$€£¢])',
    # Number + currency code: 12,345.67 USD
    r'(?P<num>\d[\d,.\s]*\d)\s*(?P<cur>USD|EUR|GBP|RON|CHF)',
    # Just a decimal number near TOTAL context
    r'(?P<num>\d[\d,.\s]*\.\d{2})',
]

# Currency symbol OCR variants (Tesseract sometimes misreads)
CURRENCY_OCR_FIXES = {
    "S$": "$", "US$": "$",
    "€": "€", "EUR": "EUR",
    "£": "£", "GBP": "GBP",
    "¢": None,  # ignore cents symbol
}


def normalize_amount(raw: str) -> Optional[float]:
    """Convert OCR'd amount string to float."""
    if not raw:
        return None
    s = raw.strip()
    # Remove spaces
    s = s.replace(" ", "")
    # Detect European format: 12.345,67
    if re.match(r'^\d{1,3}(\.\d{3})+,\d{2}$', s):
        s = s.replace(".", "").replace(",", ".")
    # Standard format: 12,345.67
    elif re.match(r'^\d{1,3}(,\d{3})+\.\d{2}$', s):
        s = s.replace(",", "")
    # Comma as decimal: 12345,67
    elif "," in s and "." not in s:
        s = s.replace(",", ".")
    else:
        s = s.replace(",", "")
    try:
        val = float(s)
        if val > 0:
            return round(val, 2)
    except ValueError:
        pass
    return None


def extract_total_amount(ocr_text: str) -> Tuple[Optional[float], Optional[str]]:
    """
    Extract the TOTAL amount and currency from OCR text.
    Strategy: find lines with TOTAL keyword, then extract the number.
    """
    lines = ocr_text.split("\n")

    # Strategy 1: Look for TOTAL lines
    for keyword_pattern in TOTAL_KEYWORDS:
        for i, line in enumerate(lines):
            if re.search(keyword_pattern, line, re.IGNORECASE):
                # Search this line and the next few lines for an amount
                search_text = " ".join(lines[i:i+3])
                for pattern in DOC_AMOUNT_PATTERNS:
                    match = re.search(pattern, search_text)
                    if match:
                        groups = match.groupdict()
                        raw_num = groups.get("num", "")
                        amount = normalize_amount(raw_num)
                        if amount and amount > 1:  # filter out tiny noise
                            cur = None
                            if "sym" in groups and groups["sym"]:
                                cur = normalize_currency(groups["sym"])
                            elif "cur" in groups and groups["cur"]:
                                cur = normalize_currency(groups["cur"])
                            return amount, cur

    # Strategy 2: Find the largest amount on the page (likely the total)
    all_amounts = []
    for pattern in DOC_AMOUNT_PATTERNS:
        for match in re.finditer(pattern, ocr_text):
            groups = match.groupdict()
            raw_num = groups.get("num", "")
            amount = normalize_amount(raw_num)
            if amount and amount > 1:
                cur = None
                if "sym" in groups and groups["sym"]:
                    cur = normalize_currency(groups["sym"])
                elif "cur" in groups and groups["cur"]:
                    cur = normalize_currency(groups["cur"])
                all_amounts.append((amount, cur, match.start()))

    if all_amounts:
        # Return the largest amount (most likely the total)
        all_amounts.sort(key=lambda x: x[0], reverse=True)
        return all_amounts[0][0], all_amounts[0][1]

    return None, None


# Document number extraction


DOC_NUMBER_KEYWORDS = [
    r"Invoice\s*(?:No\.?|Number|#|Nr\.?)\s*[:.]?\s*",
    r"Invoice\s*[:.]?\s*",
    r"Quote\s*(?:No\.?|Number|#)\s*[:.]?\s*",
    r"Quote\s*#\s*[:.]?\s*",
    r"Quotation\s*(?:No\.?|Number|#)?\s*[:.]?\s*",
    r"Ref(?:erence)?\s*[:.]?\s*",
    r"Order\s*(?:No\.?|Number)\s*[:.]?\s*",
    r"(?:No|Nr)\.?\s*[:.]?\s*",
]

# Pattern matching doc numbers with possible OCR errors in prefix
# Q can be read as 0, A, O, or @; T can be read as 7
DOC_NUMBER_PATTERN = r'(?P<docnum>[A-Z0-9@]{1,5}[-/]?\d{4}[-/]\d{3,6})'

# Common OCR misreads for document prefixes
OCR_PREFIX_CORRECTIONS = {
    # Q-prefix misreads
    "0-": "Q-", "O-": "Q-", "A-": "Q-", "@-": "Q-",
    "0T-": "QT-", "OT-": "QT-", "AT-": "QT-", "A7-": "QT-", "@T-": "QT-",
    "0UO-": "QUO-", "AU0-": "QUO-", "AUO-": "QUO-", "OUO-": "QUO-",
    "@UO-": "QUO-", "QU0-": "QUO-",
    "0FF-": "OFF-", "0F-": "OF-", "@FF-": "OFF-",
    # INV/FV/BILL are usually read correctly
}


def correct_ocr_prefix(docnum: str) -> str:
    """Apply OCR error corrections to document number prefixes."""
    upper = docnum.upper()
    for wrong, correct in OCR_PREFIX_CORRECTIONS.items():
        if upper.startswith(wrong):
            return correct + upper[len(wrong):]
    return upper


def extract_doc_number(ocr_text: str) -> Optional[str]:
    """Extract document number from OCR text."""
    # Strategy 1: keyword + number pattern
    for keyword in DOC_NUMBER_KEYWORDS:
        pattern = keyword + r'(?P<docnum>[A-Za-z0-9][\w\-/]{3,20})'
        match = re.search(pattern, ocr_text, re.IGNORECASE)
        if match:
            docnum = match.group("docnum").strip()
            docnum = correct_ocr_prefix(docnum.upper())
            # Validate: should have letters + digits + separator
            if re.match(r'^[A-Z]{1,5}[-/]?\d{4}[-/]\d{2,6}$', docnum):
                return docnum
            if len(docnum) >= 5 and any(c.isdigit() for c in docnum):
                return docnum

    # Strategy 2: standalone pattern anywhere in text (with OCR correction)
    for match in re.finditer(DOC_NUMBER_PATTERN, ocr_text):
        docnum = correct_ocr_prefix(match.group("docnum").upper())
        # Validate it looks like a real doc number
        if re.match(r'^[A-Z]{1,5}[-/]?\d{4}[-/]\d{2,6}$', docnum):
            return docnum

    return None


# Date extraction

DOC_DATE_KEYWORDS = [
    r"Due\s*Date\s*[:.]?\s*",
    r"Valid\s*Until\s*[:.]?\s*",
    r"Validity\s*[:.]?\s*",
    r"Effective\s*(?:Date)?\s*[:.]?\s*",
    r"Expir(?:es|y)\s*[:.]?\s*",
    r"Payment\s*Due\s*[:.]?\s*",
]

DATE_PATTERNS = [
    r'(?P<date>\d{4}-\d{2}-\d{2})',
    r'(?P<date>(?:January|February|March|April|May|June|July|August|September|October|November|December)\s+\d{1,2},?\s+\d{4})',
    r'(?P<date>\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\s+\d{4})',
    r'(?P<date>\d{1,2}/\d{1,2}/\d{4})',
    r'(?P<date>\d{1,2}\.\d{1,2}\.\d{4})',
]


def normalize_date(raw: str) -> Optional[str]:
    """Convert date string to YYYY-MM-DD."""
    if not raw:
        return None
    from datetime import datetime
    raw = raw.strip().replace(",", "")
    formats = [
        "%Y-%m-%d", "%B %d %Y", "%d %b %Y",
        "%m/%d/%Y", "%d/%m/%Y", "%d.%m.%Y",
    ]
    for fmt in formats:
        try:
            return datetime.strptime(raw, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return None


def extract_relevant_date(ocr_text: str, doc_type: str) -> Optional[str]:
    """
    Extract the most relevant date from document.
    For invoices: due date. For quotations: valid until. For price lists: effective date.
    """
    lines = ocr_text.split("\n")

    # Strategy 1: keyword-guided extraction
    for keyword in DOC_DATE_KEYWORDS:
        for i, line in enumerate(lines):
            if re.search(keyword, line, re.IGNORECASE):
                search_text = " ".join(lines[i:i+2])
                for pattern in DATE_PATTERNS:
                    match = re.search(pattern, search_text, re.IGNORECASE)
                    if match:
                        normalized = normalize_date(match.group("date"))
                        if normalized:
                            return normalized

    # Strategy 2: look for dates near specific keywords in full text
    priority_keywords = {
        "invoice":   ["due", "payment"],
        "quotation": ["valid", "until", "expire"],
        "price_list": ["effective"],
    }
    keywords_to_find = priority_keywords.get(doc_type, ["due", "valid", "effective"])

    all_dates = []
    for pattern in DATE_PATTERNS:
        for match in re.finditer(pattern, ocr_text, re.IGNORECASE):
            raw = match.group("date")
            normalized = normalize_date(raw)
            if normalized:
                # Check proximity to keywords
                start = max(0, match.start() - 150)
                context = ocr_text[start:match.start()].lower()
                priority = any(kw in context for kw in keywords_to_find)
                all_dates.append((normalized, priority, match.start()))

    if all_dates:
        # Prefer dates near priority keywords
        priority_dates = [d for d in all_dates if d[1]]
        if priority_dates:
            return priority_dates[0][0]
        # Otherwise return the last date (likely due/validity, not issue date)
        return all_dates[-1][0]

    return None



# Currency extraction (standalone)


def extract_currency(ocr_text: str, amount_currency: Optional[str] = None) -> Optional[str]:
    """Extract currency from document, using amount-extracted currency as fallback."""
    if amount_currency:
        return amount_currency

    # Look for explicit "Currency: XXX" line
    match = re.search(r'Currency\s*[:.]?\s*(?P<cur>USD|EUR|GBP|RON|CHF)', ocr_text, re.IGNORECASE)
    if match:
        return match.group("cur").upper()

    # Look for any currency code
    for code in CURRENCY_CODES:
        if code in ocr_text:
            return code

    # Look for symbols
    for sym, cur in [("$", "USD"), ("€", "EUR"), ("£", "GBP")]:
        if sym in ocr_text:
            return cur

    return None



# Main extraction function


def extract_fields_from_document(
    doc_path: str,
    doc_type: str = "invoice",
) -> Dict[str, Optional[str]]:
    """
    Full extraction pipeline for a single document.
    Returns dict with pred_amount, pred_currency, pred_doc_number, pred_date.
    """
    result = {
        "pred_amount": None,
        "pred_currency": None,
        "pred_doc_number": None,
        "pred_date": None,
        "ocr_text": "",
        "ocr_success": False,
    }

    try:
        # Load image
        img = load_document_image(doc_path)
        result["image_loaded"] = True

        # OCR
        ocr_text = ocr_document(img)
        result["ocr_text"] = ocr_text
        result["ocr_success"] = len(ocr_text.strip()) > 20

        if not result["ocr_success"]:
            result["error"] = (
                f"OCR returned too little text ({len(ocr_text.strip())} chars). "
                "Check that Tesseract is installed: https://github.com/UB-Mannheim/tesseract/wiki"
            )
            return result

        # Extract fields
        amount, amount_currency = extract_total_amount(ocr_text)
        result["pred_amount"] = amount

        result["pred_currency"] = extract_currency(ocr_text, amount_currency)
        result["pred_doc_number"] = extract_doc_number(ocr_text)
        result["pred_date"] = extract_relevant_date(ocr_text, doc_type)

    except Exception as e:
        result["error"] = f"{type(e).__name__}: {str(e)}"

    return result


# Evaluation


def evaluate_extraction(data_path: str, data_dir: str):
    """Evaluate document field extraction against ground truth."""
    records = []
    with open(data_path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            records.append(row)

    # Filter to records with attachments
    records_with_attach = [r for r in records if r.get("attachment_path", "")]

    print(f"\nEvaluating document extraction on {len(records_with_attach)} "
          f"documents from {os.path.basename(data_path)}")
    print(f"(Skipping {len(records) - len(records_with_attach)} records without attachments)")
    print("=" * 65)

    field_results = {
        "amount":     {"correct": 0, "incorrect": 0, "missing": 0, "total": 0},
        "currency":   {"correct": 0, "incorrect": 0, "missing": 0, "total": 0},
        "doc_number": {"correct": 0, "incorrect": 0, "missing": 0, "total": 0},
        "date":       {"correct": 0, "incorrect": 0, "missing": 0, "total": 0},
    }

    errors = []
    ocr_failures = 0

    for i, rec in enumerate(records_with_attach):
        doc_path = os.path.join(data_dir, rec["attachment_path"])
        doc_type = rec.get("doc_type", "invoice")

        if not os.path.exists(doc_path):
            continue

        # Extract
        extracted = extract_fields_from_document(doc_path, doc_type)

        if not extracted["ocr_success"]:
            ocr_failures += 1
            continue

        # Evaluate each field
        for field in ["amount", "currency", "doc_number", "date"]:
            gt_value = rec.get(f"doc_{field}", "")
            if not gt_value:
                continue

            field_results[field]["total"] += 1
            pred_value = extracted.get(f"pred_{field}")

            if pred_value is None:
                field_results[field]["missing"] += 1
                errors.append({
                    "pair_id": rec.get("pair_id", ""),
                    "field": field,
                    "error": "not_extracted",
                    "gt": gt_value,
                    "pred": None,
                    "doc_path": rec["attachment_path"],
                    "doc_type": doc_type,
                })
                continue

            # Compare
            is_correct = False
            if field == "amount":
                try:
                    gt_float = float(gt_value)
                    # Tolerance: 1% or 1.0 absolute (OCR can cause small errors)
                    tolerance = max(1.0, gt_float * 0.01)
                    is_correct = abs(pred_value - gt_float) < tolerance
                except (ValueError, TypeError):
                    pass
            elif field == "currency":
                is_correct = str(pred_value).upper() == str(gt_value).upper()
            elif field == "doc_number":
                # Flexible match: ignore dashes/slashes differences
                pred_clean = re.sub(r'[-/\s]', '', str(pred_value).upper())
                gt_clean = re.sub(r'[-/\s]', '', str(gt_value).upper())
                is_correct = pred_clean == gt_clean
            elif field == "date":
                is_correct = str(pred_value) == str(gt_value)

            if is_correct:
                field_results[field]["correct"] += 1
            else:
                field_results[field]["incorrect"] += 1
                errors.append({
                    "pair_id": rec.get("pair_id", ""),
                    "field": field,
                    "error": "wrong_value",
                    "gt": gt_value,
                    "pred": pred_value,
                    "doc_path": rec["attachment_path"],
                })

        # Progress
        if (i + 1) % 20 == 0:
            print(f"  [{i+1}/{len(records_with_attach)}] processed...")

    # Print results
    print(f"\nOCR failures: {ocr_failures}")
    print(f"\n{'Field':<15s} {'Correct':>8s} {'Wrong':>8s} {'Missing':>8s} "
          f"{'Total':>8s} {'Accuracy':>10s}")
    print("-" * 65)

    overall_correct = 0
    overall_total = 0

    for field in ["amount", "currency", "doc_number", "date"]:
        r = field_results[field]
        total = r["total"]
        acc = r["correct"] / total if total > 0 else 0.0
        print(f"{field:<15s} {r['correct']:>8d} {r['incorrect']:>8d} "
              f"{r['missing']:>8d} {total:>8d} {acc:>10.2%}")
        overall_correct += r["correct"]
        overall_total += total

    overall_acc = overall_correct / overall_total if overall_total > 0 else 0
    print("-" * 65)
    print(f"{'OVERALL':<15s} {overall_correct:>8d} "
          f"{overall_total - overall_correct:>8d} "
          f"{'':>8s} {overall_total:>8d} {overall_acc:>10.2%}")

    # Error analysis by field
    if errors:
        print(f"\nSample errors (first 15):")
        for err in errors[:15]:
            print(f"  [{err.get('pair_id','')}] {err['field']}: "
                  f"gt={err['gt']} → pred={err['pred']} "
                  f"({err['error']}) [{err.get('doc_path','')}]")

    # Error analysis by document type
    print(f"\nAccuracy by document type:")
    type_stats = defaultdict(lambda: {"correct": 0, "total": 0})
    for rec in records_with_attach:
        doc_type = rec.get("doc_type", "unknown")
        for field in ["amount", "currency", "doc_number", "date"]:
            gt = rec.get(f"doc_{field}", "")
            if gt:
                type_stats[doc_type]["total"] += 1
    # (would need per-record tracking for full accuracy, simplified here)

    # Error analysis by format
    pdf_errors = sum(1 for e in errors if e.get("doc_path", "").endswith(".pdf"))
    png_errors = sum(1 for e in errors if e.get("doc_path", "").endswith(".png"))
    print(f"\nErrors by format: PDF={pdf_errors}, PNG={png_errors}")

    return field_results, errors



# Main


def main():
    parser = argparse.ArgumentParser(description="Document field extraction")
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--data_dir", default=".")
    args = parser.parse_args()

    data_path = os.path.join(args.data_dir, f"{args.split}.csv")

    if not os.path.exists(data_path):
        print(f"Error: {data_path} not found. Run split_dataset.py first.")
        return

    results, errors = evaluate_extraction(data_path, args.data_dir)

    # Save results
    output_path = os.path.join(args.data_dir,
                                f"doc_extraction_results_{args.split}.json")
    serializable_results = {}
    for field, stats in results.items():
        serializable_results[field] = dict(stats)

    with open(output_path, "w") as f:
        json.dump({
            "field_results": serializable_results,
            "num_errors": len(errors),
            "errors": errors[:100],
        }, f, indent=2, default=str)
    print(f"\n✓ Results saved to {output_path}")


if __name__ == "__main__":
    main()
