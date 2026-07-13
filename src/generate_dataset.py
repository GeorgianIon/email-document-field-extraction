"""
generate_dataset.py
───────────────────
Generates the synthetic email - document dataset:
  - emails.csv   : email records with intent labels and ground-truth fields
  - pairs.csv    : email-to-attachment mapping with mismatch annotations
  - attachments/  : (placeholder paths — actual files generated in Step 2)

Usage:
    python generate_dataset.py
"""

import csv
import os
import random
import re
import string
from datetime import datetime, timedelta
from typing import Optional, Tuple

from config import (
    SEED,
    CLASS_DISTRIBUTION,
    ATTACHMENT_PROBABILITY,
    ATTACHMENT_DOC_TYPE,
    PDF_RATIO,
    KEY_FIELDS,
    FIELD_MENTION_PROBABILITY,
    MISMATCH_RATIO,
    MISMATCH_TYPES,
    MISMATCH_TYPE_WEIGHTS,
    CURRENCIES,
    CURRENCY_SYMBOLS,
    SUPPLIER_COMPANIES,
    SUPPLIER_CONTACTS,
    RECIPIENT_NAMES,
    AMOUNT_RANGES,
    DATE_RANGE_START,
    DATE_RANGE_END,
    VALIDITY_DAYS_RANGE,
    PAYMENT_DUE_DAYS,
    EmailRecord,
    PairRecord,
)
from templates import (
    ITEM_DESCRIPTIONS,
    SUBJECT_TEMPLATES,
    BODY_TEMPLATES,
)



# Helper functions


def random_date(start_str: str, end_str: str) -> datetime:
    """Return a random datetime between two date strings (YYYY-MM-DD)."""
    start = datetime.strptime(start_str, "%Y-%m-%d")
    end = datetime.strptime(end_str, "%Y-%m-%d")
    delta = (end - start).days
    return start + timedelta(days=random.randint(0, delta))


def format_amount(amount: float) -> str:
    """Format amount with 2 decimals, sometimes with comma as thousands sep."""
    style = random.choice(["standard", "comma", "space", "plain"])
    if style == "standard":
        return f"{amount:,.2f}"             # 12,345.67
    elif style == "comma":
        # European style: 12.345,67
        s = f"{amount:,.2f}"
        s = s.replace(",", "X").replace(".", ",").replace("X", ".")
        return s
    elif style == "space":
        s = f"{amount:,.2f}"
        return s.replace(",", " ")          # 12 345.67
    else:
        return f"{amount:.2f}"              # 12345.67


def generate_doc_number(intent: str) -> str:
    """Generate a realistic document number based on intent."""
    year = random.choice(["2024", "2025", "2026"])
    seq = random.randint(1000, 99999)

    if intent == "quote_offer" or intent == "price_validity_confirmation":
        prefix = random.choice(["QT", "QUO", "OFF", "Q"])
        return f"{prefix}-{year}-{seq}"
    elif intent == "invoice_submission":
        prefix = random.choice(["INV", "FV", "BILL", "F"])
        return f"{prefix}-{year}-{seq}"
    elif intent == "price_increase":
        prefix = random.choice(["PL", "PR", "REV"])
        return f"{prefix}-{year}-{seq}"
    else:
        prefix = random.choice(["REF", "DOC", "GEN"])
        return f"{prefix}-{year}-{seq}"


def generate_amount(doc_type: str) -> float:
    """Generate a realistic monetary amount."""
    low, high = AMOUNT_RANGES.get(doc_type, (100.0, 50000.0))
    amount = random.uniform(low, high)
    # Round to 2 decimals, sometimes to whole number
    if random.random() < 0.3:
        return round(amount, 0)
    return round(amount, 2)


