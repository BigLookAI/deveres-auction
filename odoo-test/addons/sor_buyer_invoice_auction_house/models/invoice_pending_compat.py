# ── LOCAL RECONSTRUCTION (Cimelium, 2-Jul-2026) ───────────────────────────────
# The April-test database's event form view references invoice_pending_count
# (owned by sor_buyer_invoice_auction_house in ir_model_data) which the
# available source does not define: sold lots in this auction with no buyer
# invoice yet.
#
# The DB's module version also dropped the sor_bidding dependency (sor_bidding
# is uninstalled in the April-test DB): invoices are generated from the lots'
# buyer_id/auction_result directly, so action_generate_buyer_invoices is
# overridden here to work without sor.bid.
from odoo import _, fields, models
from odoo.exceptions import UserError


class SorEventInvoicePendingCompat(models.Model):
    _inherit = 'sor.event'

    invoice_pending_count = fields.Integer(compute='_compute_invoice_pending_count')

    def _compute_invoice_pending_count(self):
        Lot = self.env['sor.lot']
        has_invoice_link = 'buyer_invoice_id' in Lot._fields
        for event in self:
            lots = Lot.search([('auction_id', '=', event.id),
                               ('auction_result', '=', 'sold')]) if event.id else Lot
            event.invoice_pending_count = (
                sum(1 for l in lots if not l.buyer_invoice_id) if has_invoice_link
                else len(lots))

    def action_generate_buyer_invoices(self):
        """Lot-based reimplementation (DB schema has no sor_bidding): group the
        sold lots by buyer_id and reuse the module's line preparation."""
        self.ensure_one()
        existing = self.env['account.move'].search(
            [('sor_event_id', '=', self.id)], limit=1)
        if existing:
            raise UserError(_(
                'Buyer invoices have already been generated for this auction. '
                'Delete the existing invoices first to regenerate.'))
        sold_lots = self.env['sor.lot'].search([
            ('auction_id', '=', self.id),
            ('auction_result', '=', 'sold'),
            ('buyer_id', '!=', False),
        ])
        if not sold_lots:
            raise UserError(_('No sold lots with a buyer found for this auction.'))
        journal = self.env['account.journal'].search([
            ('code', '=', 'AUC'), ('company_id', '=', self.company_id.id)], limit=1)
        if not journal:
            raise UserError(_('No Auction Sales journal found for company %s.')
                            % self.company_id.name)
        seq = self.env['ir.sequence'].sudo().search([
            ('code', '=', 'sor.buyer.invoice'),
            ('company_id', '=', self.company_id.id)], limit=1)
        for buyer in sold_lots.mapped('buyer_id'):
            lots = sold_lots.filtered(lambda l: l.buyer_id == buyer)
            move = self.env['account.move'].create({
                'move_type': 'out_invoice',
                'partner_id': buyer.id,
                'journal_id': journal.id,
                'invoice_date': (self.date_end or self.date_start).date()
                                if (self.date_end or self.date_start) else fields.Date.today(),
                'sor_event_id': self.id,
                'sor_lot_ids': [(6, 0, lots.ids)],
                'invoice_line_ids': self._prepare_buyer_invoice_lines(lots, buyer),
            })
            if seq:
                seq_val = seq.next_by_id()
                sale_number = getattr(self, 'sale_number', None)
                move.name = f'{seq_val}/{sale_number}' if sale_number else seq_val
        return {
            'type': 'ir.actions.act_window',
            'name': _('Buyer Invoices'),
            'res_model': 'account.move',
            'view_mode': 'list,form',
            'domain': [('sor_event_id', '=', self.id)],
        }
