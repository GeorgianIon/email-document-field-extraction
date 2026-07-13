"""
evaluate_augmented.py
─────────────────────
Evaluates Pipeline (P1) with data augmentation to address overfitting.

For each scenario (text / image / mixed):
  1. Loads clean train data + augmented train data (combined)
  2. Re-trains TF-IDF classifier on the combined set
  3. Evaluates on augmented test data
  4. Compares with clean baseline

This demonstrates that:
  - 100% accuracy on clean data is due to controlled templates
  - Augmented training + testing yields realistic, lower accuracy
  - Different augmentation types affect different pipeline components

Prerequisites:
    python augmentation.py --scenario text  --severity medium --split train
    python augmentation.py --scenario text  --severity medium --split test
    python augmentation.py --scenario image --severity medium --split train
    python augmentation.py --scenario image --severity medium --split test
    python augmentation.py --scenario mixed --severity medium --split train
    python augmentation.py --scenario mixed --severity medium --split test

Usage:
    python evaluate_augmented.py [--data_dir .]
"""

import argparse
import csv
import json
import os
import sys
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline as SkPipeline
from sklearn.metrics import accuracy_score, f1_score, classification_report, confusion_matrix

from email_field_extractor import extract_fields as extract_email_fields
from document_field_extractor import extract_fields_from_document
from reconciliation import reconcile_pair, fields_match


# ─────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────

INTENT_LABELS = [
    "invoice_submission", "other", "price_increase",
    "price_validity_confirmation", "quote_offer",
]
SEVERITY = "medium"


# ─────────────────────────────────────────────
# Data loading
# ─────────────────────────────────────────────

