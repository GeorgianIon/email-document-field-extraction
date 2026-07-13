"""
generate_documents.py
─────────────────────
Reads pairs.csv and generates the actual attachment files:
  - Invoices (PDF and PNG)
  - Quotations (PDF and PNG)
  - Price lists (PDF and PNG)

Each document uses one of several visual templates to create
realistic variation in layout, as would occur with different suppliers.

Usage:
    python generate_documents.py
"""

import csv
import os
import random
from datetime import datetime, timedelta
from io import BytesIO

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, letter
from reportlab.lib.units import mm, inch
from reportlab.pdfgen import canvas
from reportlab.lib.enums import TA_LEFT, TA_RIGHT, TA_CENTER
from PIL import Image

from config import (
    SEED,
    SUPPLIER_COMPANIES,
    SUPPLIER_CONTACTS,
    CURRENCY_SYMBOLS,
)

random.seed(SEED)

# Color palettes for different "supplier brands"

COLOR_PALETTES = [
    {"primary": colors.HexColor("#1a365d"), "accent": colors.HexColor("#2b6cb0"),
     "light": colors.HexColor("#e2e8f0"), "text": colors.HexColor("#1a202c")},
    {"primary": colors.HexColor("#22543d"), "accent": colors.HexColor("#38a169"),
     "light": colors.HexColor("#e6fffa"), "text": colors.HexColor("#1a202c")},
    {"primary": colors.HexColor("#742a2a"), "accent": colors.HexColor("#c53030"),
     "light": colors.HexColor("#fff5f5"), "text": colors.HexColor("#1a202c")},
    {"primary": colors.HexColor("#2d3748"), "accent": colors.HexColor("#4a5568"),
     "light": colors.HexColor("#edf2f7"), "text": colors.HexColor("#2d3748")},
    {"primary": colors.HexColor("#44337a"), "accent": colors.HexColor("#6b46c1"),
     "light": colors.HexColor("#faf5ff"), "text": colors.HexColor("#1a202c")},
    {"primary": colors.HexColor("#1a4e8a"), "accent": colors.HexColor("#3182ce"),
     "light": colors.HexColor("#ebf8ff"), "text": colors.HexColor("#1a202c")},
]


# Line items for invoices/quotations

LINE_ITEMS_POOL = [
    ("Mechanical component A-series", 12.50, 100),
    ("Steel bracket (custom)", 8.75, 50),
    ("Hydraulic pump assembly", 450.00, 5),
    ("Electronic module v2.1", 89.99, 20),
    ("Fastener kit (M8 x 50)", 3.25, 500),
    ("Precision cutting tool", 125.00, 10),
    ("Cable harness (2m)", 15.60, 75),
    ("PCB board rev.3", 42.00, 30),
    ("Safety valve DN25", 67.50, 15),
    ("Bearing unit 6205-2RS", 18.90, 200),
    ("Aluminium profile (6m)", 35.00, 25),
    ("Insulation panel 50mm", 22.40, 40),
    ("Connector set (10-pin)", 5.80, 150),
    ("Welding electrode E7018", 2.10, 1000),
    ("Conveyor roller 300mm", 55.00, 8),
    ("Pressure regulator 0-10bar", 78.00, 12),
    ("Optical sensor module", 195.00, 6),
    ("Chemical reagent (500ml)", 32.00, 20),
    ("Packaging material (roll)", 14.50, 60),
    ("Power supply unit 24V", 62.00, 15),
    ("Thermal paste (tube)", 7.90, 100),
    ("Stainless tubing 25mm", 28.50, 30),
    ("O-ring kit (assorted)", 9.60, 80),
    ("Motor coupling 12mm", 34.00, 20),
    ("Filter element HF-200", 45.00, 10),
    ("Shipping & handling", 0, 1),
    ("Express delivery surcharge", 0, 1),
    ("Assembly labor (hours)", 65.00, 8),
]


