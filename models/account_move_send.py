# -*- coding: utf-8 -*-

import logging

from odoo import _, models

_logger = logging.getLogger(__name__)


class AccountMoveSend(models.AbstractModel):
    _inherit = "account.move.send"

    def _call_web_service_after_invoice_pdf_render(self, invoices_data):
        """Do not crash Send & Print when SInvoice XML/PDF download fails.

        By this point the invoice may already be sent on Viettel. Soft-fail
        download errors so the wizard can finish and the user can get files
        later from SInvoice.
        """
        try:
            return super()._call_web_service_after_invoice_pdf_render(invoices_data)
        except Exception:
            _logger.exception(
                "SInvoice post-send file download failed; invoice may already be sent"
            )
            for invoice, invoice_data in invoices_data.items():
                if invoice.l10n_vn_edi_invoice_state != "sent":
                    continue
                invoice_data["error"] = {
                    "error_title": _("Error when receiving SInvoice files."),
                    "errors": [
                        _(
                            "Could not download SInvoice XML/PDF. "
                            "The invoice was already sent to SInvoice; "
                            "please download the files from SInvoice if needed."
                        )
                    ],
                }
                invoice.with_context(no_new_invoice=True).message_post(
                    body=_(
                        "Invoice sent to SInvoice, but downloading XML/PDF failed. "
                        "Please download the files from SInvoice if needed."
                    ),
                )
            if self._can_commit():
                self._cr.commit()
