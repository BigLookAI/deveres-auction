"""
Tests for sor_auction_documents.

Coverage:
  1. Module installs — fields present on sor.lot, res.company; action methods present on sor.event.
  2. hammer_price_vat_included — defaults False when company setting is off; defaults True when on.
  3. consignor_id — lot saves without consignor; consignor can be set manually.
  4. Company settings fields persist — auction_sale_terms, auction_bank_details, licence ref, director sig.
  5. Pre-Sale Advice — batch generation creates records grouped by consignor; idempotent re-run.
  6. Post-Sale Advice — batch generation for sold/passed lots only.
  7. Vendor Settlement Statement — lifecycle; sequence; commission totals; re-run protection.
"""
from odoo.tests import TransactionCase, tagged

# ---------------------------------------------------------------------------
# Class 1 — Module install verification (no fixtures required)
# ---------------------------------------------------------------------------


@tagged('post_install', '-at_install')
class TestSorAuctionDocumentsInstall(TransactionCase):
    """Field and method presence after module installation."""

    def test_consignor_id_present_on_lot(self):
        self.assertIn('consignor_id', self.env['sor.lot']._fields)

    def test_hammer_price_vat_included_present_on_lot(self):
        self.assertIn('hammer_price_vat_included', self.env['sor.lot']._fields)

    def test_pre_sale_advice_id_present_on_lot(self):
        self.assertIn('pre_sale_advice_id', self.env['sor.lot']._fields)

    def test_post_sale_advice_id_present_on_lot(self):
        self.assertIn('post_sale_advice_id', self.env['sor.lot']._fields)

    def test_vendor_settlement_id_present_on_lot(self):
        self.assertIn('vendor_settlement_id', self.env['sor.lot']._fields)

    def test_auction_sale_terms_present_on_company(self):
        self.assertIn('auction_sale_terms', self.env['res.company']._fields)

    def test_auction_bank_details_present_on_company(self):
        self.assertIn('auction_bank_details', self.env['res.company']._fields)

    def test_auction_licence_ref_present_on_company(self):
        self.assertIn('auction_licence_ref', self.env['res.company']._fields)

    def test_auction_director_signature_present_on_company(self):
        self.assertIn('auction_director_signature', self.env['res.company']._fields)

    def test_hammer_price_vat_included_present_on_company(self):
        self.assertIn('hammer_price_vat_included', self.env['res.company']._fields)

    def test_auction_vat_notice_present_on_company(self):
        self.assertIn('auction_vat_notice', self.env['res.company']._fields)

    def test_action_generate_pre_sale_advices_exists(self):
        self.assertTrue(hasattr(self.env['sor.event'], 'action_generate_pre_sale_advices'))

    def test_action_generate_post_sale_advices_exists(self):
        self.assertTrue(hasattr(self.env['sor.event'], 'action_generate_post_sale_advices'))

    def test_action_generate_vendor_settlements_exists(self):
        self.assertTrue(hasattr(self.env['sor.event'], 'action_generate_vendor_settlements'))

    def test_pre_sale_advice_model_exists(self):
        self.assertIn('sor.pre.sale.advice', self.env)

    def test_post_sale_advice_model_exists(self):
        self.assertIn('sor.post.sale.advice', self.env)

    def test_vendor_settlement_model_exists(self):
        self.assertIn('sor.vendor.settlement', self.env)


# ---------------------------------------------------------------------------
# Class 2 — Fixture-backed tests
# ---------------------------------------------------------------------------


