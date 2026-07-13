"""
Configuration for the dataset generation.
Defines classes, distributions, field schemas, and supplier data.
"""

import random
from dataclasses import dataclass, field
from typing import Optional


# Random seed for reproducibility
SEED = 42


# Intent classes and their target counts

CLASS_DISTRIBUTION = {
    "quote_offer":                  120,
    "invoice_submission":           120,
    "price_validity_confirmation":   80,
    "price_increase":                80,
    "other":                        100,
}

TOTAL_SAMPLES = sum(CLASS_DISTRIBUTION.values())  # 500


# Attachment probability per class
# True = always has attachment, float = probability

ATTACHMENT_PROBABILITY = {
    "quote_offer":                  1.0,    # always
    "invoice_submission":           1.0,    # always
    "price_validity_confirmation":  0.35,   # sometimes attaches original quote
    "price_increase":               0.30,   # sometimes attaches new price list
    "other":                        0.10,   # rarely
}


# Document type mapping (what kind of attachment)

ATTACHMENT_DOC_TYPE = {
    "quote_offer":                  "quotation",
    "invoice_submission":           "invoice",
    "price_validity_confirmation":  "quotation",   # re-attaches original quote
    "price_increase":               "price_list",
    "other":                        "generic",
}

# Format split: what % of attachments are PDF vs image

PDF_RATIO = 0.65   # 65% PDF, 35% image (PNG)


# Key fields extracted from emails and documents

KEY_FIELDS = ["amount", "currency", "doc_number", "date"]


# Probability that the email explicitly mentions each field
# (vs. being vague, leaving info only in the attachment)

FIELD_MENTION_PROBABILITY = {
    "quote_offer": {
        "amount":     0.75,
        "currency":   0.80,
        "doc_number": 0.85,
        "date":       0.70,
    },
    "invoice_submission": {
        "amount":     0.80,
        "currency":   0.85,
        "doc_number": 0.90,
        "date":       0.65,
    },
    "price_validity_confirmation": {
        "amount":     0.50,
        "currency":   0.55,
        "doc_number": 0.70,
        "date":       0.80,
    },
    "price_increase": {
        "amount":     0.60,
        "currency":   0.65,
        "doc_number": 0.30,
        "date":       0.85,
    },
    "other": {
        "amount":     0.10,
        "currency":   0.10,
        "doc_number": 0.15,
        "date":       0.20,
    },
}


# Mismatch / discrepancy settings
# ~35% of pairs with attachments will have a mismatch

MISMATCH_RATIO = 0.35

MISMATCH_TYPES = ["amount", "currency", "date"]
# doc_number mismatches are less realistic, so we focus on the above three

MISMATCH_TYPE_WEIGHTS = {
    "amount":   0.45,
    "currency": 0.25,
    "date":     0.30,
}


# Currencies

CURRENCIES = ["USD", "EUR", "GBP", "RON", "CHF"]
CURRENCY_SYMBOLS = {
    "USD": "$",
    "EUR": "€",
    "GBP": "£",
    "RON": "RON",
    "CHF": "CHF",
}

# Supplier data (fictional companies)

SUPPLIER_COMPANIES = [
    "Apex Industrial Solutions",
    "BrightLine Components Ltd.",
    "CedarTech Manufacturing",
    "Delta Precision Parts",
    "EuroSteel Supply GmbH",
    "FairPoint Logistics",
    "GlobalWire Electronics",
    "Harmon Tools & Equipment",
    "IronBridge Materials",
    "JetStream Packaging Co.",
    "Keystone Fasteners Inc.",
    "Lakewood Chemical Supply",
    "MeridianTech Systems",
    "NorthStar Industrial",
    "OmniParts Distribution",
    "PrimeEdge Components",
    "QuickFlow Hydraulics",
    "RedLine Automotive Parts",
    "SilverOak Metals",
    "TitanForge Engineering",
    "UltraSpec Optics",
    "Vanguard Electrical",
    "WestBridge Plastics",
    "Xenon Power Solutions",
    "YieldMax Agriculture Supply",
    "ZenithCraft Industries",
]

SUPPLIER_CONTACTS = [
    ("John Smith", "john.smith"),
    ("Maria Garcia", "m.garcia"),
    ("David Chen", "d.chen"),
    ("Sarah Johnson", "s.johnson"),
    ("Ahmed Hassan", "a.hassan"),
    ("Elena Popescu", "e.popescu"),
    ("Michael Brown", "m.brown"),
    ("Anna Kowalski", "a.kowalski"),
    ("Robert Taylor", "r.taylor"),
    ("Lisa Wang", "l.wang"),
    ("Thomas Mueller", "t.mueller"),
    ("Fatima Al-Rashid", "f.alrashid"),
    ("James Wilson", "j.wilson"),
    ("Priya Sharma", "p.sharma"),
    ("Carlos Mendez", "c.mendez"),
    ("Sophie Laurent", "s.laurent"),
    ("Ivan Petrov", "i.petrov"),
    ("Rachel Kim", "r.kim"),
    ("Omar Youssef", "o.youssef"),
    ("Hannah Fischer", "h.fischer"),
]


# Recipient (the user's company - buyer side)

RECIPIENT_NAMES = [
    "Procurement Team",
    "Purchasing Department",
    "Alex",
    "Customer",
    "Team",
]


# Amount ranges per document type

AMOUNT_RANGES = {
    "quotation":   (500.0, 150_000.0),
    "invoice":     (200.0, 200_000.0),
    "price_list":  (50.0, 10_000.0),     # per-item or total
    "generic":     (100.0, 50_000.0),
}


# Date ranges (documents dated within last ~2 years)

DATE_RANGE_START = "2024-06-01"
DATE_RANGE_END   = "2026-03-15"

# Validity periods (days from doc date)
VALIDITY_DAYS_RANGE = (15, 90)

# Payment due periods (days from invoice date)
PAYMENT_DUE_DAYS = [15, 30, 45, 60, 90]



# Data class for a single email record

@dataclass
class EmailRecord:
    email_id: str
    intent: str
    subject: str
    body: str
    sender_name: str
    sender_email: str
    sender_company: str
    # Ground-truth fields (as mentioned in email, None if not mentioned)
    gt_amount: Optional[float] = None
    gt_currency: Optional[str] = None
    gt_doc_number: Optional[str] = None
    gt_date: Optional[str] = None
    # Whether each field is explicitly mentioned in the email text
    mentions_amount: bool = False
    mentions_currency: bool = False
    mentions_doc_number: bool = False
    mentions_date: bool = False


@dataclass
class PairRecord:
    pair_id: str
    email_id: str
    attachment_path: Optional[str]          # None if no attachment
    attachment_format: Optional[str]        # "pdf" or "png"
    doc_type: Optional[str]                 # "invoice", "quotation", etc.
    # Ground-truth fields in the document
    doc_amount: Optional[float] = None
    doc_currency: Optional[str] = None
    doc_doc_number: Optional[str] = None
    doc_date: Optional[str] = None
    # Mismatch info
    is_consistent: bool = True
    mismatch_field: Optional[str] = None    # which field differs
    mismatch_type: Optional[str] = None     # e.g. "amount", "currency", "date"
