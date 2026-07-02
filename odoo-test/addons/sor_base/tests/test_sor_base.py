# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestSorBase(TransactionCase):
    """Tests for sor_base: module installation and dependency cascade."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Module = cls.env['ir.module.module']

    def test_module_installs_cleanly(self):
        """sor_base is installed and in the 'installed' state."""
        module = self.Module.search([('name', '=', 'sor_base')], limit=1)
        self.assertTrue(module.exists(), "sor_base module should exist")
        self.assertEqual(module.state, 'installed', "sor_base should be installed")

    def test_horizontal_dependencies_installed(self):
        """Installing sor_base installs sor_asset_paradigm and sor_business_model."""
        for dep_name in ('sor_asset_paradigm', 'sor_business_model'):
            dep = self.Module.search([('name', '=', dep_name)], limit=1)
            self.assertTrue(dep.exists(), f"{dep_name} should exist")
            self.assertEqual(dep.state, 'installed', f"{dep_name} should be installed")

    def test_bridge_modules_installed_with_sor_artwork(self):
        """Bridge modules auto-install when sor_base + sor_artwork are both present."""
        artwork = self.Module.search([('name', '=', 'sor_artwork')], limit=1)
        if not artwork or artwork.state != 'installed':
            self.skipTest("sor_artwork is not installed — bridge test skipped")
        for bridge_name in ('sor_asset_paradigm_artwork', 'sor_business_model_non_commercial'):
            bridge = self.Module.search([('name', '=', bridge_name)], limit=1)
            self.assertTrue(bridge.exists(), f"{bridge_name} should exist")
            self.assertEqual(bridge.state, 'installed', f"{bridge_name} should be installed")

    def test_sor_artwork_depends_on_sor_base(self):
        """sor_artwork declares sor_base as a dependency."""
        dep = self.env['ir.module.module.dependency'].search([
            ('module_id.name', '=', 'sor_artwork'),
            ('name', '=', 'sor_base'),
        ], limit=1)
        self.assertTrue(dep.exists(), "sor_artwork should declare sor_base as a dependency")

    def test_sor_base_is_not_an_application(self):
        """sor_base is a Hidden/Technical module, not a top-level application."""
        module = self.Module.search([('name', '=', 'sor_base')], limit=1)
        self.assertFalse(module.application, "sor_base should not be an application module")

    def test_no_models_created(self):
        """sor_base creates no models of its own."""
        # Any model listed as belonging *only* to sor_base would be unexpected
        models_only_from_base = self.env['ir.model'].search([
            ('modules', '=', 'sor_base'),
        ])
        self.assertEqual(
            len(models_only_from_base), 0,
            "sor_base should define no models of its own",
        )