def load_csv(path):
    """Load a CSV file with BOM-safe encoding."""
    if not os.path.exists(path):
        return None
    records = []
    with open(path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            records.append(dict(row))
    return records


def get_texts_and_labels(records):
    """Extract email texts and intent labels from records."""
    texts = []
    labels = []
    for rec in records:
        text = f"Subject: {rec['subject']}\n\n{rec['body']}"
        texts.append(text)
        labels.append(rec["intent"])
    return texts, labels


# ─────────────────────────────────────────────
# TF-IDF training
# ─────────────────────────────────────────────

def train_tfidf(train_texts, train_labels):
    """Train a TF-IDF + Logistic Regression classifier."""
    pipeline = SkPipeline([
        ("tfidf", TfidfVectorizer(
            max_features=10000, ngram_range=(1, 2), sublinear_tf=True)),
        ("clf", LogisticRegression(
            max_iter=1000, C=1.0, class_weight="balanced", random_state=42)),
    ])
    pipeline.fit(train_texts, train_labels)
    return pipeline


# ─────────────────────────────────────────────
# Full P1 evaluation
# ─────────────────────────────────────────────

def evaluate_p1(classifier, test_records, scenario_name):
    """
    Run the full P1 pipeline on a set of test records.
    Returns a dictionary with all metrics.
    """
    intent_preds = []
    intent_true = []

    email_field_correct = 0
    email_field_total = 0

    doc_field_correct = 0
    doc_field_total = 0

    # Per-field tracking for document extraction
    doc_per_field = {f: {"correct": 0, "total": 0}
                     for f in ["amount", "currency", "doc_number", "date"]}

    mismatch_tp = 0
    mismatch_fp = 0
    mismatch_tn = 0
    mismatch_fn = 0

    for i, rec in enumerate(test_records):
        text = f"Subject: {rec['subject']}\n\n{rec['body']}"

        # 1. Intent classification
        pred_intent = classifier.predict([text])[0]
        intent_preds.append(pred_intent)
        intent_true.append(rec["intent"])

        # 2. Email field extraction (regex — not trainable)
        email_fields = extract_email_fields(text)
        for field in ["amount", "currency", "doc_number", "date"]:
            gt = rec.get(f"gt_{field}", "")
            mentions = rec.get(f"mentions_{field}", "False") == "True"
            if not mentions or not gt:
                continue
            pred = email_fields.get(f"pred_{field}")
            email_field_total += 1
            if pred is not None and fields_match(pred, gt, field):
                email_field_correct += 1

        # 3. Document field extraction (OCR + regex — not trainable)
        attach_path = rec.get("attachment_path", "")
        doc_fields = {}
        if attach_path and os.path.exists(attach_path):
            doc_type = "invoice" if "invoice" in attach_path else "quotation"
            doc_fields = extract_fields_from_document(attach_path, doc_type)

            if doc_fields.get("ocr_success"):
                for field in ["amount", "currency", "doc_number", "date"]:
                    gt = rec.get(f"doc_{field}", "")
                    if not gt:
                        continue
                    pred = doc_fields.get(f"pred_{field}")
                    doc_field_total += 1
                    doc_per_field[field]["total"] += 1
                    if pred is not None and fields_match(pred, gt, field):
                        doc_field_correct += 1
                        doc_per_field[field]["correct"] += 1

        # 4. Mismatch detection
        if attach_path and os.path.exists(attach_path) and doc_fields.get("ocr_success"):
            recon = reconcile_pair(email_fields, doc_fields)
            gt_consistent = rec.get("is_consistent", "True") == "True"
            pred_consistent = recon["verdict"] == "consistent"

            if gt_consistent and pred_consistent:
                mismatch_tn += 1
            elif gt_consistent and not pred_consistent:
                mismatch_fp += 1
            elif not gt_consistent and not pred_consistent:
                mismatch_tp += 1
            elif not gt_consistent and pred_consistent:
                mismatch_fn += 1

        if (i + 1) % 20 == 0:
            print(f"    [{i+1}/{len(test_records)}]")

    # Compute metrics
    intent_acc = accuracy_score(intent_true, intent_preds)
    intent_f1 = f1_score(intent_true, intent_preds, average="macro", zero_division=0)
    intent_cm = confusion_matrix(intent_true, intent_preds, labels=INTENT_LABELS).tolist()

    email_acc = email_field_correct / email_field_total if email_field_total > 0 else None
    doc_acc = doc_field_correct / doc_field_total if doc_field_total > 0 else None

    mm_total = mismatch_tp + mismatch_fp + mismatch_tn + mismatch_fn
    if mm_total > 0 and (mismatch_tp + mismatch_fp) > 0 and (mismatch_tp + mismatch_fn) > 0:
        mm_prec = mismatch_tp / (mismatch_tp + mismatch_fp)
        mm_rec = mismatch_tp / (mismatch_tp + mismatch_fn)
        mm_f1 = 2 * mm_prec * mm_rec / (mm_prec + mm_rec) if (mm_prec + mm_rec) > 0 else 0
    else:
        mm_prec = mm_rec = mm_f1 = None

    return {
        "scenario": scenario_name,
        "intent_accuracy": intent_acc,
        "intent_f1_macro": intent_f1,
        "intent_cm": intent_cm,
        "email_field_accuracy": email_acc,
        "doc_field_accuracy": doc_acc,
        "doc_per_field": {f: dict(s) for f, s in doc_per_field.items()},
        "mismatch_precision": mm_prec,
        "mismatch_recall": mm_rec,
        "mismatch_f1": mm_f1,
        "mismatch_counts": {
            "tp": mismatch_tp, "fp": mismatch_fp,
            "tn": mismatch_tn, "fn": mismatch_fn,
        },
    }


# ─────────────────────────────────────────────
# Visualization
# ─────────────────────────────────────────────

def generate_plots(all_results, output_dir):
    """Generate comparison plots."""
    import matplotlib.pyplot as plt

    scenarios = ["clean", "text", "image", "mixed"]
    metrics = {
        "intent_f1_macro": "Intent F1 (macro)",
        "email_field_accuracy": "Email Field Extraction",
        "doc_field_accuracy": "Document Field Extraction",
        "mismatch_f1": "Mismatch Detection F1",
    }

    # ── 1. Grouped bar chart ──
    fig, ax = plt.subplots(figsize=(12, 6))

    x = np.arange(len(metrics))
    width = 0.18
    colors = ["#2b6cb0", "#38a169", "#e53e3e", "#d69e2e"]

    for i, scenario in enumerate(scenarios):
        values = []
        for metric_key in metrics:
            val = all_results.get(scenario, {}).get(metric_key)
            values.append(val * 100 if val is not None else 0)
        bars = ax.bar(x + i * width, values, width, label=scenario.capitalize(),
                      color=colors[i], alpha=0.85)
        for bar, val in zip(bars, values):
            if val > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 0.5,
                        f"{val:.1f}", ha="center", va="bottom", fontsize=8)

    ax.set_xticks(x + width * 1.5)
    ax.set_xticklabels(list(metrics.values()), fontsize=10)
    ax.set_ylabel("Score (%)")
    ax.set_title("Pipeline (P1): Clean vs Augmented Performance\n"
                 "(Train: clean+augmented | Test: augmented | Severity: medium)",
                 fontweight="bold")
    ax.legend()
    ax.set_ylim(0, 110)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "p1_augmentation_comparison.png")
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 2. Confusion matrices ──
    fig, axes = plt.subplots(1, 4, figsize=(22, 4.5))
    short_labels = ["INV", "OTH", "P.INC", "P.VAL", "QUO"]

    for idx, scenario in enumerate(scenarios):
        ax = axes[idx]
        cm = all_results.get(scenario, {}).get("intent_cm")
        if cm is not None:
            cm = np.array(cm)
            im = ax.imshow(cm, cmap="Blues" if idx == 0 else "Oranges",
                           interpolation="nearest")
            for r in range(cm.shape[0]):
                for c in range(cm.shape[1]):
                    color = "white" if cm[r, c] > cm.max() / 2 else "black"
                    ax.text(c, r, str(cm[r, c]), ha="center", va="center",
                            fontsize=10, color=color)
            ax.set_xticks(range(5))
            ax.set_xticklabels(short_labels, fontsize=8)
            ax.set_yticks(range(5))
            ax.set_yticklabels(short_labels, fontsize=8)
            ax.set_xlabel("Predicted")
            if idx == 0:
                ax.set_ylabel("True")
        else:
            ax.text(0.5, 0.5, "N/A", ha="center", va="center",
                    transform=ax.transAxes, fontsize=14)

        title = scenario.capitalize()
        if scenario != "clean":
            title += " augmented"
        ax.set_title(title, fontsize=11, fontweight="bold")

    plt.suptitle("Intent Classification: Confusion Matrices",
                 fontsize=14, fontweight="bold")
    plt.tight_layout()
    path = os.path.join(output_dir, "p1_confusion_matrices.png")
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # ── 3. Per-field document extraction comparison ──
    fig, ax = plt.subplots(figsize=(10, 5))
    fields = ["amount", "currency", "doc_number", "date"]

    for i, scenario in enumerate(["clean", "image", "mixed"]):
        per_field = all_results.get(scenario, {}).get("doc_per_field", {})
        values = []
        for f in fields:
            stats = per_field.get(f, {})
            total = stats.get("total", 0)
            correct = stats.get("correct", 0)
            values.append(correct / total * 100 if total > 0 else 0)
        ax.bar(np.arange(len(fields)) + i * 0.25, values, 0.25,
               label=scenario.capitalize(), color=colors[i] if i == 0 else colors[i + 1],
               alpha=0.85)

    ax.set_xticks(np.arange(len(fields)) + 0.25)
    ax.set_xticklabels(fields, fontsize=11)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Document Field Extraction: Per-Field Comparison", fontweight="bold")
    ax.legend()
    ax.set_ylim(0, 110)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "p1_doc_field_comparison.png")
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


