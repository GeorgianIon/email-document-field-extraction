"""
final_comparison.py
───────────────────
Final comparison table for all 3 paradigms, clean + augmented.

Reads:
  - augmented_results/augmentation_results.json  (P1 — local)
  - vlm_augmented_results.json                   (P2 — from Colab)
  - donut_results.json                           (P3 — from Colab/Kaggle)

Usage:
    python final_comparison.py [--data_dir .]
"""

import json
import os
import argparse


def fmt(val):
    if val is None:
        return "—"
    return f"{val * 100:.2f}%"


def load_all(data_dir):
    """Load results from all sources."""

    # ── P1: Pipeline (local) ──
    p1_path = os.path.join(data_dir, "augmented_results", "augmentation_results.json")
    if os.path.exists(p1_path):
        with open(p1_path) as f:
            p1 = json.load(f)
        print(f"[OK] P1: {p1_path}")
    else:
        print(f"[WARN] {p1_path} not found. Run evaluate_augmented.py first.")
        p1 = {}

    # ── P2: VLM (from Colab) ──
    p2 = {}
    for fname in ["vlm_augmented_results.json", "paradigm_comparison_results.json"]:
        p2_path = os.path.join(data_dir, fname)
        if os.path.exists(p2_path):
            with open(p2_path) as f:
                p2 = json.load(f)
            print(f"[OK] P2: {p2_path}")
            break
    if not p2:
        print(f"[INFO] VLM results not found — P2 pending")

    # ── P3: Donut (from Colab/Kaggle) ──
    p3 = {}
    p3_path = os.path.join(data_dir, "donut_results.json")
    if os.path.exists(p3_path):
        with open(p3_path) as f:
            p3 = json.load(f).get("paradigm_3_donut", {})
        print(f"[OK] P3: {p3_path}")
    else:
        print(f"[INFO] {p3_path} not found — P3 pending")

    return p1, p2, p3


def extract_p2_metrics(p2):
    """Extract clean and augmented metrics from VLM JSON, including mismatch."""
    clean = p2.get("vlm_clean", {})
    aug = p2.get("vlm_augmented_medium", {})

    def _extract(d):
        return {
            "intent": d.get("intent"),
            "email": d.get("email"),
            "doc": d.get("doc"),
            "mismatch_f1": d.get("mismatch_f1"),
            "mismatch_precision": d.get("mismatch_precision"),
            "mismatch_recall": d.get("mismatch_recall"),
        }

    return {
        "clean": _extract(clean),
        "text": _extract(aug.get("text", {})),
        "image": _extract(aug.get("image", {})),
        "mixed": _extract(aug.get("mixed", {})),
    }


