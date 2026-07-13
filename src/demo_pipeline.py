"""
demo_pipeline.py
────────────────
Test the full pipeline on a REAL email.

Usage:

  1. From Outlook .msg file (RECOMMENDED):
     python demo_pipeline.py --msg email_from_outlook.msg

  2. From text file + separate attachment:
     python demo_pipeline.py --file email.txt --attachment invoice.pdf

  3. Interactive (paste in console):
     python demo_pipeline.py

For .msg files, the script automatically:
  - Extracts subject, body, sender
  - Extracts all attachments to a temp folder
  - Runs the full pipeline (intent + extraction + reconciliation)

Requirements:
    pip install extract-msg reportlab Pillow pypdfium2 pytesseract scikit-learn
"""

import argparse
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from email_field_extractor import extract_fields as extract_email_fields
from document_field_extractor import extract_fields_from_document
from reconciliation import reconcile_pair


# ─────────────────────────────────────────────
# .MSG file parsing
# ─────────────────────────────────────────────

def parse_msg_file(msg_path):
    """
    Parse an Outlook .msg file.
    Returns: subject, body, sender, list of attachment paths, temp_dir.
    """
    try:
        import extract_msg
    except ImportError:
        print("ERROR: 'extract-msg' not installed.")
        print("Run:  pip install extract-msg")
        sys.exit(1)

    msg = extract_msg.Message(msg_path)

    subject = msg.subject or ""
    sender = msg.sender or ""

    # Try plain text body first, fall back to HTML
    body = msg.body or ""

    if not body.strip():
        # Many Outlook emails are HTML-only — extract text from HTML
        html_body = msg.htmlBody
        if html_body:
            if isinstance(html_body, bytes):
                html_body = html_body.decode("utf-8", errors="ignore")
            # Strip HTML tags to get plain text
            import re
            # Remove style and script blocks
            text = re.sub(r'<style[^>]*>.*?</style>', '', html_body, flags=re.DOTALL | re.IGNORECASE)
            text = re.sub(r'<script[^>]*>.*?</script>', '', text, flags=re.DOTALL | re.IGNORECASE)
            # Replace <br>, <p>, <div> with newlines
            text = re.sub(r'<br\s*/?\s*>', '\n', text, flags=re.IGNORECASE)
            text = re.sub(r'</(p|div|tr|li)>', '\n', text, flags=re.IGNORECASE)
            # Remove all remaining tags
            text = re.sub(r'<[^>]+>', '', text)
            # Clean up HTML entities
            text = text.replace('&nbsp;', ' ').replace('&amp;', '&')
            text = text.replace('&lt;', '<').replace('&gt;', '>')
            text = text.replace('&quot;', '"').replace('&#39;', "'")
            # Clean up whitespace
            text = re.sub(r'\n\s*\n', '\n\n', text)  # collapse blank lines
            text = re.sub(r'  +', ' ', text)  # collapse spaces
            body = text.strip()

    if not body.strip():
        print("  [WARN] Could not extract email body (neither plain text nor HTML)")

    print(f"  Subject: {subject}")
    print(f"  Sender: {sender}")
    print(f"  Body length: {len(body)} chars")
    if body:
        preview = body[:150].replace('\n', ' | ')
        print(f"  Body preview: {preview}...")

    # Extract attachments to temp folder
    temp_dir = tempfile.mkdtemp(prefix="email_attachments_")
    attachment_paths = []

    for att in msg.attachments:
        filename = att.longFilename or att.shortFilename
        if filename:
            try:
                att.save(customPath=temp_dir)
                filepath = os.path.join(temp_dir, filename)
                if os.path.exists(filepath):
                    size = os.path.getsize(filepath)
                    print(f"  Attachment saved: {filename} ({size/1024:.1f} KB)")
                    attachment_paths.append(filepath)
                else:
                    # Search for the file (name might differ)
                    for f in os.listdir(temp_dir):
                        full = os.path.join(temp_dir, f)
                        if full not in attachment_paths and os.path.isfile(full):
                            size = os.path.getsize(full)
                            print(f"  Attachment saved: {f} ({size/1024:.1f} KB)")
                            attachment_paths.append(full)
            except Exception as e:
                print(f"  [WARN] Failed to save attachment '{filename}': {e}")

    if not attachment_paths:
        # Last resort: check if anything was saved to temp_dir
        for f in os.listdir(temp_dir):
            full = os.path.join(temp_dir, f)
            if os.path.isfile(full):
                attachment_paths.append(full)
                print(f"  Attachment found: {f}")

    msg.close()
    return subject, body, sender, attachment_paths, temp_dir


# ─────────────────────────────────────────────
# Intent classification (keyword-based for demo)
# ─────────────────────────────────────────────

