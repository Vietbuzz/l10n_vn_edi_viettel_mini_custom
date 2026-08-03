# -*- coding: utf-8 -*-

from odoo import api, models


class AccountMoveSendWizard(models.TransientModel):
    _inherit = "account.move.send.wizard"

    @api.depends("move_id")
    def _compute_sending_method_checkboxes(self):
        super()._compute_sending_method_checkboxes()
        for wizard in self:
            if wizard.move_id.company_id.country_id.code == "VN" and wizard.sending_method_checkboxes:
                checkboxes = dict(wizard.sending_method_checkboxes)
                if "email" in checkboxes:
                    checkboxes["email"] = {**checkboxes["email"], "checked": False}
                    wizard.sending_method_checkboxes = checkboxes
