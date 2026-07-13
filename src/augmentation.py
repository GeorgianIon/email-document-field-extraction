"""
augmentation.py
───────────────
Data augmentation pipeline for robustness testing.

Three scenarios:
  1. Text Augmentation  — noisy/corrupted email text
  2. Image Augmentation — degraded document images
  3. Mixed Augmentation — both text + image corrupted simultaneously

Each scenario has 3 severity levels: light, medium, heavy.
This allows plotting degradation curves.

Usage:
    python augmentation.py --scenario text --severity medium --split test
    python augmentation.py --scenario image --severity heavy --split test
    python augmentation.py --scenario mixed --severity light --split test
    python augmentation.py --all  (runs all 9 combinations)

Requirements:
    pip install nlpaug opencv-python-headless albumentations Pillow numpy
"""

import argparse
import csv
import json
import os
import random
import re
import shutil
import sys
import numpy as np
from copy import deepcopy

random.seed(42)
np.random.seed(42)

# ─────────────────────────────────────────────
# SCENARIO 1: Text Augmentation
# ─────────────────────────────────────────────

class TextAugmenter:
    """
    Applies controlled noise to email text to simulate real-world conditions:
    - Typos (character substitution, insertion, deletion)
    - Word substitution with synonyms
    - Random word deletion
    - Case errors
    - Punctuation noise
    """

    # Common typo substitutions (nearby keys on QWERTY)
    KEYBOARD_NEIGHBORS = {
        'a': 'sqwz', 'b': 'vghn', 'c': 'xdfv', 'd': 'erfcxs',
        'e': 'wrds', 'f': 'rtgvcd', 'g': 'tyhbvf', 'h': 'yujnbg',
        'i': 'ujko', 'j': 'uikhmn', 'k': 'ijolm', 'l': 'kop',
        'm': 'njk', 'n': 'bhjm', 'o': 'iklp', 'p': 'ol',
        'q': 'wa', 'r': 'edft', 's': 'awedxz', 't': 'rfgy',
        'u': 'yhji', 'v': 'cfgb', 'w': 'qase', 'x': 'zsdc',
        'y': 'tghu', 'z': 'asx',
    }

    # Severity configs: (typo_rate, word_delete_rate, case_error_rate, punct_noise_rate)
    SEVERITY = {
        "light":  (0.02, 0.03, 0.02, 0.02),
        "medium": (0.05, 0.08, 0.05, 0.05),
        "heavy":  (0.10, 0.15, 0.10, 0.10),
    }

    def __init__(self, severity="medium"):
        self.typo_rate, self.word_del_rate, self.case_rate, self.punct_rate = \
            self.SEVERITY[severity]
        self.severity = severity

    def add_typos(self, text):
        """Introduce keyboard-based typos at character level."""
        chars = list(text)
        for i in range(len(chars)):
            if random.random() < self.typo_rate and chars[i].lower() in self.KEYBOARD_NEIGHBORS:
                action = random.choice(["substitute", "insert", "delete", "swap"])
                c = chars[i].lower()
                if action == "substitute":
                    replacement = random.choice(self.KEYBOARD_NEIGHBORS[c])
                    chars[i] = replacement if chars[i].islower() else replacement.upper()
                elif action == "insert":
                    extra = random.choice(self.KEYBOARD_NEIGHBORS[c])
                    chars[i] = chars[i] + extra
                elif action == "delete" and len(chars) > 10:
                    chars[i] = ""
                elif action == "swap" and i < len(chars) - 1:
                    chars[i], chars[i + 1] = chars[i + 1], chars[i]
        return "".join(chars)

    def delete_words(self, text):
        """Randomly delete words (simulating incomplete messages)."""
        words = text.split()
        if len(words) < 5:
            return text
        result = [
            w for w in words
            if ("\x01" in w) or (random.random() > self.word_del_rate)
        ]
        return " ".join(result) if result else text

    def case_errors(self, text):
        """Introduce random case changes."""
        chars = list(text)
        for i in range(len(chars)):
            if random.random() < self.case_rate and chars[i].isalpha():
                chars[i] = chars[i].swapcase()
            # Sometimes remove capitalization after period
            if random.random() < self.case_rate * 2 and i > 1 and chars[i - 2] == '.':
                chars[i] = chars[i].lower()
        return "".join(chars)

    def punctuation_noise(self, text):
        """Add/remove/change punctuation."""
        result = []
        for char in text:
            if char in '.,;:' and random.random() < self.punct_rate:
                action = random.choice(["remove", "double", "change"])
                if action == "remove":
                    continue
                elif action == "double":
                    result.append(char)
                    result.append(char)
                    continue
                elif action == "change":
                    result.append(random.choice('.,;:'))
                    continue
            result.append(char)
        return "".join(result)

    def number_noise(self, text):
        """Slightly modify numbers (simulating OCR or copy-paste errors)."""
        def corrupt_number(match):
            num_str = match.group()
            if random.random() < self.typo_rate * 2:
                # Swap two adjacent digits
                chars = list(num_str)
                if len(chars) >= 2:
                    i = random.randint(0, len(chars) - 2)
                    if chars[i].isdigit() and chars[i + 1].isdigit():
                        chars[i], chars[i + 1] = chars[i + 1], chars[i]
                return "".join(chars)
            return num_str
        return re.sub(r'\d[\d,.]+\d', corrupt_number, text)

    # luni în engleză, pentru recunoașterea datelor scrise textual
    _MONTHS = {
        "01": ["January", "Jan"], "02": ["February", "Feb"],
        "03": ["March", "Mar"], "04": ["April", "Apr"],
        "05": ["May"], "06": ["June", "Jun"],
        "07": ["July", "Jul"], "08": ["August", "Aug"],
        "09": ["September", "Sep", "Sept"], "10": ["October", "Oct"],
        "11": ["November", "Nov"], "12": ["December", "Dec"],
    }

    def _date_surface_forms(self, iso_date, text):
        """
        Pentru o dată în format ISO (AAAA-LL-ZZ), caută în text toate
        variantele de scriere (numerice și textuale) și le întoarce pe cele
        prezente, ca să poată fi protejate înainte de augmentare.
        """
        m = re.match(r"(\d{4})-(\d{2})-(\d{2})$", str(iso_date))
        if not m:
            return []
        y, mo, d = m.group(1), m.group(2), m.group(3)
        di, mi = int(d), int(mo)
        candidates = [
            f"{y}-{mo}-{d}",
            f"{d}.{mo}.{y}", f"{d}/{mo}/{y}",
            f"{mo}/{d}/{y}", f"{mo}.{d}.{y}",
            f"{di}.{mi}.{y}", f"{di}/{mi}/{y}",
        ]
        for name in self._MONTHS.get(mo, []):
            # zi fără zero în față (2) și cu zero (02), ambele uzuale
            for day in {str(di), d}:
                candidates += [
                    f"{name} {day}, {y}", f"{name} {day} {y}",
                    f"{day} {name} {y}", f"{day} {name}, {y}",
                ]
        # întoarce doar variantele care chiar apar în text
        return [c for c in candidates if c in text]

    def _candidate_surface_forms(self, val, text):
        """
        Given a ground-truth value, return the list of substrings that
        actually occur in `text` and should be protected. Handles the common
        cases where the stored value is normalized but the text shows a
        formatted variant: amounts with thousands separators, and dates in
        any of the usual numeric or textual formats.
        """
        forms = []
        # 1. Exact match first.
        if val in text:
            forms.append(val)
            return forms
        # 2. Currency: GT is an ISO code (EUR) but the text may use the symbol.
        currency_symbols = {
            "USD": ["$", "US$"], "EUR": ["€"], "GBP": ["£"],
            "RON": ["lei", "LEI"], "CHF": ["CHF"],
        }
        if str(val).upper() in currency_symbols:
            present = [s for s in currency_symbols[str(val).upper()] if s in text]
            if present:
                return present
        # 3. Dates: the GT is ISO (YYYY-MM-DD) but the text may use any
        #    common numeric or textual format.
        date_forms = self._date_surface_forms(val, text)
        if date_forms:
            return date_forms
        # 4. Numeric values (amounts): the GT keeps only digits and a decimal
        #    point, while the text may use thousands separators.
        digits = re.sub(r'[^0-9]', '', val)
        if digits and len(digits) >= 3:
            sep = r'[\s.,]*'
            pattern = sep.join(re.escape(ch) for ch in digits)
            for m in re.finditer(pattern, text):
                surface = m.group()
                if re.sub(r'[^0-9]', '', surface) == digits and surface not in forms:
                    forms.append(surface)
        return forms

    def _mask_protected(self, text, protected_values):
        """
        Replace protected values (amounts, currencies, doc numbers, dates)
        with placeholder tokens that survive augmentation untouched.
        Returns the masked text and a token->value mapping.

        The matching is tolerant to formatting differences between the stored
        ground-truth value and the way it appears in the text (for example,
        thousands separators in amounts), so that values are reliably
        protected even when their surface form differs from the canonical one.
        Placeholders use null characters, which no augmentation step alters.
        """
        mapping = {}
        if not protected_values:
            return text, mapping
        token_idx = 0
        # Collect all surface forms to protect, longest first, so that a
        # longer value is masked before a shorter one contained within it.
        surfaces = []
        for val in {str(v) for v in protected_values if v}:
            for surface in self._candidate_surface_forms(val, text):
                surfaces.append(surface)
        for surface in sorted(set(surfaces), key=len, reverse=True):
            if surface and surface in text:
                # Token built only from control characters: not letters
                # (immune to typos/case), not digits (immune to number noise),
                # not punctuation (immune to punctuation noise).
                token = "\x01" + ("\x02" * (token_idx + 1)) + "\x01"
                token_idx += 1
                text = text.replace(surface, token)
                mapping[token] = surface
        return text, mapping

    def _unmask_protected(self, text, mapping):
        """Restore protected values from their placeholder tokens."""
        for token, val in mapping.items():
            text = text.replace(token, val)
        return text

    def augment(self, text, protected_values=None):
        """
        Apply all augmentations to text.

        If `protected_values` is provided (e.g. amounts, currencies,
        document numbers and dates that also appear in the ground truth),
        those exact substrings are masked before augmentation and restored
        afterwards, so that the noise affects only the surrounding text and
        never corrupts values that the evaluation compares against.
        """
        text, mapping = self._mask_protected(text, protected_values)

        text = self.add_typos(text)
        text = self.delete_words(text)
        text = self.case_errors(text)
        text = self.punctuation_noise(text)
        # Only corrupt numbers at heavy severity
        if self.severity == "heavy":
            text = self.number_noise(text)

        text = self._unmask_protected(text, mapping)
        return text


