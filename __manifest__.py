{
    "name": "VN SInvoice - Mini Custom",
    "summary": "Customize buyer name/legal name sent to Viettel SInvoice",
    "version": "18.0.1.0.1",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "description": """
VN SInvoice - Mini Custom
=========================

Customize buyer name / legal name sent to Viettel SInvoice, and harden
SInvoice XML/PDF download so Send & Print does not crash after a successful send.

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