def generate_relevant_date(intent: str, base_date: datetime) -> Tuple[str, str]:
    """
    Generate a relevant date and its label based on intent.
    Returns (date_string, date_label).
    """
    if intent == "quote_offer":
        # Validity end date
        days = random.randint(*VALIDITY_DAYS_RANGE)
        d = base_date + timedelta(days=days)
        return d.strftime("%Y-%m-%d"), "validity_end"

    elif intent == "invoice_submission":
        # Payment due date
        days = random.choice(PAYMENT_DUE_DAYS)
        d = base_date + timedelta(days=days)
        return d.strftime("%Y-%m-%d"), "due_date"

    elif intent == "price_validity_confirmation":
        # Extended validity date
        days = random.randint(15, 60)
        d = base_date + timedelta(days=days)
        return d.strftime("%Y-%m-%d"), "validity_end"

    elif intent == "price_increase":
        # Effective date of new prices
        days = random.randint(14, 90)
        d = base_date + timedelta(days=days)
        return d.strftime("%Y-%m-%d"), "effective_date"

    else:
        # Generic date
        return base_date.strftime("%Y-%m-%d"), "reference_date"


def format_date_for_email(date_str: str) -> str:
    """Format a date string in a natural way for email text."""
    d = datetime.strptime(date_str, "%Y-%m-%d")
    style = random.choice(["iso", "long", "medium", "slash"])
    if style == "iso":
        return date_str                                    # 2025-06-15
    elif style == "long":
        return d.strftime("%B %d, %Y")                    # June 15, 2025
    elif style == "medium":
        return d.strftime("%d %b %Y")                     # 15 Jun 2025
    else:
        return d.strftime("%m/%d/%Y")                     # 06/15/2025


def introduce_mismatch(
    original_amount: float,
    original_currency: str,
    original_date: str,
    mismatch_field: str,
) -> Tuple[Optional[float], Optional[str], Optional[str]]:
    """
    Create a mismatched value for one field.
    Returns (new_amount, new_currency, new_date) — only the mismatched field changes.
    """
    new_amount = original_amount
    new_currency = original_currency
    new_date = original_date

    if mismatch_field == "amount":
        # Introduce a realistic amount difference
        method = random.choice(["percentage", "rounding", "digit_swap", "add_tax"])
        if method == "percentage":
            factor = random.choice([0.90, 0.95, 1.05, 1.10, 1.15, 1.20])
            new_amount = round(original_amount * factor, 2)
        elif method == "rounding":
            new_amount = round(original_amount, 0)
            if new_amount == original_amount:
                new_amount += random.choice([1, -1, 10, -10, 100])
        elif method == "digit_swap":
            # Add or subtract a small random value
            delta = random.uniform(10, 500)
            new_amount = round(original_amount + random.choice([-1, 1]) * delta, 2)
        elif method == "add_tax":
            # Simulate tax being added/removed
            tax_rate = random.choice([0.05, 0.09, 0.19, 0.21])
            new_amount = round(original_amount * (1 + tax_rate), 2)
        # Ensure it's actually different
        if new_amount == original_amount:
            new_amount = round(original_amount * 1.07, 2)

    elif mismatch_field == "currency":
        other_currencies = [c for c in CURRENCIES if c != original_currency]
        new_currency = random.choice(other_currencies)

    elif mismatch_field == "date":
        d = datetime.strptime(original_date, "%Y-%m-%d")
        shift = random.choice([-30, -15, -7, -3, -1, 1, 3, 7, 15, 30])
        new_date = (d + timedelta(days=shift)).strftime("%Y-%m-%d")

    return new_amount, new_currency, new_date



# Main generation logic


