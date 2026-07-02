# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import TransactionCase, tagged

from odoo.addons.sor_asset_paradigm_baseline.hooks import post_init_hook


@tagged('post_install', '-at_install')
class TestSorAssetParadigmBaseline(TransactionCase):
    """Tests for sor_asset_paradigm_baseline: Baseline Product creation via ORM."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.baseline = cls.env.ref(
            'sor_asset_paradigm_baseline.baseline_product',
            raise_if_not_found=False,
        )

    def test_baseline_product_exists(self):
        """post_init_hook creates the Baseline Product record."""
        self.assertTrue(
            self.baseline,
            "Baseline Product should exist after sor_asset_paradigm_baseline install",
        )

    def test_baseline_product_paradigm_is_standard(self):
        """Baseline Product has asset_paradigm='standard'."""
        self.assertEqual(
            self.baseline.asset_paradigm,
            'standard',
            "Baseline Product must carry the 'standard' paradigm",
        )

    def test_baseline_product_is_archived(self):
        """Baseline Product is archived (active=False) so it does not pollute
        normal product lists."""
        self.assertFalse(
            self.baseline.active,
            "Baseline Product should be archived (active=False)",
        )

    def test_baseline_product_created_via_orm(self):
        """Baseline Product has an ir.model.data record, confirming ORM creation
        rather than a raw SQL INSERT (which would not create the external ID)."""
        imd = self.env['ir.model.data'].search([
            ('module', '=', 'sor_asset_paradigm_baseline'),
            ('name', '=', 'baseline_product'),
            ('model', '=', 'product.template'),
        ])
        self.assertEqual(
            len(imd),
            1,
            "ir.model.data record for baseline_product must exist — confirms ORM create",
        )
        self.assertEqual(imd.res_id, self.baseline.id)

    def test_baseline_product_idempotent(self):
        """Running post_init_hook a second time does not duplicate the Baseline Product."""
        post_init_hook(self.env)
        count = self.env['ir.model.data'].search_count([
            ('module', '=', 'sor_asset_paradigm_baseline'),
            ('name', '=', 'baseline_product'),
        ])
        self.assertEqual(count, 1, "post_init_hook must be idempotent — no duplicate records")

    def test_standard_selection_value_registered(self):
        """`standard` is a valid selection value on product.template.asset_paradigm
        after this module is installed."""
        field = self.env['product.template']._fields.get('asset_paradigm')
        self.assertIsNotNone(field, "asset_paradigm field must exist on product.template")
        selection_keys = [k for k, _ in field.selection]
        self.assertIn(
            'standard',
            selection_keys,
            "'standard' must be a registered asset_paradigm selection value",
        )
