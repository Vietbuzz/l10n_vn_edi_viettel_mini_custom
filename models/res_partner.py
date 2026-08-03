# -*- coding: utf-8 -*-

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    einvoice_name_vn = fields.Char(string="E-Invoice Name (VN)", oldname="custom_legal_name")

