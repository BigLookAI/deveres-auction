"""
Tests for sor_consignment_auction.

Coverage:
  1. _resolve_consignor — (partner, None) when full chain is present.
  2. _resolve_consignor — (False, 'missing_serial') when no stock.lot for product.
  3. _resolve_consignor — (False, 'missing_movement') when serial exists but no incoming picking.
  4. _resolve_consignor — (False, 'missing_consignment') when picking exists but no consignment agreement.
  5. At-create auto-population — consignor_id set when chain resolves at lot creation.
  6. action_fetch_consignor — sets consignor_id and returns False on success.
  7. action_fetch_consignor — returns display_notification dict on failure.
  8. _resolve_consignors_for_event — skips lots that already have consignor_id set.
  9. _resolve_consignors_for_event — populates unresolved lots and returns structured result.
  10. Composability — module manifest declares both parent dependencies and auto_install=True.
"""
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorConsignmentAuction(TransactionCase):
    """Traversal chain, auto-population, interactive fetch, and batch resolution."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.consignor = cls.env['res.partner'].create({'name': 'Test Consignor CA'})
        cls.other_partner = cls.env['res.partner'].create({'name': 'Other Partner CA'})

        # --- Product for full chain (serial tracked) ---
        cls.product_full = cls.env['product.template'].create({
            'name': 'CA Full Chain Artwork',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'serial',
            'product_type': False,
        })
        cls.product_full_variant = cls.product_full.product_variant_ids[0]

        # --- Product with serial but no picking (missing_movement) ---
        cls.product_no_picking = cls.env['product.template'].create({
            'name': 'CA No Picking Artwork',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'serial',
            'product_type': False,
        })
        cls.product_no_picking_variant = cls.product_no_picking.product_variant_ids[0]

        # --- Product with picking but no consignment agreement (missing_consignment) ---
        cls.product_no_consignment = cls.env['product.template'].create({
            'name': 'CA No Consignment Artwork',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'serial',
            'product_type': False,
        })
        cls.product_no_consignment_variant = cls.product_no_consignment.product_variant_ids[0]

        # --- Product with no stock.lot at all (missing_serial) ---
        cls.product_no_serial = cls.env['product.template'].create({
            'name': 'CA No Serial Artwork',
            'type': 'consu',
            'is_storable': True,
            'tracking': 'serial',
            'product_type': False,
        })

        # Serial for full chain
        cls.stock_lot_full = cls.env['stock.lot'].create({
            'name': 'SER-CA-001',
            'product_id': cls.product_full_variant.id,
            'company_id': cls.company.id,
        })

        # Serial for missing_movement scenario
        cls.stock_lot_no_picking = cls.env['stock.lot'].create({
            'name': 'SER-CA-003',
            'product_id': cls.product_no_picking_variant.id,
            'company_id': cls.company.id,
        })

        # Serial for missing_consignment scenario
        cls.stock_lot_no_consignment = cls.env['stock.lot'].create({
            'name': 'SER-CA-004',
            'product_id': cls.product_no_consignment_variant.id,
            'company_id': cls.company.id,
        })

        # Consignment In agreement (full chain)
        cls.agreement = cls.env['sor.agreement'].create({
            'primary_partner_id': cls.consignor.id,
            'agreement_type': 'consignment_in',
        })

        # Warehouse and incoming operation type
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1,
        )
        cls.receipt_type = cls.env['stock.picking.type'].search([
            ('code', '=', 'incoming'),
            ('warehouse_id', '=', cls.warehouse.id),
        ], limit=1)

        # Source location — use any internal location; traversal cares only about picking_type code
        cls.source_loc = cls.env['stock.location'].search([
            ('usage', '=', 'internal'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.dest_loc = cls.warehouse.lot_stock_id

        # Intake picking — consignment_in, includes serial SER-CA-001
        cls.intake_picking = cls.env['stock.picking'].create({
            'picking_type_id': cls.receipt_type.id,
            'location_id': cls.source_loc.id,
            'location_dest_id': cls.dest_loc.id,
            'company_id': cls.company.id,
        })
        cls.intake_picking.write({'agreement_id': cls.agreement.id})
        cls.env['stock.move.line'].create({
            'picking_id': cls.intake_picking.id,
            'product_id': cls.product_full_variant.id,
            'lot_id': cls.stock_lot_full.id,
            'quantity': 1,
            'product_uom_id': cls.product_full_variant.uom_id.id,
            'location_id': cls.source_loc.id,
            'location_dest_id': cls.dest_loc.id,
        })

        # Picking with no agreement — includes serial SER-CA-004 (missing_consignment)
        cls.picking_no_agreement = cls.env['stock.picking'].create({
            'picking_type_id': cls.receipt_type.id,
            'location_id': cls.source_loc.id,
            'location_dest_id': cls.dest_loc.id,
            'company_id': cls.company.id,
        })
        cls.env['stock.move.line'].create({
            'picking_id': cls.picking_no_agreement.id,
            'product_id': cls.product_no_consignment_variant.id,
            'lot_id': cls.stock_lot_no_consignment.id,
            'quantity': 1,
            'product_uom_id': cls.product_no_consignment_variant.uom_id.id,
            'location_id': cls.source_loc.id,
            'location_dest_id': cls.dest_loc.id,
        })

        # Auction event
        cls.event = cls.env['sor.event'].create({
            'name': 'Test Auction CA',
            'event_type': 'auction',
            'date_start': '2026-06-01 10:00:00',
            'company_id': cls.company.id,
        })

    def _make_lot(self, product, **kwargs):
        vals = {'product_id': product.id, 'company_id': self.company.id}
        vals.update(kwargs)
        return self.env['sor.lot'].create(vals)

    # ------------------------------------------------------------------
    # 1. _resolve_consignor — complete chain
    # ------------------------------------------------------------------

    def test_resolve_consignor_success_returns_partner(self):
        """Full chain resolves to the agreement's primary_partner_id."""
        lot = self._make_lot(self.product_full)
        partner, reason = lot._resolve_consignor()
        self.assertEqual(partner, self.consignor)
        self.assertIsNone(reason)

    # ------------------------------------------------------------------
    # 2. _resolve_consignor — missing_serial
    # ------------------------------------------------------------------

    def test_resolve_consignor_missing_serial(self):
        """Returns (False, 'missing_serial') when no stock.lot exists for the product."""
        lot = self._make_lot(self.product_no_serial)
        partner, reason = lot._resolve_consignor()
        self.assertFalse(partner)
        self.assertEqual(reason, 'missing_serial')

    # ------------------------------------------------------------------
    # 3. _resolve_consignor — missing_movement
    # ------------------------------------------------------------------

    def test_resolve_consignor_missing_movement(self):
        """Returns (False, 'missing_movement') when serial exists but no incoming picking."""
        lot = self._make_lot(self.product_no_picking)
        partner, reason = lot._resolve_consignor()
        self.assertFalse(partner)
        self.assertEqual(reason, 'missing_movement')

    # ------------------------------------------------------------------
    # 4. _resolve_consignor — missing_consignment
    # ------------------------------------------------------------------

    def test_resolve_consignor_missing_consignment(self):
        """Returns (False, 'missing_consignment') when picking exists but not linked to a
        consignment_in agreement."""
        lot = self._make_lot(self.product_no_consignment)
        partner, reason = lot._resolve_consignor()
        self.assertFalse(partner)
        self.assertEqual(reason, 'missing_consignment')

    # ------------------------------------------------------------------
    # 5. At-create auto-population
    # ------------------------------------------------------------------

    def test_consignor_auto_populated_at_create_when_chain_resolves(self):
        """consignor_id is set by the create() override when the full chain is present."""
        lot = self._make_lot(self.product_full)
        self.assertEqual(lot.consignor_id, self.consignor)

    def test_consignor_not_set_at_create_when_missing_serial(self):
        """consignor_id stays False when no stock.lot exists — no error raised."""
        lot = self._make_lot(self.product_no_serial)
        self.assertFalse(lot.consignor_id)

    # ------------------------------------------------------------------
    # 6. action_fetch_consignor — success
    # ------------------------------------------------------------------

    def test_action_fetch_consignor_sets_consignor_and_returns_false(self):
        """Fetch Consignor: sets consignor_id and returns False on success."""
        lot = self._make_lot(self.product_full)
        # Clear the auto-populated consignor to simulate a manual re-fetch scenario.
        lot.consignor_id = False
        self.assertFalse(lot.consignor_id)

        result = lot.action_fetch_consignor()

        self.assertEqual(lot.consignor_id, self.consignor)
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # 7. action_fetch_consignor — failure
    # ------------------------------------------------------------------

    def test_action_fetch_consignor_returns_notification_on_failure(self):
        """Fetch Consignor: returns display_notification dict when chain is incomplete.
        Message must be user-friendly — no internal model names (stock.lot) or
        misleading instructions about enabling serial tracking."""
        lot = self._make_lot(self.product_no_serial)
        result = lot.action_fetch_consignor()

        self.assertFalse(lot.consignor_id)
        self.assertIsInstance(result, dict)
        self.assertEqual(result.get('type'), 'ir.actions.client')
        self.assertEqual(result.get('tag'), 'display_notification')
        self.assertEqual(result['params']['type'], 'warning')
        self.assertTrue(result['params']['sticky'])
        message = result['params']['message']
        self.assertIn('intake record', message)
        self.assertNotIn('stock.lot', message)
        self.assertNotIn('serial tracking', message)

    # ------------------------------------------------------------------
    # 8. _resolve_consignors_for_event — skips already-set lots
    # ------------------------------------------------------------------

    def test_batch_skips_lots_with_consignor_already_set(self):
        """Lots with consignor_id already populated are skipped; consignor unchanged."""
        lot = self._make_lot(self.product_full, auction_id=self.event.id)
        # Overwrite with a manually assigned partner different from the chain result.
        lot.consignor_id = self.other_partner

        result = self.event._resolve_consignors_for_event()

        # Lot is counted as resolved (already had consignor_id set).
        self.assertIn(lot, result['resolved'])
        # Consignor is unchanged — batch did not overwrite it.
        self.assertEqual(lot.consignor_id, self.other_partner)

    # ------------------------------------------------------------------
    # 9. _resolve_consignors_for_event — populates resolvable lots
    # ------------------------------------------------------------------

    def test_batch_populates_resolvable_lots(self):
        """Batch sets consignor_id on lots that resolve and collects unresolved diagnostics."""
        # Lot that will resolve (full chain).
        lot_ok = self._make_lot(self.product_full, auction_id=self.event.id)
        lot_ok.consignor_id = False  # clear auto-population

        # Lot that will not resolve (no serial).
        lot_fail = self._make_lot(self.product_no_serial, auction_id=self.event.id)

        result = self.event._resolve_consignors_for_event()

        self.assertIn(lot_ok, result['resolved'])
        self.assertEqual(lot_ok.consignor_id, self.consignor)

        unresolved_refs = [e['lot'] for e in result['unresolved']]
        self.assertIn(lot_fail, unresolved_refs)

    # ------------------------------------------------------------------
    # 10. Composability — manifest declares both parents and auto_install
    # ------------------------------------------------------------------

    def test_module_depends_on_both_parents(self):
        module = self.env['ir.module.module'].search(
            [('name', '=', 'sor_consignment_auction')], limit=1,
        )
        self.assertTrue(module, 'sor_consignment_auction module record not found')
        deps = module.dependencies_id.mapped('depend_id.name')
        self.assertIn('sor_consignment_agreements', deps)
        self.assertIn('sor_auction_documents', deps)

    def test_module_is_auto_install(self):
        module = self.env['ir.module.module'].search(
            [('name', '=', 'sor_consignment_auction')], limit=1,
        )
        self.assertTrue(module.auto_install)
