# -*- coding: utf-8 -*-

from freezegun import freeze_time

from odoo import Command
from odoo.addons.account.tests.common import AccountTestInvoicingCommon
from odoo.tests import tagged


@tagged("post_install_l10n", "post_install", "-at_install")
class TestSInvoiceItemInfo(AccountTestInvoicingCommon):

    @classmethod
    @AccountTestInvoicingCommon.setup_country("vn")
    def setUpClass(cls):
        super().setUpClass()
        template = cls.env["l10n_vn_edi_viettel.sinvoice.template"].create({
            "name": "1/001",
            "template_invoice_type": "1",
        })
        cls.symbol = cls.env["l10n_vn_edi_viettel.sinvoice.symbol"].create({
            "name": "K24TUT",
            "invoice_template_id": template.id,
        })
        cls.partner_a.country_id = cls.env.ref("base.vn")
        cls.product_promo = cls._create_product(name="Promo gift", default_code="PROMO", lst_price=0.0)
        cls.product_paid = cls._create_product(name="Paid product", default_code="PAID", lst_price=229630.0)
        cls.product_fee = cls._create_product(name="Logistics fee", default_code="SHIP", lst_price=5093.0)

    @freeze_time("2024-01-01")
    def test_item_info_note_between_products(self):
        """Promo (0) -> note -> paid product -> logistics fee: every product item keeps
        its own code/name/price and the note is emitted exactly once."""
        invoice = self.env["account.move"].create({
            "move_type": "out_invoice",
            "partner_id": self.partner_a.id,
            "invoice_date": "2024-01-01",
            "l10n_vn_edi_invoice_symbol": self.symbol.id,
            "invoice_line_ids": [
                Command.create({
                    "sequence": 10,
                    "product_id": self.product_promo.id,
                    "price_unit": 0.0,
                    "tax_ids": [Command.clear()],
                    "variant_description_sale": "Quà tặng KM",
                }),
                Command.create({
                    "sequence": 20,
                    "display_type": "line_note",
                    "name": "Hàng khuyến mại không thu tiền",
                }),
                Command.create({
                    "sequence": 30,
                    "product_id": self.product_paid.id,
                    "price_unit": 229630.0,
                    "tax_ids": [Command.clear()],
                    "variant_description_sale": "Sản phẩm trả tiền",
                }),
                Command.create({
                    "sequence": 40,
                    "product_id": self.product_fee.id,
                    "price_unit": 5093.0,
                    "tax_ids": [Command.clear()],
                }),
            ],
        })
        invoice.action_post()
        fee_name = invoice.invoice_line_ids.filtered(lambda ln: ln.product_id == self.product_fee).name

        items = invoice._l10n_vn_edi_generate_invoice_json()["itemInfo"]

        self.assertEqual(len(items), 4)
        self.assertEqual(items[1], {"selection": 2, "itemName": "Hàng khuyến mại không thu tiền"})
        self.assertEqual(
            [(it["itemCode"], it["itemName"], it["unitPrice"], it["itemTotalAmountWithTax"])
             for i, it in enumerate(items) if i != 1],
            [
                ("PROMO", "Quà tặng KM", 0.0, 0.0),
                ("PAID", "Sản phẩm trả tiền", 229630.0, 229630.0),
                ("SHIP", fee_name, 5093.0, 5093.0),
            ],
        )
        self.assertEqual(sum(it.get("itemTotalAmountWithTax", 0) for it in items), 234723.0)
