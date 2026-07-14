from odoo import api, fields, models


class ResPartnerBidding(models.Model):
    _inherit = 'res.partner'

    bid_ids = fields.One2many(
        comodel_name='sor.bid',
        inverse_name='bidder_id',
        string='Bids',
    )
    bid_count = fields.Integer(
        compute='_compute_bid_count',
        store=False,
    )

    @api.depends('bid_ids')
    def _compute_bid_count(self):
        for partner in self:
            partner.bid_count = self.env['sor.bid'].search_count([
                ('bidder_id', '=', partner.id),
                ('company_id', '=', self.env.company.id),
            ])

    def action_view_bids(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': 'Bids',
            'res_model': 'sor.bid',
            'view_mode': 'list,form',
            'domain': [
                ('bidder_id', '=', self.id),
                ('company_id', '=', self.env.company.id),
            ],
            'context': {'default_bidder_id': self.id},
        }
