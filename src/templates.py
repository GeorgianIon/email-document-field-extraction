"""
Email templates for each intent class.

Each class has two types of templates:
  - "explicit": email mentions key fields (amount, doc_number, date, currency)
  - "vague":    email is generic, fields are only in the attachment

Placeholders:
  {recipient}    - name/team of the buyer
  {sender_name}  - contact person at supplier
  {company}      - supplier company name
  {doc_number}   - document/invoice/quote number
  {amount}       - monetary amount (formatted)
  {currency}     - currency code or symbol
  {date}         - relevant date (due date, validity, effective)
  {items_desc}   - brief description of items/services
"""


# Item descriptions (used to fill {items_desc})

ITEM_DESCRIPTIONS = [
    "the requested mechanical components",
    "industrial-grade fasteners and fittings",
    "the electronic modules (batch Q2-2025)",
    "custom steel brackets per your specifications",
    "hydraulic pump assemblies",
    "packaging materials and shipping supplies",
    "replacement parts for production line B",
    "raw materials as per PO-2025-0443",
    "optical sensors and calibration kits",
    "chemical reagents for lab testing",
    "cable harnesses and connectors",
    "precision cutting tools",
    "thermal insulation panels",
    "stainless steel tubing (lot #4417)",
    "injection molding components",
    "PCB boards and microcontrollers",
    "safety valves and pressure regulators",
    "aluminium extrusion profiles",
    "welding consumables and electrodes",
    "conveyor belt rollers and bearings",
]


# Subject line templates per class

SUBJECT_TEMPLATES = {
    "quote_offer": [
        "Quotation {doc_number} - {company}",
        "Our offer for {items_desc}",
        "RE: Request for Quotation - {doc_number}",
        "Price quotation attached - {company}",
        "Quotation {doc_number} for your review",
        "{company} - Quotation {doc_number}",
        "Offer for {items_desc} - {doc_number}",
        "Commercial offer - {company}",
    ],
    "invoice_submission": [
        "Invoice {doc_number} - {company}",
        "Invoice attached - {doc_number}",
        "RE: Payment - Invoice {doc_number}",
        "{company} - Invoice {doc_number}",
        "Invoice for {items_desc}",
        "New invoice from {company}",
        "Invoice {doc_number} - please process",
        "Billing: {doc_number} - {company}",
    ],
    "price_validity_confirmation": [
        "RE: Price validity - {doc_number}",
        "Confirmation: prices still valid",
        "RE: Quotation {doc_number} - validity update",
        "{company} - price confirmation",
        "Our prices remain valid",
        "RE: Your inquiry about pricing",
        "Price validity extension - {doc_number}",
        "Confirmation of current pricing",
    ],
    "price_increase": [
        "Price adjustment notice - {company}",
        "Important: upcoming price changes",
        "Notice of price increase - effective {date}",
        "{company} - revised pricing",
        "Updated price list - {company}",
        "Price revision notice",
        "New pricing effective {date}",
        "Important update: pricing changes",
    ],
    "other": [
        "RE: Order status update",
        "Follow-up: recent delivery",
        "RE: Your inquiry",
        "{company} - general update",
        "Thank you for your order",
        "Delivery confirmation",
        "RE: Meeting follow-up",
        "Account update - {company}",
        "RE: Pending items",
        "Quick update from {company}",
    ],
}



# Body templates per class

# Each entry is a tuple: (body_template, explicitness)
# explicitness: "explicit" = mentions fields, "vague" = fields only in attachment