def generate_dataset(output_dir: str = "."):
    random.seed(SEED)

    emails = []
    pairs = []

    global_idx = 0

    for intent, count in CLASS_DISTRIBUTION.items():
        for i in range(count):
            global_idx += 1
            email_id = f"EMAIL-{global_idx:04d}"
            pair_id = f"PAIR-{global_idx:04d}"

            # ── Pick supplier ──
            company = random.choice(SUPPLIER_COMPANIES)
            contact_name, contact_user = random.choice(SUPPLIER_CONTACTS)
            domain = company.lower().replace(" ", "").replace(".", "").replace(",", "")
            domain = domain[:20] + ".com"
            sender_email = f"{contact_user}@{domain}"
            recipient = random.choice(RECIPIENT_NAMES)

            # ── Generate ground-truth values ──
            doc_type = ATTACHMENT_DOC_TYPE[intent]
            gt_amount = generate_amount(doc_type)
            gt_currency = random.choice(CURRENCIES)
            gt_doc_number = generate_doc_number(intent)
            base_date = random_date(DATE_RANGE_START, DATE_RANGE_END)
            gt_date_raw, date_label = generate_relevant_date(intent, base_date)

            items_desc = random.choice(ITEM_DESCRIPTIONS)

            # ── Decide which fields are mentioned in email ──
            field_probs = FIELD_MENTION_PROBABILITY[intent]
            mentions = {
                "amount":     random.random() < field_probs["amount"],
                "currency":   random.random() < field_probs["currency"],
                "doc_number": random.random() < field_probs["doc_number"],
                "date":       random.random() < field_probs["date"],
            }
            # Currency is only mentioned if amount is mentioned
            if not mentions["amount"]:
                mentions["currency"] = False
            # If amount IS mentioned, force currency to be mentioned too (realistic)
            if mentions["amount"]:
                mentions["currency"] = True

            # ── Pick template ──
            available_templates = BODY_TEMPLATES[intent]
            # Explicit templates need amount + doc_number + date to read naturally
            has_core_fields = (mentions["amount"] and mentions["doc_number"]
                               and mentions["date"])

            if has_core_fields:
                # Use explicit templates when we have enough data to fill them
                explicit_templates = [t for t in available_templates if t[1] == "explicit"]
                if explicit_templates:
                    body_template, explicitness = random.choice(explicit_templates)
                else:
                    body_template, explicitness = random.choice(available_templates)
            else:
                # Use vague templates to avoid empty gaps in the text
                vague_templates = [t for t in available_templates if t[1] == "vague"]
                if vague_templates:
                    body_template, explicitness = random.choice(vague_templates)
                else:
                    body_template, explicitness = random.choice(available_templates)

            # ── IMPORTANT: sync mentions flags with actual template ──
            # If a vague template was selected, the values won't appear in text
            # so all mentions must be set to False
            if explicitness == "vague":
                mentions = {
                    "amount": False,
                    "currency": False,
                    "doc_number": False,
                    "date": False,
                }

            # ── Format values for email text ──
            amount_str = format_amount(gt_amount) if mentions["amount"] else ""
            currency_str = gt_currency if mentions["currency"] else ""
            # Sometimes use symbol instead of code
            if mentions["currency"] and random.random() < 0.4:
                currency_str = CURRENCY_SYMBOLS.get(gt_currency, gt_currency)

            date_str = format_date_for_email(gt_date_raw) if mentions["date"] else ""
            doc_number_str = gt_doc_number if mentions["doc_number"] else ""

            # ── Build subject ──
            subject_templates = SUBJECT_TEMPLATES[intent]
            subject_template = random.choice(subject_templates)
            subject = subject_template.format(
                doc_number=gt_doc_number if mentions["doc_number"] else "",
                company=company,
                items_desc=items_desc,
                date=date_str,
            )
            # Clean up double spaces or trailing dashes from empty placeholders
            subject = " ".join(subject.split())
            subject = subject.replace("  -", " -").replace("-  ", "- ").strip(" --")

            # ── Build body ──
            body = body_template.format(
                recipient=recipient,
                sender_name=contact_name,
                company=company,
                doc_number=doc_number_str if mentions["doc_number"] else "[see attached]",
                amount=amount_str if mentions["amount"] else "[see attached]",
                currency=currency_str if mentions["currency"] else "",
                date=date_str if mentions["date"] else "[see attached]",
                items_desc=items_desc,
            )

            # Clean up any leftover artifacts from unfilled placeholders
            body = body.replace("[see attached] ", "").replace(" [see attached]", "")
            body = body.replace("[see attached]", "")
            # Remove double spaces and clean up punctuation artifacts
            body = re.sub(r'  +', ' ', body)           # collapse multiple spaces
            body = re.sub(r' ,', ',', body)             # " ," -> ","
            body = re.sub(r' \.', '.', body)            # " ." -> "."
            body = re.sub(r'\n +', '\n', body)          # leading spaces after newline
            body = re.sub(r'for \n', 'for your review.\n', body)  # fix dangling "for"

            # ── POST-GENERATION VERIFICATION ──
            # Check if each value ACTUALLY appears in the generated text
            # This catches cases where template doesn't use a placeholder
            combined_text = subject + " " + body

            if mentions["amount"] and amount_str:
                if amount_str not in combined_text:
                    mentions["amount"] = False
                    mentions["currency"] = False  # currency without amount is meaningless

            if mentions["doc_number"] and doc_number_str:
                if doc_number_str not in combined_text:
                    mentions["doc_number"] = False

            if mentions["date"] and date_str:
                if date_str not in combined_text:
                    mentions["date"] = False

            if mentions["currency"] and currency_str:
                if currency_str not in combined_text:
                    mentions["currency"] = False

            # ── Create EmailRecord ──
            email_rec = EmailRecord(
                email_id=email_id,
                intent=intent,
                subject=subject,
                body=body,
                sender_name=contact_name,
                sender_email=sender_email,
                sender_company=company,
                gt_amount=gt_amount if mentions["amount"] else None,
                gt_currency=gt_currency if mentions["currency"] else None,
                gt_doc_number=gt_doc_number if mentions["doc_number"] else None,
                gt_date=gt_date_raw if mentions["date"] else None,
                mentions_amount=mentions["amount"],
                mentions_currency=mentions["currency"],
                mentions_doc_number=mentions["doc_number"],
                mentions_date=mentions["date"],
            )
            emails.append(email_rec)

            # ── Decide attachment ──
            attach_prob = ATTACHMENT_PROBABILITY[intent]
            has_attachment = random.random() < attach_prob

            if has_attachment:
                fmt = "pdf" if random.random() < PDF_RATIO else "png"
                ext = fmt
                attachment_filename = f"{doc_type}_{global_idx:04d}.{ext}"
                attachment_path = f"attachments/{attachment_filename}"

                # Document ground-truth values (same as email GT by default)
                doc_amount = gt_amount
                doc_currency = gt_currency
                doc_doc_number = gt_doc_number
                doc_date = gt_date_raw

                # ── Introduce mismatch? ──
                is_consistent = True
                mismatch_field = None
                mismatch_type = None

                # Only introduce mismatches when email explicitly mentions the field
                if random.random() < MISMATCH_RATIO:
                    # Pick a mismatch field (weighted)
                    candidates = []
                    weights = []
                    for mf in MISMATCH_TYPES:
                        if mentions.get(mf, False):  # only if email mentions it
                            candidates.append(mf)
                            weights.append(MISMATCH_TYPE_WEIGHTS[mf])

                    if candidates:
                        # Normalize weights
                        total_w = sum(weights)
                        weights = [w / total_w for w in weights]
                        mismatch_field = random.choices(candidates, weights=weights, k=1)[0]

                        new_amount, new_currency, new_date = introduce_mismatch(
                            doc_amount, doc_currency, doc_date, mismatch_field
                        )
                        doc_amount = new_amount
                        doc_currency = new_currency
                        doc_date = new_date
                        is_consistent = False
                        mismatch_type = mismatch_field

                pair_rec = PairRecord(
                    pair_id=pair_id,
                    email_id=email_id,
                    attachment_path=attachment_path,
                    attachment_format=fmt,
                    doc_type=doc_type,
                    doc_amount=doc_amount,
                    doc_currency=doc_currency,
                    doc_doc_number=doc_doc_number,
                    doc_date=doc_date,
                    is_consistent=is_consistent,
                    mismatch_field=mismatch_field,
                    mismatch_type=mismatch_type,
                )
            else:
                pair_rec = PairRecord(
                    pair_id=pair_id,
                    email_id=email_id,
                    attachment_path=None,
                    attachment_format=None,
                    doc_type=None,
                    doc_amount=None,
                    doc_currency=None,
                    doc_doc_number=None,
                    doc_date=None,
                    is_consistent=True,
                    mismatch_field=None,
                    mismatch_type=None,
                )
            pairs.append(pair_rec)

    # ── Shuffle to avoid class ordering ──
    combined = list(zip(emails, pairs))
    random.shuffle(combined)
    emails, pairs = zip(*combined)
    emails = list(emails)
    pairs = list(pairs)

    # ── Write emails.csv ──
    emails_path = os.path.join(output_dir, "emails.csv")
    with open(emails_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "email_id", "intent", "subject", "body",
            "sender_name", "sender_email", "sender_company",
            "gt_amount", "gt_currency", "gt_doc_number", "gt_date",
            "mentions_amount", "mentions_currency",
            "mentions_doc_number", "mentions_date",
        ])
        for e in emails:
            writer.writerow([
                e.email_id, e.intent, e.subject, e.body,
                e.sender_name, e.sender_email, e.sender_company,
                e.gt_amount if e.gt_amount is not None else "",
                e.gt_currency if e.gt_currency is not None else "",
                e.gt_doc_number if e.gt_doc_number is not None else "",
                e.gt_date if e.gt_date is not None else "",
                e.mentions_amount, e.mentions_currency,
                e.mentions_doc_number, e.mentions_date,
            ])
    print(f"[OK] Written {len(emails)} emails to {emails_path}")

    # ── Write pairs.csv ──
    pairs_path = os.path.join(output_dir, "pairs.csv")
    with open(pairs_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow([
            "pair_id", "email_id", "attachment_path", "attachment_format",
            "doc_type",
            "doc_amount", "doc_currency", "doc_doc_number", "doc_date",
            "is_consistent", "mismatch_field", "mismatch_type",
        ])
        for p in pairs:
            writer.writerow([
                p.pair_id, p.email_id,
                p.attachment_path if p.attachment_path else "",
                p.attachment_format if p.attachment_format else "",
                p.doc_type if p.doc_type else "",
                p.doc_amount if p.doc_amount is not None else "",
                p.doc_currency if p.doc_currency is not None else "",
                p.doc_doc_number if p.doc_doc_number is not None else "",
                p.doc_date if p.doc_date is not None else "",
                p.is_consistent,
                p.mismatch_field if p.mismatch_field else "",
                p.mismatch_type if p.mismatch_type else "",
            ])
    print(f"[OK] Written {len(pairs)} pairs to {pairs_path}")

    # ── Print summary statistics ──
    print("\n" + "=" * 60)
    print("DATASET SUMMARY")
    print("=" * 60)

    # Class distribution
    from collections import Counter
    intent_counts = Counter(e.intent for e in emails)
    print("\n📧 Intent distribution:")
    for intent, cnt in sorted(intent_counts.items()):
        print(f"   {intent:40s} {cnt:4d}")

    # Attachment stats
    with_attach = sum(1 for p in pairs if p.attachment_path)
    without_attach = sum(1 for p in pairs if not p.attachment_path)
    print(f"\n📎 Attachments:  {with_attach} with  |  {without_attach} without")

    # Format split
    pdf_count = sum(1 for p in pairs if p.attachment_format == "pdf")
    png_count = sum(1 for p in pairs if p.attachment_format == "png")
    print(f"   PDF: {pdf_count}  |  PNG: {png_count}")

    # Mismatch stats
    mismatches = [p for p in pairs if not p.is_consistent]
    consistent = [p for p in pairs if p.is_consistent]
    print(f"\n🔍 Consistency:  {len(consistent)} consistent  |  {len(mismatches)} mismatched")

    if mismatches:
        mismatch_fields = Counter(p.mismatch_field for p in mismatches)
        print("   Mismatch breakdown:")
        for mf, cnt in sorted(mismatch_fields.items()):
            print(f"      {mf:20s} {cnt:4d}")

    # Field mention stats
    print("\n📝 Field mention rates in emails:")
    for field_name in KEY_FIELDS:
        mentioned = sum(1 for e in emails if getattr(e, f"mentions_{field_name}"))
        rate = mentioned / len(emails) * 100
        print(f"   {field_name:20s} {mentioned:4d} ({rate:.1f}%)")

    # Train/val/test split info
    print(f"\n📊 Suggested split (70/15/15):")
    n = len(emails)
    print(f"   Train: {int(n*0.70)}  |  Val: {int(n*0.15)}  |  Test: {n - int(n*0.70) - int(n*0.15)}")
    print("=" * 60)


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Generate synthetic emails.csv + pairs.csv")
    parser.add_argument(
        "--data_dir",
        default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data"),
        help="Where to write emails.csv and pairs.csv (default: ../data)",
    )
    args = parser.parse_args()
    output_dir = os.path.abspath(args.data_dir)
    os.makedirs(output_dir, exist_ok=True)
    generate_dataset(output_dir)
