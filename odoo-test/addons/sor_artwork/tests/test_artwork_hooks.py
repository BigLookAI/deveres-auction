# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import TransactionCase, tagged

from odoo.addons.sor_artwork.hooks import post_init_hook, uninstall_hook


@tagged('post_install', '-at_install')
class TestArtworkHooks(TransactionCase):
    """Tests for sor_artwork post_init_hook (menu suppression) and
    guarded default_get (product_type stamping fix)."""

    def test_post_init_hook_suppresses_inventory_menu(self):
        """Calling post_init_hook deactivates stock.menu_stock_root."""
        menu = self.env.ref('stock.menu_stock_root', raise_if_not_found=False)
        if not menu:
            self.skipTest("stock.menu_stock_root not present in this environment")
        post_init_hook(self.env)
        menu.invalidate_recordset(['active'])
        self.assertFalse(
            menu.active,
            "post_init_hook must deactivate stock.menu_stock_root",
        )

    def test_uninstall_hook_importable(self):
        """uninstall_hook is importable from the sor_artwork package."""
        self.assertTrue(callable(uninstall_hook))

    def test_default_get_returns_artwork_with_no_context(self):
        """default_get returns product_type='artwork' when no default_product_type
        is in context — preserves the SOR Artworks UI default."""
        defaults = self.env['product.template'].default_get(['product_type'])
        self.assertEqual(
            defaults.get('product_type'),
            'artwork',
            "default_get must return 'artwork' when no context hint is present",
        )

    def test_default_get_returns_artwork_with_explicit_artwork_context(self):
        """default_get returns product_type='artwork' when context explicitly
        passes default_product_type='artwork' (the Artworks window action)."""
        env = self.env(context={'default_product_type': 'artwork'})
        defaults = env['product.template'].default_get(['product_type'])
        self.assertEqual(defaults.get('product_type'), 'artwork')

    def test_default_get_does_not_override_other_context_type(self):
        """default_get does not stamp 'artwork' when context provides a
        different default_product_type — fixes the C1 demo data contamination."""
        env = self.env(context={'default_product_type': 'other_type'})
        defaults = env['product.template'].default_get(['product_type'])
        self.assertNotEqual(
            defaults.get('product_type'),
            'artwork',
            "default_get must not override a non-artwork default_product_type context",
        )
