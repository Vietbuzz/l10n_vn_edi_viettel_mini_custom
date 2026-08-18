# -*- coding: utf-8 -*-

from odoo import fields, models


class L10nVnEdiViettelJsonViewer(models.TransientModel):
    _name = "l10n_vn_edi_viettel.json.viewer"
    _description = "SInvoice JSON Payload Viewer"

    invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
        readonly=True,
    )
    unit_price_digits = fields.Integer(
        string="Unit Price Digits",
        readonly=True,
        help="Decimal digits applied to unitPrice (Product Price, capped at 6).",
    )
    json_content = fields.Text(
        string="JSON Payload",
        readonly=True,
    )
