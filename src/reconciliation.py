"""
reconciliation.py
─────────────────
Compares fields extracted from email vs document and detects mismatches.

Three evaluation scenarios:
  1. text-only:     uses only email-extracted fields
  2. document-only: uses only document-extracted fields
  3. multimodal:    compares email fields with document fields, flags mismatches

Usage:
    python reconciliation.py [--split test] [--data_dir .]
"""

import argparse
import csv
import json
import os
import re
from collections import Counter, defaultdict
from typing import Dict, Optional, Tuple

from email_field_extractor import extract_fields as extract_email_fields
from document_field_extractor import extract_fields_from_document


# ─────────────────────────────────────────────
# Normalization for comparison
# ─────────────────────────────────────────────

def normalize_for_comparison(value, field_type: str):
    """Normalize a value for cross-source comparison."""
    if value is None:
        return None

    if field_type == "amount":
        try:
            return round(float(value), 2)
        except (ValueError, TypeError):
            return None

    elif field_type == "currency":
        return str(value).upper().strip()

    elif field_type == "doc_number":
        # Remove separators for flexible matching
        return re.sub(r'[-/\s]', '', str(value).upper())

    elif field_type == "date":
        return str(value).strip()

    return str(value)


def fields_match(val_a, val_b, field_type: str) -> bool:
    """Compare two normalized values."""
    a = normalize_for_comparison(val_a, field_type)
    b = normalize_for_comparison(val_b, field_type)

    if a is None or b is None:
        return True  # Can't compare if one is missing → not a mismatch

    if field_type == "amount":
        # Allow 1% tolerance for OCR rounding
        tolerance = max(1.0, max(abs(a), abs(b)) * 0.01)
        return abs(a - b) < tolerance

    return a == b


# ─────────────────────────────────────────────
# Reconciliation logic
# ─────────────────────────────────────────────

def reconcile_pair(
    email_fields: Dict,
    doc_fields: Dict,
) -> Dict:
    """
    Compare email-extracted fields with document-extracted fields.
    Returns a reconciliation verdict.
    """
    result = {
        "verdict": "consistent",  # or "mismatch"
        "mismatched_fields": [],
        "field_comparisons": {},
    }

    for field in ["amount", "currency", "doc_number", "date"]:
        email_val = email_fields.get(f"pred_{field}")
        doc_val = doc_fields.get(f"pred_{field}")

        comparison = {
            "email_value": email_val,
            "doc_value": doc_val,
            "email_present": email_val is not None,
            "doc_present": doc_val is not None,
            "match": True,
            "comparable": email_val is not None and doc_val is not None,
        }

        if comparison["comparable"]:
            comparison["match"] = fields_match(email_val, doc_val, field)
            if not comparison["match"]:
                result["mismatched_fields"].append(field)

        result["field_comparisons"][field] = comparison

    if result["mismatched_fields"]:
        result["verdict"] = "mismatch"

    return result


# ─────────────────────────────────────────────
# Full pipeline evaluation
# ─────────────────────────────────────────────