# ─────────────────────────────────────────────
# SCENARIO 2: Image Augmentation
# ─────────────────────────────────────────────

class ImageAugmenter:
    """
    Applies realistic document degradation effects:
    - Gaussian blur (out-of-focus scan)
    - Motion blur (movement during scanning)
    - Gaussian noise (sensor noise)
    - Salt & pepper noise (degraded scan)
    - Brightness/contrast variation
    - Paper aging effect (yellowing)
    - Rotation (slight skew)
    - JPEG compression artifacts
    """

    SEVERITY = {
        "light": {
            "blur_kernel": (3, 3),
            "noise_std": 8,
            "sp_amount": 0.002,
            "brightness_range": (-15, 15),
            "contrast_range": (0.9, 1.1),
            "yellow_strength": 0.05,
            "rotation_range": (-1, 1),
            "jpeg_quality": 85,
        },
        "medium": {
            "blur_kernel": (5, 5),
            "noise_std": 20,
            "sp_amount": 0.008,
            "brightness_range": (-30, 30),
            "contrast_range": (0.75, 1.25),
            "yellow_strength": 0.15,
            "rotation_range": (-3, 3),
            "jpeg_quality": 55,
        },
        "heavy": {
            "blur_kernel": (7, 7),
            "noise_std": 40,
            "sp_amount": 0.02,
            "brightness_range": (-50, 50),
            "contrast_range": (0.6, 1.4),
            "yellow_strength": 0.30,
            "rotation_range": (-5, 5),
            "jpeg_quality": 25,
        },
    }

    def __init__(self, severity="medium"):
        self.params = self.SEVERITY[severity]
        self.severity = severity

    def gaussian_blur(self, img):
        """Simulate out-of-focus scanning."""
        import cv2
        k = self.params["blur_kernel"]
        return cv2.GaussianBlur(img, k, 0)

    def motion_blur(self, img):
        """Simulate movement during scanning."""
        import cv2
        size = self.params["blur_kernel"][0]
        kernel = np.zeros((size, size))
        kernel[int((size - 1) / 2), :] = np.ones(size)
        kernel = kernel / size
        return cv2.filter2D(img, -1, kernel)

    def gaussian_noise(self, img):
        """Add sensor noise."""
        noise = np.random.normal(0, self.params["noise_std"], img.shape).astype(np.float32)
        noisy = np.clip(img.astype(np.float32) + noise, 0, 255)
        return noisy.astype(np.uint8)

    def salt_pepper_noise(self, img):
        """Add salt & pepper noise (degraded scan)."""
        amount = self.params["sp_amount"]
        noisy = img.copy()
        # Salt
        num_salt = int(amount * img.size / 2)
        for _ in range(num_salt):
            y = random.randint(0, img.shape[0] - 1)
            x = random.randint(0, img.shape[1] - 1)
            noisy[y, x] = 255
        # Pepper
        for _ in range(num_salt):
            y = random.randint(0, img.shape[0] - 1)
            x = random.randint(0, img.shape[1] - 1)
            noisy[y, x] = 0
        return noisy

    def brightness_contrast(self, img):
        """Vary brightness and contrast."""
        brightness = random.randint(*self.params["brightness_range"])
        contrast = random.uniform(*self.params["contrast_range"])
        img = img.astype(np.float32)
        img = img * contrast + brightness
        return np.clip(img, 0, 255).astype(np.uint8)

    def paper_aging(self, img):
        """Simulate yellowed/aged paper."""
        import cv2
        strength = self.params["yellow_strength"]
        overlay = np.full_like(img, [235, 220, 180])  # yellowish tint
        blended = cv2.addWeighted(img, 1 - strength, overlay, strength, 0)
        return blended

    def slight_rotation(self, img):
        """Add slight skew/rotation."""
        import cv2
        angle = random.uniform(*self.params["rotation_range"])
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        return cv2.warpAffine(img, M, (w, h), borderMode=cv2.BORDER_REPLICATE)

    def jpeg_compress(self, img):
        """Simulate JPEG compression artifacts."""
        import cv2
        quality = self.params["jpeg_quality"]
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), quality]
        _, encoded = cv2.imencode('.jpg', img, encode_param)
        return cv2.imdecode(encoded, cv2.IMREAD_COLOR)

    def augment(self, img_array):
        """Apply a random subset of augmentations."""
        import cv2

        # Apply a random selection of effects (not all at once)
        effects = [
            self.gaussian_blur,
            self.gaussian_noise,
            self.brightness_contrast,
        ]

        if self.severity in ("medium", "heavy"):
            effects.extend([
                self.salt_pepper_noise,
                self.paper_aging,
                self.slight_rotation,
            ])

        if self.severity == "heavy":
            effects.extend([
                self.motion_blur,
                self.jpeg_compress,
            ])

        # Apply 2-3 effects at light, 3-5 at medium, 4-7 at heavy
        max_effects = {"light": 3, "medium": 5, "heavy": 7}[self.severity]
        min_effects = {"light": 2, "medium": 3, "heavy": 4}[self.severity]
        num_select = random.randint(min_effects, min(max_effects, len(effects)))

        selected = random.sample(effects, num_select)
        for effect in selected:
            img_array = effect(img_array)

        return img_array


