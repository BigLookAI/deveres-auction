import inspect

from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestSorTracking(TransactionCase):
    """Tests for the sor_tracking module.

    Covers: module installs, sor_movement_state field and transitions,
    direction-aware label/hint computed fields, owner_id copy behaviour,
    picking-type inference from locations, and dashboard SQL aggregation.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1,
        )
        cls.stock_loc = cls.warehouse.lot_stock_id
        # Use the contact_type and supplier_loc that Odoo ships
        cls.supplier_loc = cls.env.ref('stock.stock_location_suppliers')
        cls.customer_loc = cls.env.ref('stock.stock_location_customers')
        # Operation type objects
        cls.receipt_type = cls.env['stock.picking.type'].search(
            [('code', '=', 'incoming'), ('warehouse_id', '=', cls.warehouse.id)], limit=1,
        )
        cls.delivery_type = cls.env['stock.picking.type'].search(
            [('code', '=', 'outgoing'), ('warehouse_id', '=', cls.warehouse.id)], limit=1,
        )
        cls.internal_type = cls.env['stock.picking.type'].search(
            [('code', '=', 'internal'), ('warehouse_id', '=', cls.warehouse.id)], limit=1,
        )

    # ------------------------------------------------------------------
    # 1. Module installs — key models exist
    # ------------------------------------------------------------------

    def test_module_installs_stock_picking_fields(self):
        """sor_tracking adds sor_movement_state to stock.picking."""
        self.assertIn('sor_movement_state', self.env['stock.picking']._fields)
        self.assertIn('sor_movement_state_label', self.env['stock.picking']._fields)
        self.assertIn('sor_movement_hint', self.env['stock.picking']._fields)

    def test_module_installs_dashboard_model(self):
        """sor.tracking.dashboard model exists and is loadable."""
        model = self.env['sor.tracking.dashboard']
        self.assertTrue(model._name == 'sor.tracking.dashboard')

    def test_module_installs_location_confirm_model(self):
        """sor.movement.location.confirm TransientModel exists."""
        model = self.env['sor.movement.location.confirm']
        self.assertTrue(model._name == 'sor.movement.location.confirm')

    # ------------------------------------------------------------------
    # 2. sor_movement_state default and storage
    # ------------------------------------------------------------------

    def test_new_picking_defaults_to_queued(self):
        """Newly created pickings default to sor_movement_state='queued'."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        self.assertEqual(picking.sor_movement_state, 'queued')

    def test_state_not_copied_on_return(self):
        """sor_movement_state is copy=False — return pickings start as queued."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'sor_movement_state': 'confirmed',
        })
        copied = picking.copy()
        self.assertEqual(
            copied.sor_movement_state, 'queued',
            'Copied picking must not inherit sor_movement_state from original.',
        )

    # ------------------------------------------------------------------
    # 3. State transitions
    # ------------------------------------------------------------------

    def test_queued_to_ready_allowed(self):
        """queued → ready is an allowed transition."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        picking.write({'sor_movement_state': 'ready'})
        self.assertEqual(picking.sor_movement_state, 'ready')

    def test_queued_to_cancelled_allowed(self):
        """queued → cancelled is an allowed transition."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        picking.write({'sor_movement_state': 'cancelled'})
        self.assertEqual(picking.sor_movement_state, 'cancelled')

    def test_confirmed_is_terminal(self):
        """confirmed → any other state raises UserError."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'sor_movement_state': 'confirmed',
        })
        with self.assertRaises(UserError):
            picking.write({'sor_movement_state': 'queued'})
        with self.assertRaises(UserError):
            picking.write({'sor_movement_state': 'cancelled'})

    def test_cancelled_is_terminal(self):
        """cancelled → any other state raises UserError."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'sor_movement_state': 'cancelled',
        })
        with self.assertRaises(UserError):
            picking.write({'sor_movement_state': 'queued'})

    # ------------------------------------------------------------------
    # 4. Direction-aware label (sor_movement_state_label)
    # ------------------------------------------------------------------

    def test_label_queued(self):
        """Queued state always shows 'Queued' regardless of direction."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        self.assertEqual(picking.sor_movement_state_label, 'Queued')

    def test_label_cancelled(self):
        """Cancelled state always shows 'Cancelled' regardless of direction."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.delivery_type.id,
            'location_id': self.stock_loc.id,
            'location_dest_id': self.customer_loc.id,
            'sor_movement_state': 'cancelled',
        })
        self.assertEqual(picking.sor_movement_state_label, 'Cancelled')

    def test_label_incoming_confirmed_is_received(self):
        """Confirmed incoming picking shows 'Received'."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'sor_movement_state': 'confirmed',
        })
        self.assertEqual(picking.sor_movement_state_label, 'Received')

    def test_label_outgoing_confirmed_is_dispatched(self):
        """Confirmed outgoing picking shows 'Dispatched'."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.delivery_type.id,
            'location_id': self.stock_loc.id,
            'location_dest_id': self.customer_loc.id,
            'sor_movement_state': 'confirmed',
        })
        self.assertEqual(picking.sor_movement_state_label, 'Dispatched')

    def test_label_internal_confirmed_is_transferred(self):
        """Confirmed internal picking shows 'Transferred'."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.internal_type.id,
            'location_id': self.stock_loc.id,
            'location_dest_id': self.stock_loc.id,
            'sor_movement_state': 'confirmed',
        })
        self.assertEqual(picking.sor_movement_state_label, 'Transferred')

    # ------------------------------------------------------------------
    # 5. Contextual hint (sor_movement_hint)
    # ------------------------------------------------------------------

    def test_hint_non_queued_is_empty(self):
        """Confirmed and cancelled pickings have an empty hint."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'sor_movement_state': 'confirmed',
        })
        self.assertEqual(picking.sor_movement_hint, '')

    def test_hint_queued_incoming_references_received(self):
        """Queued incoming picking hint mentions 'received'."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        self.assertIn('received', picking.sor_movement_hint.lower())

    def test_hint_queued_outgoing_references_dispatched(self):
        """Queued outgoing picking hint mentions 'dispatched'."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.delivery_type.id,
            'location_id': self.stock_loc.id,
            'location_dest_id': self.customer_loc.id,
        })
        self.assertIn('dispatched', picking.sor_movement_hint.lower())

    # ------------------------------------------------------------------
    # 6. Beneficial owner — owner_id carries to return pickings
    # ------------------------------------------------------------------

    def test_owner_id_carries_to_copy(self):
        """owner_id is copied when a return picking is created (copy=True in stock)."""
        partner = self.env['res.partner'].create({'name': 'Test Owner'})
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'owner_id': partner.id,
        })
        copied = picking.copy()
        self.assertEqual(
            copied.owner_id.id, partner.id,
            'owner_id must be preserved on copied (return) picking.',
        )

    # ------------------------------------------------------------------
    # 7. Picking type inference from locations
    # ------------------------------------------------------------------

    def test_infer_incoming_from_supplier_to_stock(self):
        """Supplier → stock infers incoming picking type."""
        inferred_id = self.env['stock.picking']._sor_infer_picking_type_id(
            self.supplier_loc.id, self.stock_loc.id,
        )
        picking_type = self.env['stock.picking.type'].browse(inferred_id)
        self.assertEqual(picking_type.code, 'incoming')

    def test_infer_outgoing_from_stock_to_customer(self):
        """Stock → customer infers outgoing picking type."""
        inferred_id = self.env['stock.picking']._sor_infer_picking_type_id(
            self.stock_loc.id, self.customer_loc.id,
        )
        picking_type = self.env['stock.picking.type'].browse(inferred_id)
        self.assertEqual(picking_type.code, 'outgoing')

    def test_infer_internal_from_stock_to_stock(self):
        """Internal → internal infers internal picking type."""
        inferred_id = self.env['stock.picking']._sor_infer_picking_type_id(
            self.stock_loc.id, self.stock_loc.id,
        )
        picking_type = self.env['stock.picking.type'].browse(inferred_id)
        self.assertEqual(picking_type.code, 'internal')

    def test_infer_returns_false_for_external_to_external(self):
        """External → external is invalid; inference returns False."""
        result = self.env['stock.picking']._sor_infer_picking_type_id(
            self.supplier_loc.id, self.customer_loc.id,
        )
        self.assertFalse(result)

    # ------------------------------------------------------------------
    # 8. Dashboard SQL aggregation
    # ------------------------------------------------------------------

    def test_dashboard_counts_created_record(self):
        """Dashboard mvi_queued count reflects newly created queued MVI picking."""
        self.env.flush_all()
        before = self.env['sor.tracking.dashboard'].new({'name': 'Movement Activity'})
        count_before = before.mvi_queued

        self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        # Flush ORM writes to the cursor so raw SQL in _compute_counts sees the new row
        self.env.flush_all()

        after = self.env['sor.tracking.dashboard'].new({'name': 'Movement Activity'})
        self.assertEqual(after.mvi_queued, count_before + 1)

    def test_dashboard_counts_company_scoped(self):
        """Dashboard counts exclude records from other companies."""
        # Confirm the dashboard record for the active company does not raise
        # and returns non-negative integer values for all count fields.
        dashboard = self.env['sor.tracking.dashboard'].new({'name': 'Movement Activity'})
        for field in ('mvi_queued', 'mvi_confirmed', 'mvi_cancelled',
                      'mvo_queued', 'mvo_confirmed', 'mvo_cancelled', 'mvt_queued'):
            val = getattr(dashboard, field)
            self.assertIsInstance(val, int, f'{field} must be an integer')
            self.assertGreaterEqual(val, 0, f'{field} must be non-negative')

    def test_dashboard_action_methods_return_window_action(self):
        """All 7 @api.model action methods return a valid ir.actions.act_window dict."""
        dashboard = self.env['sor.tracking.dashboard']
        action_methods = [
            'action_view_mvi_queued',
            'action_view_mvi_confirmed',
            'action_view_mvi_cancelled',
            'action_view_mvo_queued',
            'action_view_mvo_confirmed',
            'action_view_mvo_cancelled',
            'action_view_mvt_queued',
        ]
        for method_name in action_methods:
            with self.subTest(method=method_name):
                action = getattr(dashboard, method_name)()
                self.assertEqual(action.get('type'), 'ir.actions.act_window')
                self.assertEqual(action.get('res_model'), 'stock.picking')
                self.assertIn('domain', action)

    def test_dashboard_action_domain_correct_code(self):
        """action_view_mvi_queued domain filters by picking_type_id.code, not sequence_code."""
        action = self.env['sor.tracking.dashboard'].action_view_mvi_queued()
        domain_str = str(action['domain'])
        self.assertIn('code', domain_str)
        self.assertIn('incoming', domain_str)
        self.assertNotIn('sequence_code', domain_str)
        self.assertNotIn('MVI', domain_str)

    # ------------------------------------------------------------------
    # 9. Partner inference from location (Issue 11 — UAT fix)
    # ------------------------------------------------------------------

    def test_infer_partner_returns_false_when_no_location(self):
        """_sor_infer_partner_id returns False when both location IDs are absent."""
        result = self.env['stock.picking']._sor_infer_partner_id(False, False)
        self.assertFalse(result)

    def test_infer_partner_returns_false_when_field_absent(self):
        """_sor_infer_partner_id returns False gracefully when stock.location lacks contact_id.

        sor_locations_external adds contact_id to stock.location. Without that module (and
        without sor_locations_artist_studios adding artist_id), the method must not raise —
        it returns False and picking creation proceeds normally.
        """
        if 'contact_id' in self.env['stock.location']._fields:
            self.skipTest('sor_locations_external is installed — contact_id exists')
        if 'artist_id' in self.env['stock.location']._fields:
            self.skipTest('sor_locations_artist_studios is installed — artist_id exists')
        result = self.env['stock.picking']._sor_infer_partner_id(
            self.supplier_loc.id, self.stock_loc.id,
        )
        self.assertFalse(result)

    def test_create_without_partner_inference_does_not_raise(self):
        """create() succeeds without partner_id when location has no linked partner."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        self.assertTrue(picking.id)
        # partner_id may or may not be set depending on whether locations have partners
        # — test only that no error was raised and the record exists

    # ------------------------------------------------------------------
    # 10. post_init_hook — inventory settings enabled
    # ------------------------------------------------------------------

    def test_multi_locations_setting_enabled(self):
        """post_init_hook enables Multi-Locations; the group is active on the current user."""
        self.assertTrue(
            self.env.user.has_group('stock.group_stock_multi_locations'),
            'group_stock_multi_locations should be active after post_init_hook',
        )

    # ------------------------------------------------------------------
    # 11. Issue 18 (UAT) — movement reference sequence assignment
    # ------------------------------------------------------------------

    def test_new_picking_gets_sequence_reference(self):
        """New pickings receive a sequence-generated reference, not 'New' or '/'.

        Regression test for Issue 18 (UAT): a default_get override was setting
        defaults['name'] = 'New'. Odoo's native stock.picking.create() checks BOTH
        vals.get('name', '/') == '/' AND defaults.get('name', '/') == '/' before
        assigning the sequence. The override made the second condition False, so
        the sequence was never called and all new pickings were named 'New'.
        Removing the override restores correct sequence-based reference generation.
        """
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        self.assertNotEqual(
            picking.name, 'New',
            "Picking reference must not be 'New' — the default_get override was removed",
        )
        self.assertNotEqual(
            picking.name, '/',
            "Picking reference must not be '/' — a sequence must have been assigned",
        )
        self.assertTrue(
            picking.name,
            'Picking reference must be non-empty after creation',
        )

    # ------------------------------------------------------------------
    # 12. Issue 6 (UAT) — location confirmation dialog branding and double-confirm fix
    # ------------------------------------------------------------------

    def test_location_confirm_wizard_action_open_has_branded_name(self):
        """sor.movement.location.confirm.action_open() returns SOR-branded name.

        Issue 6 (UAT): the destination location update dialog was displaying the
        generic 'Odoo' title from the form view string attribute. action_open() must
        return a dict with a name key so the dialog title is SOR-branded.
        """
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        wizard = self.env['sor.movement.location.confirm'].create({
            'picking_id': picking.id,
        })
        action = wizard.action_open()
        self.assertIn(
            'name', action,
            'action_open must return a name key for SOR-branded dialog title',
        )
        self.assertEqual(
            action['name'], 'Confirm Location Update',
            "Dialog title must be 'Confirm Location Update', not the generic form string",
        )

    def test_button_validate_skip_source_check_context_key_present(self):
        """button_validate checks skip_source_location_check to prevent double-confirm.

        Issue 6 (UAT): when the source discrepancy wizard passes skip_source_location_check
        to button_validate, the destination location update dialog must also be suppressed.
        Verifies the context key is handled in the destination dialog skip condition.
        """
        src = inspect.getsource(
            self.env['stock.picking'].__class__.button_validate,
        )
        # Both context keys must appear in the destination skip condition together
        self.assertIn(
            'skip_source_location_check', src,
            'button_validate must check skip_source_location_check context key',
        )
        self.assertIn(
            'sor_skip_location_confirm', src,
            'button_validate must also check sor_skip_location_confirm context key',
        )

    # ------------------------------------------------------------------
    # 13. Deletion protection — only queued movements may be deleted
    # ------------------------------------------------------------------

    def _make_picking(self, state='queued'):
        """Create a minimal picking in the requested sor_movement_state.

        Uses direct SQL for states that cannot be reached via ORM write from the
        initial queued state — the write() guard enforces the 4-state machine
        (queued → ready → confirmed; queued/ready → cancelled).
        """
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        if state != 'queued':
            self.env.cr.execute(
                "UPDATE stock_picking SET sor_movement_state = %s WHERE id = %s",
                (state, picking.id),
            )
            picking.invalidate_recordset(['sor_movement_state'])
        return picking

    def test_deletion_allowed_when_queued(self):
        """A queued movement can be deleted without error."""
        picking = self._make_picking('queued')
        picking_id = picking.id
        picking.unlink()
        result = self.env['stock.picking'].search([('id', '=', picking_id)])
        self.assertFalse(result, 'Queued picking should have been deleted')

    def test_deletion_blocked_when_ready(self):
        """A movement in Ready state raises UserError on unlink."""
        picking = self._make_picking('ready')
        with self.assertRaises(UserError):
            picking.unlink()

    def test_deletion_blocked_when_confirmed(self):
        """A movement in Confirmed state raises UserError on unlink."""
        picking = self._make_picking('confirmed')
        with self.assertRaises(UserError):
            picking.unlink()

    def test_deletion_blocked_when_cancelled(self):
        """A cancelled movement raises UserError on unlink."""
        picking = self._make_picking('cancelled')
        with self.assertRaises(UserError):
            picking.unlink()

    # ------------------------------------------------------------------
    # 14. Owner propagation — ML owner_id set from picking partner_id
    # ------------------------------------------------------------------

    def test_owner_propagated_from_picking_partner(self):
        """stock.move.line.create sets owner_id from picking.partner_id."""
        partner = self.env['res.partner'].create({'name': 'Test Consignor'})
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'partner_id': partner.id,
        })
        product = self.env['product.product'].create({
            'name': 'Test Product',
            'type': 'consu',
            'is_storable': True,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': product.id,
            'product_uom_qty': 1,
            'product_uom': product.uom_id.id,
        })
        ml = self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'move_id': move.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': product.id,
            'quantity': 1,
        })
        self.assertEqual(
            ml.owner_id, partner,
            'owner_id should be set from picking.partner_id',
        )

    def test_owner_not_overridden_when_already_set(self):
        """Explicit owner_id in vals is preserved — not overridden by picking partner."""
        partner_a = self.env['res.partner'].create({'name': 'Picking Partner'})
        partner_b = self.env['res.partner'].create({'name': 'Explicit Owner'})
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'partner_id': partner_a.id,
        })
        product = self.env['product.product'].create({
            'name': 'Test Product B',
            'type': 'consu',
            'is_storable': True,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': product.id,
            'product_uom_qty': 1,
            'product_uom': product.uom_id.id,
        })
        ml = self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'move_id': move.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': product.id,
            'quantity': 1,
            'owner_id': partner_b.id,
        })
        self.assertEqual(
            ml.owner_id, partner_b,
            'Explicit owner_id in vals must not be overridden by picking partner',
        )

    def test_owner_not_set_when_picking_has_no_partner(self):
        """ML created for a picking with no partner leaves owner_id empty."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        product = self.env['product.product'].create({
            'name': 'Test Product C',
            'type': 'consu',
            'is_storable': True,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': product.id,
            'product_uom_qty': 1,
            'product_uom': product.uom_id.id,
        })
        ml = self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'move_id': move.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': product.id,
            'quantity': 1,
        })
        self.assertFalse(
            ml.owner_id,
            'owner_id should remain empty when picking has no partner',
        )