def evaluate_all_scenarios(data_path: str, data_dir: str):
    """
    Run and evaluate all three scenarios:
      1. Text-only: email field extraction accuracy
      2. Document-only: document field extraction accuracy
      3. Multimodal: mismatch detection (comparing both sources)
    """
    records = []
    with open(data_path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            records.append(row)

    records_with_attach = [r for r in records if r.get("attachment_path", "")]

    print(f"\n{'='*65}")
    print(f"FULL PIPELINE EVALUATION — {os.path.basename(data_path)}")
    print(f"{'='*65}")
    print(f"Total records: {len(records)}")
    print(f"With attachments: {len(records_with_attach)}")

    # ── SCENARIO 1: Text-Only ──
    print(f"\n{'─'*65}")
    print(f"SCENARIO 1: TEXT-ONLY (email extraction)")
    print(f"{'─'*65}")

    text_only_results = {"correct": 0, "incorrect": 0, "total": 0}
    for rec in records:
        text = f"Subject: {rec['subject']}\n\n{rec['body']}"
        extracted = extract_email_fields(text)

        for field in ["amount", "currency", "doc_number", "date"]:
            gt = rec.get(f"gt_{field}", "")
            mentions = rec.get(f"mentions_{field}", "False") == "True"
            if not mentions or not gt:
                continue

            pred = extracted.get(f"pred_{field}")
            text_only_results["total"] += 1

            if pred is not None:
                norm_pred = normalize_for_comparison(pred, field)
                norm_gt = normalize_for_comparison(gt, field)
                if norm_pred == norm_gt or fields_match(pred, gt, field):
                    text_only_results["correct"] += 1
                else:
                    text_only_results["incorrect"] += 1
            else:
                text_only_results["incorrect"] += 1

    text_acc = (text_only_results["correct"] / text_only_results["total"]
                if text_only_results["total"] > 0 else 0)
    print(f"  Field extraction accuracy: {text_acc:.2%} "
          f"({text_only_results['correct']}/{text_only_results['total']})")

    # ── SCENARIO 2: Document-Only ──
    print(f"\n{'─'*65}")
    print(f"SCENARIO 2: DOCUMENT-ONLY (OCR + extraction)")
    print(f"{'─'*65}")

    doc_only_results = {"correct": 0, "incorrect": 0, "total": 0}
    doc_extractions = {}  # Cache for scenario 3

    for rec in records_with_attach:
        doc_path = os.path.join(data_dir, rec["attachment_path"])
        if not os.path.exists(doc_path):
            continue

        doc_type = rec.get("doc_type", "invoice")
        extracted = extract_fields_from_document(doc_path, doc_type)
        doc_extractions[rec["email_id"]] = extracted

        for field in ["amount", "currency", "doc_number", "date"]:
            gt = rec.get(f"doc_{field}", "")
            if not gt:
                continue

            pred = extracted.get(f"pred_{field}")
            doc_only_results["total"] += 1

            if pred is not None and fields_match(pred, gt, field):
                doc_only_results["correct"] += 1
            else:
                doc_only_results["incorrect"] += 1

    doc_acc = (doc_only_results["correct"] / doc_only_results["total"]
               if doc_only_results["total"] > 0 else 0)
    print(f"  Field extraction accuracy: {doc_acc:.2%} "
          f"({doc_only_results['correct']}/{doc_only_results['total']})")

    # ── SCENARIO 3: MULTIMODAL (mismatch detection) ──
    print(f"\n{'─'*65}")
    print(f"SCENARIO 3: MULTIMODAL (mismatch detection)")
    print(f"{'─'*65}")

    # Only evaluate on records that have both email fields and document
    tp = 0   # True positive: correctly detected mismatch
    fp = 0   # False positive: flagged mismatch but actually consistent
    tn = 0   # True negative: correctly identified as consistent
    fn = 0   # False negative: missed a real mismatch

    detailed_results = []

    for rec in records_with_attach:
        email_id = rec["email_id"]
        gt_consistent = rec.get("is_consistent", "True") == "True"
        gt_mismatch_field = rec.get("mismatch_field", "")

        # Email extraction
        text = f"Subject: {rec['subject']}\n\n{rec['body']}"
        email_extracted = extract_email_fields(text)

        # Document extraction (from cache)
        doc_extracted = doc_extractions.get(email_id, {})

        # Reconcile
        recon = reconcile_pair(email_extracted, doc_extracted)
        pred_consistent = recon["verdict"] == "consistent"

        # Evaluate
        if gt_consistent and pred_consistent:
            tn += 1
        elif gt_consistent and not pred_consistent:
            fp += 1
        elif not gt_consistent and not pred_consistent:
            tp += 1
        elif not gt_consistent and pred_consistent:
            fn += 1

        detailed_results.append({
            "email_id": email_id,
            "gt_consistent": gt_consistent,
            "pred_consistent": pred_consistent,
            "gt_mismatch_field": gt_mismatch_field,
            "pred_mismatched_fields": recon["mismatched_fields"],
            "correct": gt_consistent == pred_consistent,
        })

    # Metrics
    total = tp + fp + tn + fn
    accuracy = (tp + tn) / total if total > 0 else 0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = (2 * precision * recall / (precision + recall)
          if (precision + recall) > 0 else 0)

    print(f"\n  Confusion Matrix:")
    print(f"  {'':>20s} {'Pred Consistent':>18s} {'Pred Mismatch':>15s}")
    print(f"  {'GT Consistent':>20s} {tn:>18d} {fp:>15d}")
    print(f"  {'GT Mismatch':>20s} {fn:>18d} {tp:>15d}")

    print(f"\n  Mismatch Detection Metrics:")
    print(f"    Accuracy:   {accuracy:.4f}")
    print(f"    Precision:  {precision:.4f}")
    print(f"    Recall:     {recall:.4f}")
    print(f"    F1 Score:   {f1:.4f}")

    # Analysis: why were mismatches missed?
    missed = [d for d in detailed_results if not d["gt_consistent"] and d["pred_consistent"]]
    if missed:
        print(f"\n  Missed mismatches ({len(missed)}):")
        miss_reasons = Counter()
        for m in missed:
            # Check if the email even mentions the mismatched field
            rec = next(r for r in records_with_attach if r["email_id"] == m["email_id"])
            mf = m["gt_mismatch_field"]
            mentions = rec.get(f"mentions_{mf}", "False") == "True"
            if not mentions:
                miss_reasons["email_doesnt_mention_field"] += 1
            else:
                miss_reasons["extraction_error"] += 1
            print(f"    {m['email_id']}: gt_mismatch={mf}, "
                  f"email_mentions={mentions}, "
                  f"pred_mismatches={m['pred_mismatched_fields']}")
        print(f"\n  Miss reasons: {dict(miss_reasons)}")

    false_alarms = [d for d in detailed_results if d["gt_consistent"] and not d["pred_consistent"]]
    if false_alarms:
        print(f"\n  False alarms ({len(false_alarms)}):")
        for fa in false_alarms[:5]:
            print(f"    {fa['email_id']}: pred_mismatches={fa['pred_mismatched_fields']}")

    # ── SUMMARY TABLE ──
    print(f"\n{'='*65}")
    print(f"SUMMARY — ALL SCENARIOS")
    print(f"{'='*65}")
    print(f"{'Scenario':<25s} {'Metric':<25s} {'Value':>10s}")
    print(f"{'-'*65}")
    print(f"{'Text-Only':<25s} {'Field Extraction Acc.':<25s} {text_acc:>10.2%}")
    print(f"{'Document-Only':<25s} {'Field Extraction Acc.':<25s} {doc_acc:>10.2%}")
    print(f"{'Multimodal':<25s} {'Mismatch Accuracy':<25s} {accuracy:>10.2%}")
    print(f"{'Multimodal':<25s} {'Mismatch Precision':<25s} {precision:>10.2%}")
    print(f"{'Multimodal':<25s} {'Mismatch Recall':<25s} {recall:>10.2%}")
    print(f"{'Multimodal':<25s} {'Mismatch F1':<25s} {f1:>10.2%}")
    print(f"{'='*65}")

    return {
        "text_only": {
            "field_extraction_accuracy": float(text_acc),
            "correct": text_only_results["correct"],
            "total": text_only_results["total"],
        },
        "document_only": {
            "field_extraction_accuracy": float(doc_acc),
            "correct": doc_only_results["correct"],
            "total": doc_only_results["total"],
        },
        "multimodal": {
            "accuracy": float(accuracy),
            "precision": float(precision),
            "recall": float(recall),
            "f1": float(f1),
            "tp": tp, "fp": fp, "tn": tn, "fn": fn,
        },
        "detailed_results": detailed_results,
    }


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Reconciliation & full evaluation")
    parser.add_argument("--split", default="test", choices=["train", "val", "test"])
    parser.add_argument("--data_dir", default=".")
    args = parser.parse_args()

    data_path = os.path.join(args.data_dir, f"{args.split}.csv")

    if not os.path.exists(data_path):
        print(f"Error: {data_path} not found.")
        return

    results = evaluate_all_scenarios(data_path, args.data_dir)

    # Save
    output_path = os.path.join(args.data_dir,
                                f"reconciliation_results_{args.split}.json")
    # Remove non-serializable items
    save_results = {k: v for k, v in results.items() if k != "detailed_results"}
    with open(output_path, "w") as f:
        json.dump(save_results, f, indent=2)
    print(f"\n✓ Results saved to {output_path}")


if __name__ == "__main__":
    main()