# ─────────────────────────────────────────────
# Augmented dataset generation
# ─────────────────────────────────────────────

def load_split_records(split_path):
    """Load records from a split CSV."""
    records = []
    with open(split_path, "r", encoding="utf-8-sig") as f:
        for row in csv.DictReader(f):
            records.append(dict(row))
    return records


def _protected_values_for_record(rec):
    """
    Collect the critical values that appear in the email text and are used
    as ground truth, so the augmenter can keep them intact. Only fields
    actually mentioned in the email are considered; values present solely
    in the document are not in the email text and need no protection here.
    """
    values = []
    for field in ("amount", "currency", "doc_number", "date"):
        if rec.get("mentions_%s" % field, "False") == "True":
            val = rec.get("gt_%s" % field, "")
            if val:
                values.append(val)
    return values


def augment_text_scenario(records, severity, output_dir):
    """
    Scenario 1: Augment only email text, keep documents unchanged.
    Critical ground-truth values mentioned in the email are protected
    from corruption, so that the introduced noise affects only the
    surrounding text and never the values used during evaluation.
    """
    aug = TextAugmenter(severity)
    augmented = []

    for rec in records:
        new_rec = dict(rec)
        protected = _protected_values_for_record(rec)
        # Augment subject and body
        new_rec["subject"] = aug.augment(rec["subject"], protected)
        new_rec["body"] = aug.augment(rec["body"], protected)
        augmented.append(new_rec)

    return augmented