def generate_line_items(total_target: float, currency: str):
    """Generate realistic line items that sum close to the target total."""
    items = []
    remaining = total_target
    num_items = random.randint(2, 7)

    for i in range(num_items - 1):
        item_name, base_price, max_qty = random.choice(LINE_ITEMS_POOL[:25])
        if base_price == 0:
            continue
        # Scale price to fit target
        qty = random.randint(1, min(max_qty, 50))
        unit_price = round(remaining / (num_items - i) / qty * random.uniform(0.5, 1.5), 2)
        unit_price = max(1.0, unit_price)
        line_total = round(unit_price * qty, 2)

        if line_total > remaining * 0.95:
            line_total = round(remaining * random.uniform(0.2, 0.5), 2)
            unit_price = round(line_total / qty, 2)
            line_total = round(unit_price * qty, 2)

        items.append({
            "description": item_name,
            "qty": qty,
            "unit_price": unit_price,
            "total": line_total,
        })
        remaining -= line_total

    # Last item absorbs the remainder
    if remaining > 0:
        item_name, _, _ = random.choice(LINE_ITEMS_POOL[:25])
        qty = random.randint(1, 10)
        unit_price = round(remaining / qty, 2)
        line_total = round(unit_price * qty, 2)
        items.append({
            "description": item_name,
            "qty": qty,
            "unit_price": unit_price,
            "total": line_total,
        })

    return items


def format_currency_amount(amount: float, currency: str) -> str:
    """Format an amount with currency symbol/code."""
    symbol = CURRENCY_SYMBOLS.get(currency, currency)
    if currency in ("USD", "GBP"):
        return f"{symbol}{amount:,.2f}"
    elif currency == "EUR":
        return f"{symbol}{amount:,.2f}"
    else:
        return f"{amount:,.2f} {symbol}"



# Invoice/Quotation drawing functions


def draw_invoice_style_a(c, w, h, data, palette):
    """Clean modern invoice with colored header bar."""
    # Header bar
    c.setFillColor(palette["primary"])
    c.rect(0, h - 80, w, 80, fill=True, stroke=False)

    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 22)
    c.drawString(30, h - 50, "INVOICE")
    c.setFont("Helvetica", 10)
    c.drawString(30, h - 68, data["company"])

    # Invoice details (right side)
    c.setFont("Helvetica-Bold", 10)
    c.drawRightString(w - 30, h - 40, f"Invoice No: {data['doc_number']}")
    c.setFont("Helvetica", 10)
    c.drawRightString(w - 30, h - 55, f"Date: {data['issue_date']}")
    c.drawRightString(w - 30, h - 70, f"Due Date: {data['date']}")

    # Bill To section
    y = h - 120
    c.setFillColor(palette["text"])
    c.setFont("Helvetica-Bold", 11)
    c.drawString(30, y, "Bill To:")
    c.setFont("Helvetica", 10)
    c.drawString(30, y - 15, data.get("buyer_company", "Purchasing Department"))
    c.drawString(30, y - 30, data.get("buyer_address", "123 Business Street, Suite 400"))

    # From section (right)
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(w - 30, y, "From:")
    c.setFont("Helvetica", 10)
    c.drawRightString(w - 30, y - 15, data["company"])
    c.drawRightString(w - 30, y - 30, data.get("supplier_address", "456 Industrial Ave"))

    # Table header
    y = h - 190
    c.setFillColor(palette["light"])
    c.rect(25, y - 5, w - 50, 20, fill=True, stroke=False)
    c.setFillColor(palette["primary"])
    c.setFont("Helvetica-Bold", 9)
    c.drawString(30, y, "Description")
    c.drawRightString(350, y, "Qty")
    c.drawRightString(440, y, "Unit Price")
    c.drawRightString(w - 30, y, "Amount")

    # Line items
    c.setFillColor(palette["text"])
    c.setFont("Helvetica", 9)
    y -= 25
    for item in data["items"]:
        c.drawString(30, y, item["description"])
        c.drawRightString(350, y, str(item["qty"]))
        c.drawRightString(440, y, f"{item['unit_price']:,.2f}")
        c.drawRightString(w - 30, y, f"{item['total']:,.2f}")
        y -= 18

    # Separator line
    y -= 5
    c.setStrokeColor(palette["accent"])
    c.setLineWidth(1)
    c.line(300, y, w - 30, y)

    # Subtotal / Total
    y -= 20
    subtotal = sum(i["total"] for i in data["items"])
    c.setFont("Helvetica", 10)
    c.drawRightString(440, y, "Subtotal:")
    c.drawRightString(w - 30, y, f"{subtotal:,.2f}")

    y -= 18
    c.setFont("Helvetica-Bold", 11)
    c.drawRightString(440, y, "TOTAL:")
    c.drawRightString(w - 30, y, format_currency_amount(data["amount"], data["currency"]))

    # Footer
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawString(30, 30, f"Payment terms: Net {random.choice([15,30,45,60])} days")
    c.drawRightString(w - 30, 30, f"Currency: {data['currency']}")


