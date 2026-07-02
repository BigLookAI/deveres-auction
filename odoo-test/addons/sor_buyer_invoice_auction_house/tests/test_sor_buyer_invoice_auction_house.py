from odoo.exceptions import UserError
from odoo.tests import TransactionCase


class TestSorBuyerInvoiceAuctionHouse(TransactionCase):
    """Tests for sor_buyer_invoice_auction_house — AUC journal, invoice generation, buyer's premium."""

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company

    def test_auc_journal_provisioned(self):
        """An Auction Sales journal with code AUC exists for the main company after install."""
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        self.assertTrue(journal, 'AUC journal should be provisioned for main company')
        self.assertEqual(journal.type, 'sale')

    def test_buyer_invoice_sequence_provisioned(self):
        """A buyer invoice sequence (code sor.buyer.invoice) exists for the main company."""
        seq = self.env['ir.sequence'].search([
            ('code', '=', 'sor.buyer.invoice'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        self.assertTrue(seq, 'Buyer invoice sequence should be provisioned for main company')

    def test_auc_journal_provisioned_for_new_company(self):
        """Creating a new company provisions an AUC journal for it."""
        new_company = self.env['res.company'].create({'name': 'Test AUC Company'})
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', new_company.id),
        ], limit=1)
        self.assertTrue(journal, 'AUC journal should be auto-provisioned for new company')

    def test_sor_lot_ids_on_account_move(self):
        """account.move has sor_lot_ids Many2many field."""
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        partner = self.env['res.partner'].create({'name': 'Test Buyer'})
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': journal.id,
        })
        self.assertIsNotNone(move.sor_lot_ids)

    def test_account_move_line_sor_fields(self):
        """account.move.line has sor_lot_id, sor_line_type, and sor_buyers_premium_pct fields."""
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        partner = self.env['res.partner'].create({'name': 'Test Buyer 2'})
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': journal.id,
        })
        self.assertTrue(hasattr(move.invoice_line_ids, 'sor_lot_id'))
        self.assertTrue(hasattr(move.invoice_line_ids, 'sor_line_type'))
        self.assertTrue(hasattr(move.invoice_line_ids, 'sor_buyers_premium_pct'))

    def test_generate_invoices_duplicate_guard(self):
        """Generating invoices a second time raises UserError."""
        event = self.env['sor.event'].create({
            'name': 'Guard Test Auction',
            'event_type': 'auction',
            'date_start': '2026-01-01 10:00:00',
            'company_id': self.company.id,
        })
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        partner = self.env['res.partner'].create({'name': 'Guard Buyer'})
        self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': journal.id,
            'sor_event_id': event.id,
        })
        with self.assertRaises(UserError):
            event.action_generate_buyer_invoices()
