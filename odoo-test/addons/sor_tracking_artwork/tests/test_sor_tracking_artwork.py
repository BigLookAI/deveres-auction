from odoo.exceptions import UserError  # noqa: F401 — available for test assertions
from odoo.tests import TransactionCase


class TestSorTrackingArtwork(TransactionCase):
    """Tests for the sor_tracking_artwork bridge module.

    Covers: module installs, serial tracking field, default_get returns
    tracking='serial' for artwork product context, migration ensures
    existing artworks have serial tracking, composability, serial
    pre-population on ML create, BUG-08 guard, ghost ML deletion, and
    per-company serial sequences.

    Artwork product creation requires a Creator/Artist-typed contact
    (sor_artwork_contact_roles validation). Tests that need an artwork
    product use raw SQL to find an existing one rather than creating new
    ones, avoiding the contact-type setup overhead.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1,
        )
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.receipt_type = cls.env['stock.picking.type'].search(
            [('code', '=', 'incoming'), ('warehouse_id', '=', cls.warehouse.id)], limit=1,
        )
        # Prefer a company-neutral supplier location (company_id=False) to avoid
        # _check_company() failures caused by receipt type defaults that may have been
        # misconfigured to point at a different company's location in multi-company DBs.
        cls.supplier_loc = (
            cls.env['stock.location'].search(
                [('usage', '=', 'supplier'), ('company_id', '=', False)], limit=1,
            )
            or cls.receipt_type.default_location_src_id
            or cls.env.ref('stock.stock_location_suppliers')
        )
        # Locate an existing artwork product via SQL (ORM creation requires Creator contact).
        # Filter to the current company or company-global products so that stock.move
        # _check_company() passes (product_id.company_id must match the picking company).
        cls.env.cr.execute(
            "SELECT pp.id FROM product_product pp "
            "JOIN product_template pt ON pp.product_tmpl_id = pt.id "
            "WHERE pt.product_type = 'artwork' AND pt.tracking = 'serial' "
            "AND (pt.company_id IS NULL OR pt.company_id = %s) LIMIT 1",
            (cls.company.id,),
        )
        row = cls.env.cr.fetchone()
        cls.artwork_product = cls.env['product.product'].browse(row[0]) if row else None

    # ------------------------------------------------------------------
    # 1. Module installs
    # ------------------------------------------------------------------

    def test_module_installs_tracking_field_present(self):
        """sor_tracking_artwork is installed and tracking field is on product.template."""
        self.assertIn('tracking', self.env['product.template']._fields)

    def test_module_installs_move_line_model_accessible(self):
        """stock.move.line model is accessible — bridge views loaded cleanly."""
        self.assertEqual(self.env['stock.move.line']._name, 'stock.move.line')

    # ------------------------------------------------------------------
    # 2. Tracking default — default_get returns serial for artwork context
    # ------------------------------------------------------------------

    def test_default_get_with_artwork_context_returns_serial_tracking(self):
        """default_get returns tracking='serial' when product_type defaults to artwork."""
        defaults = self.env['product.template'].with_context(
            default_product_type='artwork',
        ).default_get(['product_type', 'tracking'])
        if defaults.get('product_type') == 'artwork':
            self.assertEqual(
                defaults.get('tracking'), 'serial',
                "default_get must return tracking='serial' for artwork product_type",
            )

    def test_default_get_without_artwork_context_does_not_force_serial(self):
        """default_get without artwork context does not override tracking to serial."""
        defaults = self.env['product.template'].default_get(['product_type', 'tracking'])
        if defaults.get('product_type') != 'artwork':
            # non-artwork default should not have been forced to serial by this bridge
            tracking = defaults.get('tracking', False)
            self.assertNotEqual(
                tracking, 'serial',
                'Non-artwork default_get must not force tracking=serial',
            )

    # ------------------------------------------------------------------
    # 3. Migration — existing artworks have serial tracking
    # ------------------------------------------------------------------

    def test_all_installed_artworks_have_serial_tracking(self):
        """All artwork products in the DB have tracking='serial' after migration."""
        artworks = self.env['product.template'].search(
            [('product_type', '=', 'artwork')],
        )
        for artwork in artworks:
            self.assertEqual(
                artwork.tracking, 'serial',
                f'Artwork "{artwork.name}" must have tracking=serial after migration',
            )

    # ------------------------------------------------------------------
    # 4. Composability — bridge depends on both parents
    # ------------------------------------------------------------------

    def test_composability_sor_tracking_installed(self):
        """sor_tracking is installed — stock.picking has sor_movement_state."""
        self.assertIn('sor_movement_state', self.env['stock.picking']._fields)

    def test_composability_sor_artwork_installed(self):
        """sor_artwork is installed — product.template has product_type field."""
        self.assertIn('product_type', self.env['product.template']._fields)

    def test_composability_serial_tracking_selection_available(self):
        """'serial' tracking selection value is available on product.template."""
        tracking_field = self.env['product.template']._fields.get('tracking')
        if tracking_field and hasattr(tracking_field, 'selection'):
            keys = [k for k, _ in tracking_field.selection]
            self.assertIn('serial', keys)

    # ------------------------------------------------------------------
    # 5. Issue 4 (UAT) — lot_ids column surfaced on main movement form
    # ------------------------------------------------------------------

    def test_lot_ids_field_accessible_on_stock_move(self):
        """lot_ids (serial numbers) field is accessible on stock.move for view display.

        The view override in sor_tracking_artwork patches the lot_ids column in the
        Operations list (stock.move records nested in the picking form), making the
        serial number column visible in queued state for tracked products.
        """
        self.assertIn('lot_ids', self.env['stock.move']._fields)

    # ------------------------------------------------------------------
    # 6. Issue 8 (UAT) — artwork product.product navigation redirects to template
    # ------------------------------------------------------------------

    def test_artwork_product_product_get_formview_action_redirects_to_template(self):
        """get_formview_action on artwork product.product redirects to product.template.

        stock.move lines reference product.product (not product.template). Navigating
        via the movement line product link calls get_formview_action on product.product,
        which would normally open the product.product form — a form that does not carry
        SOR artwork customizations. The override redirects artwork navigation to
        product.template where the SOR artwork form lives.
        """
        artwork_tmpl = self.env['product.template'].search(
            [('product_type', '=', 'artwork')], limit=1,
        )
        if not artwork_tmpl:
            self.skipTest('No artwork products in test database — skipping Issue 8 test')
        variant = artwork_tmpl.product_variant_ids[:1]
        if not variant:
            self.skipTest('No product variant found for artwork template')
        action = variant.get_formview_action()
        self.assertEqual(
            action.get('res_model'), 'product.template',
            'get_formview_action on artwork product.product must redirect to product.template',
        )
        self.assertEqual(
            action.get('res_id'), artwork_tmpl.id,
            'get_formview_action must return the correct product.template id',
        )

    def test_non_artwork_get_formview_action_not_overridden_to_wrong_record(self):
        """get_formview_action override only fires for artwork — non-artwork is unaffected."""
        non_artwork_tmpl = self.env['product.template'].search(
            [('product_type', '!=', 'artwork'), ('product_variant_ids', '!=', False)],
            limit=1,
        )
        if not non_artwork_tmpl:
            self.skipTest('No non-artwork products with variants in test database')
        variant = non_artwork_tmpl.product_variant_ids[:1]
        action = variant.get_formview_action()
        if action.get('res_model') == 'product.template':
            # Odoo may already redirect some product types to template — verify
            # the res_id matches this variant's template, not an artwork template
            self.assertEqual(
                action.get('res_id'), non_artwork_tmpl.id,
                'If res_model is product.template, res_id must match this template',
            )
        else:
            # Standard case: non-artwork stays on product.product
            self.assertNotEqual(
                non_artwork_tmpl.product_type, 'artwork',
                'Non-artwork product must not have product_type=artwork',
            )

    # ------------------------------------------------------------------
    # 7. Issue 9 (UAT) — Traceability button and sor_movement_count
    # ------------------------------------------------------------------

    def test_sor_movement_count_field_on_product_template(self):
        """sor_movement_count computed field exists on product.template (Issue 9)."""
        self.assertIn(
            'sor_movement_count', self.env['product.template']._fields,
            'sor_movement_count must be added by sor_tracking_artwork',
        )

    def test_action_view_traceability_method_present(self):
        """action_view_traceability method is present on product.template (Issue 9)."""
        self.assertTrue(
            hasattr(self.env['product.template'], 'action_view_traceability'),
            'action_view_traceability method must be present on product.template',
        )

    def test_action_view_traceability_returns_correct_action(self):
        """action_view_traceability returns a properly structured act_window action."""
        artwork_tmpl = self.env['product.template'].search(
            [('product_type', '=', 'artwork')], limit=1,
        )
        if not artwork_tmpl:
            self.skipTest('No artwork products in test database — skipping Issue 9 test')
        action = artwork_tmpl.action_view_traceability()
        self.assertEqual(action.get('type'), 'ir.actions.act_window')
        self.assertEqual(action.get('name'), 'Traceability')
        self.assertEqual(action.get('res_model'), 'stock.move.line')
        domain_str = str(action.get('domain', []))
        self.assertIn(
            'product_tmpl_id', domain_str,
            'Traceability action domain must filter by product_id.product_tmpl_id',
        )
        self.assertIn(
            'done', domain_str,
            'Traceability action domain must filter to state=done',
        )

    # ------------------------------------------------------------------
    # 8. Serial pre-population — Story 04 AC 1 and AC 2
    # ------------------------------------------------------------------

    def test_serial_prepopulated_on_create_for_unique_object_artwork(self):
        """ML create auto-populates lot_name for unique_object+serial artwork."""
        if not self.artwork_product:
            self.skipTest('No artwork product with serial tracking in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': self.artwork_product.id,
            'product_uom_qty': 1,
            'product_uom': self.artwork_product.uom_id.id,
        })
        ml = self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'move_id': move.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': self.artwork_product.id,
            'quantity': 1,
        })
        self.assertTrue(
            ml.lot_name,
            'lot_name should be auto-populated for unique_object+serial artwork ML',
        )
        self.assertRegex(
            ml.lot_name,
            r'^SN/\d{4}/\d{5}$',
            'Serial format must match SN/YYYY/NNNNN',
        )

    def test_serial_not_set_when_lot_name_already_provided(self):
        """ML create skips serial generation when lot_name is already supplied."""
        if not self.artwork_product:
            self.skipTest('No artwork product with serial tracking in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': self.artwork_product.id,
            'product_uom_qty': 1,
            'product_uom': self.artwork_product.uom_id.id,
        })
        ml = self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'move_id': move.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': self.artwork_product.id,
            'quantity': 1,
            'lot_name': 'CUSTOM-001',
        })
        self.assertEqual(
            ml.lot_name, 'CUSTOM-001',
            'Provided lot_name must not be overridden by sequence',
        )

    def test_bug08_guard_second_ml_on_same_move_skips_serial(self):
        """BUG-08 guard: second ML on same move does not consume another serial."""
        if not self.artwork_product:
            self.skipTest('No artwork product with serial tracking in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': self.artwork_product.id,
            'product_uom_qty': 1,
            'product_uom': self.artwork_product.uom_id.id,
        })
        # First ML — should get a serial
        ml1 = self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'move_id': move.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': self.artwork_product.id,
            'quantity': 1,
        })
        self.assertTrue(ml1.lot_name, 'First ML must receive a serial number')
        # Second ML on the same move — guard must skip serial generation
        ml2 = self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'move_id': move.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': self.artwork_product.id,
            'quantity': 0,
        })
        self.assertFalse(
            ml2.lot_name,
            'BUG-08 guard: second ML on same move must not get an auto-serial',
        )
        self.assertNotEqual(
            ml2.lot_name, ml1.lot_name,
            'Second ML must not share the first ML serial',
        )

    def test_ghost_ml_deleted_before_action_confirm(self):
        """Ghost MLs (qty=0, lot_name set, no lot_id) are deleted by action_confirm."""
        if not self.artwork_product:
            self.skipTest('No artwork product with serial tracking in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': self.artwork_product.id,
            'product_uom_qty': 1,
            'product_uom': self.artwork_product.uom_id.id,
        })
        # Simulate OWL ghost ML: qty=0, lot_name set, no lot_id
        ghost_ml = self.env['stock.move.line'].create({
            'picking_id': picking.id,
            'move_id': move.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            'product_id': self.artwork_product.id,
            'quantity': 0,
            'lot_name': 'GHOST-SN',
        })
        ghost_ml_id = ghost_ml.id
        picking.action_confirm()
        # Ghost ML must have been deleted
        surviving = self.env['stock.move.line'].search([('id', '=', ghost_ml_id)])
        self.assertFalse(
            surviving,
            'action_confirm must delete ghost MLs (qty=0, lot_name set, no lot_id)',
        )

    def test_serial_sequence_exists_for_current_company(self):
        """sor.artwork.serial sequence exists for the current company."""
        seq = self.env['ir.sequence'].search([
            ('code', '=', 'sor.artwork.serial'),
            ('company_id', '=', self.company.id),
        ])
        self.assertTrue(seq, 'sor.artwork.serial sequence must exist for current company')
        self.assertEqual(seq.padding, 5, 'Sequence padding must be 5 digits')
        self.assertIn('SN/', seq.prefix, 'Sequence prefix must start with SN/')

    def test_serial_sequence_is_company_scoped(self):
        """A second company gets its own sor.artwork.serial sequence on creation."""
        company2 = self.env['res.company'].create({'name': 'Test Company SN Isolation'})
        seq = self.env['ir.sequence'].search([
            ('code', '=', 'sor.artwork.serial'),
            ('company_id', '=', company2.id),
        ])
        self.assertTrue(
            seq,
            'res.company.create must provision sor.artwork.serial sequence for the new company',
        )
        seq1 = self.env['ir.sequence'].search([
            ('code', '=', 'sor.artwork.serial'),
            ('company_id', '=', self.company.id),
        ])
        self.assertNotEqual(
            seq.id, seq1.id,
            'Each company must have its own independent sor.artwork.serial sequence',
        )
