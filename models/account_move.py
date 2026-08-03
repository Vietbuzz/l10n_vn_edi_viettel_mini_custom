# -*- coding: utf-8 -*-

import base64
import io
import logging
import zipfile

from odoo import _, fields, models
from odoo.exceptions import UserError

_logger = logging.getLogger(__name__)


class AccountMove(models.Model):
    _inherit = "account.move"

    def _l10n_vn_edi_fetch_invoice_xml_file_data(self):
        """Fetch XML from SInvoice without crashing the Send wizard.

        Viettel may return:
        - nested ZIP (outer -> inner -> xml) — standard Odoo expectation
        - flat ZIP containing .xml directly
        - empty / not-yet-ready / non-zip payload

        On any unpack failure, return a soft error so the invoice (already sent)
        is not rolled back by an uncaught BadZipFile.
        """
        self.ensure_one()
        files_data, error_message = self._l10n_vn_edi_fetch_invoice_file_data("ZIP")
        if error_message:
            return {}, error_message

        file_b64 = (files_data or {}).get("fileToBytes") or ""
        if not file_b64:
            return {}, _(
                "SInvoice XML is not ready yet. The invoice was already sent; "
                "please download the XML later from SInvoice or retry."
            )

        try:
            file_bytes = base64.b64decode(file_b64)
        except Exception:
            _logger.exception(
                "SInvoice XML base64 decode failed for move %s", self.id
            )
            return {}, _(
                "Could not decode SInvoice XML file. The invoice was already sent; "
                "please download it from SInvoice."
            )

        try:
            xml_payload = self._l10n_vn_edi_extract_xml_from_sinvoice_bytes(file_bytes)
        except Exception:
            _logger.exception(
                "SInvoice XML unpack failed for move %s", self.id
            )
            return {}, _(
                "Could not unpack SInvoice XML file. The invoice was already sent; "
                "please download it from SInvoice."
            )

        if not xml_payload:
            return {}, _(
                "No XML found in SInvoice ZIP response. The invoice was already sent; "
                "please download it from SInvoice."
            )
        return xml_payload, ""

    def _l10n_vn_edi_extract_xml_from_sinvoice_bytes(self, file_bytes):
        """Return XML attachment dict from SInvoice file bytes, or None."""
        if not file_bytes:
            return None

        # Raw XML (no ZIP wrapper)
        stripped = file_bytes.lstrip()
        if stripped.startswith(b"<?xml") or stripped.startswith(b"<"):
            return {
                "name": f"{(self.l10n_vn_edi_invoice_number or self.name or 'sinvoice').replace('/', '_')}.xml",
                "mimetype": "application/xml",
                "raw": file_bytes,
                "res_field": "l10n_vn_edi_sinvoice_xml_file",
            }

        if not zipfile.is_zipfile(io.BytesIO(file_bytes)):
            raise zipfile.BadZipFile("File is not a zip file")

        with zipfile.ZipFile(io.BytesIO(file_bytes)) as zip_file:
            # 1) Flat ZIP: XML at top level
            xml_from_flat = self._l10n_vn_edi_find_xml_in_zip(zip_file)
            if xml_from_flat:
                return xml_from_flat

            # 2) Nested ZIP: outer zip contains an inner zip (Odoo standard path)
            for info in zip_file.filelist:
                if info.is_dir():
                    continue
                inner_bytes = zip_file.read(info)
                if not zipfile.is_zipfile(io.BytesIO(inner_bytes)):
                    # Maybe a loose XML with unexpected extension
                    inner_stripped = inner_bytes.lstrip()
                    if inner_stripped.startswith(b"<?xml") or inner_stripped.startswith(b"<"):
                        name = info.filename if info.filename.endswith(".xml") else f"{info.filename}.xml"
                        return {
                            "name": name,
                            "mimetype": "application/xml",
                            "raw": inner_bytes,
                            "res_field": "l10n_vn_edi_sinvoice_xml_file",
                        }
                    continue
                with zipfile.ZipFile(io.BytesIO(inner_bytes)) as inner_zip:
                    xml_from_inner = self._l10n_vn_edi_find_xml_in_zip(inner_zip)
                    if xml_from_inner:
                        return xml_from_inner

        return None

    def _l10n_vn_edi_find_xml_in_zip(self, zip_file):
        """Find the first .xml entry in a ZipFile and return attachment dict."""
        for info in zip_file.filelist:
            if info.is_dir():
                continue
            if info.filename.lower().endswith(".xml"):
                return {
                    "name": info.filename,
                    "mimetype": "application/xml",
                    "raw": zip_file.read(info),
                    "res_field": "l10n_vn_edi_sinvoice_xml_file",
                }
        return None

    def _l10n_vn_edi_fetch_invoice_pdf_file_data(self):
        """Fetch PDF from SInvoice; soft-fail instead of crashing Send wizard."""
        self.ensure_one()
        try:
            return super()._l10n_vn_edi_fetch_invoice_pdf_file_data()
        except Exception:
            _logger.exception(
                "SInvoice PDF fetch failed for move %s", self.id
            )
            return {}, _(
                "Could not download SInvoice PDF file. The invoice was already sent; "
                "please download it from SInvoice."
            )

    def button_request_cancel(self):
        """TT78: do not cancel issued e-invoices; create a decreasing adjustment (credit note) instead."""
        vn_sent = self.filtered(lambda m: m.country_code == "VN" and m._l10n_vn_edi_is_sent() and m.l10n_vn_edi_invoice_state != "canceled")
        if vn_sent and vn_sent == self:
            action = self.env["ir.actions.actions"]._for_xml_id("account.action_view_account_move_reversal")
            action["context"] = {
                **self.env.context,
                "active_model": "account.move",
                "active_ids": vn_sent.ids,
                "default_reason": _("Cancel e-invoice (TT78) - create decreasing adjustment"),
                "default_l10n_vn_edi_adjustment_type": "1",
                "default_l10n_vn_edi_agreement_document_name": "NA",
                "default_l10n_vn_edi_agreement_document_date": fields.Datetime.now(),
            }
            return action
        return super().button_request_cancel()

    def _l10n_vn_edi_cancel_invoice(self, *args, **kwargs):
        """Hard block Viettel cancel API for TT78 compliance."""
        raise UserError(
            _("Theo Thông tư 78, không được hủy hoá đơn điện tử đã phát hành. Vui lòng tạo hoá đơn điều chỉnh giảm (credit note) để thay thế thao tác hủy.")
        )

    def _l10n_vn_edi_add_buyer_information(self, json_values):
        super()._l10n_vn_edi_add_buyer_information(json_values)
        self.ensure_one()

        buyer_info = json_values.get("buyerInfo")
        if not buyer_info:
            return

        partner_custom = (self.partner_id.einvoice_name_vn or "").strip()
        if partner_custom:
            buyer_info["buyerName"] = partner_custom

        commercial_partner = self.commercial_partner_id
        is_individual = getattr(commercial_partner, "company_type", False) == "person" or not commercial_partner.is_company
        commercial_custom = (commercial_partner.einvoice_name_vn or "").strip()
        use_custom_field = bool(partner_custom or commercial_custom)

        # Only apply the "retail" behavior (blank legal name for individuals) when the new field is defined.
        # Otherwise, keep the original behavior from the base module (can show both buyer and company names).
        if is_individual and use_custom_field:
            buyer_info["buyerLegalName"] = ""
            return

        if commercial_custom:
            buyer_info["buyerLegalName"] = commercial_custom

    def _l10n_vn_edi_add_general_invoice_information(self, json_values):
        super()._l10n_vn_edi_add_general_invoice_information(json_values)
        self.ensure_one()
        if self.country_code == "VN" and self.move_type == "out_refund":
            json_values.setdefault("generalInvoiceInfo", {})["adjustedNote"] = "Điều chỉnh giảm tiền"

    def _l10n_vn_edi_add_item_information(self, json_values):
        """TT78: decreasing adjustments (out_refund) keep quantity & unitPrice positive;
        isIncreaseItem=False (already set by base module) tells Viettel this is a decrease.
        Also uses variant_description_sale as itemName when available."""
        super()._l10n_vn_edi_add_item_information(json_values)
        self.ensure_one()

        item_info = json_values.get("itemInfo") or []
        product_lines = self.invoice_line_ids.filtered(lambda ln: ln.display_type == "product")
        for item, line in zip(item_info, product_lines):
            variant_desc = (line.variant_description_sale or "").strip()
            if variant_desc:
                item["itemName"] = variant_desc

        if self.country_code != "VN" or self.move_type != "out_refund":
            return

        for item in item_info:
            for key in ("unitPrice", "quantity", "itemTotalAmountWithoutTax", "taxAmount",
                        "itemTotalAmountAfterDiscount", "itemTotalAmountWithTax", "adjustmentTaxAmount"):
                if key in item:
                    item[key] = abs(item[key])
            item["isIncreaseItem"] = False