def draw_invoice_style_b(c, w, h, data, palette):
    """Traditional invoice with border and boxed header."""
    # Outer border
    c.setStrokeColor(palette["primary"])
    c.setLineWidth(2)
    c.rect(20, 20, w - 40, h - 40, fill=False, stroke=True)

    # Company name
    y = h - 55
    c.setFillColor(palette["primary"])
    c.setFont("Helvetica-Bold", 16)
    c.drawString(40, y, data["company"])

    # INVOICE title (right)
    c.setFont("Helvetica-Bold", 24)
    c.drawRightString(w - 40, y, "INVOICE")

    # Horizontal line
    y -= 15
    c.setLineWidth(1)
    c.line(40, y, w - 40, y)

    # Details box
    y -= 30
    c.setFillColor(palette["light"])
    c.rect(w - 250, y - 50, 220, 65, fill=True, stroke=False)
    c.setFillColor(palette["text"])
    c.setFont("Helvetica-Bold", 9)
    c.drawString(w - 240, y, f"Invoice Number:")
    c.drawString(w - 240, y - 15, f"Invoice Date:")
    c.drawString(w - 240, y - 30, f"Due Date:")
    c.drawString(w - 240, y - 45, f"Currency:")
    c.setFont("Helvetica", 9)
    c.drawString(w - 140, y, data["doc_number"])
    c.drawString(w - 140, y - 15, data["issue_date"])
    c.drawString(w - 140, y - 30, data["date"])
    c.drawString(w - 140, y - 45, data["currency"])

    # Bill To
    c.setFont("Helvetica-Bold", 10)
    c.drawString(40, y, "BILL TO:")
    c.setFont("Helvetica", 9)
    c.drawString(40, y - 15, data.get("buyer_company", "Client Company Ltd."))
    c.drawString(40, y - 30, data.get("buyer_address", "789 Commerce Blvd"))

    # Table
    y -= 80
    # Header
    c.setFillColor(palette["primary"])
    c.rect(35, y - 3, w - 70, 18, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "#")
    c.drawString(60, y, "Item Description")
    c.drawRightString(370, y, "Qty")
    c.drawRightString(450, y, "Unit Price")
    c.drawRightString(w - 40, y, "Total")

    # Items
    c.setFillColor(palette["text"])
    c.setFont("Helvetica", 9)
    y -= 22
    for idx, item in enumerate(data["items"], 1):
        if idx % 2 == 0:
            c.setFillColor(palette["light"])
            c.rect(35, y - 3, w - 70, 16, fill=True, stroke=False)
        c.setFillColor(palette["text"])
        c.drawString(40, y, str(idx))
        c.drawString(60, y, item["description"])
        c.drawRightString(370, y, str(item["qty"]))
        c.drawRightString(450, y, f"{item['unit_price']:,.2f}")
        c.drawRightString(w - 40, y, f"{item['total']:,.2f}")
        y -= 18

    # Total box
    y -= 15
    c.setStrokeColor(palette["primary"])
    c.setLineWidth(1.5)
    c.rect(350, y - 25, w - 390, 30, fill=False, stroke=True)
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(palette["primary"])
    c.drawString(360, y - 18, "TOTAL:")
    c.drawRightString(w - 45, y - 18,
                       format_currency_amount(data["amount"], data["currency"]))


