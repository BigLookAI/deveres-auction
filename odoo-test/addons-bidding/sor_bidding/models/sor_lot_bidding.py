from odoo import _, api, fields, models
from odoo.exceptions import UserError


class SorLotBidding(models.Model):
    _inherit = 'sor.lot'

    bid_ids = fields.One2many(
        comodel_name='sor.bid',
        inverse_name='lot_id',
        string='Bids',
    )
    bid_count = fields.Integer(
        compute='_compute_bid_count',
        store=False,
    )

    @api.depends('bid_ids')
    def _compute_bid_count(self):
        for lot in self:
            lot.bid_count = len(lot.bid_ids)

    def action_view_bids(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bids',
            'res_model': 'sor.bid',
            'view_mode': 'list,form',
            'domain': [('lot_id', '=', self.id)],
            'context': {'default_lot_id': self.id},
        }

    def action_mark_sold(self):
        for lot in self:
            if not lot.bid_ids:
                raise UserError(
                    _('Lot "%s" cannot be marked Sold because it has no bids. '
                      'At least one bid must be recorded before marking a lot as Sold.')
                    % lot.lot_reference,
                )
            winning_bid = lot.bid_ids.sorted('amount', reverse=True)[0]
            lot.hammer_price = winning_bid.amount
            winning_bid.is_winning_bid = True
        return super().action_mark_sold()
