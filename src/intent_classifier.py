"""

== INTENT CLASSIFIER ==

Pipeline:
  1. Load train/val/test CSVs
  2. Tokenize email text (subject + body)
  3. Fine-tune bert-base-uncased (or distilbert for speed)
  4. Evaluate on val and test
  5. Save model + classification report

Usage:
    python intent_classifier.py [--model distilbert] [--epochs 10] [--batch_size 16]

Requirements:
    pip install transformers datasets scikit-learn torch accelerate
"""

import argparse
import csv
import json
import os
import warnings
warnings.filterwarnings("ignore")

import numpy as np
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    accuracy_score,
    f1_score,
)


# Configuration


INTENT_LABELS = [
    "invoice_submission",
    "other",
    "price_increase",
    "price_validity_confirmation",
    "quote_offer",
]

LABEL2ID = {label: i for i, label in enumerate(INTENT_LABELS)}
ID2LABEL = {i: label for label, i in LABEL2ID.items()}

MODEL_OPTIONS = {
    "bert":       "bert-base-uncased",
    "distilbert": "distilbert-base-uncased",
    "roberta":    "roberta-base",
}

# Data loading


def load_split(filepath):
    """Load a split CSV and return texts + labels."""
    texts = []
    labels = []

    with open(filepath, "r", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Combine subject and body as input text
            # This gives the model both signals
            subject = row.get("subject", "")
            body = row.get("body", "")
            text = f"Subject: {subject}\n\n{body}"

            texts.append(text)
            labels.append(LABEL2ID[row["intent"]])

    return texts, labels



# Training with Hugging Face Trainer


def train_with_transformers(
    train_texts, train_labels,
    val_texts, val_labels,
    model_name="bert-base-uncased",
    epochs=10,
    batch_size=16,
    learning_rate=2e-5,
    output_dir="./intent_model",
):
    """Fine-tune a transformer model for intent classification."""
    from transformers import (
        AutoTokenizer,
        AutoModelForSequenceClassification,
        TrainingArguments,
        Trainer,
    )
    from datasets import Dataset

    print(f"\n{'='*55}")
    print(f"INTENT CLASSIFIER — Fine-tuning")
    print(f"{'='*55}")
    print(f"Model:       {model_name}")
    print(f"Train size:  {len(train_texts)}")
    print(f"Val size:    {len(val_texts)}")
    print(f"Epochs:      {epochs}")
    print(f"Batch size:  {batch_size}")
    print(f"LR:          {learning_rate}")
    print(f"{'='*55}\n")

    # Load tokenizer and model
    tokenizer = AutoTokenizer.from_pretrained(model_name)
    model = AutoModelForSequenceClassification.from_pretrained(
        model_name,
        num_labels=len(INTENT_LABELS),
        id2label=ID2LABEL,
        label2id=LABEL2ID,
    )

    # Create HF datasets
    train_dataset = Dataset.from_dict({
        "text": train_texts,
        "label": train_labels,
    })
    val_dataset = Dataset.from_dict({
        "text": val_texts,
        "label": val_labels,
    })

    # Tokenize
    def tokenize_fn(examples):
        return tokenizer(
            examples["text"],
            padding="max_length",
            truncation=True,
            max_length=512,
        )

    print("Tokenizing...")
    train_dataset = train_dataset.map(tokenize_fn, batched=True, remove_columns=["text"])
    val_dataset = val_dataset.map(tokenize_fn, batched=True, remove_columns=["text"])

    # Set format for PyTorch
    train_dataset.set_format("torch")
    val_dataset.set_format("torch")

    # Metrics function
    def compute_metrics(eval_pred):
        logits, labels = eval_pred
        predictions = np.argmax(logits, axis=-1)
        acc = accuracy_score(labels, predictions)
        f1_macro = f1_score(labels, predictions, average="macro")
        f1_weighted = f1_score(labels, predictions, average="weighted")
        return {
            "accuracy": acc,
            "f1_macro": f1_macro,
            "f1_weighted": f1_weighted,
        }

    # Training arguments
    training_args = TrainingArguments(
        output_dir=output_dir,
        num_train_epochs=epochs,
        per_device_train_batch_size=batch_size,
        per_device_eval_batch_size=batch_size,
        learning_rate=learning_rate,
        weight_decay=0.01,
        eval_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1_macro",
        greater_is_better=True,
        logging_steps=20,
        save_total_limit=2,
        report_to="none",
        fp16=False,  # Set True if GPU supports it
        seed=42,
    )

    # Trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=val_dataset,
        compute_metrics=compute_metrics,
    )

    # Train
    print("Starting training...")
    train_result = trainer.train()
    print(f"\nTraining complete!")
    print(f"  Training loss: {train_result.training_loss:.4f}")

    # Evaluate on validation
    val_results = trainer.evaluate()
    print(f"\nValidation results:")
    for k, v in val_results.items():
        if isinstance(v, float):
            print(f"  {k}: {v:.4f}")

    # Save model
    trainer.save_model(os.path.join(output_dir, "best_model"))
    tokenizer.save_pretrained(os.path.join(output_dir, "best_model"))
    print(f"\n✓ Model saved to {output_dir}/best_model")

    return trainer, tokenizer


