{
    "name": "VN SInvoice - Mini Custom",
    "summary": "Customize buyer name/legal name sent to Viettel SInvoice",
    "version": "18.0.1.0.7",
    "category": "Accounting/Localizations",
    "license": "LGPL-3",
    "description": """
VN SInvoice - Mini Custom
=========================

Customize buyer name / legal name sent to Viettel SInvoice, harden
SInvoice XML/PDF download after send, let Invoicing users send
e-invoices via sudo credential access (password stays Settings-only),
round unitPrice to Product Price digits, preview JSON / draft PDF,
choose SInvoice payment method on Sale Order and Invoice (TM/CK or Không thu tiền / KTT).

See README.md in the module folder for full documentation.
""",
    "depends": [
        "l10n_vn_edi_viettel",
        "sale",
        "variant_description_invoice",
    ],
    "data": [
        "security/ir.model.access.csv",
        "views/res_partner_views.xml",
        "views/account_move_views.xml",
        "views/sale_order_views.xml",
        "wizard/l10n_vn_edi_json_viewer_views.xml",
        "wizard/l10n_vn_edi_pdf_preview_views.xml",
    ],
    "installable": True,
    "application": False,
}
