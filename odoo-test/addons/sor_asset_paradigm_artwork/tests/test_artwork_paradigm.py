from odoo.tests import TransactionCase, tagged

from odoo.addons.sor_asset_paradigm.models.const import SUPPRESSIBLE_ELEMENTS
from odoo.addons.sor_asset_paradigm_artwork.hooks import post_init_hook


@tagged('post_install', '-at_install')
class TestArtworkParadigm(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # sor_artwork requires a Creator-type contact and dimensions for all products.
        creator_type = cls.env['sor.contact.type'].search(
            [('code', '=', 'creator')], limit=1,
        )
        cls.creator = cls.env['res.partner'].create({
            'name': 'Test Creator (Artwork Paradigm)',
            'contact_types': [(4, creator_type.id)] if creator_type else [],
        })
        # cls.artwork gets asset_paradigm='unique_object' set by the bridge create() override.
        cls.artwork = cls.env['product.template'].create({
            'name': 'Test Artwork',
            'creator_id': cls.creator.id,
            'dimensions_width': 10.0,
            'dimensions_height': 10.0,
        })
        # cls.standard is explicitly given 'standard' paradigm so the bridge does not
        # override it with 'unique_object'. This simulates a non-unique-object product
        # for suppression boundary tests.
        cls.standard = cls.env['product.template'].create({
            'name': 'Test Standard Product',
            'creator_id': cls.creator.id,
            'dimensions_width': 10.0,
            'dimensions_height': 10.0,
            'asset_paradigm': 'standard',
        })

    # --- AC1: auto-install (structural — presence of module implies it) ---

    # --- AC2: paradigm auto-assigned on create/write ---

    def test_new_artwork_gets_unique_object_paradigm(self):
        self.assertEqual(self.artwork.asset_paradigm, 'unique_object')

    def test_explicit_non_unique_object_paradigm_not_overridden_on_create(self):
        # The bridge create() only assigns unique_object when no paradigm is set.
        # cls.standard was created with asset_paradigm='standard' — bridge left it unchanged.
        self.assertEqual(self.standard.asset_paradigm, 'standard')

    def test_write_product_type_to_artwork_sets_paradigm(self):
        product = self.env['product.template'].create({
            'name': 'Future Artwork',
            'creator_id': self.creator.id,
            'dimensions_width': 10.0,
            'dimensions_height': 10.0,
        })
        # Forcibly clear the paradigm via SQL to simulate a pre-paradigm product,
        # then trigger the bridge write() override by writing product_type='artwork'.
        self.env.cr.execute(
            "UPDATE product_template SET asset_paradigm = NULL WHERE id = %s",
            (product.id,),
        )
        self.env.cache.invalidate()
        self.assertFalse(product.asset_paradigm)
        product.write({'product_type': 'artwork'})
        self.assertEqual(product.asset_paradigm, 'unique_object')

    # --- AC3: rule records installed ---

    def test_thirteen_rules_installed_for_unique_object(self):
        count = self.env['sor.asset.paradigm.rule'].search_count(
            [('paradigm', '=', 'unique_object')],
        )
        self.assertEqual(count, 13)

    def test_all_element_keys_covered(self):
        rules = self.env['sor.asset.paradigm.rule'].with_context(active_test=False).search(
            [('paradigm', '=', 'unique_object')],
        )
        installed_keys = {r.element_key for r in rules}
        expected_keys = {k for k, _ in SUPPRESSIBLE_ELEMENTS}
        self.assertEqual(installed_keys, expected_keys)

    # --- AC4, AC5, AC7: suppression booleans ---

    def test_is_forecast_btn_suppressed_true_for_artwork(self):
        self.assertTrue(self.artwork.is_forecast_btn_suppressed)

    def test_all_suppression_booleans_true_for_artwork(self):
        self.assertTrue(self.artwork.is_forecast_btn_suppressed)
        self.assertTrue(self.artwork.is_reorder_btn_suppressed)
        self.assertTrue(self.artwork.is_moves_btn_suppressed)
        self.assertTrue(self.artwork.is_putaway_btn_suppressed)
        self.assertTrue(self.artwork.is_storage_cap_btn_suppressed)
        self.assertTrue(self.artwork.is_qty_available_suppressed)
        self.assertTrue(self.artwork.is_qty_column_suppressed)
        self.assertTrue(self.artwork.is_operations_group_suppressed)
        self.assertTrue(self.artwork.is_replenish_suppressed)
        self.assertTrue(self.artwork.is_odoo_product_type_field_suppressed)
        self.assertTrue(self.artwork.is_product_type_field_suppressed)
        self.assertTrue(self.artwork.is_track_inventory_field_suppressed)
        self.assertTrue(self.artwork.is_inventory_tab_suppressed)

    def test_show_qty_status_button_false_for_artwork_template(self):
        self.assertFalse(self.artwork.show_on_hand_qty_status_button)
        self.assertFalse(self.artwork.show_forecasted_qty_status_button)

    # --- AC8: standard product not suppressed ---

    def test_standard_product_not_suppressed(self):
        self.assertFalse(self.standard.is_element_suppressed('forecast_button'))
        self.assertFalse(self.standard.is_element_suppressed('qty_column'))
        self.assertFalse(self.standard.is_element_suppressed('inventory_tab'))

    # --- AC9: rule toggle ---

    def test_rule_toggle_affects_suppression(self):
        rule = self.env['sor.asset.paradigm.rule'].search(
            [('paradigm', '=', 'unique_object'), ('element_key', '=', 'forecast_button')],
            limit=1,
        )
        self.assertTrue(rule, "forecast_button rule not found")
        self.assertTrue(self.artwork.is_forecast_btn_suppressed)
        try:
            rule.write({'active': False})
            self.artwork._compute_artwork_suppression()
            self.assertFalse(self.artwork.is_forecast_btn_suppressed)
        finally:
            rule.write({'active': True})

    # --- post_init_hook: backfill ---

    def test_post_init_hook_sets_paradigm_on_existing_artworks(self):
        product = self.env['product.template'].create({
            'name': 'Pre-existing Artwork',
            'creator_id': self.creator.id,
            'dimensions_width': 10.0,
            'dimensions_height': 10.0,
        })
        # Simulate a pre-existing record by forcibly clearing paradigm
        self.env.cr.execute(
            "UPDATE product_template SET asset_paradigm = NULL WHERE id = %s",
            (product.id,),
        )
        self.env.cache.invalidate()
        self.assertFalse(product.asset_paradigm)

        post_init_hook(self.env)

        # Flush pending ORM writes to DB, then clear the record cache before re-reading.
        self.env.flush_all()
        product.invalidate_recordset(['asset_paradigm'])
        self.assertEqual(product.asset_paradigm, 'unique_object')