@tagged('post_install', '-at_install')
class TestSorAuctionDocuments(TransactionCase):
    """hammer_price_vat_included defaults, settings persistence, document generation."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.consignor_a = cls.env['res.partner'].create({
            'name': 'Test Consignor A',
            'ref': 'CON-001',
        })
        cls.consignor_b = cls.env['res.partner'].create({
            'name': 'Test Consignor B',
            'ref': 'CON-002',
        })

        cls.product = cls.env['product.template'].search(
            [('is_storable', '=', True)], limit=1,
        )
        if not cls.product:
            msg = 'No storable product found — cannot run sor_auction_documents tests'
            raise RuntimeError(msg)

        cls.event = cls.env['sor.event'].create({
            'name': 'Test Auction AD',
            'event_type': 'auction',
            'date_start': '2026-06-01 10:00:00',
            'company_id': cls.company.id,
            'sale_number': 'A999',
        })

    def _make_lot(self, **kwargs):
        vals = {'product_id': self.product.id, 'company_id': self.company.id}
        vals.update(kwargs)
        return self.env['sor.lot'].create(vals)

    # ------------------------------------------------------------------
    # hammer_price_vat_included
    # ------------------------------------------------------------------

    def test_hammer_price_vat_included_defaults_false(self):
        self.company.hammer_price_vat_included = False
        lot = self._make_lot()
        self.assertFalse(lot.hammer_price_vat_included)

    def test_hammer_price_vat_included_defaults_true_from_company(self):
        self.company.hammer_price_vat_included = True
        lot = self._make_lot()
        self.assertTrue(lot.hammer_price_vat_included)

    # ------------------------------------------------------------------
    # consignor_id
    # ------------------------------------------------------------------

    def test_lot_saves_without_consignor(self):
        lot = self._make_lot()
        self.assertFalse(lot.consignor_id)

    def test_consignor_id_can_be_set_manually(self):
        lot = self._make_lot(consignor_id=self.consignor_a.id)
        self.assertEqual(lot.consignor_id, self.consignor_a)

    # ------------------------------------------------------------------
    # Company settings persistence
    # ------------------------------------------------------------------

    def test_auction_sale_terms_persists(self):
        self.company.auction_sale_terms = '<p>Test sale terms</p>'
        self.company.flush_recordset(['auction_sale_terms'])
        self.company.invalidate_recordset(['auction_sale_terms'])
        self.assertIn('Test sale terms', self.company.auction_sale_terms)

    def test_auction_bank_details_persists(self):
        self.company.auction_bank_details = 'IBAN: IE12 BOFI 9000 0112 3456 78'
        self.assertEqual(
            self.company.auction_bank_details, 'IBAN: IE12 BOFI 9000 0112 3456 78',
        )

    def test_auction_licence_ref_persists(self):
        self.company.auction_licence_ref = 'PSRA Licence No. 002261'
        self.assertEqual(self.company.auction_licence_ref, 'PSRA Licence No. 002261')

    def test_auction_director_signature_persists(self):
        self.company.auction_director_signature = 'Rory Guthrie, Director'
        self.assertEqual(self.company.auction_director_signature, 'Rory Guthrie, Director')

    def test_auction_vat_notice_persists(self):
        self.company.auction_vat_notice = 'VAT is accounted for under the margin scheme.'
        self.assertEqual(
            self.company.auction_vat_notice, 'VAT is accounted for under the margin scheme.',
        )

    # ------------------------------------------------------------------
    # Pre-Sale Advice — batch generation
    # ------------------------------------------------------------------

    def test_pre_sale_advice_batch_creates_per_consignor(self):
        """One PSA record per consignor for catalogued lots."""
        lot_a = self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='catalogued',
        )
        self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_b.id,
            state='catalogued',
        )
        self.event.action_generate_pre_sale_advices()
        advices = self.env['sor.pre.sale.advice'].search([('event_id', '=', self.event.id)])
        self.assertEqual(len(advices), 2)
        consignors = advices.mapped('consignor_id')
        self.assertIn(self.consignor_a, consignors)
        self.assertIn(self.consignor_b, consignors)
        # Lots are linked
        psa_a = advices.filtered(lambda p: p.consignor_id == self.consignor_a)
        self.assertEqual(lot_a.pre_sale_advice_id, psa_a)

    def test_pre_sale_advice_excludes_lots_without_consignor(self):
        lot_no_consignor = self._make_lot(
            auction_id=self.event.id,
            state='catalogued',
        )
        # Add another with consignor so batch doesn't fail with UserError
        self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='catalogued',
        )
        self.event.action_generate_pre_sale_advices()
        self.assertFalse(lot_no_consignor.pre_sale_advice_id)

    def test_pre_sale_advice_idempotent_rerun(self):
        """Re-running batch generation does not create duplicate PSA records."""
        self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='catalogued',
        )
        self.event.action_generate_pre_sale_advices()
        count_first = self.env['sor.pre.sale.advice'].search_count([
            ('event_id', '=', self.event.id),
        ])
        self.event.action_generate_pre_sale_advices()
        count_second = self.env['sor.pre.sale.advice'].search_count([
            ('event_id', '=', self.event.id),
        ])
        self.assertEqual(count_first, count_second)

    def test_pre_sale_advice_name_computed(self):
        """Name follows PSA/{sale_number}/{consignor_ref} pattern."""
        self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='catalogued',
        )
        self.event.action_generate_pre_sale_advices()
        psa = self.env['sor.pre.sale.advice'].search([
            ('event_id', '=', self.event.id),
            ('consignor_id', '=', self.consignor_a.id),
        ], limit=1)
        self.assertEqual(psa.name, 'PSA/A999/CON-001')

    # ------------------------------------------------------------------
    # Post-Sale Advice — batch generation
    # ------------------------------------------------------------------

    def test_post_sale_advice_batch_creates_for_sold_passed(self):
        """PSoA records created for sold and passed lots only."""
        self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='sold',
        )
        self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='passed',
        )
        # Set event to closed so batch generation is allowed
        self.event.status = 'closed'
        self.event.action_generate_post_sale_advices()
        posa = self.env['sor.post.sale.advice'].search([('event_id', '=', self.event.id)])
        self.assertEqual(len(posa), 1)  # Both lots under same consignor → 1 PSoA

    # ------------------------------------------------------------------
    # Vendor Settlement Statement
    # ------------------------------------------------------------------

    def test_vss_created_with_sequence_name(self):
        """VSS name combines sequence number and event sale_number: {seq}/{sale_number}."""
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        self.assertNotEqual(vss.name, 'New')
        self.assertTrue(vss.name)
        # BUG-07 fix: combined format stored in name at creation time
        self.assertIn('/A999', vss.name)

    def test_vss_initial_state_is_draft(self):
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        self.assertEqual(vss.state, 'draft')

    def test_vss_lifecycle_draft_to_payment_confirmed(self):
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        vss.action_confirm_payment()
        self.assertEqual(vss.state, 'payment_confirmed')

    def test_vss_lifecycle_draft_to_cancelled(self):
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        vss.action_cancel()
        self.assertEqual(vss.state, 'cancelled')

    def test_vss_totals_computed(self):
        """Commission totals computed from lot_ids."""
        lot = self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='sold',
            hammer_price=1000.0,
            sellers_commission_pct=10.0,
        )
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        lot.vendor_settlement_id = vss
        vss.invalidate_recordset(['total_hammer', 'total_commission', 'net_proceeds'])
        self.assertAlmostEqual(vss.total_hammer, 1000.0)
        self.assertAlmostEqual(vss.total_commission, 100.0)
        self.assertAlmostEqual(vss.net_proceeds, 900.0)

    def test_vss_rerun_skips_non_draft(self):
        """Re-running batch generation does not update Payment Confirmed VSSes."""
        self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='sold',
        )
        self.event.status = 'closed'
        self.event.action_generate_vendor_settlements()
        vss = self.env['sor.vendor.settlement'].search([
            ('event_id', '=', self.event.id),
            ('consignor_id', '=', self.consignor_a.id),
        ], limit=1)
        vss.action_confirm_payment()
        # Re-run: VSS in payment_confirmed should not be updated
        lot2 = self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='sold',
        )
        self.event.action_generate_vendor_settlements()
        self.assertFalse(lot2.vendor_settlement_id)

    def test_vss_sequence_provisioned_for_company(self):
        """Sequence exists for the test company."""
        seq = self.env['ir.sequence'].search([
            ('code', '=', 'sor.vendor.settlement'),
            ('company_id', '=', self.company.id),
        ])
        self.assertTrue(seq)