def classify_intent_simple(text):
    """
    Keyword-based intent classification.
    Designed for real-world emails with natural phrasing.
    The trained baseline model (baseline_model.pkl) works great on synthetic data
    but may struggle with real emails, so keywords are used as primary for demo.
    """
    text_lower = text.lower()

    scores = {
        "invoice_submission": 0,
        "quote_offer": 0,
        "price_validity_confirmation": 0,
        "price_increase": 0,
        "other": 0,
    }

    # Invoice signals
    for kw in ["invoice", "billing", "payment due", "amount due", "payable",
                "remittance", "bill attached", "balance due"]:
        if kw in text_lower:
            scores["invoice_submission"] += 3

    # Quote/offer signals
    for kw in ["quotation", "quote", "commercial offer", "our offer",
                "price proposal", "cost estimate", "proposal attached"]:
        if kw in text_lower:
            scores["quote_offer"] += 3

    # Price increase signals (check BEFORE validity — "increase" overrides "valid")
    for kw in ["price increase", "price adjustment", "price revision",
                "revised pricing", "new pricing", "price change",
                "cost increase", "updated price", "new prices",
                "prices will increase", "rate increase", "tariff increase",
                "increase based on", "% increase", "surcharge"]:
        if kw in text_lower:
            scores["price_increase"] += 4  # higher weight — strong signal

    # Also check for "increase" near "price" (within ~50 chars)
    import re
    if re.search(r'price.{0,50}increase|increase.{0,50}price', text_lower):
        scores["price_increase"] += 3
    if re.search(r'new.{0,20}price', text_lower):
        scores["price_increase"] += 3

    # Price validity signals (only if increase signals are absent)
    for kw in ["still valid", "remain valid", "prices remain", "confirm that",
                "validity confirmation", "still applicable", "still active",
                "has not changed", "prices unchanged", "no change in price",
                "confirm the prices", "prices are confirmed"]:
        if kw in text_lower:
            scores["price_validity_confirmation"] += 3

    # "valid until" is ambiguous — could be quote or validity confirmation
    # But NOT price increase (increase + valid until = increase with end date)
    if "valid until" in text_lower and scores["price_increase"] == 0:
        scores["quote_offer"] += 1
        scores["price_validity_confirmation"] += 1

    best = max(scores, key=scores.get)
    return best if scores[best] > 0 else "other"


# ─────────────────────────────────────────────
# Main pipeline
# ─────────────────────────────────────────────