def print_tables(p1, p2, p3):
    w = 90

    p2m = extract_p2_metrics(p2) if p2 else {}

    # Table 1: Clean data
    p1c = p1.get("clean", {})
    p2c = p2m.get("clean", {})

    print(f"\n{'=' * w}")
    print("TABLE 1: PERFORMANCE ON CLEAN DATA")
    print(f"{'=' * w}")
    print(f"{'Metric':<30s} {'P1 Pipeline':>15s} {'P2 VLM':>15s} {'P3 Donut':>15s}")
    print(f"{'-' * w}")
    print(f"{'Intent F1 / Accuracy':<30s} "
          f"{fmt(p1c.get('intent_f1_macro')):>15s} "
          f"{fmt(p2c.get('intent')):>15s} "
          f"{'N/A':>15s}")
    print(f"{'Email Field Extraction':<30s} "
          f"{fmt(p1c.get('email_field_accuracy')):>15s} "
          f"{fmt(p2c.get('email')):>15s} "
          f"{'N/A':>15s}")
    print(f"{'Document Field Extraction':<30s} "
          f"{fmt(p1c.get('doc_field_accuracy')):>15s} "
          f"{fmt(p2c.get('doc')):>15s} "
          f"{fmt(p3.get('clean_accuracy')):>15s}")
    print(f"{'Mismatch Detection F1':<30s} "
          f"{fmt(p1c.get('mismatch_f1')):>15s} "
          f"{fmt(p2c.get('mismatch_f1')):>15s} "
          f"{'N/A':>15s}")

    # Table 2: P1 augmented
    print(f"\n{'=' * w}")
    print("TABLE 2: PIPELINE (P1) — CLEAN vs AUGMENTED")
    print("Train: clean + augmented (medium) | Test: augmented (medium)")
    print(f"{'=' * w}")
    print(f"{'Scenario':<22s} {'Intent F1':>12s} {'Email Ext':>12s} "
          f"{'Doc Ext':>12s} {'Mismatch F1':>12s}")
    print(f"{'-' * w}")

    for key, label in [("clean", "Clean (baseline)"),
                        ("text", "Aug. text"),
                        ("image", "Aug. image"),
                        ("mixed", "Aug. mixed")]:
        m = p1.get(key, {})
        print(f"{label:<22s} "
              f"{fmt(m.get('intent_f1_macro')):>12s} "
              f"{fmt(m.get('email_field_accuracy')):>12s} "
              f"{fmt(m.get('doc_field_accuracy')):>12s} "
              f"{fmt(m.get('mismatch_f1')):>12s}")

    # Table 3: P2 VLM augmented (now with mismatch)
    if p2m:
        print(f"\n{'=' * w}")
        print("TABLE 3: VLM (P2) — CLEAN vs AUGMENTED (no re-training)")
        print(f"{'=' * w}")
        print(f"{'Scenario':<22s} {'Intent':>12s} {'Email Ext':>12s} "
              f"{'Doc Ext':>12s} {'Mismatch F1':>12s}")
        print(f"{'-' * w}")

        for key, label in [("clean", "Clean (baseline)"),
                            ("text", "Aug. text"),
                            ("image", "Aug. image"),
                            ("mixed", "Aug. mixed")]:
            m = p2m.get(key, {})
            print(f"{label:<22s} "
                  f"{fmt(m.get('intent')):>12s} "
                  f"{fmt(m.get('email')):>12s} "
                  f"{fmt(m.get('doc')):>12s} "
                  f"{fmt(m.get('mismatch_f1')):>12s}")

    # Table 4: P3 Donut augmented
    if p3:
        print(f"\n{'=' * w}")
        print("TABLE 4: DONUT (P3) — CLEAN vs AUGMENTED")
        print("Train: clean + augmented images | Test: augmented images")
        print(f"{'=' * w}")
        print(f"{'Data':<30s} {'Doc Field Accuracy':>20s}")
        print(f"{'-' * w}")
        print(f"{'Clean':<30s} {fmt(p3.get('clean_accuracy')):>20s}")
        print(f"{'Image augmented':<30s} {fmt(p3.get('augmented_accuracy')):>20s}")

        clean_pf = p3.get("clean_per_field", {})
        aug_pf = p3.get("augmented_per_field", {})
        if clean_pf and aug_pf:
            print(f"\n{'Field':<20s} {'Clean':>15s} {'Augmented':>15s}")
            print(f"{'-' * 55}")
            for f in ["amount", "currency", "doc_number", "date"]:
                cs = clean_pf.get(f, {})
                aus = aug_pf.get(f, {})
                ca = cs.get("correct", 0) / cs.get("total", 1) if cs.get("total", 0) > 0 else 0
                aa = aus.get("correct", 0) / aus.get("total", 1) if aus.get("total", 0) > 0 else 0
                print(f"{f:<20s} {fmt(ca):>15s} {fmt(aa):>15s}")

    # Table 5: Mismatch comparison P1 vs P2
    print(f"\n{'=' * w}")
    print("TABLE 5: MISMATCH DETECTION — P1 vs P2 ACROSS SCENARIOS")
    print(f"{'=' * w}")
    print(f"{'Scenario':<18s} {'P1 Prec':>10s} {'P1 Rec':>10s} {'P1 F1':>9s} "
          f"{'P2 Prec':>10s} {'P2 Rec':>10s} {'P2 F1':>9s}")
    print(f"{'-' * w}")

    for key, label in [("clean", "Clean"),
                        ("text", "Aug. text"),
                        ("image", "Aug. image"),
                        ("mixed", "Aug. mixed")]:
        p1m = p1.get(key, {})
        p2m_s = p2m.get(key, {})
        print(f"{label:<18s} "
              f"{fmt(p1m.get('mismatch_precision')):>10s} "
              f"{fmt(p1m.get('mismatch_recall')):>10s} "
              f"{fmt(p1m.get('mismatch_f1')):>9s} "
              f"{fmt(p2m_s.get('mismatch_precision')):>10s} "
              f"{fmt(p2m_s.get('mismatch_recall')):>10s} "
              f"{fmt(p2m_s.get('mismatch_f1')):>9s}")

    # Table 6: Trade-offs
    print(f"\n{'=' * w}")
    print("TABLE 6: TRADE-OFF ANALYSIS")
    print(f"{'=' * w}")
    print(f"{'Criterion':<30s} {'P1 Pipeline':>15s} {'P2 VLM':>15s} {'P3 Donut':>15s}")
    print(f"{'-' * w}")
    print(f"{'Training required':<30s} {'Yes (BERT)':>15s} {'No':>15s} {'Yes':>15s}")
    print(f"{'Separate OCR step':<30s} {'Yes':>15s} {'No':>15s} {'No':>15s}")
    print(f"{'GPU at inference':<30s} {'No':>15s} {'Yes':>15s} {'Yes':>15s}")
    print(f"{'Interpretability':<30s} {'High':>15s} {'Low':>15s} {'Medium':>15s}")
    print(f"{'New field types':<30s} {'New code':>15s} {'New prompt':>15s} {'Re-train':>15s}")
    print(f"{'Speed (per pair)':<30s} {'~0.5s':>15s} {'~5-30s':>15s} {'~1-3s':>15s}")
    print(f"{'Parameters':<30s} {'~66M':>15s} {'~3B':>15s} {'~200M':>15s}")
    print(f"{'Overfitting risk':<30s} {'High':>15s} {'None':>15s} {'Moderate':>15s}")
    print(f"{'=' * w}")


