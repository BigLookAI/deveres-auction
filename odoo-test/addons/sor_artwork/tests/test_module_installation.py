# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestModuleInstallation(TransactionCase):
    """Test module installation in clean environment.

    Verifies that:
    - Module installs without errors
    - All models are created and accessible
    - All views are accessible
    - Security access rules are loaded
    - Dependencies are resolved
    - Data files load correctly
    """

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.Module = cls.env['ir.module.module']
        cls.Model = cls.env['ir.model']
        cls.View = cls.env['ir.ui.view']
        cls.Access = cls.env['ir.model.access']
        cls.ProductTemplate = cls.env['product.template']
        cls.ArtworkImage = cls.env['sor.art.work.image']

    def test_module_installs_cleanly(self):
        """Test that sor_artwork module installs without errors."""
        module = self.Module.search([('name', '=', 'sor_artwork')], limit=1)
        self.assertTrue(module.exists(), "Module sor_artwork should exist")
        self.assertEqual(
            module.state,
            'installed',
            "Module sor_artwork should be in 'installed' state",
        )

    def test_all_models_created(self):
        """Test that all models are created and accessible."""
        # Test product.template model (inherited)
        self.assertTrue(
            self.ProductTemplate._name == 'product.template',
            "product.template model should be accessible",
        )

        # Test sor.art.work.image model
        self.assertTrue(
            self.ArtworkImage._name == 'sor.art.work.image',
            "sor.art.work.image model should be accessible",
        )

        # Verify model is registered in ir.model
        art_image_model = self.Model.search([
            ('model', '=', 'sor.art.work.image'),
        ], limit=1)
        self.assertTrue(
            art_image_model.exists(),
            "sor.art.work.image should be registered in ir.model",
        )

    def test_security_access_rules_loaded(self):
        """Test that security access rules are loaded correctly."""
        # Check access rules for product.template
        product_access = self.Access.search([
            ('name', 'like', '%artwork%'),
            ('model_id.model', '=', 'product.template'),
        ])
        self.assertTrue(
            product_access.exists(),
            "Security access rules for product.template should exist",
        )

        # Check access rules for sor.art.work.image
        image_access = self.Access.search([
            ('name', 'like', '%sor.art.work.image%'),
            ('model_id.model', '=', 'sor.art.work.image'),
        ])
        self.assertTrue(
            image_access.exists(),
            "Security access rules for sor.art.work.image should exist",
        )

        # Verify at least user and system access rules exist
        user_access = self.Access.search([
            ('name', 'like', '%user%'),
            ('model_id.model', 'in', ['product.template', 'sor.art.work.image']),
        ])
        self.assertTrue(
            user_access.exists(),
            "User access rules should exist",
        )

    def test_views_accessible(self):
        """Test that all views are accessible and can be loaded."""
        # Check form view
        form_view = self.View.search([
            ('name', '=', 'product.template.form.artwork'),
            ('model', '=', 'product.template'),
        ], limit=1)
        self.assertTrue(
            form_view.exists(),
            "Form view 'product.template.form.artwork' should exist",
        )

        # Check tree/list view
        tree_view = self.View.search([
            ('name', '=', 'product.template.tree.artwork'),
            ('model', '=', 'product.template'),
        ], limit=1)
        self.assertTrue(
            tree_view.exists(),
            "Tree view 'product.template.tree.artwork' should exist",
        )

        # Check search view
        search_view = self.View.search([
            ('name', '=', 'product.template.search.artwork'),
            ('model', '=', 'product.template'),
        ], limit=1)
        self.assertTrue(
            search_view.exists(),
            "Search view 'product.template.search.artwork' should exist",
        )

        # Verify views can be loaded (no errors)
        try:
            form_view_arch = form_view.get_combined_arch()
            tree_view_arch = tree_view.get_combined_arch()
            search_view_arch = search_view.get_combined_arch()
            self.assertTrue(
                form_view_arch is not None,
                "Form view should be loadable",
            )
            self.assertTrue(
                tree_view_arch is not None,
                "Tree view should be loadable",
            )
            self.assertTrue(
                search_view_arch is not None,
                "Search view should be loadable",
            )
        except Exception as e:  # noqa: BLE001
            self.fail(f"Views should load without errors: {e}")

    def test_dependencies_resolved(self):
        """Test that all dependencies are installed."""
        # Check product module (required dependency)
        product_module = self.Module.search([
            ('name', '=', 'product'),
        ], limit=1)
        self.assertTrue(
            product_module.exists(),
            "Dependency 'product' module should exist",
        )
        self.assertEqual(
            product_module.state,
            'installed',
            "Dependency 'product' module should be installed",
        )

        # Note: sor_contact_roles is NOT a direct dependency of sor_artwork.
        # The coupling is handled by the sor_artwork_contact_roles bridge module,
        # which auto-installs when both sor_artwork and sor_contact_roles are present.

    def test_data_files_loaded(self):
        """Test that data files are loaded correctly."""
        # Check that security file data is loaded (access rules)
        # This is already tested in test_security_access_rules_loaded
        # But we can verify the action exists
        action = self.env['ir.actions.act_window'].search([
            ('name', '=', 'Artworks'),
        ], limit=1)
        self.assertTrue(
            action.exists(),
            "Action 'Artworks' should exist (from data files)",
        )

        # Check menu items exist
        menu = self.env['ir.ui.menu'].search([
            ('name', '=', 'Artworks'),
        ], limit=1)
        self.assertTrue(
            menu.exists(),
            "Menu 'Artworks' should exist (from data files)",
        )

    def test_module_uninstall(self):
        """Test that module can be uninstalled cleanly (optional test).

        Note: This test may be skipped in production as uninstalling
        may cause data loss. Use with caution.
        """
        # This test is optional and may be skipped
        # Uncomment if you want to test uninstallation
        # module = self.Module.search([('name', '=', 'sor_artwork')], limit=1)
        # if module.exists() and module.state == 'installed':
        #     try:
        #         module.button_immediate_uninstall()
        #         self.assertEqual(module.state, 'uninstalled')
        #         # Reinstall for other tests
        #         module.button_immediate_install()
        #     except Exception as e:
        #         self.fail(f"Module should uninstall cleanly: {e}")
        pass

    def test_model_fields_exist(self):
        """Test that all expected fields exist on models."""
        # Test product.template fields
        product_fields = self.ProductTemplate._fields
        expected_fields = [
            'product_type',
            'product_subtype',
            'dimensions_width',
            'dimensions_height',
            'dimensions_depth',
            'medium',
            'creation_year',
            'creator_id',
            'condition',
            'provenance',
            'certificate_of_authenticity',
            'certificate_attachment_ids',
            'work_image_ids',
            'edition_info',
        ]

        for field_name in expected_fields:
            self.assertIn(
                field_name,
                product_fields,
                f"Field '{field_name}' should exist on product.template",
            )

        # Test sor.art.work.image fields
        image_fields = self.ArtworkImage._fields
        expected_image_fields = ['work_id', 'name', 'image', 'sequence']

        for field_name in expected_image_fields:
            self.assertIn(
                field_name,
                image_fields,
                f"Field '{field_name}' should exist on sor.art.work.image",
            )
