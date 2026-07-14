from odoo import Command
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
        cls.journal = cls.env['account.journal'].search([
            ('type', '=', 'sale'),
            ('company_id', '=', cls.company.id),
        ], limit=1)
        cls.invoice = cls.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': cls.partner.id,
            'journal_id': cls.journal.id,
            'sor_event_id': cls.event.id,
        })
        # account.move.line.product_id is a product.product (variant), not product.template
        cls.product = cls.env['product.product'].search(
            [('sale_ok', '=', True)], limit=1,
        )

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

    # ------------------------------------------------------------------
    # Story 01 — Restrict Payments List Create
    # ------------------------------------------------------------------

    def _create_posted_invoice_with_line(self, partner=None, price=500.0):
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': (partner or self.partner).id,
            'journal_id': self.journal.id,
            'sor_event_id': self.event.id,
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id,
                'quantity': 1,
                'price_unit': price,
            })],
        })
        move.action_post()
        return move

    def _register_payment(self, move, amount):
        wizard = self.env['account.payment.register'].with_context(
            active_model='account.move', active_ids=move.ids,
        ).create({'amount': amount})
        wizard._create_payments()

    def test_open_payments_uses_no_create_view_with_multiple_payments(self):
        """open_payments() substitutes the no-create list view when 2+ payments exist."""
        move = self._create_posted_invoice_with_line(price=1000.0)
        self._register_payment(move, 400.0)
        self._register_payment(move, 600.0)
        self.assertEqual(len(move.reconciled_payment_ids), 2)
        action = move.open_payments()
        no_create_view = self.env.ref('sor_buyer_invoice.view_account_payment_list_no_create')
        list_view_ids = [view_id for view_id, view_type in action['views'] if view_type == 'list']
        self.assertEqual(list_view_ids, [no_create_view.id])

    def test_open_payments_form_only_for_single_payment(self):
        """open_payments() with exactly 1 payment returns no list entry — no-create view is irrelevant here."""
        move = self._create_posted_invoice_with_line(price=500.0)
        self._register_payment(move, 500.0)
        self.assertEqual(len(move.reconciled_payment_ids), 1)
        action = move.open_payments()
        view_types = [view_type for _, view_type in action['views']]
        self.assertNotIn('list', view_types)

    def test_general_payments_action_view_unaffected(self):
        """The general Payments action's own list view carries no create='0' override."""
        view = self.env.ref('account.view_account_payment_tree')
        self.assertNotIn('create="0"', view.arch)

    def test_existing_payment_remains_readable_after_restriction(self):
        """Existing payment records remain fully readable — restriction only affects list 'New' button."""
        move = self._create_posted_invoice_with_line(price=300.0)
        self._register_payment(move, 300.0)
        payment = move.reconciled_payment_ids
        self.assertTrue(payment.exists())
        self.assertEqual(payment.amount, 300.0)

    # ------------------------------------------------------------------
    # Story 03 — Bespoke Buyer Invoice PDF
    # ------------------------------------------------------------------

    def test_get_name_invoice_report_returns_sor_template_for_event_linked(self):
        """_get_name_invoice_report() dispatches to the SOR template when sor_event_id is set."""
        self.assertEqual(
            self.invoice._get_name_invoice_report(),
            'sor_buyer_invoice.report_invoice_document_sor_buyer_invoice',
        )

    def test_get_name_invoice_report_native_for_non_event_invoice(self):
        """_get_name_invoice_report() falls through to native for invoices with no sor_event_id."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
        })
        self.assertEqual(move._get_name_invoice_report(), 'account.report_invoice_document')

    def _render(self, move):
        report = self.env.ref('account.account_invoices')
        html, _content_type = report._render_qweb_html(report.id, move.ids)
        return html.decode() if isinstance(html, bytes) else html

    def test_report_title_posted_invoice(self):
        """Rendered PDF shows the 'Invoice' title for a posted, event-linked invoice."""
        move = self._create_posted_invoice_with_line()
        html = self._render(move)
        self.assertIn('Invoice', html)
        self.assertNotIn('Draft Invoice', html)
        self.assertNotIn('Cancelled Invoice', html)

    def test_report_title_draft_invoice(self):
        """Rendered PDF shows 'Draft Invoice' for a draft, event-linked invoice."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'sor_event_id': self.event.id,
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id, 'quantity': 1, 'price_unit': 150.0,
            })],
        })
        html = self._render(move)
        self.assertIn('Draft Invoice', html)

    def test_report_title_cancelled_invoice(self):
        """Rendered PDF shows 'Cancelled Invoice' for a cancelled, event-linked invoice."""
        move = self._create_posted_invoice_with_line(price=100.0)
        move.button_cancel()
        html = self._render(move)
        self.assertIn('Cancelled Invoice', html)

    def test_report_title_credit_note(self):
        """Rendered PDF shows 'Credit Note' (not an invoice title) for an event-linked credit note."""
        move = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'sor_event_id': self.event.id,
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id, 'quantity': 1, 'price_unit': 80.0,
            })],
        })
        move.action_post()
        html = self._render(move)
        self.assertIn('Credit Note', html)

    def test_report_shows_payment_status_for_paid_invoice(self):
        """BUG-01 regression: a fully-paid invoice's PDF shows 'Paid on' and 'Amount Due'."""
        move = self._create_posted_invoice_with_line(price=200.0)
        self._register_payment(move, 200.0)
        html = self._render(move)
        self.assertIn('Paid on', html)
        self.assertIn('Amount Due', html)

    def test_report_no_payment_status_block_for_unpaid_draft(self):
        """A draft (unpaid, unposted) invoice's PDF shows no payment-status block."""
        move = self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': self.partner.id,
            'journal_id': self.journal.id,
            'sor_event_id': self.event.id,
            'invoice_line_ids': [Command.create({
                'product_id': self.product.id, 'quantity': 1, 'price_unit': 150.0,
            })],
        })
        html = self._render(move)
        self.assertNotIn('Paid on', html)
