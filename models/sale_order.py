# -*- coding: utf-8 -*-

from odoo import fields, models


class SaleOrder(models.Model):
    _inherit = "sale.order"

    sinvoice_payment_method = fields.Selection(
        selection=[
            ("TM/CK", "Tiền mặt / Chuyển khoản"),
            ("KTT", "Không thu tiền"),
        ],
        string="SInvoice Payment Method",
        default="TM/CK",
        copy=True,
    )

    def _prepare_invoice(self):
        values = super()._prepare_invoice()
        values["sinvoice_payment_method"] = self.sinvoice_payment_method or "TM/CK"
        return values
