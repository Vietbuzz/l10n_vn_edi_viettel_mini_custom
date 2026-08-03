{
    "name": "VN SInvoice - Mini Custom",
    "summary": "Customize buyer name/legal name sent to Viettel SInvoice",
    "version": "18.0.1.0.2",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "description": """
VN SInvoice - Mini Custom
=========================

Customize buyer name / legal name sent to Viettel SInvoice, harden
SInvoice XML/PDF download after send, and let Invoicing users send
e-invoices via sudo credential access (password stays Settings-only).

See README.md in the module folder for full documentation.
""",
    "depends": [
        "l10n_vn_edi_viettel",
        "variant_description_invoice",
    ],
    "data": [
        "views/res_partner_views.xml",
    ],
    "installable": True,
    "application": False,
}

