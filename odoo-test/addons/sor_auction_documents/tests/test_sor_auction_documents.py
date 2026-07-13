"""
Tests for sor_auction_documents.

Coverage:
  1. Module installs — fields present on sor.lot, res.company; action methods present on sor.event.
  2. vat_margin_scheme — defaults False when company setting is off; defaults True when on.
  3. consignor_id — lot saves without consignor; consignor can be set manually.
  4. Company settings fields persist — psa/posa/vss content top/bottom, auction VAT notice.
  5. Pre-Sale Advice — batch generation creates records grouped by consignor; idempotent re-run.
  6. Post-Sale Advice — batch generation for sold/passed lots only.
  7. Vendor Settlement Statement — lifecycle; sequence; commission and Fixed Charges totals; re-run protection.
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

    def test_vat_margin_scheme_present_on_lot(self):
        self.assertIn('vat_margin_scheme', self.env['sor.lot']._fields)

    def test_vat_margin_scheme_lot_field_has_no_column_name_kwarg(self):
        """Story 02: sor.lot.vat_margin_scheme carries no column_name kwarg (dead parameter removed)."""
        field = self.env['sor.lot']._fields['vat_margin_scheme']
        self.assertFalse(hasattr(field, 'column_name'))

    def test_pre_sale_advice_id_present_on_lot(self):
        self.assertIn('pre_sale_advice_id', self.env['sor.lot']._fields)

    def test_post_sale_advice_id_present_on_lot(self):
        self.assertIn('post_sale_advice_id', self.env['sor.lot']._fields)

    def test_vendor_settlement_id_present_on_lot(self):
        self.assertIn('vendor_settlement_id', self.env['sor.lot']._fields)

    def test_psa_content_top_present_on_company(self):
        self.assertIn('psa_content_top', self.env['res.company']._fields)

    def test_psa_content_bottom_present_on_company(self):
        self.assertIn('psa_content_bottom', self.env['res.company']._fields)

    def test_posa_content_top_present_on_company(self):
        self.assertIn('posa_content_top', self.env['res.company']._fields)

    def test_posa_content_bottom_present_on_company(self):
        self.assertIn('posa_content_bottom', self.env['res.company']._fields)

    def test_vss_content_top_present_on_company(self):
        self.assertIn('vss_content_top', self.env['res.company']._fields)

    def test_vss_content_bottom_present_on_company(self):
        self.assertIn('vss_content_bottom', self.env['res.company']._fields)

    def test_vat_margin_scheme_present_on_company(self):
        self.assertIn('vat_margin_scheme', self.env['res.company']._fields)

    def test_auction_vat_notice_present_on_company(self):
        self.assertIn('auction_vat_notice', self.env['res.company']._fields)

    def test_action_generate_pre_sale_advices_exists(self):
        self.assertTrue(hasattr(self.env['sor.event'], 'action_generate_pre_sale_advices'))

    def test_action_generate_post_sale_advices_exists(self):
        self.assertTrue(hasattr(self.env['sor.event'], 'action_generate_post_sale_advices'))

    def test_action_generate_vendor_settlements_exists(self):
        self.assertTrue(hasattr(self.env['sor.event'], 'action_generate_vendor_settlements'))

    def test_action_send_all_pre_sale_advices_removed(self):
        """Story 02 AC 6: the event-level 'Send All' method is deleted, not merely hidden."""
        self.assertFalse(hasattr(self.env['sor.event'], 'action_send_all_pre_sale_advices'))

    def test_action_send_all_post_sale_advices_removed(self):
        """Story 02 AC 6: the event-level 'Send All' method is deleted, not merely hidden."""
        self.assertFalse(hasattr(self.env['sor.event'], 'action_send_all_post_sale_advices'))

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
    """vat_margin_scheme defaults, settings persistence, document generation."""

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

        cls.product = cls.env['product.template'].create({
            'name': 'Test Product AD',
            'type': 'consu',
            'is_storable': True,
            'product_type': False,
        })

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
    # vat_margin_scheme
    # ------------------------------------------------------------------

    def test_vat_margin_scheme_defaults_false(self):
        self.company.vat_margin_scheme = False
        lot = self._make_lot()
        self.assertFalse(lot.vat_margin_scheme)

    def test_vat_margin_scheme_defaults_true_from_company(self):
        self.company.vat_margin_scheme = True
        lot = self._make_lot()
        self.assertTrue(lot.vat_margin_scheme)

    # ------------------------------------------------------------------
    # consignor_id
    # ------------------------------------------------------------------

    def test_lot_saves_without_consignor(self):
        lot = self._make_lot()
        self.assertFalse(lot.consignor_id)

    def test_consignor_id_can_be_set_manually(self):
        lot = self._make_lot(consignor_id=self.consignor_a.id)
        self.assertEqual(lot.consignor_id, self.consignor_a)

    def test_consignor_subtype_auto_assigned_on_lot_create(self):
        """Consignor sub-type is assigned to consignor_id partner when lot is created (BUG-U1-02).

        Only runs when sor_contact_roles is installed and the Consignor sub-type
        seed record exists. If the sub-type is absent the test is skipped — this
        guards against running in a minimal stack where contact roles are not installed.
        """
        consignor_subtype = self.env['sor.contact.type'].search(
            [('code', '=', 'consignor'), ('parent_type_id', '!=', False)], limit=1,
        )
        if not consignor_subtype:
            self.skipTest('Consignor sub-type not present — sor_contact_roles not installed')
        partner = self.env['res.partner'].create({'name': 'New Consignor Partner'})
        self.assertNotIn(consignor_subtype, partner.contact_subtypes)
        self._make_lot(consignor_id=partner.id)
        partner.invalidate_recordset(['contact_subtypes'])
        self.assertIn(consignor_subtype, partner.contact_subtypes)

    def test_consignor_subtype_auto_assigned_on_consignor_id_write(self):
        """Consignor sub-type is assigned when consignor_id is updated on an existing lot (BUG-U1-02)."""
        consignor_subtype = self.env['sor.contact.type'].search(
            [('code', '=', 'consignor'), ('parent_type_id', '!=', False)], limit=1,
        )
        if not consignor_subtype:
            self.skipTest('Consignor sub-type not present — sor_contact_roles not installed')
        partner = self.env['res.partner'].create({'name': 'Write Consignor Partner'})
        lot = self._make_lot()
        self.assertFalse(lot.consignor_id)
        lot.write({'consignor_id': partner.id})
        partner.invalidate_recordset(['contact_subtypes'])
        self.assertIn(consignor_subtype, partner.contact_subtypes)

    # ------------------------------------------------------------------
    # Company settings persistence
    # ------------------------------------------------------------------

    def test_psa_content_top_persists(self):
        self.company.psa_content_top = '<p>Test PSA top</p>'
        self.company.flush_recordset(['psa_content_top'])
        self.company.invalidate_recordset(['psa_content_top'])
        self.assertIn('Test PSA top', self.company.psa_content_top)

    def test_psa_content_bottom_persists(self):
        self.company.psa_content_bottom = '<p>Test PSA bottom</p>'
        self.company.flush_recordset(['psa_content_bottom'])
        self.company.invalidate_recordset(['psa_content_bottom'])
        self.assertIn('Test PSA bottom', self.company.psa_content_bottom)

    def test_vss_content_bottom_persists(self):
        self.company.vss_content_bottom = '<p>IBAN: IE12 BOFI 9000 0112 3456 78</p>'
        self.company.flush_recordset(['vss_content_bottom'])
        self.company.invalidate_recordset(['vss_content_bottom'])
        self.assertIn('IBAN', self.company.vss_content_bottom)

    def test_auction_vat_notice_persists(self):
        self.company.auction_vat_notice = 'VAT is accounted for under the margin scheme.'
        self.assertIn(
            'VAT is accounted for under the margin scheme.', self.company.auction_vat_notice,
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

    def test_vss_totals_deduct_fixed_charges(self):
        """Fixed Charges reduce net_proceeds in addition to commission."""
        lot = self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='sold',
            hammer_price=1000.0,
            sellers_commission_pct=10.0,
        )
        charge_type = self.env['sor.fixed.charge.type'].search([('name', '=', 'Restoration')], limit=1)
        self.env['sor.lot.fixed.charge'].create({
            'lot_id': lot.id,
            'charge_type_id': charge_type.id,
            'amount': 50.0,
        })
        self.env['sor.lot.fixed.charge'].create({
            'lot_id': lot.id,
            'charge_type_id': self.env['sor.fixed.charge.type'].search(
                [('name', '=', 'Framing')], limit=1,
            ).id,
            'amount': 30.0,
        })
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        lot.vendor_settlement_id = vss
        vss.invalidate_recordset(['total_hammer', 'total_commission', 'total_fixed_charges', 'net_proceeds'])
        self.assertAlmostEqual(vss.total_hammer, 1000.0)
        self.assertAlmostEqual(vss.total_commission, 100.0)
        self.assertAlmostEqual(vss.total_fixed_charges, 80.0)
        self.assertAlmostEqual(vss.net_proceeds, 820.0)

    def test_vss_totals_zero_fixed_charges_when_none_recorded(self):
        """total_fixed_charges is zero (not None) when a lot has no Fixed Charges."""
        lot = self._make_lot(
            auction_id=self.event.id,
            consignor_id=self.consignor_a.id,
            state='sold',
            hammer_price=500.0,
            sellers_commission_pct=10.0,
        )
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        lot.vendor_settlement_id = vss
        vss.invalidate_recordset(['total_fixed_charges', 'net_proceeds'])
        self.assertAlmostEqual(vss.total_fixed_charges, 0.0)
        self.assertAlmostEqual(vss.net_proceeds, 450.0)

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

    # ------------------------------------------------------------------
    # Pending count fields (Sprint 19 — Document Generation UX)
    # ------------------------------------------------------------------

    def test_psa_pending_count_reflects_eligible_lots(self):
        """psa_pending_count counts catalogued lots with a consignor and no PSA."""
        event = self.env['sor.event'].create({
            'name': 'PSA Pending Count Test',
            'event_type': 'auction',
            'date_start': '2026-07-01 10:00:00',
            'company_id': self.company.id,
        })
        self.assertEqual(event.psa_pending_count, 0)
        self._make_lot(auction_id=event.id, consignor_id=self.consignor_a.id, state='catalogued')
        self._make_lot(auction_id=event.id, consignor_id=self.consignor_b.id, state='catalogued')
        self.assertEqual(event.psa_pending_count, 2)

    def test_psa_pending_count_excludes_lots_without_consignor(self):
        """Lots without a consignor are excluded from psa_pending_count."""
        event = self.env['sor.event'].create({
            'name': 'PSA Excl Consignor Test',
            'event_type': 'auction',
            'date_start': '2026-07-01 10:00:00',
            'company_id': self.company.id,
        })
        self._make_lot(auction_id=event.id, state='catalogued')  # no consignor
        self.assertEqual(event.psa_pending_count, 0)

    def test_psa_pending_count_zero_after_generation(self):
        """psa_pending_count drops to 0 after all PSAs are generated."""
        event = self.env['sor.event'].create({
            'name': 'PSA Zero After Gen Test',
            'event_type': 'auction',
            'date_start': '2026-07-01 10:00:00',
            'company_id': self.company.id,
            'sale_number': 'B001',
        })
        self._make_lot(auction_id=event.id, consignor_id=self.consignor_a.id, state='catalogued')
        self.assertEqual(event.psa_pending_count, 1)
        event.action_generate_pre_sale_advices()
        self.assertEqual(event.psa_pending_count, 0)

    def test_posa_pending_count_reflects_eligible_lots(self):
        """posa_pending_count counts sold/passed lots with a consignor and no POSA."""
        event = self.env['sor.event'].create({
            'name': 'POSA Pending Count Test',
            'event_type': 'auction',
            'date_start': '2026-07-01 10:00:00',
            'company_id': self.company.id,
        })
        self._make_lot(auction_id=event.id, consignor_id=self.consignor_a.id, state='sold')
        self._make_lot(auction_id=event.id, consignor_id=self.consignor_b.id, state='passed')
        self.assertEqual(event.posa_pending_count, 2)

    def test_vss_pending_count_reflects_eligible_lots(self):
        """vss_pending_count counts sold/passed lots with a consignor and no VSS."""
        event = self.env['sor.event'].create({
            'name': 'VSS Pending Count Test',
            'event_type': 'auction',
            'date_start': '2026-07-01 10:00:00',
            'company_id': self.company.id,
        })
        self._make_lot(auction_id=event.id, consignor_id=self.consignor_a.id, state='sold')
        self.assertEqual(event.vss_pending_count, 1)

    # ------------------------------------------------------------------
    # PSA state field (Sprint 19 — Document Generation UX)
    # ------------------------------------------------------------------

    def test_psa_state_defaults_to_draft(self):
        """A newly created PSA record has state 'draft'."""
        psa = self.env['sor.pre.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        self.assertEqual(psa.state, 'draft')

    def test_psa_bulk_mark_sent_updates_state(self):
        """action_bulk_send sets state to 'sent' for draft PSAs whose consignor has an email."""
        self.consignor_a.email = 'consignor.a@example.com'
        psa = self.env['sor.pre.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        self.assertEqual(psa.state, 'draft')
        psa.action_bulk_send()
        self.assertEqual(psa.state, 'sent')

    def test_posa_state_defaults_to_draft(self):
        """A newly created POSA record has state 'draft'."""
        posa = self.env['sor.post.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        self.assertEqual(posa.state, 'draft')

    def test_posa_bulk_mark_sent_updates_state(self):
        """action_bulk_send on POSA sets state to 'sent' when the consignor has an email."""
        self.consignor_a.email = 'consignor.a@example.com'
        posa = self.env['sor.post.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        posa.action_bulk_send()
        self.assertEqual(posa.state, 'sent')

    # ------------------------------------------------------------------
    # VSS bulk send — action_bulk_send (Story 03; no prior test existed)
    # ------------------------------------------------------------------

    def test_vss_bulk_send_updates_state_when_email_present(self):
        """action_bulk_send on VSS sets state to 'sent' when the consignor has an email."""
        self.consignor_a.email = 'consignor.a@example.com'
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        vss.action_confirm_payment()
        vss.action_bulk_send()
        self.assertEqual(vss.state, 'sent')

    def test_vss_bulk_send_preserves_state_when_no_email(self):
        """action_bulk_send on VSS never lies about a state it did not achieve (mirrors Bug B01 fix on PSA/POSA)."""
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_b.id,  # no email set anywhere in this class
            'company_id': self.company.id,
        })
        vss.action_confirm_payment()
        vss.action_bulk_send()
        self.assertEqual(vss.state, 'payment_confirmed')

    def test_vss_bulk_send_posts_chatter_note_when_skipped(self):
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_b.id,
            'company_id': self.company.id,
        })
        vss.action_confirm_payment()
        vss.action_bulk_send()
        self.assertTrue(
            vss.message_ids.filtered(lambda m: 'no email on file' in (m.body or '')),
        )

    # ------------------------------------------------------------------
    # Individual send — template wiring (Story 01)
    # ------------------------------------------------------------------

    def test_psa_individual_send_uses_template(self):
        """action_send_by_email wires default_template_id, not a hardcoded subject (Story 01 AC 1)."""
        psa = self.env['sor.pre.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        result = psa.action_send_by_email()
        template = self.env.ref('sor_auction_documents.mail_template_sor_pre_sale_advice')
        self.assertEqual(result['context']['default_template_id'], template.id)
        self.assertNotIn('default_subject', result['context'])

    def test_posa_individual_send_uses_template(self):
        """action_send_by_email wires default_template_id, not a hardcoded subject (Story 01 AC 2)."""
        posa = self.env['sor.post.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        result = posa.action_send_by_email()
        template = self.env.ref('sor_auction_documents.mail_template_sor_post_sale_advice')
        self.assertEqual(result['context']['default_template_id'], template.id)
        self.assertNotIn('default_subject', result['context'])

    def test_vss_individual_send_uses_template(self):
        """action_send_by_email wires default_template_id, not a hardcoded subject (Story 01 AC 3)."""
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        vss.action_confirm_payment()
        result = vss.action_send_by_email()
        template = self.env.ref('sor_auction_documents.mail_template_sor_vendor_settlement')
        self.assertEqual(result['context']['default_template_id'], template.id)
        self.assertNotIn('default_subject', result['context'])

    def test_vss_individual_send_works_from_sent_state(self):
        """action_send_by_email is a safe resend from 'sent' state (Story 01 AC 3 / Story 04)."""
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        vss.action_confirm_payment()
        vss.action_send_by_email()
        self.assertEqual(vss.state, 'sent')
        result = vss.action_send_by_email()
        self.assertEqual(vss.state, 'sent')
        self.assertEqual(result['res_model'], 'mail.compose.message')

    # ------------------------------------------------------------------
    # Bulk-send mail template correctness (BUG-01 regression)
    #
    # `use_default_to` defaults to True on mail.template and, if left set,
    # silently overrides `partner_to` in mass-mail mode — the resulting
    # mail.mail is created with no recipient at all. See
    # odoo_conventions/orm_and_field_patterns.md for the full mechanism.
    # ------------------------------------------------------------------

    def test_psa_template_use_default_to_false(self):
        template = self.env.ref('sor_auction_documents.mail_template_sor_pre_sale_advice')
        self.assertFalse(template.use_default_to)

    def test_posa_template_use_default_to_false(self):
        template = self.env.ref('sor_auction_documents.mail_template_sor_post_sale_advice')
        self.assertFalse(template.use_default_to)

    def test_vss_template_use_default_to_false(self):
        template = self.env.ref('sor_auction_documents.mail_template_sor_vendor_settlement')
        self.assertFalse(template.use_default_to)

    def test_psa_bulk_send_populates_recipient(self):
        """Regression (BUG-01): the mail.mail created by bulk send has a real recipient."""
        self.consignor_a.email = 'consignor.a@example.com'
        psa = self.env['sor.pre.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        before_ids = self.env['mail.mail'].search([]).ids
        psa.action_bulk_send()
        new_mail = self.env['mail.mail'].search([('id', 'not in', before_ids)], order='id desc', limit=1)
        self.assertTrue(new_mail, 'A mail.mail record should have been created')
        self.assertIn(self.consignor_a, new_mail.recipient_ids)

    def test_posa_bulk_send_populates_recipient(self):
        """Regression (BUG-01): the mail.mail created by bulk send has a real recipient."""
        self.consignor_a.email = 'consignor.a@example.com'
        posa = self.env['sor.post.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        before_ids = self.env['mail.mail'].search([]).ids
        posa.action_bulk_send()
        new_mail = self.env['mail.mail'].search([('id', 'not in', before_ids)], order='id desc', limit=1)
        self.assertTrue(new_mail, 'A mail.mail record should have been created')
        self.assertIn(self.consignor_a, new_mail.recipient_ids)

    def test_vss_bulk_send_populates_recipient(self):
        """Regression (BUG-01): the mail.mail created by bulk send has a real recipient."""
        self.consignor_a.email = 'consignor.a@example.com'
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        vss.action_confirm_payment()
        before_ids = self.env['mail.mail'].search([]).ids
        vss.action_bulk_send()
        new_mail = self.env['mail.mail'].search([('id', 'not in', before_ids)], order='id desc', limit=1)
        self.assertTrue(new_mail, 'A mail.mail record should have been created')
        self.assertIn(self.consignor_a, new_mail.recipient_ids)

    # ------------------------------------------------------------------
    # Bulk-send notification chaining (BUG-02 / BUG-03 regression)
    #
    # An ir.actions.server with state="code" only returns a client action
    # if the code assigns to a variable literally named `action`; a
    # display_notification action only triggers the calling view's
    # reload/deselect if its params include a 'next' action. See
    # odoo_conventions/orm_and_field_patterns.md for both mechanisms.
    # ------------------------------------------------------------------

    def test_psa_bulk_send_notification_closes_view(self):
        self.consignor_a.email = 'consignor.a@example.com'
        psa = self.env['sor.pre.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        result = psa.action_bulk_send()
        self.assertEqual(result['params'].get('next'), {'type': 'ir.actions.act_window_close'})

    def test_posa_bulk_send_notification_closes_view(self):
        self.consignor_a.email = 'consignor.a@example.com'
        posa = self.env['sor.post.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        result = posa.action_bulk_send()
        self.assertEqual(result['params'].get('next'), {'type': 'ir.actions.act_window_close'})

    def test_vss_bulk_send_notification_closes_view(self):
        self.consignor_a.email = 'consignor.a@example.com'
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        vss.action_confirm_payment()
        result = vss.action_bulk_send()
        self.assertEqual(result['params'].get('next'), {'type': 'ir.actions.act_window_close'})

    def test_psa_bulk_send_server_action_returns_notification(self):
        """Regression (BUG-02): the ir.actions.server record must assign to `action`."""
        self.consignor_a.email = 'consignor.a@example.com'
        psa = self.env['sor.pre.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        server_action = self.env.ref('sor_auction_documents.action_server_bulk_send_pre_sale_advice')
        result = server_action.with_context(
            active_ids=psa.ids, active_model='sor.pre.sale.advice',
        ).run()
        self.assertIsNotNone(result)
        self.assertEqual(result.get('tag'), 'display_notification')

    def test_posa_bulk_send_server_action_returns_notification(self):
        """Regression (BUG-02): the ir.actions.server record must assign to `action`."""
        self.consignor_a.email = 'consignor.a@example.com'
        posa = self.env['sor.post.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        server_action = self.env.ref('sor_auction_documents.action_server_bulk_send_post_sale_advice')
        result = server_action.with_context(
            active_ids=posa.ids, active_model='sor.post.sale.advice',
        ).run()
        self.assertIsNotNone(result)
        self.assertEqual(result.get('tag'), 'display_notification')

    def test_vss_bulk_send_server_action_returns_notification(self):
        """Regression (BUG-02): the ir.actions.server record must assign to `action`."""
        self.consignor_a.email = 'consignor.a@example.com'
        vss = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        vss.action_confirm_payment()
        server_action = self.env.ref('sor_auction_documents.action_server_vss_bulk_mark_sent')
        result = server_action.with_context(
            active_ids=vss.ids, active_model='sor.vendor.settlement',
        ).run()
        self.assertIsNotNone(result)

    # ------------------------------------------------------------------
    # Bulk-send not-eligible count (BUG-04 regression — UAT Issue Log #1)
    #
    # Records selected in a non-eligible starting state are excluded from
    # the sent/skipped split before it ever runs. Without an explicit
    # not_eligible_count, they silently vanish from the notification with
    # no indication they were ever selected.
    # ------------------------------------------------------------------

    def test_psa_bulk_send_reports_not_eligible_count(self):
        self.consignor_a.email = 'consignor.a@example.com'
        self.consignor_b.email = 'consignor.b@example.com'
        eligible = self.env['sor.pre.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        already_sent = self.env['sor.pre.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_b.id,
            'company_id': self.company.id,
            'state': 'sent',
        })
        result = (eligible | already_sent).action_bulk_send()
        self.assertEqual(eligible.state, 'sent')
        self.assertEqual(already_sent.state, 'sent')  # untouched — was already sent
        self.assertIn('1 not eligible (wrong state)', result['params']['message'])
        self.assertTrue(result['params']['sticky'])

    def test_posa_bulk_send_reports_not_eligible_count(self):
        self.consignor_a.email = 'consignor.a@example.com'
        self.consignor_b.email = 'consignor.b@example.com'
        eligible = self.env['sor.post.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        already_sent = self.env['sor.post.sale.advice'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_b.id,
            'company_id': self.company.id,
            'state': 'sent',
        })
        result = (eligible | already_sent).action_bulk_send()
        self.assertIn('1 not eligible (wrong state)', result['params']['message'])
        self.assertTrue(result['params']['sticky'])

    def test_vss_bulk_send_reports_not_eligible_count(self):
        self.consignor_a.email = 'consignor.a@example.com'
        self.consignor_b.email = 'consignor.b@example.com'
        eligible = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_a.id,
            'company_id': self.company.id,
        })
        eligible.action_confirm_payment()
        still_draft = self.env['sor.vendor.settlement'].create({
            'event_id': self.event.id,
            'consignor_id': self.consignor_b.id,
            'company_id': self.company.id,
        })
        result = (eligible | still_draft).action_bulk_send()
        self.assertEqual(eligible.state, 'sent')
        self.assertEqual(still_draft.state, 'draft')  # untouched — was not payment_confirmed
        self.assertIn('1 not eligible (wrong state)', result['params']['message'])
        self.assertTrue(result['params']['sticky'])
        self.assertEqual(result.get('tag'), 'display_notification')
