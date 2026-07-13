"""
verifica_augmentare.py
──────────────────────
Script de verificare a calității datelor augmentate de text.

Rol: confirmă că valorile critice (sumă, monedă, număr document, dată)
care sunt menționate în e-mail și folosite ca adevăr de referință (ground
truth) NU au fost corupte de augmentarea de text. După repararea fișierului
augmentation.py, rata de pierdere ar trebui să fie aproape de 0%.

Utilizare:
    # mai întâi regenerează datele cu codul reparat:
    python augmentation.py --scenario text  --severity medium --split train
    python augmentation.py --scenario text  --severity medium --split test
    python augmentation.py --scenario mixed --severity medium --split train
    python augmentation.py --scenario mixed --severity medium --split test

    # apoi verifică un fișier augmentat:
    python verifica_augmentare.py --file augmented/train_text_medium.csv
    python verifica_augmentare.py --file augmented/test_text_medium.csv
    python verifica_augmentare.py --file augmented/train_mixed_medium.csv

Interpretare:
    - O valoare este considerată "prezentă" dacă apare în textul augmentat,
      cu toleranță la formatare (separatori de mii la sume, cratime la
      numerele de document, formate alternative la date).
    - Rata de pierdere ar trebui să fie 0% sau foarte apropiată. O rată
      ridicată indică faptul că protejarea valorilor nu a funcționat.
"""

import argparse
import csv
import re


CURRENCY_SYMBOLS = {
    "USD": ["USD", "$", "US$"],
    "EUR": ["EUR", "€"],
    "GBP": ["GBP", "£"],
    "RON": ["RON", "lei", "LEI"],
    "CHF": ["CHF"],
}

MONTHS = {
    "01": ["january", "jan"], "02": ["february", "feb"],
    "03": ["march", "mar"], "04": ["april", "apr"],
    "05": ["may"], "06": ["june", "jun"],
    "07": ["july", "jul"], "08": ["august", "aug"],
    "09": ["september", "sep", "sept"], "10": ["october", "oct"],
    "11": ["november", "nov"], "12": ["december", "dec"],
}


def only_digits(s):
    return re.sub(r"[^0-9]", "", str(s))


def date_variants(iso_date):
    """
    Pentru o dată ISO (AAAA-LL-ZZ), întoarce tipare care acoperă formatele
    uzuale: numerice (cu punct, slash, ordine zi/lună sau lună/zi) și
    textuale (luna scrisă cu litere, în engleză).
    """
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", str(iso_date))
    if not m:
        return [str(iso_date).lower()]
    y, mo, d = m.group(1), m.group(2), m.group(3)
    di, mi = int(d), int(mo)
    variants = {
        f"{y}-{mo}-{d}",
        f"{d}.{mo}.{y}", f"{d}/{mo}/{y}",
        f"{mo}/{d}/{y}", f"{mo}.{d}.{y}",
        f"{di}.{mi}.{y}", f"{di}/{mi}/{y}",
    }
    # variante textuale: "october 26, 2025", "26 october 2025", cu zi cu/fără zero
    for name in MONTHS.get(mo, []):
        for day in {str(di), d}:
            variants.add(f"{name} {day}, {y}")
            variants.add(f"{name} {day} {y}")
            variants.add(f"{day} {name} {y}")
            variants.add(f"{day} {name}, {y}")
    return [v.lower() for v in variants]


def value_present(field, gt, text):
    """Verifică, cu toleranță la formatare, dacă valoarea gt apare în text."""
    if not gt:
        return True

    if field == "amount":
        gtd = only_digits(gt)
        return bool(gtd) and gtd in only_digits(text)

    if field == "doc_number":
        norm = lambda s: re.sub(r"[-/\s]", "", str(s)).upper()
        return norm(gt) in norm(text)

    if field == "currency":
        # acceptăm atât codul ISO, cât și simbolul corespunzător
        forms = CURRENCY_SYMBOLS.get(str(gt).upper(), [str(gt)])
        return any(form in text for form in forms)

    if field == "date":
        low = text.lower()
        return any(v in low for v in date_variants(gt))

    return str(gt).upper() in text.upper()


def main():
    parser = argparse.ArgumentParser(
        description="Verifică integritatea valorilor critice în datele augmentate de text."
    )
    parser.add_argument("--file", required=True,
                        help="Fișierul CSV augmentat de verificat.")
    args = parser.parse_args()

    with open(args.file, "r", encoding="utf-8-sig") as f:
        records = list(csv.DictReader(f))

    fields = ["amount", "currency", "doc_number", "date"]
    checked = {f: 0 for f in fields}
    lost = {f: 0 for f in fields}
    lost_examples = {f: [] for f in fields}

    for rec in records:
        text = (rec.get("subject", "") or "") + " " + (rec.get("body", "") or "")
        for field in fields:
            mentions = rec.get(f"mentions_{field}", "False") == "True"
            gt = rec.get(f"gt_{field}", "")
            if not mentions or not gt:
                continue
            checked[field] += 1
            if not value_present(field, gt, text):
                lost[field] += 1
                if len(lost_examples[field]) < 3:
                    lost_examples[field].append(
                        (rec.get("email_id", "?"), gt, text.strip()[:140])
                    )

    print(f"\nFișier verificat: {args.file}")
    print(f"Total înregistrări: {len(records)}")
    print("=" * 60)
    total_checked = 0
    total_lost = 0
    for field in fields:
        c, l = checked[field], lost[field]
        total_checked += c
        total_lost += l
        if c:
            rate = 100 * l / c
            status = "OK" if rate < 1.0 else ("ATENTIE" if rate < 5 else "PROBLEMA")
            print(f"  {field:12s}: {l:3d}/{c:3d} pierdute  ({rate:5.1f}%)  [{status}]")
        else:
            print(f"  {field:12s}: niciun caz de verificat")

    print("=" * 60)
    if total_checked:
        overall = 100 * total_lost / total_checked
        print(f"  TOTAL       : {total_lost}/{total_checked} pierdute  ({overall:.2f}%)")
        if overall < 1.0:
            print("\n  Rezultat: valorile critice sunt protejate corect.")
        else:
            print("\n  Rezultat: încă există valori pierdute. Verifică exemplele de mai jos.")

    # afișează câteva exemple de pierderi, dacă există
    any_examples = any(lost_examples[f] for f in fields)
    if any_examples:
        print("\nExemple de valori pierdute:")
        for field in fields:
            for eid, gt, snippet in lost_examples[field]:
                print(f"  [{field}] {eid}: gt='{gt}'")
                print(f"       text: {snippet}")


if __name__ == "__main__":
    main()
