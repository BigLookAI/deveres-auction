from odoo.tests import TransactionCase


class TestSorConsignmentAgreementsAuctionHouse(TransactionCase):
    """Tests for sor_consignment_agreements_auction_house — Auction Terms fields on sor.agreement."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.partner = cls.env['res.partner'].create({'name': 'Test Consignor'})
        cls.agreement = cls.env['sor.agreement'].create({
            'agreement_type': 'consignment_in',
            'primary_partner_id': cls.partner.id,
            'company_id': cls.company.id,
        })

    def test_auction_fields_present(self):
        """sor.agreement has all four auction house fields."""
        self.assertTrue(hasattr(self.agreement, 'catalogue_estimate'))
        self.assertTrue(hasattr(self.agreement, 'reserve_price'))
        self.assertTrue(hasattr(self.agreement, 'vendor_commission_pct'))
        self.assertTrue(hasattr(self.agreement, 'vendor_commission_amount'))

    def test_fields_persist_on_save(self):
        """Auction terms fields persist after write and reload."""
        self.agreement.write({
            'catalogue_estimate': 5000.0,
            'reserve_price': 3500.0,
            'vendor_commission_pct': 15.0,
        })
        self.agreement.invalidate_recordset()
        self.assertEqual(self.agreement.catalogue_estimate, 5000.0)
        self.assertEqual(self.agreement.reserve_price, 3500.0)
        self.assertEqual(self.agreement.vendor_commission_pct, 15.0)

    def test_fields_optional(self):
        """Agreement can be saved without any auction terms values."""
        agreement = self.env['sor.agreement'].create({
            'agreement_type': 'consignment_in',
            'primary_partner_id': self.partner.id,
            'company_id': self.company.id,
        })
        self.assertEqual(agreement.catalogue_estimate, 0.0)
        self.assertEqual(agreement.reserve_price, 0.0)
        self.assertEqual(agreement.vendor_commission_pct, 0.0)

    def test_vendor_commission_amount_is_zero_at_mvp(self):
        """vendor_commission_amount always returns 0.0 at MVP (lot-linking not yet implemented)."""
        self.agreement.vendor_commission_pct = 20.0
        self.assertEqual(self.agreement.vendor_commission_amount, 0.0)

    def test_currency_id_from_company(self):
        """currency_id is derived from company currency."""
        self.assertEqual(self.agreement.currency_id, self.company.currency_id)