def generate_plots(p1, p2, p3, output_dir):
    try:
        import matplotlib.pyplot as plt
        import numpy as np
    except ImportError:
        print("matplotlib not available — skipping plots")
        return

    p2m = extract_p2_metrics(p2) if p2 else {}
    os.makedirs(output_dir, exist_ok=True)

    # Plot 1: Clean data — all 3 paradigms with mismatch
    fig, ax = plt.subplots(figsize=(11, 5))
    p1c = p1.get("clean", {})
    p2c = p2m.get("clean", {})

    metrics = ["Intent", "Email Ext.", "Doc Ext.", "Mismatch F1"]
    p1_vals = [
        (p1c.get("intent_f1_macro") or 0) * 100,
        (p1c.get("email_field_accuracy") or 0) * 100,
        (p1c.get("doc_field_accuracy") or 0) * 100,
        (p1c.get("mismatch_f1") or 0) * 100,
    ]
    p2_vals = [
        (p2c.get("intent") or 0) * 100,
        (p2c.get("email") or 0) * 100,
        (p2c.get("doc") or 0) * 100,
        (p2c.get("mismatch_f1") or 0) * 100,
    ]
    p3_vals = [0, 0, (p3.get("clean_accuracy") or 0) * 100, 0]

    x = np.arange(len(metrics))
    width = 0.25

    bars1 = ax.bar(x - width, p1_vals, width, label="P1: Pipeline", color="#2b6cb0")
    bars2 = ax.bar(x, p2_vals, width, label="P2: VLM Zero-Shot", color="#38a169")
    bars3 = ax.bar(x + width, p3_vals, width, label="P3: Donut", color="#e53e3e")

    for bars in [bars1, bars2, bars3]:
        for bar in bars:
            h = bar.get_height()
            if h > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, h + 0.5,
                        f"{h:.1f}%", ha="center", fontsize=8)

    ax.set_xticks(x)
    ax.set_xticklabels(metrics)
    ax.set_ylabel("Score (%)")
    ax.set_title("Clean Data: Three-Paradigm Comparison", fontweight="bold")
    ax.legend()
    ax.set_ylim(0, 115)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "comparison_clean_3paradigms.png")
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # Plot 2: P1 clean vs augmented
    fig, ax = plt.subplots(figsize=(12, 5))
    scenarios = ["clean", "text", "image", "mixed"]
    scenario_labels = ["Clean", "Text aug.", "Image aug.", "Mixed aug."]
    metric_keys = ["intent_f1_macro", "email_field_accuracy",
                   "doc_field_accuracy", "mismatch_f1"]
    metric_labels = ["Intent F1", "Email Ext.", "Doc Ext.", "Mismatch F1"]
    colors = ["#2b6cb0", "#38a169", "#e53e3e", "#d69e2e"]

    x = np.arange(len(metric_labels))
    width = 0.2

    for i, (sc, sc_label) in enumerate(zip(scenarios, scenario_labels)):
        vals = []
        for mk in metric_keys:
            v = p1.get(sc, {}).get(mk)
            vals.append(v * 100 if v is not None else 0)
        bars = ax.bar(x + i * width, vals, width, label=sc_label,
                      color=colors[i], alpha=0.85)
        for bar, v in zip(bars, vals):
            if v > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, v + 0.3,
                        f"{v:.1f}", ha="center", fontsize=7)

    ax.set_xticks(x + width * 1.5)
    ax.set_xticklabels(metric_labels)
    ax.set_ylabel("Score (%)")
    ax.set_title("Pipeline (P1): Clean vs Augmented Performance", fontweight="bold")
    ax.legend()
    ax.set_ylim(0, 115)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "p1_clean_vs_augmented.png")
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # Plot 3: VLM clean vs augmented (4 metrics now)
    if p2m and p2m.get("clean"):
        fig, axes = plt.subplots(1, 4, figsize=(20, 4.5))
        vlm_metrics = [("intent", "Intent Accuracy"),
                       ("email", "Email Field Acc."),
                       ("doc", "Doc Field Acc."),
                       ("mismatch_f1", "Mismatch F1")]

        for idx, (mk, title) in enumerate(vlm_metrics):
            ax = axes[idx]
            labels = ["Clean", "Text\naug.", "Image\naug.", "Mixed\naug."]
            vals = [(p2m["clean"].get(mk) or 0) * 100]
            for sc in ["text", "image", "mixed"]:
                vals.append((p2m.get(sc, {}).get(mk) or 0) * 100)
            bar_colors = ["#2b6cb0"] + ["#e53e3e"] * 3
            bars = ax.bar(range(len(vals)), vals, color=bar_colors, alpha=0.85)
            for bar, v in zip(bars, vals):
                if v > 0:
                    ax.text(bar.get_x() + bar.get_width() / 2, v + 0.5,
                            f"{v:.1f}%", ha="center", fontsize=8)
            ax.set_xticks(range(len(labels)))
            ax.set_xticklabels(labels, fontsize=9)
            ax.set_ylabel("Score (%)")
            ax.set_title(title, fontweight="bold")
            ax.set_ylim(0, 110)
            ax.grid(axis="y", alpha=0.3)

        plt.suptitle("VLM (P2): Clean vs Augmented (no re-training)",
                     fontsize=13, fontweight="bold")
        plt.tight_layout()
        path = os.path.join(output_dir, "p2_vlm_clean_vs_augmented.png")
        plt.savefig(path, dpi=200, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {path}")

    # Plot 4: Donut clean vs augmented
    if p3 and p3.get("clean_accuracy"):
        fig, ax = plt.subplots(figsize=(8, 5))
        clean_pf = p3.get("clean_per_field", {})
        aug_pf = p3.get("augmented_per_field", {})
        fields = ["amount", "currency", "doc_number", "date"]
        field_labels = ["Overall"] + fields

        clean_vals = [p3["clean_accuracy"] * 100]
        aug_vals = [p3.get("augmented_accuracy", 0) * 100]

        for f in fields:
            cs = clean_pf.get(f, {})
            aus = aug_pf.get(f, {})
            clean_vals.append(
                cs["correct"] / cs["total"] * 100 if cs.get("total", 0) > 0 else 0)
            aug_vals.append(
                aus["correct"] / aus["total"] * 100 if aus.get("total", 0) > 0 else 0)

        x = np.arange(len(field_labels))
        bars1 = ax.bar(x - 0.18, clean_vals, 0.35, label="Clean", color="#2b6cb0")
        bars2 = ax.bar(x + 0.18, aug_vals, 0.35, label="Image augmented", color="#e53e3e")

        for bar, v in zip(list(bars1) + list(bars2), clean_vals + aug_vals):
            if v > 0:
                ax.text(bar.get_x() + bar.get_width() / 2, v + 0.5,
                        f"{v:.1f}%", ha="center", fontsize=8)

        ax.set_xticks(x)
        ax.set_xticklabels(field_labels)
        ax.set_ylabel("Accuracy (%)")
        ax.set_title("Donut (P3): Clean vs Augmented", fontweight="bold")
        ax.legend()
        ax.set_ylim(0, 115)
        ax.grid(axis="y", alpha=0.3)
        plt.tight_layout()
        path = os.path.join(output_dir, "p3_donut_clean_vs_augmented.png")
        plt.savefig(path, dpi=200, bbox_inches="tight")
        plt.close()
        print(f"  Saved: {path}")

    # Plot 5: Document extraction comparison
    fig, ax = plt.subplots(figsize=(8, 5))
    paradigms = ["P1: Pipeline\n(OCR+Regex)", "P2: VLM\n(Zero-Shot)", "P3: Donut\n(Fine-Tuned)"]
    clean_doc = [
        (p1.get("clean", {}).get("doc_field_accuracy") or 0) * 100,
        (p2m.get("clean", {}).get("doc") or 0) * 100,
        (p3.get("clean_accuracy") or 0) * 100,
    ]
    aug_doc = [
        (p1.get("image", {}).get("doc_field_accuracy") or 0) * 100,
        (p2m.get("image", {}).get("doc") or 0) * 100,
        (p3.get("augmented_accuracy") or 0) * 100,
    ]

    x = np.arange(len(paradigms))
    bars1 = ax.bar(x - 0.18, clean_doc, 0.35, label="Clean", color="#2b6cb0")
    bars2 = ax.bar(x + 0.18, aug_doc, 0.35, label="Image augmented", color="#e53e3e")

    for bar, v in zip(list(bars1) + list(bars2), clean_doc + aug_doc):
        if v > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.5,
                    f"{v:.1f}%", ha="center", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(paradigms, fontsize=10)
    ax.set_ylabel("Accuracy (%)")
    ax.set_title("Document Field Extraction: All Paradigms\nClean vs Image Augmented",
                 fontweight="bold")
    ax.legend()
    ax.set_ylim(0, 115)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "doc_extraction_all_paradigms.png")
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")

    # Plot 6: Mismatch F1 — P1 vs P2 across scenarios (NEW)
    fig, ax = plt.subplots(figsize=(10, 5))
    scenarios_lbl = ["Clean", "Text aug.", "Image aug.", "Mixed aug."]
    scenarios_keys = ["clean", "text", "image", "mixed"]

    p1_mm = []
    p2_mm = []
    for k in scenarios_keys:
        p1_mm.append((p1.get(k, {}).get("mismatch_f1") or 0) * 100)
        p2_mm.append((p2m.get(k, {}).get("mismatch_f1") or 0) * 100)

    x = np.arange(len(scenarios_lbl))
    bars1 = ax.bar(x - 0.18, p1_mm, 0.35, label="P1: Pipeline", color="#2b6cb0")
    bars2 = ax.bar(x + 0.18, p2_mm, 0.35, label="P2: VLM", color="#38a169")

    for bar, v in zip(list(bars1) + list(bars2), p1_mm + p2_mm):
        if v > 0:
            ax.text(bar.get_x() + bar.get_width() / 2, v + 0.5,
                    f"{v:.1f}%", ha="center", fontsize=9)

    ax.set_xticks(x)
    ax.set_xticklabels(scenarios_lbl)
    ax.set_ylabel("Mismatch F1 (%)")
    ax.set_title("Mismatch Detection F1: P1 vs P2 Across Scenarios",
                 fontweight="bold")
    ax.legend()
    ax.set_ylim(0, 110)
    ax.grid(axis="y", alpha=0.3)
    plt.tight_layout()
    path = os.path.join(output_dir, "mismatch_f1_comparison.png")
    plt.savefig(path, dpi=200, bbox_inches="tight")
    plt.close()
    print(f"  Saved: {path}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--data_dir", default=".")
    args = parser.parse_args()

    data_dir = args.data_dir
    output_dir = os.path.join(data_dir, "augmented_results")

    p1, p2, p3 = load_all(data_dir)
    print_tables(p1, p2, p3)

    print(f"\nGenerating plots...")
    generate_plots(p1, p2, p3, output_dir)
    print("\nDone!")


if __name__ == "__main__":
    main()