# ─────────────────────────────────────────────
# Print results table
# ─────────────────────────────────────────────

def fmt(val):
    """Format a metric value as percentage string."""
    if val is None:
        return "—"
    return f"{val * 100:.2f}%"


def print_results(all_results):
    """Print formatted comparison table."""
    w = 85
    print(f"\n{'=' * w}")
    print("PIPELINE (P1): CLEAN vs AUGMENTED PERFORMANCE")
    print(f"Training: clean + augmented (medium) | Testing: augmented (medium)")
    print(f"{'=' * w}")
    print(f"{'Scenario':<22s} {'Intent F1':>12s} {'Email Ext':>12s} "
          f"{'Doc Ext':>12s} {'Mismatch F1':>12s}")
    print(f"{'-' * w}")

    for scenario in ["clean", "text", "image", "mixed"]:
        m = all_results.get(scenario, {})
        label = {
            "clean": "Clean (baseline)",
            "text": "Aug. text",
            "image": "Aug. image",
            "mixed": "Aug. mixed",
        }[scenario]

        print(f"{label:<22s} "
              f"{fmt(m.get('intent_f1_macro')):>12s} "
              f"{fmt(m.get('email_field_accuracy')):>12s} "
              f"{fmt(m.get('doc_field_accuracy')):>12s} "
              f"{fmt(m.get('mismatch_f1')):>12s}")

    print(f"{'=' * w}")

    # Degradation analysis
    clean = all_results.get("clean", {})
    print(f"\nDegradation analysis (clean -> augmented):")
    for scenario in ["text", "image", "mixed"]:
        aug = all_results.get(scenario, {})
        drops = []
        for metric in ["intent_f1_macro", "email_field_accuracy",
                        "doc_field_accuracy", "mismatch_f1"]:
            c = clean.get(metric)
            a = aug.get(metric)
            if c is not None and a is not None:
                drop = (c - a) * 100
                if drop > 0.5:
                    name = metric.replace("_", " ").replace("f1 macro", "F1")
                    drops.append(f"{name}: -{drop:.1f}pp")
        if drops:
            print(f"  {scenario}: {', '.join(drops)}")
        else:
            print(f"  {scenario}: no significant degradation")


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Evaluate P1 pipeline with data augmentation")
    parser.add_argument("--data_dir", default=".",
                        help="Directory containing CSV files and augmented/ folder")
    args = parser.parse_args()

    data_dir = args.data_dir
    aug_dir = os.path.join(data_dir, "augmented")
    output_dir = os.path.join(data_dir, "augmented_results")
    os.makedirs(output_dir, exist_ok=True)

    all_results = {}

    # ══════════════════════════════════════════
    # Step 1: Evaluate on CLEAN data (baseline)
    # ══════════════════════════════════════════
    print(f"\n{'=' * 60}")
    print("Step 1: CLEAN baseline (train clean -> test clean)")
    print(f"{'=' * 60}")

    clean_train = load_csv(os.path.join(data_dir, "train.csv"))
    clean_test = load_csv(os.path.join(data_dir, "test.csv"))

    if clean_train is None or clean_test is None:
        print("ERROR: train.csv or test.csv not found!")
        return

    print(f"  Train: {len(clean_train)} records")
    print(f"  Test:  {len(clean_test)} records")

    # Train baseline TF-IDF on clean data
    train_texts, train_labels = get_texts_and_labels(clean_train)
    clean_classifier = train_tfidf(train_texts, train_labels)
    print(f"  TF-IDF trained on {len(train_texts)} clean examples")

    # Evaluate on clean test
    print(f"  Evaluating on clean test...")
    all_results["clean"] = evaluate_p1(clean_classifier, clean_test, "clean")
    print(f"  Intent F1: {fmt(all_results['clean']['intent_f1_macro'])}")
    print(f"  Email Ext: {fmt(all_results['clean']['email_field_accuracy'])}")
    print(f"  Doc Ext:   {fmt(all_results['clean']['doc_field_accuracy'])}")
    print(f"  Mismatch:  {fmt(all_results['clean']['mismatch_f1'])}")

    # ══════════════════════════════════════════
    # Step 2: Evaluate on each augmented scenario
    # ══════════════════════════════════════════
    for scenario in ["text", "image", "mixed"]:
        print(f"\n{'=' * 60}")
        print(f"Step 2: {scenario.upper()} augmentation "
              f"(train clean+aug -> test aug)")
        print(f"{'=' * 60}")

        # Load augmented train and test CSVs
        aug_train_path = os.path.join(aug_dir, f"train_{scenario}_{SEVERITY}.csv")
        aug_test_path = os.path.join(aug_dir, f"test_{scenario}_{SEVERITY}.csv")

        aug_train = load_csv(aug_train_path)
        aug_test = load_csv(aug_test_path)

        if aug_train is None:
            print(f"  SKIPPED: {aug_train_path} not found")
            print(f"  Run: python augmentation.py --scenario {scenario} "
                  f"--severity {SEVERITY} --split train")
            continue

        if aug_test is None:
            print(f"  SKIPPED: {aug_test_path} not found")
            print(f"  Run: python augmentation.py --scenario {scenario} "
                  f"--severity {SEVERITY} --split test")
            continue

        print(f"  Aug train: {len(aug_train)} records")
        print(f"  Aug test:  {len(aug_test)} records")

        # Decide whether to re-train TF-IDF
        if scenario in ("text", "mixed"):
            # Email text is augmented -> re-train TF-IDF on combined data
            aug_train_texts, aug_train_labels = get_texts_and_labels(aug_train)
            combined_texts = train_texts + aug_train_texts
            combined_labels = train_labels + aug_train_labels
            classifier = train_tfidf(combined_texts, combined_labels)
            print(f"  TF-IDF re-trained on {len(combined_texts)} examples "
                  f"({len(train_texts)} clean + {len(aug_train_texts)} augmented)")
        else:
            # Image scenario: email text unchanged, use clean classifier
            classifier = clean_classifier
            print(f"  TF-IDF: using clean model (emails unchanged in image scenario)")

        # Evaluate on augmented test
        print(f"  Evaluating on {scenario}-augmented test...")
        all_results[scenario] = evaluate_p1(classifier, aug_test, scenario)
        print(f"  Intent F1: {fmt(all_results[scenario]['intent_f1_macro'])}")
        print(f"  Email Ext: {fmt(all_results[scenario]['email_field_accuracy'])}")
        print(f"  Doc Ext:   {fmt(all_results[scenario]['doc_field_accuracy'])}")
        print(f"  Mismatch:  {fmt(all_results[scenario]['mismatch_f1'])}")

    # ══════════════════════════════════════════
    # Step 3: Print comparison table
    # ══════════════════════════════════════════
    print_results(all_results)

    # ══════════════════════════════════════════
    # Step 4: Generate plots
    # ══════════════════════════════════════════
    print(f"\nGenerating plots...")
    try:
        generate_plots(all_results, output_dir)
    except ImportError as e:
        print(f"  Skipping plots: {e}")
        print(f"  Install: pip install matplotlib")

    # ══════════════════════════════════════════
    # Step 5: Save results JSON
    # ══════════════════════════════════════════
    # Make JSON-serializable
    save_data = {}
    for key, metrics in all_results.items():
        save_data[key] = {}
        for mk, mv in metrics.items():
            if isinstance(mv, (np.floating, np.integer)):
                save_data[key][mk] = float(mv)
            elif isinstance(mv, np.ndarray):
                save_data[key][mk] = mv.tolist()
            else:
                save_data[key][mk] = mv

    results_path = os.path.join(output_dir, "augmentation_results.json")
    with open(results_path, "w") as f:
        json.dump(save_data, f, indent=2)
    print(f"\nResults saved: {results_path}")
    print("Done!")


if __name__ == "__main__":
    main()