def augment_image_scenario(records, severity, output_dir):
    """
    Scenario 2: Augment only document images, keep email text unchanged.
    Creates degraded copies of attachments.
    """
    import cv2
    from PIL import Image
    import pypdfium2 as pdfium

    aug = ImageAugmenter(severity)
    aug_attach_dir = os.path.join(output_dir, f"attachments_img_{severity}")
    os.makedirs(aug_attach_dir, exist_ok=True)

    augmented = []
    for rec in records:
        new_rec = dict(rec)
        attach_path = rec.get("attachment_path", "")

        if attach_path and os.path.exists(attach_path):
            filename = os.path.basename(attach_path)
            # Always output as PNG (easier to augment)
            out_filename = os.path.splitext(filename)[0] + ".png"
            out_path = os.path.join(aug_attach_dir, out_filename)

            # Load image
            if attach_path.lower().endswith(".pdf"):
                pdf = pdfium.PdfDocument(attach_path)
                page = pdf[0]
                bitmap = page.render(scale=200 / 72)
                img = bitmap.to_pil()
                pdf.close()
            else:
                img = Image.open(attach_path)

            # Convert to numpy array for augmentation
            img_array = np.array(img.convert("RGB"))
            # Apply augmentation
            augmented_img = aug.augment(img_array)
            # Save
            cv2.imwrite(out_path, cv2.cvtColor(augmented_img, cv2.COLOR_RGB2BGR))

            new_rec["attachment_path"] = out_path
            new_rec["attachment_format"] = "png"

        augmented.append(new_rec)

    return augmented


