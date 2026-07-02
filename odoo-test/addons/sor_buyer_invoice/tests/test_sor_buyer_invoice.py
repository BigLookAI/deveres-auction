from odoo.tests.common import TransactionCase


class TestSorBuyerInvoice(TransactionCase):
    """Tests for sor_buyer_invoice — event-invoice link layer."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.event = cls.env['sor.event'].create({
            'name': 'Test Auction',
            'event_type': 'auction',
            'date_start': '2026-01-01 10:00:00',
            'company_id': cls.company.id,
        })
        cls.partner = cls.env['res.partner'].create({'name': 'Test Buyer'})
        journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner.id,
            'journal_id': journal.id,
            'sor_event_id': cls.event.id,
        })

    def test_sor_event_id_field_on_account_move(self):
        """account.move has sor_event_id field linking to sor.event."""
        self.assertEqual(self.invoice.sor_event_id, self.event)

    def test_invoice_count_on_event(self):
        """sor.event.invoice_count reflects linked invoices."""
        count = self.event.invoice_count
        self.assertGreaterEqual(count, 1)

    def test_invoice_count_excludes_other_event(self):
        """invoice_count is scoped to this event — does not count other events' invoices."""
        other_event = self.env['sor.event'].create({
            'name': 'Other Auction',
            'event_type': 'auction',
            'date_start': '2026-01-02 10:00:00',
            'company_id': self.company.id,
        })
        self.assertEqual(other_event.invoice_count, 0)

    def test_action_view_buyer_invoices_domain(self):
        """action_view_buyer_invoices returns domain filtered to this event."""
        action = self.event.action_view_buyer_invoices()
        self.assertEqual(action['res_model'], 'account.move')
        self.assertIn(('sor_event_id', '=', self.event.id), action['domain'])

    def test_psra_number_field_on_company(self):
        """res.company has auction_psra_number field."""
        self.company.auction_psra_number = 'PSRA-001234'
        self.assertEqual(self.company.auction_psra_number, 'PSRA-001234')
