
from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SorEvent(models.Model):
    _inherit = 'sor.event'

    invoice_pending_count = fields.Integer(
        compute='_compute_invoice_pending_count',
        store=False,
    )

    @api.depends()
    def _compute_invoice_pending_count(self):
        bidding_installed = 'sor.bid' in self.env.registry
        for event in self:
            already_invoiced_lot_ids = set(
                self.env['account.move'].search([
                    ('sor_event_id', '=', event.id),
                    ('move_type', '=', 'out_invoice'),
                ]).sor_lot_ids.ids,
            )
            if bidding_installed:
                winning_bids = self.env['sor.bid'].search([
                    ('lot_id.auction_id', '=', event.id),
                    ('is_winning_bid', '=', True),
                ])
                pending_buyers = {
                    bid.bidder_id.id for bid in winning_bids
                    if bid.bidder_id and bid.lot_id.id not in already_invoiced_lot_ids
                }
            else:
                sold_lots = self.env['sor.lot'].search([
                    ('auction_id', '=', event.id),
                    ('state', '=', 'sold'),
                    ('buyer_id', '!=', False),
                ])
                pending_buyers = {
                    lot.buyer_id.id for lot in sold_lots
                    if lot.id not in already_invoiced_lot_ids
                }
            event.invoice_pending_count = len(pending_buyers)

    def action_generate_buyer_invoices(self):
        self.ensure_one()
        bidding_installed = 'sor.bid' in self.env.registry

        # Find lots already invoiced for this event — skip them (incremental)
        already_invoiced_lot_ids = set(
            self.env['account.move'].search([
                ('sor_event_id', '=', self.id),
                ('move_type', '=', 'out_invoice'),
            ]).sor_lot_ids.ids,
        )

        # Build buyer_map: buyer → list of lots (bidding path) or lots (fallback path)
        buyer_map = {}
        if bidding_installed:
            winning_bids = self.env['sor.bid'].search([
                ('lot_id.auction_id', '=', self.id),
                ('is_winning_bid', '=', True),
            ])
            if not winning_bids:
                raise UserError(_('No winning bids found for this auction.'))
            for bid in winning_bids:
                if bid.bidder_id and bid.lot_id.id not in already_invoiced_lot_ids:
                    buyer_map.setdefault(bid.bidder_id, []).append(bid.lot_id)
        else:
            sold_lots = self.env['sor.lot'].search([
                ('auction_id', '=', self.id),
                ('state', '=', 'sold'),
                ('buyer_id', '!=', False),
            ])
            if not sold_lots:
                raise UserError(_('No sold lots with a buyer recorded for this auction.'))
            for lot in sold_lots:
                if lot.id not in already_invoiced_lot_ids:
                    buyer_map.setdefault(lot.buyer_id, []).append(lot)

        if not buyer_map:
            raise UserError(_(
                'All buyer invoices have already been generated for this auction.',
            ))

        # Locate Auction Sales journal for this company
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)
        if not journal:
            raise UserError(_(
                'No Auction Sales journal found for company %s.',
            ) % self.company_id.name)

        # Buyer invoice sequence for this company
        seq = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'sor.buyer.invoice'),
            ('company_id', '=', self.company_id.id),
        ], limit=1)

        for buyer, lots_list in buyer_map.items():
            lots = self.env['sor.lot'].browse([lot.id for lot in lots_list])
            lines = self._prepare_buyer_invoice_lines(lots, buyer)
            move = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': buyer.id,
                'journal_id': journal.id,
                'invoice_date': (self.date_end or self.date_start).date() if (self.date_end or self.date_start) else fields.Date.today(),
                'sor_event_id': self.id,
                'sor_lot_ids': [(6, 0, lots.ids)],
                'invoice_line_ids': lines,
            })

            # Assign invoice number: {sequential}/{sale_number}
            if seq:
                seq_val = seq.next_by_id()
                sale_number = getattr(self, 'sale_number', None)
                move.name = f'{seq_val}/{sale_number}' if sale_number else seq_val

        invoice_count = len(buyer_map)
        self.message_post(
            body=_('%d buyer invoice(s) generated.') % invoice_count,
            subtype_xmlid='mail.mt_note',
        )
        return {
            'type': 'ir.actions.act_window',
            'name': _('Buyer Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('sor_event_id', '=', self.id)],
        }

    def _prepare_buyer_invoice_lines(self, lots, buyer):
        lines = []
        for lot in lots:
            lot_desc = lot.lot_number or ''
            if lot.product_id:
                lot_desc = f'{lot.lot_number} — {lot.product_id.name}' if lot.lot_number else lot.product_id.name
            lines.append((0, 0, {
                'name': lot_desc,
                'quantity': 1.0,
                'price_unit': lot.hammer_price or 0.0,
                'sor_lot_id': lot.id,
                'sor_line_type': 'hammer',
                'tax_ids': [],
            }))
            premium_pct = lot.buyers_premium_pct or 0.0
            if premium_pct:
                hammer = lot.hammer_price or 0.0
                premium_amount = round(hammer * premium_pct / 100.0, 2)
                lot_ref = lot.lot_number or str(lot.id)
                lines.append((0, 0, {
                    'name': f"Buyer's Premium — {lot_ref} ({premium_pct:.1f}%)",
                    'quantity': 1.0,
                    'price_unit': premium_amount,
                    'sor_lot_id': lot.id,
                    'sor_line_type': 'buyers_premium',
                    'sor_buyers_premium_pct': premium_pct,
                    'tax_ids': [],
                }))
        return lines