def augment_mixed_scenario(records, severity, output_dir):
    """
    Scenario 3: Augment BOTH text and images simultaneously.
    """
    import cv2
    from PIL import Image
    import pypdfium2 as pdfium

    text_aug = TextAugmenter(severity)
    img_aug = ImageAugmenter(severity)
    aug_attach_dir = os.path.join(output_dir, f"attachments_mix_{severity}")
    os.makedirs(aug_attach_dir, exist_ok=True)

    augmented = []
    for rec in records:
        new_rec = dict(rec)

        # Augment text (protecting critical ground-truth values)
        protected = _protected_values_for_record(rec)
        new_rec["subject"] = text_aug.augment(rec["subject"], protected)
        new_rec["body"] = text_aug.augment(rec["body"], protected)

        # Augment image
        attach_path = rec.get("attachment_path", "")
        if attach_path and os.path.exists(attach_path):
            filename = os.path.basename(attach_path)
            out_filename = os.path.splitext(filename)[0] + ".png"
            out_path = os.path.join(aug_attach_dir, out_filename)

            if attach_path.lower().endswith(".pdf"):
                pdf = pdfium.PdfDocument(attach_path)
                page = pdf[0]
                bitmap = page.render(scale=200 / 72)
                img = bitmap.to_pil()
                pdf.close()
            else:
                img = Image.open(attach_path)

            img_array = np.array(img.convert("RGB"))
            augmented_img = img_aug.augment(img_array)
            cv2.imwrite(out_path, cv2.cvtColor(augmented_img, cv2.COLOR_RGB2BGR))

            new_rec["attachment_path"] = out_path
            new_rec["attachment_format"] = "png"

        augmented.append(new_rec)

    return augmented


def save_augmented_csv(records, output_path):
    """Save augmented records to CSV."""
    if not records:
        return
    fieldnames = list(records[0].keys())
    with open(output_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)


# ─────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Data augmentation for robustness testing")
    parser.add_argument("--scenario", choices=["text", "image", "mixed"],
                        help="Augmentation scenario")
    parser.add_argument("--severity", choices=["light", "medium", "heavy"],
                        default="medium", help="Augmentation severity")
    parser.add_argument("--split", default="test",
                        help="Which split to augment")
    parser.add_argument("--data_dir", default=".", help="Data directory")
    parser.add_argument("--all", action="store_true",
                        help="Run all 9 combinations (3 scenarios × 3 severities)")
    args = parser.parse_args()

    data_dir = args.data_dir
    output_dir = os.path.join(data_dir, "augmented")
    os.makedirs(output_dir, exist_ok=True)

    split_path = os.path.join(data_dir, f"{args.split}.csv")
    if not os.path.exists(split_path):
        print(f"Error: {split_path} not found")
        return

    records = load_split_records(split_path)
    print(f"Loaded {len(records)} records from {args.split}.csv")

    if args.all:
        scenarios = ["text", "image", "mixed"]
        severities = ["light", "medium", "heavy"]
    else:
        scenarios = [args.scenario]
        severities = [args.severity]

    for scenario in scenarios:
        for severity in severities:
            print(f"\n{'='*55}")
            print(f"Augmenting: scenario={scenario}, severity={severity}")
            print(f"{'='*55}")

            if scenario == "text":
                augmented = augment_text_scenario(records, severity, output_dir)
            elif scenario == "image":
                augmented = augment_image_scenario(records, severity, output_dir)
            elif scenario == "mixed":
                augmented = augment_mixed_scenario(records, severity, output_dir)

            # Save augmented CSV
            out_csv = os.path.join(output_dir, f"{args.split}_{scenario}_{severity}.csv")
            save_augmented_csv(augmented, out_csv)
            print(f"Saved: {out_csv} ({len(augmented)} records)")

    print(f"\nAll augmentation complete! Files in: {output_dir}/")


if __name__ == "__main__":
    main()
