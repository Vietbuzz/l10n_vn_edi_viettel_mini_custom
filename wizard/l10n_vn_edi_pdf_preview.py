# -*- coding: utf-8 -*-

from odoo import fields, models


class L10nVnEdiViettelPdfPreview(models.TransientModel):
    _name = "l10n_vn_edi_viettel.pdf.preview"
    _description = "SInvoice Draft PDF Preview"

    invoice_id = fields.Many2one(
        comodel_name="account.move",
        string="Invoice",
        readonly=True,
    )
    pdf_filename = fields.Char(string="File Name", readonly=True)
    pdf_file = fields.Binary(
        string="PDF Preview",
        readonly=True,
        attachment=False,
    )
