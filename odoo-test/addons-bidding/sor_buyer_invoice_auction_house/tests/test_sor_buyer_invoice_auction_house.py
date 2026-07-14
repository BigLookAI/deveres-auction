from odoo.exceptions import UserError
from odoo.tests import TransactionCase

from odoo.addons.sor_buyer_invoice_auction_house import hooks


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

    # ------------------------------------------------------------------
    # Buyer Invoice bulk send (Story 03 — Auction Documents and Invoice
    # Email Behaviour). No prior test existed for action_bulk_send_sor_invoice.
    # ------------------------------------------------------------------

    def _make_invoice(self, partner):
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        return self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': partner.id,
            'journal_id': journal.id,
        })

    def test_buyer_invoice_bulk_template_use_default_to_false(self):
        """Regression (BUG-01): use_default_to must be False or partner_to is silently ignored
        in mass-mail mode (see odoo_conventions/orm_and_field_patterns.md)."""
        template = self.env.ref('sor_buyer_invoice_auction_house.mail_template_sor_buyer_invoice_bulk')
        self.assertFalse(template.use_default_to)

    def test_action_bulk_send_sor_invoice_populates_recipient(self):
        """Regression (BUG-01): the mail.mail created by bulk send has a real recipient."""
        partner = self.env['res.partner'].create({
            'name': 'Test Buyer With Email', 'email': 'buyer.with.email@example.com',
        })
        move = self._make_invoice(partner)
        before_ids = self.env['mail.mail'].search([]).ids
        move.action_bulk_send_sor_invoice()
        new_mail = self.env['mail.mail'].search([('id', 'not in', before_ids)], order='id desc', limit=1)
        self.assertTrue(new_mail, 'A mail.mail record should have been created')
        self.assertIn(partner, new_mail.recipient_ids)

    def test_action_bulk_send_sor_invoice_skips_no_email_with_chatter(self):
        partner = self.env['res.partner'].create({'name': 'Test Buyer No Email'})
        move = self._make_invoice(partner)
        move.action_bulk_send_sor_invoice()
        self.assertTrue(
            move.message_ids.filtered(lambda m: 'no email on file' in (m.body or '')),
        )

    def test_action_bulk_send_sor_invoice_notification_closes_view(self):
        """Regression (BUG-03): notification must chain to act_window_close so the list refreshes."""
        partner = self.env['res.partner'].create({
            'name': 'Test Buyer With Email 2', 'email': 'buyer.with.email.2@example.com',
        })
        move = self._make_invoice(partner)
        result = move.action_bulk_send_sor_invoice()
        self.assertEqual(result['params'].get('next'), {'type': 'ir.actions.act_window_close'})

    def test_action_bulk_send_sor_invoice_server_action_returns_notification(self):
        """Regression (BUG-02): the ir.actions.server record must assign to `action`."""
        partner = self.env['res.partner'].create({
            'name': 'Test Buyer With Email 3', 'email': 'buyer.with.email.3@example.com',
        })
        move = self._make_invoice(partner)
        server_action = self.env.ref(
            'sor_buyer_invoice_auction_house.action_server_bulk_send_buyer_invoice',
        )
        result = server_action.with_context(
            active_ids=move.ids, active_model='account.move',
        ).run()
        self.assertIsNotNone(result)
        self.assertEqual(result.get('tag'), 'display_notification')

    def test_action_bulk_send_sor_invoice_reports_not_eligible_count(self):
        """Regression (BUG-04): a selected record with the wrong move_type must be
        reported as not eligible rather than silently vanishing from the summary."""
        partner = self.env['res.partner'].create({
            'name': 'Test Buyer With Email 4', 'email': 'buyer.with.email.4@example.com',
        })
        invoice = self._make_invoice(partner)
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'), ('company_id', '=', self.company.id),
        ], limit=1)
        credit_note = self.env['account.move'].create({
            'move_type': 'out_refund',
            'partner_id': partner.id,
            'journal_id': journal.id,
        })
        result = (invoice | credit_note).action_bulk_send_sor_invoice()
        self.assertIn('1 not eligible (wrong state)', result['params']['message'])
        self.assertTrue(result['params']['sticky'])

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

    # ------------------------------------------------------------------
    # invoice_pending_count (Sprint 19 — Document Generation UX)
    # ------------------------------------------------------------------

    def test_invoice_pending_count_zero_with_no_bids(self):
        """invoice_pending_count is 0 when the event has no winning bids."""
        event = self.env['sor.event'].create({
            'name': 'Pending Count No Bids Test',
            'event_type': 'auction',
            'date_start': '2026-02-01 10:00:00',
            'company_id': self.company.id,
        })
        self.assertEqual(event.invoice_pending_count, 0)

    def test_invoice_pending_count_reflects_buyers_with_winning_bids(self):
        """invoice_pending_count equals the number of distinct buyers with winning bids (sor_bidding path)."""
        if 'sor.bid' not in self.env.registry:
            self.skipTest('sor_bidding not installed — bidding path not active')
        product = self.env['product.template'].search(
            [('is_storable', '=', True)], limit=1,
        )
        if not product:
            self.skipTest('No storable product found')
        event = self.env['sor.event'].create({
            'name': 'Pending Count Winning Bid Test',
            'event_type': 'auction',
            'date_start': '2026-02-02 10:00:00',
            'company_id': self.company.id,
        })
        lot = self.env['sor.lot'].create({
            'product_id': product.id,
            'company_id': self.company.id,
            'auction_id': event.id,
            'state': 'sold',
        })
        buyer = self.env['res.partner'].create({'name': 'Pending Count Buyer'})
        self.env['sor.bid'].create({
            'lot_id': lot.id,
            'bidder_id': buyer.id,
            'company_id': self.company.id,
            'is_winning_bid': True,
            'amount': 1000.0,
            'bid_type': 'floor',
        })
        self.assertEqual(event.invoice_pending_count, 1)

    def test_invoice_pending_count_zero_after_invoice_generated(self):
        """invoice_pending_count drops to 0 once an invoice covering the lot exists (sor_bidding path).

        Granularity is (event, buyer, lot) — BUG-05 — so the invoice must reference the
        specific lot via sor_lot_ids, mirroring what action_generate_buyer_invoices() sets.
        """
        if 'sor.bid' not in self.env.registry:
            self.skipTest('sor_bidding not installed — bidding path not active')
        product = self.env['product.template'].search(
            [('is_storable', '=', True)], limit=1,
        )
        if not product:
            self.skipTest('No storable product found')
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        event = self.env['sor.event'].create({
            'name': 'Pending Count After Invoice Test',
            'event_type': 'auction',
            'date_start': '2026-02-03 10:00:00',
            'company_id': self.company.id,
        })
        lot = self.env['sor.lot'].create({
            'product_id': product.id,
            'company_id': self.company.id,
            'auction_id': event.id,
            'state': 'sold',
        })
        buyer = self.env['res.partner'].create({'name': 'Post-Invoice Buyer'})
        self.env['sor.bid'].create({
            'lot_id': lot.id,
            'bidder_id': buyer.id,
            'company_id': self.company.id,
            'is_winning_bid': True,
            'amount': 2000.0,
            'bid_type': 'floor',
        })
        self.assertEqual(event.invoice_pending_count, 1)
        # Generate the invoice for this buyer, covering this lot
        self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': buyer.id,
            'journal_id': journal.id,
            'sor_event_id': event.id,
            'sor_lot_ids': [(6, 0, [lot.id])],
        })
        # Invalidate cached count so the next read triggers a fresh recompute
        event.invalidate_recordset(['invoice_pending_count'])
        self.assertEqual(event.invoice_pending_count, 0)

    def test_invoice_pending_count_one_when_buyer_has_new_unbilled_lot(self):
        """Regression (BUG-05): a buyer's newly-sold lot stays pending even though the
        buyer already has an invoice for this event covering a different lot."""
        if 'sor.bid' not in self.env.registry:
            self.skipTest('sor_bidding not installed — bidding path not active')
        product = self.env['product.template'].search(
            [('is_storable', '=', True)], limit=1,
        )
        if not product:
            self.skipTest('No storable product found')
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        event = self.env['sor.event'].create({
            'name': 'Incremental Pending Count Test',
            'event_type': 'auction',
            'date_start': '2026-02-04 10:00:00',
            'company_id': self.company.id,
        })
        buyer = self.env['res.partner'].create({'name': 'Repeat Buyer'})
        invoiced_lot = self.env['sor.lot'].create({
            'product_id': product.id,
            'company_id': self.company.id,
            'auction_id': event.id,
            'state': 'sold',
        })
        new_lot = self.env['sor.lot'].create({
            'product_id': product.id,
            'company_id': self.company.id,
            'auction_id': event.id,
            'state': 'sold',
        })
        for lot in (invoiced_lot, new_lot):
            self.env['sor.bid'].create({
                'lot_id': lot.id,
                'bidder_id': buyer.id,
                'company_id': self.company.id,
                'is_winning_bid': True,
                'amount': 1500.0,
                'bid_type': 'floor',
            })
        # Buyer already has an invoice, but it only covers invoiced_lot
        self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': buyer.id,
            'journal_id': journal.id,
            'sor_event_id': event.id,
            'sor_lot_ids': [(6, 0, [invoiced_lot.id])],
        })
        event.invalidate_recordset(['invoice_pending_count'])
        self.assertEqual(event.invoice_pending_count, 1)

    # ------------------------------------------------------------------
    # Fallback path: buyer_id on sor.lot (no sor_bidding)
    # ------------------------------------------------------------------

    def test_invoice_pending_count_fallback_buyer_id(self):
        """invoice_pending_count counts distinct buyers via lot.buyer_id when sor_bidding absent."""
        if 'sor.bid' in self.env.registry:
            self.skipTest('sor_bidding installed — fallback path not active')
        buyer = self.env['res.partner'].create({'name': 'Fallback Count Buyer'})
        event = self.env['sor.event'].create({
            'name': 'Fallback Count Test Auction',
            'event_type': 'auction',
            'date_start': '2026-03-01 10:00:00',
            'company_id': self.company.id,
        })
        self.env['sor.lot'].create([
            {
                'company_id': self.company.id,
                'auction_id': event.id,
                'state': 'sold',
                'buyer_id': buyer.id,
                'hammer_price': 500.0,
            },
            {
                'company_id': self.company.id,
                'auction_id': event.id,
                'state': 'sold',
                'buyer_id': buyer.id,
                'hammer_price': 750.0,
            },
        ])
        # Two sold lots, same buyer → 1 distinct pending buyer
        self.assertEqual(event.invoice_pending_count, 1)

    def test_invoice_pending_count_fallback_drops_after_invoice(self):
        """invoice_pending_count drops to 0 once an invoice covering the lot exists (fallback path).

        Granularity is (event, buyer, lot) — BUG-05 — so the invoice must reference the
        specific lot via sor_lot_ids, mirroring what action_generate_buyer_invoices() sets.
        """
        if 'sor.bid' in self.env.registry:
            self.skipTest('sor_bidding installed — fallback path not active')
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        buyer = self.env['res.partner'].create({'name': 'Fallback Invoice Buyer'})
        event = self.env['sor.event'].create({
            'name': 'Fallback Invoice Drop Test',
            'event_type': 'auction',
            'date_start': '2026-03-02 10:00:00',
            'company_id': self.company.id,
        })
        lot = self.env['sor.lot'].create({
            'company_id': self.company.id,
            'auction_id': event.id,
            'state': 'sold',
            'buyer_id': buyer.id,
            'hammer_price': 1000.0,
        })
        self.assertEqual(event.invoice_pending_count, 1)
        self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': buyer.id,
            'journal_id': journal.id,
            'sor_event_id': event.id,
            'sor_lot_ids': [(6, 0, [lot.id])],
        })
        event.invalidate_recordset(['invoice_pending_count'])
        self.assertEqual(event.invoice_pending_count, 0)

    def test_invoice_pending_count_fallback_one_when_buyer_has_new_unbilled_lot(self):
        """Regression (BUG-05, fallback path): a buyer's newly-sold lot stays pending
        even though the buyer already has an invoice for this event covering a
        different lot."""
        if 'sor.bid' in self.env.registry:
            self.skipTest('sor_bidding installed — fallback path not active')
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company.id),
        ], limit=1)
        buyer = self.env['res.partner'].create({'name': 'Fallback Repeat Buyer'})
        event = self.env['sor.event'].create({
            'name': 'Fallback Incremental Pending Count Test',
            'event_type': 'auction',
            'date_start': '2026-03-03 10:00:00',
            'company_id': self.company.id,
        })
        invoiced_lot, _new_lot = self.env['sor.lot'].create([
            {
                'company_id': self.company.id,
                'auction_id': event.id,
                'state': 'sold',
                'buyer_id': buyer.id,
                'hammer_price': 500.0,
            },
            {
                'company_id': self.company.id,
                'auction_id': event.id,
                'state': 'sold',
                'buyer_id': buyer.id,
                'hammer_price': 750.0,
            },
        ])
        self.env['account.move'].create({
            'move_type': 'out_invoice',
            'partner_id': buyer.id,
            'journal_id': journal.id,
            'sor_event_id': event.id,
            'sor_lot_ids': [(6, 0, [invoiced_lot.id])],
        })
        event.invalidate_recordset(['invoice_pending_count'])
        self.assertEqual(event.invoice_pending_count, 1)

    # ------------------------------------------------------------------
    # _ensure_auction_payment_methods (Story 04 — Payment Method Line Provisioning)
    # ------------------------------------------------------------------

    def _bank_journal(self):
        return self.env['account.journal'].search([
            ('company_id', '=', self.company.id),
            ('type', '=', 'bank'),
        ], limit=1)

    def test_payment_method_lines_provisioned_on_bank_journal(self):
        """The four auction payment methods exist on the company's Bank journal after install."""
        journal = self._bank_journal()
        names = journal.inbound_payment_method_line_ids.mapped('name')
        for label in ('Debit Card', 'Bank Transfer', 'Cheque', 'Bank Draft'):
            self.assertIn(label, names)

    def test_payment_method_lines_use_journal_own_reconcile_false_account(self):
        """Each provisioned line's payment_account_id is the journal's own reconcile=False account."""
        journal = self._bank_journal()
        for label in ('Debit Card', 'Bank Transfer', 'Cheque', 'Bank Draft'):
            line = journal.inbound_payment_method_line_ids.filtered(lambda line, label=label: line.name == label)
            self.assertTrue(line, f'{label} line should exist')
            self.assertEqual(line.payment_account_id, journal.default_account_id)
            self.assertFalse(line.payment_account_id.reconcile)

    def test_ensure_auction_payment_methods_idempotent(self):
        """Running the provisioning function twice does not create duplicate lines."""
        journal = self._bank_journal()
        count_before = len(journal.inbound_payment_method_line_ids)
        hooks._ensure_auction_payment_methods(self.env, self.company)
        journal.invalidate_recordset(['inbound_payment_method_line_ids'])
        self.assertEqual(len(journal.inbound_payment_method_line_ids), count_before)

    def test_ensure_auction_payment_methods_leaves_pre_existing_lines_untouched(self):
        """A pre-existing line under one of the four names is not corrected (going-forward-only).

        Simulates the deVeres scenario: a line already exists under one of the four
        names, but its account was set incorrectly (e.g. manually, before this story).
        The name-match idempotency check must skip it regardless of its account.
        """
        journal = self._bank_journal()
        outstanding_receipts = self.env['account.account'].search([
            ('company_ids', 'in', self.company.id),
            ('account_type', '=', 'asset_receivable'),
            ('reconcile', '=', True),
        ], limit=1)
        if not outstanding_receipts:
            self.skipTest('No reconcile=True receivable account found to simulate a misconfigured line')
        debit_card_line = journal.inbound_payment_method_line_ids.filtered(
            lambda line: line.name == 'Debit Card',
        )
        self.assertTrue(debit_card_line, 'Debit Card line should already be provisioned')
        debit_card_line.payment_account_id = outstanding_receipts

        hooks._ensure_auction_payment_methods(self.env, self.company)

        journal.invalidate_recordset(['inbound_payment_method_line_ids'])
        debit_card_line.invalidate_recordset(['payment_account_id'])
        self.assertEqual(
            debit_card_line.payment_account_id, outstanding_receipts,
            'Pre-existing line must be left untouched, even though its account is wrong',
        )
        self.assertEqual(
            len(journal.inbound_payment_method_line_ids.filtered(lambda line: line.name == 'Debit Card')),
            1,
            'No duplicate Debit Card line should be created',
        )

    def test_ensure_auction_payment_methods_skips_company_with_no_bank_journal(self):
        """No error is raised for a company with no type='bank' journal yet (chart not applied)."""
        new_company = self.env['res.company'].create({'name': 'Test No-Bank-Journal Company'})
        # Should not raise, even though no bank journal exists for this fresh company yet
        hooks._ensure_auction_payment_methods(self.env, new_company)

    # ------------------------------------------------------------------
    # Story 03 — Bespoke Buyer Invoice PDF: lot breakdown table & VAT notice
    # ------------------------------------------------------------------

    def _generate_invoice_for_sold_lot(self, vat_margin_scheme=False, hammer_price=1000.0, premium_pct=20.0):
        product = self.env['product.template'].search([('sale_ok', '=', True)], limit=1)
        buyer = self.env['res.partner'].create({'name': 'Bridge Test Buyer'})
        event = self.env['sor.event'].create({
            'name': 'Bridge Test Auction',
            'event_type': 'auction',
            'status': 'active',
            'date_start': '2026-04-01 10:00:00',
            'company_id': self.company.id,
        })
        lot = self.env['sor.lot'].create({
            'auction_id': event.id,
            'product_id': product.id,
            'lot_number': 'BRIDGE-01',
            'buyer_id': buyer.id,
            'hammer_price': hammer_price,
            'buyers_premium_pct': premium_pct,
            'vat_margin_scheme': vat_margin_scheme,
            'state': 'sold',
        })
        if 'sor.bid' in self.env.registry:
            self.env['sor.bid'].create({
                'lot_id': lot.id,
                'bidder_id': buyer.id,
                'company_id': self.company.id,
                'is_winning_bid': True,
                'amount': hammer_price,
                'bid_type': 'floor',
            })
        event.action_generate_buyer_invoices()
        move = self.env['account.move'].search([('sor_event_id', '=', event.id)], limit=1)
        move.action_post()
        return move

    def _render(self, move):
        report = self.env.ref('account.account_invoices')
        html, _content_type = report._render_qweb_html(report.id, move.ids)
        return html.decode() if isinstance(html, bytes) else html

    def test_lot_breakdown_table_rendered(self):
        """The rebuilt bridge template renders the Lot no / Hammer / Buyer's premium table."""
        move = self._generate_invoice_for_sold_lot(hammer_price=1000.0, premium_pct=20.0)
        html = self._render(move)
        self.assertIn('Lot no', html)
        self.assertIn('BRIDGE-01', html)
        self.assertIn('Total Hammer', html)
        self.assertIn('Total Buyer', html)

    def test_vat_notice_rendered_when_margin_scheme(self):
        """The statutory VAT notice renders when a lot on the invoice is margin-scheme."""
        self.company.auction_vat_notice = '<p>Test statutory margin scheme notice.</p>'
        move = self._generate_invoice_for_sold_lot(vat_margin_scheme=True)
        html = self._render(move)
        self.assertIn('Test statutory margin scheme notice.', html)

    def test_vat_notice_absent_when_no_margin_scheme(self):
        """The statutory VAT notice does not render when no lot on the invoice is margin-scheme."""
        self.company.auction_vat_notice = '<p>Test statutory margin scheme notice.</p>'
        move = self._generate_invoice_for_sold_lot(vat_margin_scheme=False)
        html = self._render(move)
        self.assertNotIn('Test statutory margin scheme notice.', html)
