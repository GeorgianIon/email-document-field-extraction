"""
split_dataset.py
────────────────
Splits the dataset into train/val/test (70/15/15) with stratification
on intent class AND mismatch presence, ensuring no data leakage.

Produces:
  - splits.json  : mapping of split name -> list of email_ids
  - train.csv, val.csv, test.csv : filtered versions of emails.csv + pairs.csv merged

Usage:
    python split_dataset.py
"""

import csv
import json
import os
import random
from collections import defaultdict

from config import SEED

random.seed(SEED)

TRAIN_RATIO = 0.70
VAL_RATIO   = 0.15
TEST_RATIO  = 0.15


def load_data(base_dir):
    """Load emails and pairs, merge them by email_id."""
    with open(os.path.join(base_dir, "emails.csv"), "r", encoding="utf-8-sig") as f:
        emails = {row["email_id"]: row for row in csv.DictReader(f)}

    with open(os.path.join(base_dir, "pairs.csv"), "r", encoding="utf-8-sig") as f:
        pairs = {row["email_id"]: row for row in csv.DictReader(f)}

    # Merge into single records
    records = []
    for eid, email in emails.items():
        pair = pairs.get(eid, {})
        merged = {**email, **pair}
        records.append(merged)

    return records


def stratified_split(records):
    """
    Split records into train/val/test, stratified by:
      - intent class (5 classes)
      - has_attachment (binary)
      - is_consistent (binary, only for those with attachments)

    This creates ~20 strata, ensuring each split has representative
    samples from all combinations.
    """
    # Build strata
    strata = defaultdict(list)
    for rec in records:
        intent = rec["intent"]
        has_attach = "yes" if rec.get("attachment_path", "") else "no"
        is_consist = rec.get("is_consistent", "True")

        # Stratification key
        if has_attach == "yes":
            key = f"{intent}__attach__{is_consist}"
        else:
            key = f"{intent}__no_attach"

        strata[key].append(rec)

    train, val, test = [], [], []

    for key, recs in sorted(strata.items()):
        random.shuffle(recs)
        n = len(recs)
        n_train = max(1, int(n * TRAIN_RATIO))
        n_val = max(1, int(n * VAL_RATIO)) if n > 2 else 0
        n_test = n - n_train - n_val

        # Ensure at least 1 in test if we have enough
        if n_test <= 0 and n > 2:
            n_train -= 1
            n_test = 1

        train.extend(recs[:n_train])
        val.extend(recs[n_train:n_train + n_val])
        test.extend(recs[n_train + n_val:])

    # Shuffle each split
    random.shuffle(train)
    random.shuffle(val)
    random.shuffle(test)

    return train, val, test


def write_split_csv(records, filepath):
    """Write a merged split to CSV."""
    if not records:
        return

    fieldnames = [
        "email_id", "intent", "subject", "body",
        "sender_name", "sender_email", "sender_company",
        "gt_amount", "gt_currency", "gt_doc_number", "gt_date",
        "mentions_amount", "mentions_currency",
        "mentions_doc_number", "mentions_date",
        "pair_id", "attachment_path", "attachment_format", "doc_type",
        "doc_amount", "doc_currency", "doc_doc_number", "doc_date",
        "is_consistent", "mismatch_field", "mismatch_type",
    ]

    with open(filepath, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for rec in records:
            writer.writerow(rec)


def main(base_dir=None):
    if base_dir is None:
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    base_dir = os.path.abspath(base_dir)
    records = load_data(base_dir)

    print(f"Total records: {len(records)}")

    train, val, test = stratified_split(records)

    print(f"\nSplit sizes:")
    print(f"  Train: {len(train)} ({len(train)/len(records)*100:.1f}%)")
    print(f"  Val:   {len(val)} ({len(val)/len(records)*100:.1f}%)")
    print(f"  Test:  {len(test)} ({len(test)/len(records)*100:.1f}%)")

    # Verify no leakage
    train_ids = {r["email_id"] for r in train}
    val_ids = {r["email_id"] for r in val}
    test_ids = {r["email_id"] for r in test}
    assert len(train_ids & val_ids) == 0, "Leakage between train and val!"
    assert len(train_ids & test_ids) == 0, "Leakage between train and test!"
    assert len(val_ids & test_ids) == 0, "Leakage between val and test!"
    assert len(train_ids) + len(val_ids) + len(test_ids) == len(records)
    print("\n✓ No data leakage detected")

    # Print stratification stats
    from collections import Counter
    print("\nIntent distribution per split:")
    for name, split in [("Train", train), ("Val", val), ("Test", test)]:
        counts = Counter(r["intent"] for r in split)
        parts = [f"{k}={v}" for k, v in sorted(counts.items())]
        print(f"  {name:6s}: {', '.join(parts)}")

    # Attachment distribution
    print("\nAttachment distribution per split:")
    for name, split in [("Train", train), ("Val", val), ("Test", test)]:
        with_att = sum(1 for r in split if r.get("attachment_path", ""))
        without = len(split) - with_att
        print(f"  {name:6s}: with={with_att}, without={without}")

    # Mismatch distribution
    print("\nMismatch distribution per split:")
    for name, split in [("Train", train), ("Val", val), ("Test", test)]:
        mm = sum(1 for r in split if r.get("is_consistent") == "False")
        ok = sum(1 for r in split
                 if r.get("is_consistent") == "True" and r.get("attachment_path", ""))
        print(f"  {name:6s}: consistent={ok}, mismatched={mm}")

    # Save splits
    write_split_csv(train, os.path.join(base_dir, "train.csv"))
    write_split_csv(val, os.path.join(base_dir, "val.csv"))
    write_split_csv(test, os.path.join(base_dir, "test.csv"))

    # Save split mapping (for reproducibility)
    splits = {
        "train": [r["email_id"] for r in train],
        "val":   [r["email_id"] for r in val],
        "test":  [r["email_id"] for r in test],
    }
    with open(os.path.join(base_dir, "splits.json"), "w") as f:
        json.dump(splits, f, indent=2)

    print(f"\n✓ Saved: train.csv ({len(train)}), val.csv ({len(val)}), test.csv ({len(test)})")
    print(f"✓ Saved: splits.json")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Stratified train/val/test split")
    parser.add_argument(
        "--data_dir",
        default=None,
        help="Folder holding emails.csv + pairs.csv; splits written here (default: ../data)",
    )
    args = parser.parse_args()
    main(args.data_dir)