def evaluate_on_test(trainer, tokenizer, test_texts, test_labels, output_dir):
    """Run full evaluation on the test set."""
    from datasets import Dataset

    print(f"\n{'='*55}")
    print(f"TEST SET EVALUATION")
    print(f"{'='*55}")

    test_dataset = Dataset.from_dict({
        "text": test_texts,
        "label": test_labels,
    })

    def tokenize_fn(examples):
        return tokenizer(
            examples["text"],
            padding="max_length",
            truncation=True,
            max_length=512,
        )

    test_dataset = test_dataset.map(tokenize_fn, batched=True, remove_columns=["text"])
    test_dataset.set_format("torch")

    # Predict
    predictions = trainer.predict(test_dataset)
    preds = np.argmax(predictions.predictions, axis=-1)
    true_labels = predictions.label_ids

    # Classification report
    report = classification_report(
        true_labels, preds,
        target_names=INTENT_LABELS,
        digits=4,
    )
    print("\nClassification Report:")
    print(report)

    # Confusion matrix
    cm = confusion_matrix(true_labels, preds)
    print("Confusion Matrix:")
    # Header
    print(f"{'':>35s}", end="")
    for label in INTENT_LABELS:
        print(f"{label[:8]:>10s}", end="")
    print()
    for i, row in enumerate(cm):
        print(f"  {INTENT_LABELS[i]:>33s}", end="")
        for val in row:
            print(f"{val:10d}", end="")
        print()

    # Overall metrics
    acc = accuracy_score(true_labels, preds)
    f1_macro = f1_score(true_labels, preds, average="macro")
    f1_weighted = f1_score(true_labels, preds, average="weighted")

    print(f"\nOverall:")
    print(f"  Accuracy:     {acc:.4f}")
    print(f"  F1 (macro):   {f1_macro:.4f}")
    print(f"  F1 (weighted):{f1_weighted:.4f}")

    # Save results
    results = {
        "accuracy": float(acc),
        "f1_macro": float(f1_macro),
        "f1_weighted": float(f1_weighted),
        "classification_report": report,
        "confusion_matrix": cm.tolist(),
        "predictions": preds.tolist(),
        "true_labels": true_labels.tolist(),
    }
    results_path = os.path.join(output_dir, "test_results.json")
    with open(results_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\n✓ Results saved to {results_path}")

    return results



# Lightweight baseline (TF-IDF + Logistic Regression)


def train_baseline(train_texts, train_labels, val_texts, val_labels,
                   test_texts, test_labels):
    """
    Train a simple TF-IDF + Logistic Regression baseline.
    Useful as a reference point and runs in seconds (no GPU needed).
    """
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.linear_model import LogisticRegression
    from sklearn.pipeline import Pipeline

    print(f"\n{'='*55}")
    print(f"BASELINE — TF-IDF + Logistic Regression")
    print(f"{'='*55}")

    pipeline = Pipeline([
        ("tfidf", TfidfVectorizer(
            max_features=10000,
            ngram_range=(1, 2),
            sublinear_tf=True,
        )),
        ("clf", LogisticRegression(
            max_iter=1000,
            C=1.0,
            class_weight="balanced",
            random_state=42,
        )),
    ])

    # Train
    pipeline.fit(train_texts, train_labels)

    # Evaluate on val
    val_preds = pipeline.predict(val_texts)
    val_acc = accuracy_score(val_labels, val_preds)
    val_f1 = f1_score(val_labels, val_preds, average="macro")
    print(f"\nValidation:  accuracy={val_acc:.4f}  f1_macro={val_f1:.4f}")

    # Evaluate on test
    test_preds = pipeline.predict(test_texts)
    test_acc = accuracy_score(test_labels, test_preds)
    test_f1 = f1_score(test_labels, test_preds, average="macro")

    report = classification_report(
        test_labels, test_preds,
        target_names=INTENT_LABELS,
        digits=4,
    )
    print(f"\nTest Set Results:")
    print(report)
    print(f"Overall:  accuracy={test_acc:.4f}  f1_macro={test_f1:.4f}")

    # Feature importance — top keywords per class
    print("\nTop discriminative features per class:")
    feature_names = pipeline.named_steps["tfidf"].get_feature_names_out()
    coefs = pipeline.named_steps["clf"].coef_

    for i, label in enumerate(INTENT_LABELS):
        top_indices = np.argsort(coefs[i])[-8:][::-1]
        top_features = [feature_names[j] for j in top_indices]
        print(f"  {label:35s}: {', '.join(top_features)}")

    # Save model for demo_pipeline.py
    import pickle
    model_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)), "baseline_model.pkl"
    )
    with open(model_path, "wb") as f:
        pickle.dump(pipeline, f)
    print(f"\n✓ Baseline model saved to {model_path}")

    return {
        "val_accuracy": float(val_acc),
        "val_f1_macro": float(val_f1),
        "test_accuracy": float(test_acc),
        "test_f1_macro": float(test_f1),
        "classification_report": report,
    }