BODY_TEMPLATES = {
    "quote_offer": [
        #  EXPLICIT templates 
        (
            "Dear {recipient},\n\n"
            "Thank you for your inquiry. Please find attached our quotation "
            "{doc_number} for {items_desc}.\n\n"
            "The total quoted amount is {amount} {currency}, valid until {date}.\n\n"
            "Should you have any questions or require adjustments, please do not "
            "hesitate to contact us.\n\n"
            "Best regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Hi {recipient},\n\n"
            "As per your request, we are pleased to submit our commercial offer.\n\n"
            "Quotation number: {doc_number}\n"
            "Total: {amount} {currency}\n"
            "Validity: {date}\n\n"
            "The detailed breakdown is in the attached document. "
            "Please let us know if you'd like to proceed.\n\n"
            "Kind regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Dear {recipient},\n\n"
            "Further to our recent discussion, I am sending you our quotation "
            "ref. {doc_number} covering {items_desc}.\n\n"
            "The total comes to {amount} {currency}. This offer remains valid "
            "through {date}. Delivery terms and conditions are outlined in "
            "the attached document.\n\n"
            "Looking forward to your feedback.\n\n"
            "Regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Hello {recipient},\n\n"
            "We have prepared quotation {doc_number} as requested. "
            "The quoted value is {amount} {currency}, with a validity period "
            "ending on {date}.\n\n"
            "Full details are enclosed. We hope this meets your requirements "
            "and look forward to working with you.\n\n"
            "Best,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Dear {recipient},\n\n"
            "Attached is our quotation ({doc_number}) for the items you requested. "
            "The total price is {amount} {currency}.\n\n"
            "Please note that this offer expires on {date}. "
            "We would appreciate your confirmation at your earliest convenience.\n\n"
            "Thank you,\n{sender_name}\n{company}",
            "explicit"
        ),
        #  VAGUE templates 
        (
            "Dear {recipient},\n\n"
            "Please find attached our quotation for {items_desc} as discussed.\n\n"
            "All pricing details and terms are included in the attached document. "
            "Feel free to reach out if you need any clarification.\n\n"
            "Best regards,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Hi {recipient},\n\n"
            "As requested, I'm sending over our offer for your review. "
            "Everything is detailed in the attachment.\n\n"
            "Let me know if you have any questions or if anything needs to be adjusted.\n\n"
            "Cheers,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Dear {recipient},\n\n"
            "Following your request, we have prepared a quotation for "
            "{items_desc}. Please see the attached file for the full breakdown.\n\n"
            "We remain at your disposal for any further information.\n\n"
            "Regards,\n{sender_name}\n{company}",
            "vague"
        ),
    ],

    "invoice_submission": [
        #  EXPLICIT templates 
        (
            "Dear {recipient},\n\n"
            "Please find attached invoice {doc_number} in the amount of "
            "{amount} {currency}.\n\n"
            "Payment is due by {date}. If you have any questions regarding "
            "this invoice, please contact our accounting department.\n\n"
            "Thank you,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Hi {recipient},\n\n"
            "We are sending you invoice no. {doc_number} for {items_desc}.\n\n"
            "Invoice amount: {amount} {currency}\n"
            "Due date: {date}\n\n"
            "The invoice is attached in the agreed format. "
            "Please process at your earliest convenience.\n\n"
            "Best regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Dear {recipient},\n\n"
            "Attached is invoice {doc_number}, issued for the recent delivery of "
            "{items_desc}. The total payable is {amount} {currency}, "
            "with a payment deadline of {date}.\n\n"
            "Please confirm receipt of this invoice.\n\n"
            "Regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Hello {recipient},\n\n"
            "This email contains invoice {doc_number} for your records.\n\n"
            "Amount due: {amount} {currency}\n"
            "Payment terms: Net 30 (due {date})\n\n"
            "Should you require a revised copy or have billing questions, "
            "please don't hesitate to reach out.\n\n"
            "Kind regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Dear {recipient},\n\n"
            "Please find enclosed our invoice {doc_number} for {amount} {currency} "
            "covering {items_desc}.\n\n"
            "The due date for payment is {date}. We kindly ask that you process "
            "this within the agreed timeline.\n\n"
            "Thank you for your business.\n\n"
            "Best,\n{sender_name}\n{company}",
            "explicit"
        ),
        #  VAGUE templates 
        (
            "Dear {recipient},\n\n"
            "Please find the attached invoice for the goods delivered last week.\n\n"
            "Let us know if everything is in order.\n\n"
            "Regards,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Hi {recipient},\n\n"
            "Attached is the invoice for your recent order. "
            "All details are in the document.\n\n"
            "Thank you,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Dear {recipient},\n\n"
            "I'm sending you the invoice for {items_desc} as agreed. "
            "Please review the attached and process accordingly.\n\n"
            "Best regards,\n{sender_name}\n{company}",
            "vague"
        ),
    ],

    "price_validity_confirmation": [
        #  EXPLICIT templates 
        (
            "Dear {recipient},\n\n"
            "Following your inquiry, we are pleased to confirm that the prices "
            "in quotation {doc_number} remain valid until {date}.\n\n"
            "The total amount of {amount} {currency} as originally quoted "
            "is still applicable. Please feel free to place your order "
            "before the expiration date.\n\n"
            "Best regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Hi {recipient},\n\n"
            "This is to confirm that our offer {doc_number} is still active.\n\n"
            "Confirmed amount: {amount} {currency}\n"
            "Valid through: {date}\n\n"
            "Let us know if you wish to proceed.\n\n"
            "Regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Dear {recipient},\n\n"
            "In response to your email, we confirm that quotation {doc_number} "
            "for {amount} {currency} is still valid. The prices will be honored "
            "until {date}.\n\n"
            "We look forward to your confirmation.\n\n"
            "Kind regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Hello {recipient},\n\n"
            "Good news — the pricing from our quotation {doc_number} has not changed. "
            "The quoted total of {amount} {currency} holds until {date}.\n\n"
            "Don't hesitate to reach out if you need anything else.\n\n"
            "Best,\n{sender_name}\n{company}",
            "explicit"
        ),
        # VAGUE templates
        (
            "Dear {recipient},\n\n"
            "We can confirm that the prices from our previous quotation "
            "are still valid. No changes have been made.\n\n"
            "Please let us know if you'd like to go ahead with the order.\n\n"
            "Regards,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Hi {recipient},\n\n"
            "As requested, we confirm that our offer remains unchanged. "
            "All previously communicated terms are still in effect.\n\n"
            "Best regards,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Dear {recipient},\n\n"
            "Thank you for checking in. We are happy to confirm that "
            "the quoted prices have not been revised and remain applicable.\n\n"
            "Kind regards,\n{sender_name}\n{company}",
            "vague"
        ),
    ],

    "price_increase": [
        # EXPLICIT templates
        (
            "Dear {recipient},\n\n"
            "We regret to inform you that due to increases in raw material costs, "
            "we will need to adjust our pricing effective {date}.\n\n"
            "The new price for {items_desc} will be {amount} {currency}. "
            "We understand this may be inconvenient and are happy to discuss "
            "any concerns you may have.\n\n"
            "Sincerely,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Hi {recipient},\n\n"
            "Please be advised that our prices will be updated as of {date}.\n\n"
            "New pricing: {amount} {currency} for {items_desc}.\n\n"
            "Orders placed before {date} will be honored at the current rates. "
            "We appreciate your understanding.\n\n"
            "Best regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Dear {recipient},\n\n"
            "This notice is to inform you of an upcoming price revision for "
            "{items_desc}.\n\n"
            "Effective date: {date}\n"
            "Revised amount: {amount} {currency}\n\n"
            "We value your partnership and have done our best to keep "
            "the adjustment as minimal as possible.\n\n"
            "Regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        (
            "Hello {recipient},\n\n"
            "Due to rising operational and supply chain costs, we must "
            "unfortunately increase the price of {items_desc} to "
            "{amount} {currency}, starting from {date}.\n\n"
            "Please reach out if you would like to discuss volume-based "
            "discounts or alternative options.\n\n"
            "Kind regards,\n{sender_name}\n{company}",
            "explicit"
        ),
        # VAGUE templates
        (
            "Dear {recipient},\n\n"
            "We would like to notify you of upcoming changes to our price list. "
            "The updated pricing details are attached.\n\n"
            "We apologize for any inconvenience and remain available to discuss.\n\n"
            "Regards,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Hi {recipient},\n\n"
            "Please note that we will be revising our pricing structure "
            "in the near future. Details will follow shortly.\n\n"
            "Thank you for your understanding.\n\n"
            "Best,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Dear {recipient},\n\n"
            "This is a courtesy notice regarding an upcoming adjustment "
            "to our standard pricing. The changes reflect increased costs "
            "across several product categories.\n\n"
            "We will share the updated price list soon.\n\n"
            "Sincerely,\n{sender_name}\n{company}",
            "vague"
        ),
    ],

    "other": [
        (
            "Dear {recipient},\n\n"
            "Thank you for your recent order. We wanted to let you know "
            "that it has been received and is currently being processed.\n\n"
            "We will notify you once the shipment is ready.\n\n"
            "Best regards,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Hi {recipient},\n\n"
            "Just a quick follow-up on our conversation from last week. "
            "Please let us know if you need any additional information "
            "from our side.\n\n"
            "Thanks,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Dear {recipient},\n\n"
            "We wanted to confirm that your delivery has been dispatched "
            "and should arrive within 3-5 business days.\n\n"
            "Tracking information will be sent separately.\n\n"
            "Regards,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Hello {recipient},\n\n"
            "We are writing to inform you that our offices will be closed "
            "for the holiday period from December 23 to January 2. "
            "Orders placed after December 20 will be processed in January.\n\n"
            "Happy holidays!\n\n"
            "Best,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Dear {recipient},\n\n"
            "Thank you for your continued partnership. We are reaching out "
            "to schedule our annual review meeting. Would any time next week "
            "work for you?\n\n"
            "Looking forward to your reply.\n\n"
            "Kind regards,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Hi {recipient},\n\n"
            "We have updated our bank account details for future payments. "
            "Please find the new information below and update your records.\n\n"
            "If you have any questions, please contact our finance team.\n\n"
            "Best regards,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Dear {recipient},\n\n"
            "This is a reminder that there are outstanding items on your account. "
            "Please review and let us know if there's anything we can help with.\n\n"
            "Thank you,\n{sender_name}\n{company}",
            "vague"
        ),
        (
            "Hello {recipient},\n\n"
            "We wanted to share some exciting news — {company} has recently "
            "expanded our product line. We'd love to discuss how our new "
            "offerings might benefit your operations.\n\n"
            "Shall we set up a call?\n\n"
            "Regards,\n{sender_name}\n{company}",
            "vague"
        ),
    ],
}