def draw_quotation_style_a(c, w, h, data, palette):
    """Professional quotation with accent stripe."""
    # Left accent stripe
    c.setFillColor(palette["accent"])
    c.rect(0, 0, 8, h, fill=True, stroke=False)

    # Title
    y = h - 50
    c.setFillColor(palette["primary"])
    c.setFont("Helvetica-Bold", 26)
    c.drawString(30, y, "QUOTATION")

    # Company
    c.setFont("Helvetica", 11)
    c.setFillColor(palette["text"])
    c.drawString(30, y - 25, data["company"])

    # Quote info (right aligned)
    c.setFont("Helvetica-Bold", 9)
    c.drawRightString(w - 30, y, f"Quote #: {data['doc_number']}")
    c.setFont("Helvetica", 9)
    c.drawRightString(w - 30, y - 15, f"Date: {data['issue_date']}")
    c.drawRightString(w - 30, y - 30, f"Valid Until: {data['date']}")

    # Separator
    y -= 55
    c.setStrokeColor(palette["accent"])
    c.setLineWidth(0.5)
    c.line(25, y, w - 25, y)

    # Prepared For
    y -= 25
    c.setFont("Helvetica-Bold", 10)
    c.setFillColor(palette["primary"])
    c.drawString(30, y, "Prepared For:")
    c.setFont("Helvetica", 9)
    c.setFillColor(palette["text"])
    c.drawString(30, y - 15, data.get("buyer_company", "Valued Customer"))

    # Table
    y -= 50
    c.setFillColor(palette["primary"])
    c.rect(25, y - 3, w - 50, 18, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(30, y, "Description")
    c.drawRightString(360, y, "Qty")
    c.drawRightString(450, y, "Unit Price")
    c.drawRightString(w - 30, y, "Amount")

    c.setFillColor(palette["text"])
    c.setFont("Helvetica", 9)
    y -= 22
    for item in data["items"]:
        c.drawString(30, y, item["description"])
        c.drawRightString(360, y, str(item["qty"]))
        c.drawRightString(450, y, f"{item['unit_price']:,.2f}")
        c.drawRightString(w - 30, y, f"{item['total']:,.2f}")
        y -= 18

    # Total section
    y -= 10
    c.setStrokeColor(palette["accent"])
    c.line(350, y, w - 25, y)
    y -= 20
    c.setFont("Helvetica-Bold", 12)
    c.setFillColor(palette["primary"])
    c.drawRightString(450, y, "TOTAL QUOTE:")
    c.drawRightString(w - 30, y,
                       format_currency_amount(data["amount"], data["currency"]))

    # Validity notice
    y -= 40
    c.setFont("Helvetica-Oblique", 9)
    c.setFillColor(colors.grey)
    c.drawString(30, y,
                  f"This quotation is valid until {data['date']}. "
                  "Prices are subject to change after the validity period.")

    # Footer
    c.setFont("Helvetica", 8)
    c.drawString(30, 30, f"Currency: {data['currency']}")
    c.drawRightString(w - 30, 30, data["company"])


def draw_quotation_style_b(c, w, h, data, palette):
    """Simple quotation with table focus."""
    y = h - 50
    c.setFillColor(palette["text"])
    c.setFont("Helvetica-Bold", 20)
    c.drawCentredString(w / 2, y, data["company"])

    y -= 30
    c.setFont("Helvetica-Bold", 14)
    c.setFillColor(palette["accent"])
    c.drawCentredString(w / 2, y, "COMMERCIAL OFFER")

    # Details
    y -= 35
    c.setFont("Helvetica", 10)
    c.setFillColor(palette["text"])
    c.drawString(40, y, f"Reference: {data['doc_number']}")
    c.drawRightString(w - 40, y, f"Date: {data['issue_date']}")
    y -= 15
    c.drawString(40, y, f"Valid Until: {data['date']}")
    c.drawRightString(w - 40, y, f"Currency: {data['currency']}")

    # Line
    y -= 15
    c.setStrokeColor(palette["primary"])
    c.setLineWidth(1)
    c.line(35, y, w - 35, y)

    # Table header
    y -= 25
    c.setFillColor(palette["light"])
    c.rect(35, y - 5, w - 70, 20, fill=True, stroke=False)
    c.setFillColor(palette["primary"])
    c.setFont("Helvetica-Bold", 9)
    c.drawString(40, y, "No.")
    c.drawString(70, y, "Description")
    c.drawRightString(370, y, "Quantity")
    c.drawRightString(460, y, "Price/Unit")
    c.drawRightString(w - 40, y, "Line Total")

    c.setFillColor(palette["text"])
    c.setFont("Helvetica", 9)
    y -= 22
    for idx, item in enumerate(data["items"], 1):
        c.drawString(40, y, str(idx))
        c.drawString(70, y, item["description"])
        c.drawRightString(370, y, str(item["qty"]))
        c.drawRightString(460, y, f"{item['unit_price']:,.2f}")
        c.drawRightString(w - 40, y, f"{item['total']:,.2f}")
        y -= 18
        # Alternating row shading
        if idx % 2 == 0:
            c.setFillColor(colors.Color(0.97, 0.97, 0.97))
            c.rect(35, y - 3, w - 70, 16, fill=True, stroke=False)
            c.setFillColor(palette["text"])

    # Double line before total
    y -= 8
    c.setLineWidth(0.5)
    c.line(350, y, w - 35, y)
    y -= 3
    c.line(350, y, w - 35, y)

    y -= 22
    c.setFont("Helvetica-Bold", 13)
    c.setFillColor(palette["primary"])
    c.drawRightString(460, y, "TOTAL:")
    c.drawRightString(w - 40, y,
                       format_currency_amount(data["amount"], data["currency"]))

    # Note at bottom
    y -= 50
    c.setFont("Helvetica", 8)
    c.setFillColor(colors.grey)
    c.drawString(40, y, "Terms: Payment upon acceptance. Delivery within 2-4 weeks after order confirmation.")
    y -= 12
    c.drawString(40, y, f"This quote expires on {data['date']}.")


def draw_price_list(c, w, h, data, palette):
    """Simple price list / price update document."""
    # Header
    y = h - 50
    c.setFillColor(palette["primary"])
    c.setFont("Helvetica-Bold", 20)
    c.drawString(30, y, "PRICE LIST")

    c.setFont("Helvetica", 11)
    c.setFillColor(palette["text"])
    c.drawString(30, y - 22, data["company"])

    c.setFont("Helvetica", 9)
    c.drawRightString(w - 30, y, f"Ref: {data['doc_number']}")
    c.drawRightString(w - 30, y - 14, f"Effective: {data['date']}")
    c.drawRightString(w - 30, y - 28, f"Currency: {data['currency']}")

    # Separator
    y -= 50
    c.setStrokeColor(palette["accent"])
    c.setLineWidth(1)
    c.line(25, y, w - 25, y)

    # Table
    y -= 25
    c.setFillColor(palette["primary"])
    c.rect(25, y - 4, w - 50, 20, fill=True, stroke=False)
    c.setFillColor(colors.white)
    c.setFont("Helvetica-Bold", 9)
    c.drawString(30, y, "Item")
    c.drawRightString(w - 30, y, "New Price")

    c.setFillColor(palette["text"])
    c.setFont("Helvetica", 9)
    y -= 22
    for item in data["items"]:
        c.drawString(30, y, item["description"])
        c.drawRightString(w - 30, y,
                           format_currency_amount(item["unit_price"], data["currency"]))
        y -= 16

    # Total / representative amount
    y -= 15
    c.setStrokeColor(palette["accent"])
    c.line(350, y, w - 25, y)
    y -= 20
    c.setFont("Helvetica-Bold", 11)
    c.setFillColor(palette["primary"])
    c.drawRightString(w - 30, y,
                       f"Representative total: "
                       f"{format_currency_amount(data['amount'], data['currency'])}")


# Main rendering pipeline


INVOICE_STYLES = [draw_invoice_style_a, draw_invoice_style_b]
QUOTATION_STYLES = [draw_quotation_style_a, draw_quotation_style_b]

BUYER_COMPANIES = [
    ("TechCorp International", "123 Innovation Drive, Building C"),
    ("Nordic Manufacturing AB", "Industrivägen 45, Stockholm"),
    ("Atlantic Procurement Ltd.", "78 Commerce Street, London EC2"),
    ("Pacific Industries Corp.", "500 Harbor Blvd, Suite 1200"),
    ("Central European Trading GmbH", "Handelsstraße 12, Vienna"),
]

SUPPLIER_ADDRESSES = [
    "100 Industrial Park Road, Warehouse 5",
    "250 Commerce Boulevard, Floor 3",
    "P.O. Box 4421, Business District",
    "75 Manufacturing Lane",
    "1200 Enterprise Way, Unit B",
]


def render_document(pair_row: dict, output_dir: str):
    """Render a single document (invoice, quotation, or price list)."""
    doc_type = pair_row["doc_type"]
    fmt = pair_row["attachment_format"]
    path = pair_row["attachment_path"]
    full_path = os.path.join(output_dir, path)

    amount = float(pair_row["doc_amount"])
    currency = pair_row["doc_currency"]
    doc_number = pair_row["doc_doc_number"]
    date_str = pair_row["doc_date"]

    # Pick a company name (from pairs we don't have company, so derive or pick)
    company = random.choice(SUPPLIER_COMPANIES)
    buyer_company, buyer_address = random.choice(BUYER_COMPANIES)
    supplier_address = random.choice(SUPPLIER_ADDRESSES)
    palette = random.choice(COLOR_PALETTES)

    # Generate line items
    items = generate_line_items(amount, currency)

    # Recalculate actual total from items to match
    actual_total = sum(i["total"] for i in items)
    # Adjust last item to hit exact target
    if items:
        diff = amount - actual_total
        items[-1]["total"] = round(items[-1]["total"] + diff, 2)
        if items[-1]["qty"] > 0:
            items[-1]["unit_price"] = round(items[-1]["total"] / items[-1]["qty"], 2)
            items[-1]["total"] = round(items[-1]["unit_price"] * items[-1]["qty"], 2)

    # Generate an issue date (a few days before the relevant date)
    try:
        rel_date = datetime.strptime(date_str, "%Y-%m-%d")
        issue_date = rel_date - timedelta(days=random.randint(1, 30))
    except (ValueError, TypeError):
        issue_date = datetime(2025, 6, 1)

    data = {
        "company": company,
        "doc_number": doc_number,
        "amount": amount,
        "currency": currency,
        "date": date_str,
        "issue_date": issue_date.strftime("%Y-%m-%d"),
        "items": items,
        "buyer_company": buyer_company,
        "buyer_address": buyer_address,
        "supplier_address": supplier_address,
    }

    # Choose page size
    pagesize = random.choice([A4, letter])
    w, h = pagesize

    # Create PDF in memory
    buf = BytesIO()
    c_pdf = canvas.Canvas(buf, pagesize=pagesize)

    # Pick drawing style
    if doc_type == "invoice":
        draw_fn = random.choice(INVOICE_STYLES)
    elif doc_type == "quotation":
        draw_fn = random.choice(QUOTATION_STYLES)
    elif doc_type == "price_list":
        draw_fn = draw_price_list
    else:
        # generic — use a quotation style
        draw_fn = random.choice(QUOTATION_STYLES)

    draw_fn(c_pdf, w, h, data, palette)
    c_pdf.showPage()
    c_pdf.save()

    if fmt == "pdf":
        # Write PDF directly
        with open(full_path, "wb") as f:
            f.write(buf.getvalue())
    elif fmt == "png":
        # Convert PDF to PNG using pdf2image-like approach with reportlab
        # We'll use a simpler method: re-render at screen resolution
        # Actually, let's use Pillow to convert from the PDF bytes
        # Since we don't have poppler, we'll render using reportlab + PIL
        _pdf_to_png(buf.getvalue(), full_path)

    return full_path


def _pdf_to_png(pdf_bytes: bytes, output_path: str, dpi: int = 150):
    """
    Convert single-page PDF to PNG.
    Uses reportlab's renderPM or falls back to a simple approach.
    """
    try:
        # Try using pypdfium2 if available
        import pypdfium2 as pdfium
        pdf = pdfium.PdfDocument(pdf_bytes)
        page = pdf[0]
        scale = dpi / 72
        bitmap = page.render(scale=scale)
        img = bitmap.to_pil()
        img.save(output_path, "PNG")
        pdf.close()
    except ImportError:
        # Fallback: save as PDF first, then note that conversion is needed
        # For the dataset, we'll save the PDF and convert with another tool
        pdf_path = output_path.replace(".png", ".pdf")
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        # Try using Pillow directly (limited PDF support)
        try:
            from subprocess import run, PIPE
            result = run(
                ["pdftoppm", "-png", "-r", str(dpi), "-singlefile",
                 pdf_path, output_path.replace(".png", "")],
                capture_output=True, timeout=30
            )
            if result.returncode == 0 and os.path.exists(output_path):
                os.remove(pdf_path)
            else:
                # If pdftoppm not available, keep the PDF and rename
                os.rename(pdf_path, output_path.replace(".png", ".pdf"))
                print(f"   [WARN] Could not convert to PNG: {output_path}")
        except Exception:
            os.rename(pdf_path, output_path.replace(".png", ".pdf"))
            print(f"   [WARN] Could not convert to PNG: {output_path}")


def main(base_dir=None):
    random.seed(SEED)

    if base_dir is None:
        base_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data")
    base_dir = os.path.abspath(base_dir)
    pairs_path = os.path.join(base_dir, "pairs.csv")
    attachments_dir = os.path.join(base_dir, "attachments")
    os.makedirs(attachments_dir, exist_ok=True)

    # Read pairs
    with open(pairs_path, "r") as f:
        reader = csv.DictReader(f)
        pairs = list(reader)

    # Filter to pairs with attachments
    pairs_with_attach = [p for p in pairs if p["attachment_path"]]
    print(f"Generating {len(pairs_with_attach)} documents...")

    generated = {"pdf": 0, "png": 0}
    errors = 0

    for i, pair in enumerate(pairs_with_attach):
        try:
            render_document(pair, base_dir)
            generated[pair["attachment_format"]] += 1
            if (i + 1) % 50 == 0:
                print(f"   [{i+1}/{len(pairs_with_attach)}] generated...")
        except Exception as e:
            errors += 1
            print(f"   [ERROR] {pair['pair_id']}: {e}")

    print(f"\n{'='*50}")
    print(f"DOCUMENT GENERATION COMPLETE")
    print(f"{'='*50}")
    print(f"PDFs generated:  {generated['pdf']}")
    print(f"PNGs generated:  {generated['png']}")
    print(f"Errors:          {errors}")

    # Verify files exist
    files = os.listdir(attachments_dir)
    print(f"Files in attachments/: {len(files)}")
    pdf_files = [f for f in files if f.endswith(".pdf")]
    png_files = [f for f in files if f.endswith(".png")]
    print(f"   .pdf: {len(pdf_files)}")
    print(f"   .png: {len(png_files)}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Render PDF/PNG attachments from pairs.csv")
    parser.add_argument(
        "--data_dir",
        default=None,
        help="Folder holding pairs.csv; attachments/ is written here (default: ../data)",
    )
    args = parser.parse_args()
    main(args.data_dir)