# Main


def main():
    parser = argparse.ArgumentParser(description="Train intent classifier")
    parser.add_argument("--model", default="distilbert",
                        choices=["bert", "distilbert", "roberta"],
                        help="Which transformer to fine-tune")
    parser.add_argument("--epochs", type=int, default=10)
    parser.add_argument("--batch_size", type=int, default=16)
    parser.add_argument("--lr", type=float, default=2e-5)
    parser.add_argument("--baseline_only", action="store_true",
                        help="Only run TF-IDF baseline (no GPU needed)")
    parser.add_argument("--data_dir", default=".",
                        help="Directory containing train.csv, val.csv, test.csv")
    args = parser.parse_args()

    # Load data
    print("Loading data...")
    train_texts, train_labels = load_split(
        os.path.join(args.data_dir, "train.csv"))
    val_texts, val_labels = load_split(
        os.path.join(args.data_dir, "val.csv"))
    test_texts, test_labels = load_split(
        os.path.join(args.data_dir, "test.csv"))

    print(f"  Train: {len(train_texts)} samples")
    print(f"  Val:   {len(val_texts)} samples")
    print(f"  Test:  {len(test_texts)} samples")

    # Always run baseline first (fast, no GPU)
    baseline_results = train_baseline(
        train_texts, train_labels,
        val_texts, val_labels,
        test_texts, test_labels,
    )

    if args.baseline_only:
        print("\n✓ Baseline only mode — done.")
        return

    # Fine-tune transformer
    model_name = MODEL_OPTIONS[args.model]
    output_dir = os.path.join(args.data_dir, f"intent_model_{args.model}")
    os.makedirs(output_dir, exist_ok=True)

    trainer, tokenizer = train_with_transformers(
        train_texts, train_labels,
        val_texts, val_labels,
        model_name=model_name,
        epochs=args.epochs,
        batch_size=args.batch_size,
        learning_rate=args.lr,
        output_dir=output_dir,
    )

    # Evaluate on test
    test_results = evaluate_on_test(
        trainer, tokenizer,
        test_texts, test_labels,
        output_dir,
    )

    # Comparison summary
    print(f"\n{'='*55}")
    print(f"COMPARISON SUMMARY")
    print(f"{'='*55}")
    print(f"{'Method':<30s} {'Accuracy':>10s} {'F1 (macro)':>12s}")
    print(f"{'-'*55}")
    print(f"{'TF-IDF + LogReg':<30s} "
          f"{baseline_results['test_accuracy']:>10.4f} "
          f"{baseline_results['test_f1_macro']:>12.4f}")
    print(f"{args.model.upper() + ' fine-tuned':<30s} "
          f"{test_results['accuracy']:>10.4f} "
          f"{test_results['f1_macro']:>12.4f}")
    print(f"{'='*55}")


if __name__ == "__main__":
    main()
