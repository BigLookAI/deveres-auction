from odoo.tests import TransactionCase, tagged

from odoo.addons.sor_technical_menu.utils import set_menu_active


@tagged('post_install', '-at_install')
class TestSorTechnicalMenu(TransactionCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.menu = cls.env.ref('sor_technical_menu.menu_sor_technical_root')

    def test_menu_record_exists(self):
        self.assertTrue(
            self.menu,
            "menu_sor_technical_root should exist after module install",
        )

    def test_menu_name(self):
        self.assertEqual(
            self.menu.name,
            "SOR",
            "SOR Technical root menu should be named 'SOR'",
        )

    def test_menu_parent_is_base_menu_custom(self):
        expected_parent = self.env.ref('base.menu_custom')
        self.assertEqual(
            self.menu.parent_id,
            expected_parent,
            "SOR menu root parent should be base.menu_custom (Settings → Technical)",
        )

    def test_menu_group_restricted_to_developer_mode(self):
        group_no_one = self.env.ref('base.group_no_one')
        self.assertIn(
            group_no_one,
            self.menu.group_ids,
            "SOR menu root should be restricted to base.group_no_one (developer mode only)",
        )

    def test_composability_at_least_one_submenu_present(self):
        known_child_xmlids = [
            'sor_asset_paradigm.menu_sor_paradigm_rules',
            'sor_business_model.menu_sor_business_model_rules',
            'sor_events.menu_sor_events_technical',
            'sor_legal_agreement.menu_sor_agreements_technical',
        ]
        installed_submenus = []
        for xmlid in known_child_xmlids:
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                installed_submenus.append(xmlid)

        self.assertTrue(
            len(installed_submenus) > 0,
            "At least one SOR module should have registered a submenu under "
            "menu_sor_technical_root. Found none of: %s" % known_child_xmlids,
        )

    def test_set_menu_active_utility_importable(self):
        """set_menu_active is importable from sor_technical_menu.utils."""
        self.assertTrue(callable(set_menu_active))

    def test_set_menu_active_suppresses_and_restores(self):
        """set_menu_active(env, xmlid, False) deactivates a menu;
        set_menu_active(env, xmlid, True) restores it."""
        xmlid = 'sor_technical_menu.menu_sor_technical_root'
        set_menu_active(self.env, xmlid, False)
        menu = self.env.ref(xmlid)
        self.assertFalse(menu.active, "set_menu_active(False) must deactivate the menu")
        set_menu_active(self.env, xmlid, True)
        menu.invalidate_recordset(['active'])
        self.assertTrue(menu.active, "set_menu_active(True) must reactivate the menu")

    def test_set_menu_active_missing_xmlid_does_not_raise(self):
        """set_menu_active with a non-existent xmlid is a no-op — does not raise."""
        set_menu_active(self.env, 'nonexistent.xmlid_that_does_not_exist', False)

    def test_composability_submenu_parent_is_sor_root(self):
        known_child_xmlids = [
            'sor_asset_paradigm.menu_sor_paradigm_rules',
            'sor_business_model.menu_sor_business_model_rules',
            'sor_events.menu_sor_events_technical',
            'sor_legal_agreement.menu_sor_agreements_technical',
        ]
        for xmlid in known_child_xmlids:
            record = self.env.ref(xmlid, raise_if_not_found=False)
            if record:
                self.assertEqual(
                    record.parent_id,
                    self.menu,
                    "%s should have menu_sor_technical_root as its parent" % xmlid,
                )
