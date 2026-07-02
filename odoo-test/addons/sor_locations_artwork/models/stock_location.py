# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import _, fields, models


class StockLocation(models.Model):
    _inherit = 'stock.location'

    artwork_count = fields.Integer(
        string='Artworks',
        compute='_compute_artwork_count',
    )

    def _compute_artwork_count(self):
        for location in self:
            location.artwork_count = self.env['product.template'].search_count([
                ('current_location_id', '=', location.id),
                '|', ('company_id', '=', False),
                     ('company_id', '=', location.company_id.id),
            ])

    def action_open_artworks(self):
        self.ensure_one()
        return {
            'type': 'ir.actions.act_window',
            'name': _('Artworks'),
            'res_model': 'product.template',
            'view_mode': 'list,form',
            'domain': [
                ('current_location_id', '=', self.id),
                ('product_type', '=', 'artwork'),
                '|', ('company_id', '=', False),
                     ('company_id', '=', self.company_id.id),
            ],
        }