def run_demo(subject, body, sender=None, attachment_paths=None):
    """Run the full pipeline on a single email."""
    full_text = f"Subject: {subject}\n\n{body}"
    attachment_paths = attachment_paths or []

    supported_ext = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".bmp"}
    doc_attachments = [
        p for p in attachment_paths
        if os.path.splitext(p)[1].lower() in supported_ext
    ]

    print("\n" + "=" * 65)
    print("PIPELINE DEMO — Real Email Analysis")
    print("=" * 65)

    if sender:
        print(f"\nFrom:    {sender}")
    print(f"Subject: {subject}")
    print(f"Body:    {len(body)} characters")
    print(f"Attachments: {len(attachment_paths)} total, "
          f"{len(doc_attachments)} processable (PDF/image)")

    if attachment_paths:
        for p in attachment_paths:
            ext = os.path.splitext(p)[1].lower()
            tag = "  processable" if ext in supported_ext else "  skipped"
            print(f"  -> {os.path.basename(p)} [{tag}]")

    # ── Step 1: Intent Classification ──
    print(f"\n{'─' * 65}")
    print("STEP 1: Intent Classification")
    print(f"{'─' * 65}")

    intent = classify_intent_simple(full_text)
    intent_descriptions = {
        "invoice_submission": "Supplier is sending an invoice",
        "quote_offer": "Supplier is sending a quotation/offer",
        "price_validity_confirmation": "Supplier confirms prices are still valid",
        "price_increase": "Supplier announces a price increase",
        "other": "General communication",
    }
    print(f"  Predicted intent: {intent}")
    print(f"  Meaning: {intent_descriptions.get(intent, 'Unknown')}")

    # ── Step 2: Email Field Extraction ──
    print(f"\n{'─' * 65}")
    print("STEP 2: Email Field Extraction")
    print(f"{'─' * 65}")

    email_fields = extract_email_fields(full_text)

    for field in ["amount", "currency", "doc_number", "date"]:
        val = email_fields.get(f"pred_{field}")
        if val is not None:
            print(f"  {field:15s}: {val}")
        else:
            print(f"  {field:15s}: -- (not mentioned in email)")

    # ── Step 3 & 4: Process each document attachment ──
    doc_fields = {}

    if doc_attachments:
        for att_path in doc_attachments:
            att_name = os.path.basename(att_path)

            print(f"\n{'─' * 65}")
            print(f"STEP 3: Document Extraction — {att_name}")
            print(f"{'─' * 65}")

            doc_type = "invoice" if intent == "invoice_submission" else "quotation"

            # Check file exists and has content
            if not os.path.exists(att_path):
                print(f"  File not found: {att_path}")
                continue
            fsize = os.path.getsize(att_path)
            print(f"  File size: {fsize/1024:.1f} KB")

            if fsize < 100:
                print(f"  File too small ({fsize} bytes) — likely empty or corrupt")
                continue

            doc_fields = extract_fields_from_document(att_path, doc_type)

            # Show error details if OCR failed
            if doc_fields.get("error"):
                print(f"  Error: {doc_fields['error']}")

            if doc_fields.get("ocr_success"):
                for field in ["amount", "currency", "doc_number", "date"]:
                    val = doc_fields.get(f"pred_{field}")
                    if val is not None:
                        print(f"  {field:15s}: {val}")
                    else:
                        print(f"  {field:15s}: -- (not found in document)")

                ocr_text = doc_fields.get("ocr_text", "")
                if ocr_text:
                    preview = ocr_text[:200].replace("\n", " | ")
                    print(f"\n  OCR preview: {preview}...")

                # ── Step 4: Reconciliation ──
                print(f"\n{'─' * 65}")
                print(f"STEP 4: Reconciliation — email vs {att_name}")
                print(f"{'─' * 65}")

                recon = reconcile_pair(email_fields, doc_fields)

                print(f"\n  {'Field':<15s} {'Email':>15s} {'Document':>15s} {'Match':>8s}")
                print(f"  {'─' * 55}")

                for field in ["amount", "currency", "doc_number", "date"]:
                    comp = recon["field_comparisons"][field]
                    e_val = str(comp["email_value"]) if comp["email_value"] is not None else "--"
                    d_val = str(comp["doc_value"]) if comp["doc_value"] is not None else "--"

                    if not comp["comparable"]:
                        match_str = "N/A"
                    elif comp["match"]:
                        match_str = "OK"
                    else:
                        match_str = "DIFF!"

                    print(f"  {field:<15s} {e_val:>15s} {d_val:>15s} {match_str:>8s}")

                print(f"\n  VERDICT: ", end="")
                if recon["verdict"] == "consistent":
                    print("CONSISTENT — email and document agree")
                else:
                    fields = ", ".join(recon["mismatched_fields"])
                    print(f"MISMATCH detected on: {fields}")

            else:
                print("  OCR failed — could not extract text from document")

    else:
        print(f"\n{'─' * 65}")
        print("STEPS 3-4: Skipped — no processable attachments")
        print(f"{'─' * 65}")

    # ── Summary ──
    print(f"\n{'=' * 65}")
    print("SUMMARY")
    print(f"{'=' * 65}")
    print(f"  Intent:         {intent}")
    print(f"  Email fields:   amount={email_fields.get('pred_amount')}, "
          f"currency={email_fields.get('pred_currency')}, "
          f"doc_nr={email_fields.get('pred_doc_number')}, "
          f"date={email_fields.get('pred_date')}")
    if doc_fields and doc_fields.get("ocr_success"):
        print(f"  Doc fields:     amount={doc_fields.get('pred_amount')}, "
              f"currency={doc_fields.get('pred_currency')}, "
              f"doc_nr={doc_fields.get('pred_doc_number')}, "
              f"date={doc_fields.get('pred_date')}")
        recon = reconcile_pair(email_fields, doc_fields)
        verdict = recon["verdict"].upper()
        if recon["mismatched_fields"]:
            verdict += f" on {', '.join(recon['mismatched_fields'])}"
        print(f"  Reconciliation: {verdict}")
    print(f"{'=' * 65}")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Demo: test the full pipeline on a real email",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python demo_pipeline.py --msg email_from_outlook.msg
  python demo_pipeline.py --file email.txt --attachment invoice.pdf
  python demo_pipeline.py  (interactive mode)
        """
    )
    parser.add_argument("--msg", help="Outlook .msg file")
    parser.add_argument("--file", help="Text file (line 1=subject, rest=body)")
    parser.add_argument("--attachment", help="Path to attachment PDF or image")
    args = parser.parse_args()

    temp_dir = None

    try:
        if args.msg:
            if not os.path.exists(args.msg):
                print(f"Error: file not found: {args.msg}")
                return
            print(f"Parsing Outlook message: {args.msg}")
            subject, body, sender, attachment_paths, temp_dir = parse_msg_file(args.msg)
            run_demo(subject, body, sender, attachment_paths)

        elif args.file:
            with open(args.file, "r", encoding="utf-8") as f:
                lines = f.readlines()
            subject = lines[0].strip() if lines else ""
            body = "".join(lines[1:]).strip()
            attachments = [args.attachment] if args.attachment else []
            run_demo(subject, body, attachment_paths=attachments)

        else:
            print("Paste your email below.")
            print("First line = subject, then the body.")
            print("Type END on a new line when done.")
            print("-" * 40)

            lines = []
            while True:
                try:
                    line = input()
                    if line.strip() == "END":
                        break
                    lines.append(line)
                except EOFError:
                    break

            if not lines:
                print("No input received.")
                return

            subject = lines[0].strip()
            body = "\n".join(lines[1:]).strip()
            run_demo(subject, body)

    finally:
        if temp_dir and os.path.exists(temp_dir):
            shutil.rmtree(temp_dir, ignore_errors=True)


if __name__ == "__main__":
    main()
