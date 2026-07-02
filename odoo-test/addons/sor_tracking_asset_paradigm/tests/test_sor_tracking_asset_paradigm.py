from odoo.tests import TransactionCase


class TestSorTrackingAssetParadigm(TransactionCase):
    """Tests for the sor_tracking_asset_paradigm bridge module.

    Covers: module installs, sor_all_unique_objects computed field on
    stock.picking and stock.move, automatic quantity defaulting for
    unique-object products, and composability.

    Data setup uses raw SQL to locate existing products rather than
    creating new ones. sor_tracking_asset_paradigm loads before
    sor_artwork in the module dependency order, so sor_artwork's
    product_type NOT NULL constraint exists in the DB but the field
    is not yet in the ORM — product creation via ORM would fail.
    Raw SQL product lookup sidesteps this ordering constraint.

    Odoo 19 note: stock.move has no 'name' field (_rec_name = 'reference').
    All create() calls omit 'name'; description_picking is computed from the product.
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.warehouse = cls.env['stock.warehouse'].search(
            [('company_id', '=', cls.company.id)], limit=1,
        )
        cls.stock_loc = cls.warehouse.lot_stock_id
        cls.supplier_loc = cls.env.ref('stock.stock_location_suppliers')
        cls.receipt_type = cls.env['stock.picking.type'].search(
            [('code', '=', 'incoming'), ('warehouse_id', '=', cls.warehouse.id)], limit=1,
        )

        # Locate existing unique_object product via SQL — avoids ORM field validation
        # for selection values that may not yet be in the registry at this load phase.
        cls.env.cr.execute("""
            SELECT pp.id
            FROM product_product pp
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            WHERE pt.asset_paradigm = 'unique_object'
            LIMIT 1
        """)
        row = cls.env.cr.fetchone()
        cls.unique_product = cls.env['product.product'].browse(row[0]) if row else None

        # Locate existing storable non-unique-object product for standard-case tests.
        cls.env.cr.execute("""
            SELECT pp.id
            FROM product_product pp
            JOIN product_template pt ON pp.product_tmpl_id = pt.id
            WHERE pt.is_storable = true
            AND (pt.asset_paradigm IS NULL OR pt.asset_paradigm != 'unique_object')
            LIMIT 1
        """)
        row = cls.env.cr.fetchone()
        cls.standard_product = cls.env['product.product'].browse(row[0]) if row else None

    # ------------------------------------------------------------------
    # 1. Module installs
    # ------------------------------------------------------------------

    def test_module_installs_picking_field(self):
        """sor_tracking_asset_paradigm adds sor_all_unique_objects to stock.picking."""
        self.assertIn('sor_all_unique_objects', self.env['stock.picking']._fields)

    def test_module_installs_move_field(self):
        """sor_tracking_asset_paradigm adds sor_all_unique_objects to stock.move."""
        self.assertIn('sor_all_unique_objects', self.env['stock.move']._fields)

    def test_module_installs_asset_paradigm_field(self):
        """sor_asset_paradigm is installed — product.template has asset_paradigm field."""
        self.assertIn('asset_paradigm', self.env['product.template']._fields)

    # ------------------------------------------------------------------
    # 2. sor_all_unique_objects computed field on stock.picking
    # ------------------------------------------------------------------

    def test_all_unique_objects_true_when_all_moves_are_unique(self):
        """sor_all_unique_objects is True when all moves are unique_object products."""
        if not self.unique_product:
            self.skipTest('No unique_object products in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        self.env['stock.move'].create({
            'picking_id': picking.id,
            'product_id': self.unique_product.id,
            'product_uom_qty': 1,
            'product_uom': self.unique_product.uom_id.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        picking.invalidate_recordset(['sor_all_unique_objects'])
        self.assertTrue(
            picking.sor_all_unique_objects,
            'Picking with only unique_object product must have sor_all_unique_objects=True',
        )

    def test_all_unique_objects_false_for_empty_picking(self):
        """sor_all_unique_objects is False when the picking has no move lines."""
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        self.assertFalse(
            picking.sor_all_unique_objects,
            'Empty picking must have sor_all_unique_objects=False',
        )

    def test_all_unique_objects_false_for_mixed_picking(self):
        """sor_all_unique_objects is False when picking has mixed paradigm products."""
        if not self.unique_product or not self.standard_product:
            self.skipTest('Requires both unique_object and standard products in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        uom = self.env.ref('uom.product_uom_unit')
        self.env['stock.move'].create([
            {
                'picking_id': picking.id,
                'product_id': self.unique_product.id,
                'product_uom_qty': 1,
                'product_uom': uom.id,
                'location_id': self.supplier_loc.id,
                'location_dest_id': self.stock_loc.id,
            },
            {
                'picking_id': picking.id,
                'product_id': self.standard_product.id,
                'product_uom_qty': 5,
                'product_uom': uom.id,
                'location_id': self.supplier_loc.id,
                'location_dest_id': self.stock_loc.id,
            },
        ])
        picking.invalidate_recordset(['sor_all_unique_objects'])
        self.assertFalse(
            picking.sor_all_unique_objects,
            'Picking with mixed paradigm products must have sor_all_unique_objects=False',
        )

    def test_all_unique_objects_false_for_standard_only_picking(self):
        """sor_all_unique_objects is False when all moves are standard products."""
        if not self.standard_product:
            self.skipTest('No standard storable products in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        self.env['stock.move'].create({
            'picking_id': picking.id,
            'product_id': self.standard_product.id,
            'product_uom_qty': 5,
            'product_uom': self.standard_product.uom_id.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        picking.invalidate_recordset(['sor_all_unique_objects'])
        self.assertFalse(
            picking.sor_all_unique_objects,
            'Picking with only standard products must have sor_all_unique_objects=False',
        )

    # ------------------------------------------------------------------
    # 3. sor_all_unique_objects propagates to stock.move
    # ------------------------------------------------------------------

    def test_move_reflects_picking_all_unique_objects_value(self):
        """stock.move.sor_all_unique_objects mirrors its picking's computed value."""
        if not self.unique_product:
            self.skipTest('No unique_object products in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'product_id': self.unique_product.id,
            'product_uom_qty': 1,
            'product_uom': self.unique_product.uom_id.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        picking.invalidate_recordset(['sor_all_unique_objects'])
        move.invalidate_recordset(['sor_all_unique_objects'])
        self.assertTrue(picking.sor_all_unique_objects)
        self.assertEqual(
            move.sor_all_unique_objects, picking.sor_all_unique_objects,
            'stock.move.sor_all_unique_objects must mirror picking value',
        )

    # ------------------------------------------------------------------
    # 4. Quantity defaulting for unique-object products in create()
    # ------------------------------------------------------------------

    def test_create_move_without_qty_defaults_to_one_for_unique_object(self):
        """create() sets product_uom_qty=1 for unique_object products when omitted."""
        if not self.unique_product:
            self.skipTest('No unique_object products in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'product_id': self.unique_product.id,
            'product_uom': self.unique_product.uom_id.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
            # product_uom_qty deliberately omitted
        })
        self.assertEqual(
            move.product_uom_qty, 1,
            'Unique-object move created without qty must default to 1',
        )

    def test_create_move_with_explicit_qty_not_overridden(self):
        """create() does not override product_uom_qty when explicitly provided."""
        if not self.unique_product:
            self.skipTest('No unique_object products in test DB')
        picking = self.env['stock.picking'].create({
            'picking_type_id': self.receipt_type.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        move = self.env['stock.move'].create({
            'picking_id': picking.id,
            'product_id': self.unique_product.id,
            'product_uom_qty': 3,
            'product_uom': self.unique_product.uom_id.id,
            'location_id': self.supplier_loc.id,
            'location_dest_id': self.stock_loc.id,
        })
        self.assertEqual(
            move.product_uom_qty, 3,
            'Explicitly provided product_uom_qty must not be overridden',
        )

    # ------------------------------------------------------------------
    # 5. Composability — bridge depends on both parents
    # ------------------------------------------------------------------

    def test_composability_sor_tracking_installed(self):
        """sor_tracking is installed — sor_movement_state field is present."""
        self.assertIn('sor_movement_state', self.env['stock.picking']._fields)

    def test_composability_sor_asset_paradigm_installed(self):
        """sor_asset_paradigm is installed — asset_paradigm field is present."""
        self.assertIn('asset_paradigm', self.env['product.template']._fields)

    def test_unique_object_paradigm_in_db(self):
        """Products can store asset_paradigm='unique_object' in the database.

        Verified via raw SQL since the ORM selection may not include 'unique_object'
        at this module's load phase — sor_asset_paradigm_artwork, which adds the
        selection value, may load after this module in the --test-enable sequence.
        """
        if not self.unique_product:
            self.skipTest('No unique_object products in test DB')
        self.env.cr.execute(
            "SELECT asset_paradigm FROM product_template WHERE id = %s",
            (self.unique_product.product_tmpl_id.id,),
        )
        row = self.env.cr.fetchone()
        self.assertEqual(row[0], 'unique_object')
