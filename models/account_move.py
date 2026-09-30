# -*- coding: utf-8 -*-

import base64
import io
import json
import logging
import zipfile

from odoo import _, fields, models
from odoo.exceptions import UserError
from odoo.tools.float_utils import float_repr, float_round

_logger = logging.getLogger(__name__)

# SInvoice rejects unitPrice with more than 6 decimal digits.
_SINVOICE_UNIT_PRICE_MAX_DIGITS = 6


class AccountMove(models.Model):
    _inherit = "account.move"

    sinvoice_payment_method = fields.Selection(
        selection=[
            ("TM/CK", "Tiền mặt / Chuyển khoản"),
            ("KTT", "Không thu tiền"),
        ],
        string="SInvoice Payment Method",
        default="TM/CK",
        copy=True,
    )

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

    # -------------------------------------------------------------------------
    # SInvoice credentials access (Accounting users)
    # -------------------------------------------------------------------------

    def _l10n_vn_edi_get_credentials_company(self):
        """Resolve credential company with sudo to avoid field ACL AccessError.

        SInvoice credentials on res.company stay restricted to Settings
        (base.group_system). Invoice users only need them in the send flow.
        """
        self.ensure_one()
        return super(AccountMove, self.sudo())._l10n_vn_edi_get_credentials_company()

    def _l10n_vn_edi_get_access_token(self):
        """Read/write token & login credentials under sudo for invoice users."""
        self.ensure_one()
        return super(AccountMove, self.sudo())._l10n_vn_edi_get_access_token()

    def _l10n_vn_edi_check_invoice_configuration(self):
        """Validate SInvoice setup under sudo so credential field ACL does not block send."""
        self.ensure_one()
        return super(AccountMove, self.sudo())._l10n_vn_edi_check_invoice_configuration()

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

    def _l10n_vn_edi_add_payment_information(self, json_values):
        """Send paymentMethodName as free text (Viettel accepts plain text)."""
        self.ensure_one()
        if self.country_code == "VN":
            json_values["payments"] = [{
                "paymentMethodName": self.sinvoice_payment_method or "TM/CK",
            }]
            return
        return super()._l10n_vn_edi_add_payment_information(json_values)

    def _l10n_vn_edi_add_general_invoice_information(self, json_values):
        super()._l10n_vn_edi_add_general_invoice_information(json_values)
        self.ensure_one()
        if self.country_code == "VN" and self.move_type == "out_refund":
            json_values.setdefault("generalInvoiceInfo", {})["adjustedNote"] = "Điều chỉnh giảm tiền"

    def _l10n_vn_edi_get_unit_price_digits(self):
        """Digits for unitPrice: Product Price accuracy, capped at SInvoice max (6)."""
        digits = self.env["decimal.precision"].precision_get("Product Price")
        return min(max(int(digits or 0), 0), _SINVOICE_UNIT_PRICE_MAX_DIGITS)

    def _l10n_vn_edi_round_unit_price(self, amount):
        """Round unit price for SInvoice JSON (avoid float artifacts / excess decimals)."""
        digits = self._l10n_vn_edi_get_unit_price_digits()
        rounded = float_round(float(amount or 0.0), precision_digits=digits)
        return float(float_repr(rounded, digits))

    def _l10n_vn_edi_add_item_information(self, json_values):
        """Customize itemInfo built by the base module.

        Each item is first paired with the invoice line it was built from, matching
        whichever base version is running:
        - Odoo >= 1b28fc90fb: base emits product, line_note (selection=2) and discount lines.
        - Older base: base emits product lines only.
        If neither matches the item count, raise instead of sending misaligned items.

        On product items only (notes are skipped):
        - use variant_description_sale as itemName when available;
        - TT78: decreasing adjustments (out_refund) keep quantity & amounts positive,
          isIncreaseItem=False tells Viettel this is a decrease;
        - round unitPrice to Product Price digits (max 6 for SInvoice).

        Finally rebuild itemInfo in invoice line order so each note (Add a note) appears
        exactly once as selection=2 (no STT, no amount), whichever base version emitted it.
        """
        super()._l10n_vn_edi_add_item_information(json_values)
        self.ensure_one()

        item_info = json_values.get("itemInfo") or []
        base_lines = self.invoice_line_ids.filtered(
            lambda ln: ln.display_type in ("product", "line_note", "discount")
        )
        if len(item_info) != len(base_lines):
            base_lines = self.invoice_line_ids.filtered(lambda ln: ln.display_type == "product")
        if len(item_info) != len(base_lines):
            raise UserError(_(
                "Cannot build SInvoice items for %(invoice)s: %(items)s items were generated "
                "but %(lines)s matching invoice lines were found. Please contact your administrator.",
                invoice=self.name,
                items=len(item_info),
                lines=len(base_lines),
            ))
        item_by_line_id = dict(zip(base_lines.ids, item_info))

        product_pairs = [
            (line, item_by_line_id[line.id])
            for line in base_lines
            if line.display_type != "line_note" and item_by_line_id[line.id].get("selection") != 2
        ]
        for line, item in product_pairs:
            variant_desc = (line.variant_description_sale or "").strip()
            if variant_desc:
                item["itemName"] = variant_desc

        if self.country_code == "VN" and self.move_type == "out_refund":
            for _line, item in product_pairs:
                for key in ("unitPrice", "quantity", "itemTotalAmountWithoutTax", "taxAmount",
                            "itemTotalAmountAfterDiscount", "itemTotalAmountWithTax", "adjustmentTaxAmount"):
                    if key in item:
                        item[key] = abs(item[key])
                item["isIncreaseItem"] = False

        if self.country_code == "VN":
            for _line, item in product_pairs:
                if "unitPrice" in item:
                    item["unitPrice"] = self._l10n_vn_edi_round_unit_price(item["unitPrice"])

            # Viettel selection=2 is for notes (no STT, no amount). Rebuild itemInfo in
            # invoice line order; add notes ourselves only when base did not emit them.
            ordered_items = []
            for line in self.invoice_line_ids.sorted(key=lambda ln: (ln.sequence, ln.id)):
                item = item_by_line_id.get(line.id)
                if item is not None:
                    if line.display_type == "line_note" or item.get("selection") == 2:
                        note_name = (item.get("itemName") or "").strip()
                        if not note_name:
                            continue
                        item["itemName"] = note_name
                    ordered_items.append(item)
                elif line.display_type == "line_note":
                    note_name = (line.name or "").strip()
                    if note_name:
                        ordered_items.append({
                            "selection": 2,
                            "itemName": note_name,
                        })
            json_values["itemInfo"] = ordered_items

    def _l10n_vn_edi_generate_preview_invoice_json(self):
        """Build SInvoice JSON for debug/preview without permanently changing issue date."""
        self.ensure_one()
        previous_issue_date = self.l10n_vn_edi_issue_date
        try:
            return self._l10n_vn_edi_generate_invoice_json()
        finally:
            self.l10n_vn_edi_issue_date = previous_issue_date

    def action_l10n_vn_edi_view_payload_json(self):
        """Open a wizard with the JSON payload that would be sent to SInvoice."""
        self.ensure_one()
        if self.country_code != "VN" or self.move_type not in ("out_invoice", "out_refund"):
            raise UserError(_("SInvoice JSON preview is only available for Vietnamese customer invoices."))

        json_values = self._l10n_vn_edi_generate_preview_invoice_json()
        viewer = self.env["l10n_vn_edi_viettel.json.viewer"].create({
            "invoice_id": self.id,
            "json_content": json.dumps(json_values, ensure_ascii=False, indent=2, default=str),
            "unit_price_digits": self._l10n_vn_edi_get_unit_price_digits(),
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("SInvoice JSON Preview"),
            "res_model": "l10n_vn_edi_viettel.json.viewer",
            "view_mode": "form",
            "res_id": viewer.id,
            "target": "new",
        }

    def action_l10n_vn_edi_preview_draft_pdf(self):
        """Call Viettel createInvoiceDraftPreview and show the returned PDF.

        Payload is the same as createInvoice, but SInvoice does not store or issue
        the invoice (API 7.20 in partner webservice docs).
        """
        self.ensure_one()
        if self.country_code != "VN" or self.move_type not in ("out_invoice", "out_refund"):
            raise UserError(_("SInvoice PDF preview is only available for Vietnamese customer invoices."))

        errors = self._l10n_vn_edi_check_invoice_configuration()
        if errors:
            raise UserError("\n".join(errors))

        from odoo.addons.l10n_vn_edi_viettel.models.account_move import (
            SINVOICE_API_URL,
            _l10n_vn_edi_send_request,
        )

        json_values = self._l10n_vn_edi_generate_preview_invoice_json()
        access_token, error = self._l10n_vn_edi_get_access_token()
        if error:
            raise UserError(error)

        response, error_message = _l10n_vn_edi_send_request(
            method="POST",
            url=f"{SINVOICE_API_URL}InvoiceAPI/InvoiceUtilsWS/createInvoiceDraftPreview/{self.company_id.vat}",
            json_data=json_values,
            cookies={"access_token": access_token},
        )
        if error_message:
            raise UserError(error_message)

        error_code = response.get("errorCode")
        if error_code:
            raise UserError(
                _("SInvoice draft preview failed: %(code)s — %(desc)s",
                  code=error_code,
                  desc=response.get("description") or "")
            )

        file_b64 = response.get("fileToBytes")
        if not file_b64:
            raise UserError(_("SInvoice draft preview returned no PDF content."))

        filename = response.get("fileName") or f"{(self.name or 'sinvoice_preview').replace('/', '_')}.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"

        viewer = self.env["l10n_vn_edi_viettel.pdf.preview"].create({
            "invoice_id": self.id,
            "pdf_filename": filename,
            "pdf_file": file_b64,
        })
        return {
            "type": "ir.actions.act_window",
            "name": _("SInvoice Draft PDF Preview"),
            "res_model": "l10n_vn_edi_viettel.pdf.preview",
            "view_mode": "form",
            "res_id": viewer.id,
            "target": "new",
        }

