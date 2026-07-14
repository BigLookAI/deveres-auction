from odoo.tests import TransactionCase


class TestSorAccounting(TransactionCase):
    """Tests for sor_accounting — Auction Sales journal provisioning and GL surface suppression."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def test_gl_menus_restricted_to_developer_mode(self):
        """GL/reporting menus are restricted to group_no_one after install."""
        menu_xmlids = [
            'account.menu_board_journal_1',
            'account.menu_finance_payables',
            'account.menu_finance_entries',
            'account.account_audit_menu',
            'account.menu_finance_reports',
            'account.menu_finance_configuration',
        ]
        developer_group = self.env.ref('base.group_no_one')
        for xmlid in menu_xmlids:
            menu = self.env.ref(xmlid, raise_if_not_found=False)
            if menu:
                self.assertIn(
                    developer_group,
                    menu.group_ids,
                    f'{xmlid} should be restricted to developer mode',
                )

    def test_receipt_selector_widget_not_present(self):
        """The ReceiptSelector widget fix view exists and targets move_type field."""
        view = self.env.ref(
            'sor_accounting.account_move_form_receipt_selector_fix',
            raise_if_not_found=False,
        )
        self.assertIsNotNone(view, 'ReceiptSelector fix view should exist')
        self.assertIn('radio', view.arch, 'Fix view should replace widget with radio')
