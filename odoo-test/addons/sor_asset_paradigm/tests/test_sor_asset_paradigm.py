from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestAssetParadigm(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # sor_artwork (installed in this DB) requires a Creator-type contact on all products
        # and also requires dimensions_width / dimensions_height.
        creator_type = cls.env['sor.contact.type'].search(
            [('code', '=', 'creator')], limit=1,
        )
        cls.creator = cls.env['res.partner'].create({
            'name': 'Test Creator (Paradigm)',
            'contact_types': [(4, creator_type.id)] if creator_type else [],
        })
        # Pass asset_paradigm='standard' explicitly so the sor_asset_paradigm_artwork
        # bridge does not override it with 'unique_object'. This keeps cls.product
        # neutral for base-module suppression tests (standard paradigm, no rules).
        cls.product = cls.env['product.template'].create({
            'name': 'Test Product',
            'type': 'consu',
            'is_storable': True,
            'creator_id': cls.creator.id,
            'dimensions_width': 10.0,
            'dimensions_height': 10.0,
            'asset_paradigm': 'standard',
        })

    def _set_debug_param(self, value):
        self.env['ir.config_parameter'].sudo().set_param(
            'sor_asset_paradigm.debug_show_quant_ui', value,
        )

    def tearDown(self):
        super().tearDown()
        self._set_debug_param('False')

    # --- AC3: is_element_suppressed ---

    def test_is_element_suppressed_returns_false_with_no_rules_for_paradigm(self):
        # 'standard' paradigm has no installed rules → not suppressed
        self.assertFalse(
            self.product.is_element_suppressed('forecast_button'),
        )

    def test_is_element_suppressed_returns_false_when_no_rules(self):
        self.product.write({'asset_paradigm': 'standard'})
        self.assertFalse(
            self.product.is_element_suppressed('forecast_button'),
        )

    def test_is_element_suppressed_returns_true_with_suppressed_rule(self):
        self.product.write({'asset_paradigm': 'standard'})
        rule = self.env['sor.asset.paradigm.rule'].create({
            'paradigm': 'standard',
            'element_key': 'forecast_button',
            'active': True,
        })
        self.assertTrue(self.product.is_element_suppressed('forecast_button'))
        rule.unlink()

    def test_is_element_suppressed_returns_false_with_unsuppressed_rule(self):
        self.product.write({'asset_paradigm': 'standard'})
        rule = self.env['sor.asset.paradigm.rule'].create({
            'paradigm': 'standard',
            'element_key': 'forecast_button',
            'active': False,
        })
        self.assertFalse(self.product.is_element_suppressed('forecast_button'))
        rule.unlink()

    # --- AC4: debug param ---

    def test_debug_param_overrides_suppressed_rule(self):
        self.product.write({'asset_paradigm': 'standard'})
        rule = self.env['sor.asset.paradigm.rule'].create({
            'paradigm': 'standard',
            'element_key': 'forecast_button',
            'active': True,
        })
        self.assertTrue(self.product.is_element_suppressed('forecast_button'))
        self._set_debug_param('True')
        self.assertFalse(self.product.is_element_suppressed('forecast_button'))
        rule.unlink()

    # --- AC7: baseline bridge (sor_asset_paradigm_baseline installed alongside) ---

    def test_baseline_product_has_standard_paradigm(self):
        baseline = self.env['product.template'].with_context(active_test=False).search(
            [('name', 'ilike', 'Baseline Product')], limit=1,
        )
        self.assertTrue(baseline, "Baseline Product record not found")
        self.assertEqual(baseline.asset_paradigm, 'standard')

    def test_baseline_product_is_inactive(self):
        baseline = self.env['product.template'].with_context(active_test=False).search(
            [('name', 'ilike', 'Baseline Product')], limit=1,
        )
        self.assertTrue(baseline, "Baseline Product record not found")
        self.assertFalse(baseline.active)

    def test_baseline_product_is_not_suppressed(self):
        baseline = self.env['product.template'].with_context(active_test=False).search(
            [('name', 'ilike', 'Baseline Product')], limit=1,
        )
        self.assertTrue(baseline, "Baseline Product record not found")
        self.assertFalse(baseline.is_element_suppressed('forecast_button'))


@tagged('post_install', '-at_install')
class TestAssetParadigmConstraint(TransactionCase):
    """Story 06 — UNIQUE(paradigm, element_key) constraint is enforced at DB level."""

    def test_duplicate_paradigm_element_key_raises(self):
        """Creating two rules with the same (paradigm, element_key) raises an Exception."""
        self.env['sor.asset.paradigm.rule'].create({
            'paradigm': 'standard',
            'element_key': 'test_constraint_key',
            'active': True,
        })
        with self.assertRaises(Exception):
            self.env['sor.asset.paradigm.rule'].create({
                'paradigm': 'standard',
                'element_key': 'test_constraint_key',
                'active': False,
            })
            self.env.flush_all()

    def test_different_element_key_same_paradigm_ok(self):
        """Two rules with the same paradigm but different element_key do not conflict."""
        self.env['sor.asset.paradigm.rule'].create({
            'paradigm': 'standard',
            'element_key': 'test_key_alpha',
            'active': True,
        })
        rule2 = self.env['sor.asset.paradigm.rule'].create({
            'paradigm': 'standard',
            'element_key': 'test_key_beta',
            'active': True,
        })
        self.assertTrue(rule2.exists())

    def test_same_element_key_different_paradigm_ok(self):
        """Two rules with the same element_key but different paradigm do not conflict."""
        self.env['sor.asset.paradigm.rule'].create({
            'paradigm': 'standard',
            'element_key': 'test_shared_key',
            'active': True,
        })
        rule2 = self.env['sor.asset.paradigm.rule'].create({
            'paradigm': 'unique_object',
            'element_key': 'test_shared_key',
            'active': True,
        })
        self.assertTrue(rule2.exists())
